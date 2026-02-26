"""Testy dla modułu service_monitor."""

import asyncio
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.helpers.url_fixtures import TEST_EXAMPLE_HTTP
from venom_core.core.service_monitor import (
    ServiceHealthMonitor,
    ServiceInfo,
    ServiceRegistry,
    ServiceStatus,
)


@pytest.fixture
def service_registry():
    """Fixture dla ServiceRegistry."""
    return ServiceRegistry()


@pytest.fixture
def service_monitor(service_registry):
    """Fixture dla ServiceHealthMonitor."""
    return ServiceHealthMonitor(service_registry)


def test_service_registry_initialization(service_registry):
    """Test inicjalizacji rejestru usług."""
    assert service_registry is not None
    assert isinstance(service_registry.services, dict)
    # Sprawdź czy zarejestrowano domyślne usługi
    assert len(service_registry.services) > 0


def test_register_service(service_registry):
    """Test rejestracji nowej usługi."""
    test_service = ServiceInfo(
        name="Test Service",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
        description="Test service",
        is_critical=True,
    )

    service_registry.register_service(test_service)

    assert "Test Service" in service_registry.services
    assert service_registry.services["Test Service"] == test_service


def test_get_service(service_registry):
    """Test pobierania usługi z rejestru."""
    test_service = ServiceInfo(
        name="Test Service",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
    )

    service_registry.register_service(test_service)

    retrieved = service_registry.get_service("Test Service")
    assert retrieved is not None
    assert retrieved.name == "Test Service"

    # Test nieistniejącej usługi
    not_found = service_registry.get_service("NonExistent")
    assert not_found is None


def test_get_all_services(service_registry):
    """Test pobierania wszystkich usług."""
    services = service_registry.get_all_services()
    assert isinstance(services, list)
    assert len(services) > 0


def test_get_critical_services(service_registry):
    """Test pobierania krytycznych usług."""
    # Dodaj usługę krytyczną
    critical_service = ServiceInfo(
        name="Critical Service",
        service_type="api",
        is_critical=True,
    )
    service_registry.register_service(critical_service)

    # Dodaj usługę niekrytyczną
    non_critical_service = ServiceInfo(
        name="Non-Critical Service",
        service_type="api",
        is_critical=False,
    )
    service_registry.register_service(non_critical_service)

    critical_services = service_registry.get_critical_services()

    assert len(critical_services) > 0
    assert all(s.is_critical for s in critical_services)


def test_set_orchestrator(service_monitor):
    orchestrator = MagicMock()
    service_monitor.set_orchestrator(orchestrator)
    assert service_monitor.orchestrator is orchestrator


def test_service_registry_registers_openai_and_docker_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS.OPENAI_API_KEY",
        "sk-enabled",
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS.LLM_SERVICE_TYPE",
        "openai",
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS.ENABLE_SANDBOX",
        True,
    )
    registry = ServiceRegistry()
    names = {service.name for service in registry.get_all_services()}
    assert "OpenAI API" in names
    assert "Docker Daemon" in names


def test_service_registry_skips_docker_when_sandbox_disabled(monkeypatch):
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS.OPENAI_API_KEY",
        "",
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS.LLM_SERVICE_TYPE",
        "local",
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS.ENABLE_SANDBOX",
        False,
    )
    registry = ServiceRegistry()
    names = {service.name for service in registry.get_all_services()}
    assert "Docker Daemon" not in names
    assert "LanceDB" in names


def test_get_all_services_returns_list(service_monitor):
    services = service_monitor.get_all_services()
    assert isinstance(services, list)
    assert len(services) > 0


@pytest.mark.asyncio
async def test_check_http_service_online(service_monitor):
    """Test sprawdzania usługi HTTP która jest online."""
    test_service = ServiceInfo(
        name="Test HTTP Service",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
    )

    with patch(
        "venom_core.core.service_monitor.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await service_monitor._check_service_health(test_service)

        assert result.status == ServiceStatus.ONLINE
        assert result.latency_ms >= 0
        assert result.last_check is not None


@pytest.mark.asyncio
async def test_check_http_service_offline(service_monitor):
    """Test sprawdzania usługi HTTP która jest offline."""
    test_service = ServiceInfo(
        name="Test HTTP Service",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
    )

    with patch(
        "venom_core.core.service_monitor.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await service_monitor._check_service_health(test_service)

        assert result.status == ServiceStatus.OFFLINE
        assert result.error_message is not None


@pytest.mark.asyncio
async def test_check_http_service_openai_degraded_branch(service_monitor):
    service = ServiceInfo(
        name="OpenAI API",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
    )

    with patch(
        "venom_core.core.service_monitor.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await service_monitor._check_http_service(service)

    assert mock_client_cls.call_args.kwargs["provider"] == "openai"
    assert service.status == ServiceStatus.DEGRADED
    assert service.error_message == "HTTP 429"


@pytest.mark.asyncio
async def test_check_http_service_openai_adds_bearer_header(
    service_monitor, monkeypatch: pytest.MonkeyPatch
):
    service = ServiceInfo(
        name="OpenAI API",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS.OPENAI_API_KEY",
        "sk-test",
    )

    with patch(
        "venom_core.core.service_monitor.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await service_monitor._check_http_service(service)

    kwargs = mock_client.aget.await_args.kwargs
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert service.status == ServiceStatus.ONLINE


@pytest.mark.asyncio
async def test_check_http_service_github_offline_branch(service_monitor):
    service = ServiceInfo(
        name="GitHub API",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
    )

    with patch(
        "venom_core.core.service_monitor.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await service_monitor._check_http_service(service)

    assert mock_client_cls.call_args.kwargs["provider"] == "github"
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message == "HTTP 503"


@pytest.mark.asyncio
async def test_check_http_service_github_adds_bearer_header(
    service_monitor, monkeypatch: pytest.MonkeyPatch
):
    service = ServiceInfo(
        name="GitHub API",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS.GITHUB_TOKEN",
        SimpleNamespace(get_secret_value=lambda: "gh-token"),
    )

    with patch(
        "venom_core.core.service_monitor.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await service_monitor._check_http_service(service)

    kwargs = mock_client.aget.await_args.kwargs
    assert kwargs["headers"]["Authorization"] == "Bearer gh-token"
    assert service.status == ServiceStatus.ONLINE


@pytest.mark.asyncio
async def test_check_http_service_github_blank_token_skips_auth_header(
    service_monitor, monkeypatch: pytest.MonkeyPatch
):
    service = ServiceInfo(
        name="GitHub API",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS.GITHUB_TOKEN",
        SimpleNamespace(get_secret_value=lambda: "   "),
    )

    with patch(
        "venom_core.core.service_monitor.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await service_monitor._check_http_service(service)

    kwargs = mock_client.aget.await_args.kwargs
    assert "Authorization" not in kwargs["headers"]
    assert service.status == ServiceStatus.ONLINE


@pytest.mark.asyncio
async def test_check_health_all_services(service_monitor):
    """Test sprawdzania zdrowia wszystkich usług."""
    # Mock check_service_health
    with patch.object(
        service_monitor, "_check_service_health", new_callable=AsyncMock
    ) as mock_check:

        def create_mock_service(service):
            service.status = ServiceStatus.ONLINE
            service.latency_ms = 50.0
            service.last_check = "2024-01-01 12:00:00"
            return service

        mock_check.side_effect = create_mock_service

        services = await service_monitor.check_health()

        assert isinstance(services, list)
        assert len(services) > 0
        assert mock_check.called


@pytest.mark.asyncio
async def test_check_health_specific_service(service_monitor, service_registry):
    """Test sprawdzania zdrowia konkretnej usługi."""
    # Dodaj testową usługę
    test_service = ServiceInfo(
        name="Specific Test Service",
        service_type="api",
        endpoint=TEST_EXAMPLE_HTTP,
    )
    service_registry.register_service(test_service)

    # Mock check_service_health
    with patch.object(
        service_monitor, "_check_service_health", new_callable=AsyncMock
    ) as mock_check:

        def create_mock_service(service):
            service.status = ServiceStatus.ONLINE
            service.latency_ms = 50.0
            return service

        mock_check.side_effect = create_mock_service

        services = await service_monitor.check_health(
            service_name="Specific Test Service"
        )

        assert len(services) == 1
        assert services[0].name == "Specific Test Service"


@pytest.mark.asyncio
async def test_check_health_unknown_service_returns_empty(service_monitor):
    services = await service_monitor.check_health(service_name="Missing Service")
    assert services == []


@pytest.mark.asyncio
async def test_check_health_converts_exceptions_to_offline_status(service_monitor):
    with patch.object(
        service_monitor,
        "_check_service_health",
        new=AsyncMock(side_effect=RuntimeError("explode")),
    ):
        services = await service_monitor.check_health()

    assert services
    assert all(service.status == ServiceStatus.OFFLINE for service in services)
    assert all(service.error_message for service in services)


@pytest.mark.asyncio
async def test_check_health_preserves_service_when_result_shape_is_unexpected(
    service_monitor,
):
    with patch.object(
        service_monitor,
        "_check_service_health",
        new=AsyncMock(return_value=None),
    ):
        services = await service_monitor.check_health()

    assert services
    assert all(isinstance(service, ServiceInfo) for service in services)


@pytest.mark.asyncio
async def test_check_health_accepts_serviceinfo_result_instance(service_monitor):
    original = service_monitor.registry.get_all_services()[0]
    replacement = ServiceInfo(
        name=original.name,
        service_type=original.service_type,
        endpoint=original.endpoint,
        status=ServiceStatus.DEGRADED,
    )

    with patch.object(
        service_monitor,
        "_check_service_health",
        new=AsyncMock(return_value=replacement),
    ):
        services = await service_monitor.check_health(service_name=original.name)

    assert services == [replacement]


@pytest.mark.asyncio
async def test_check_service_health_unknown_type_sets_unknown(service_monitor):
    test_service = ServiceInfo(name="Mystery", service_type="mystery")
    result = await service_monitor._check_service_health(test_service)
    assert result.status == ServiceStatus.UNKNOWN


@pytest.mark.asyncio
async def test_check_service_health_ws_broadcast_error_is_non_fatal():
    registry = ServiceRegistry()
    monitor = ServiceHealthMonitor(
        registry,
        event_broadcaster=SimpleNamespace(
            broadcast_event=MagicMock(side_effect=RuntimeError("ws down"))
        ),
    )
    service = ServiceInfo(name="Mystery", service_type="mystery")
    result = await monitor._check_service_health(service)
    assert result.status == ServiceStatus.UNKNOWN


@pytest.mark.asyncio
async def test_check_service_health_ws_import_error_is_non_fatal(
    service_monitor, monkeypatch
):
    original_import = __import__

    def _import(name, *args, **kwargs):
        if name == "venom_core.api.stream":
            raise ImportError("stream unavailable")
        return original_import(name, *args, **kwargs)

    service_monitor.event_broadcaster = SimpleNamespace(broadcast_event=AsyncMock())
    monkeypatch.setattr("builtins.__import__", _import)

    service = ServiceInfo(name="Mystery", service_type="mystery")
    result = await service_monitor._check_service_health(service)

    assert result.status == ServiceStatus.UNKNOWN


@pytest.mark.asyncio
async def test_spawn_background_task_discards_completed_task(service_monitor):
    service_monitor._spawn_background_task(asyncio.sleep(0))
    assert len(service_monitor._background_tasks) == 1
    await asyncio.gather(*list(service_monitor._background_tasks))
    await asyncio.sleep(0)
    assert len(service_monitor._background_tasks) == 0


@pytest.mark.asyncio
async def test_check_service_health_broadcast_payload_has_service_type_alias():
    registry = ServiceRegistry()
    broadcaster = SimpleNamespace(broadcast_event=AsyncMock())
    monitor = ServiceHealthMonitor(registry, event_broadcaster=broadcaster)
    service = ServiceInfo(name="Alias Service", service_type="mystery")

    await monitor._check_service_health(service)
    await asyncio.sleep(0)

    assert broadcaster.broadcast_event.await_count >= 1
    kwargs = broadcaster.broadcast_event.await_args.kwargs
    assert kwargs["data"]["type"] == "mystery"
    assert kwargs["data"]["service_type"] == "mystery"


@pytest.mark.asyncio
async def test_check_service_health_broadcast_schedule_error_is_non_fatal():
    registry = ServiceRegistry()
    broadcaster = SimpleNamespace(broadcast_event=AsyncMock())
    monitor = ServiceHealthMonitor(registry, event_broadcaster=broadcaster)
    monitor._spawn_background_task = MagicMock(
        side_effect=RuntimeError("schedule-fail")
    )
    service = ServiceInfo(name="Schedule Fail", service_type="mystery")

    result = await monitor._check_service_health(service)

    assert result.status == ServiceStatus.UNKNOWN


def test_get_summary(service_monitor, service_registry):
    """Test generowania podsumowania zdrowia systemu."""
    # Dodaj usługi z różnymi statusami
    online_service = ServiceInfo(
        name="Online Service", service_type="api", status=ServiceStatus.ONLINE
    )
    offline_service = ServiceInfo(
        name="Offline Service",
        service_type="api",
        status=ServiceStatus.OFFLINE,
        is_critical=True,
    )

    service_registry.register_service(online_service)
    service_registry.register_service(offline_service)

    summary = service_monitor.get_summary()

    assert "total_services" in summary
    assert "online" in summary
    assert "offline" in summary
    assert "critical_offline" in summary
    assert "system_healthy" in summary

    # System nie jest zdrowy bo krytyczna usługa jest offline
    assert summary["system_healthy"] is False
    assert "Offline Service" in summary["critical_offline"]


@pytest.mark.asyncio
async def test_check_docker_service_online(service_monitor):
    """Test sprawdzania Docker daemon który jest online."""
    test_service = ServiceInfo(
        name="Docker Daemon",
        service_type="docker",
        endpoint="unix:///var/run/docker.sock",
    )

    # Mock subprocess
    with patch("asyncio.create_subprocess_exec") as mock_subprocess:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Docker info", b"")

        mock_subprocess.return_value = mock_process

        result = await service_monitor._check_service_health(test_service)

        assert result.status == ServiceStatus.ONLINE


@pytest.mark.asyncio
async def test_check_local_database_service(service_monitor):
    """Test sprawdzania lokalnej bazy danych."""
    test_service = ServiceInfo(
        name="Local Database",
        service_type="database",
        description="ChromaDB",
    )

    # Mock chromadb
    with patch("venom_core.core.service_monitor.chromadb") as mock_chromadb:
        mock_client = MagicMock()
        mock_client.list_collections.return_value = []
        mock_chromadb.Client.return_value = mock_client

        result = await service_monitor._check_service_health(test_service)

        assert result.status == ServiceStatus.ONLINE


@pytest.mark.asyncio
async def test_check_local_database_service_redis_missing_dependency(service_monitor):
    service = ServiceInfo(
        name="Redis",
        service_type="database",
        endpoint="redis://localhost:6379/0",
        description="redis",
    )
    await service_monitor._check_local_database_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message


@pytest.mark.asyncio
async def test_check_local_database_service_redis_module_not_found_branch(
    service_monitor, monkeypatch
):
    service = ServiceInfo(
        name="Redis",
        service_type="database",
        endpoint="redis://localhost:6379/0",
        description="redis",
    )
    original_import = __import__

    def _import(name, *args, **kwargs):
        if name == "redis.asyncio":
            raise ModuleNotFoundError("redis.asyncio")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _import)
    await service_monitor._check_local_database_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message == "redis nie jest zainstalowany"


@pytest.mark.asyncio
async def test_check_mcp_service_import_error_branch(service_monitor, monkeypatch):
    fake_module = ModuleType("venom_core.skills.mcp_manager_skill")
    monkeypatch.setitem(
        __import__("sys").modules, "venom_core.skills.mcp_manager_skill", fake_module
    )
    service = ServiceInfo(name="MCP Engine", service_type="mcp")
    await service_monitor._check_mcp_service(service)
    assert service.status == ServiceStatus.OFFLINE


@pytest.mark.asyncio
async def test_check_mcp_service_success_sets_online(
    service_monitor, monkeypatch, tmp_path
):
    class DummyMcpSkill:
        def __init__(self):
            self.repos_root = str(tmp_path)

    fake_module = ModuleType("venom_core.skills.mcp_manager_skill")
    fake_module.McpManagerSkill = DummyMcpSkill
    monkeypatch.setitem(
        __import__("sys").modules, "venom_core.skills.mcp_manager_skill", fake_module
    )

    # Create a couple of fake tool directories inside the repos root
    (tmp_path / "tool-a").mkdir()
    (tmp_path / "tool-b").mkdir()

    service = ServiceInfo(name="MCP Engine", service_type="mcp")
    await service_monitor._check_mcp_service(service)

    assert service.status == ServiceStatus.ONLINE
    assert "Zaimportowano" in (service.error_message or "")


@pytest.mark.asyncio
async def test_check_mcp_service_success_without_repos_dir(
    service_monitor, monkeypatch, tmp_path
):
    class DummyMcpSkill:
        def __init__(self):
            self.repos_root = str(tmp_path / "missing-repos")

    fake_module = ModuleType("venom_core.skills.mcp_manager_skill")
    fake_module.McpManagerSkill = DummyMcpSkill
    monkeypatch.setitem(
        __import__("sys").modules, "venom_core.skills.mcp_manager_skill", fake_module
    )
    service = ServiceInfo(name="MCP Engine", service_type="mcp")
    await service_monitor._check_mcp_service(service)
    assert service.status == ServiceStatus.ONLINE
    assert service.error_message == "Zaimportowano 0 narzędzi"


@pytest.mark.asyncio
async def test_check_semantic_kernel_service_without_orchestrator(service_monitor):
    service_monitor.orchestrator = None
    service = ServiceInfo(name="Semantic Kernel", service_type="orchestrator")
    await service_monitor._check_semantic_kernel_service(service)
    assert service.status == ServiceStatus.UNKNOWN


@pytest.mark.asyncio
async def test_check_semantic_kernel_service_counts_functions(service_monitor):
    kernel = SimpleNamespace(
        plugins={
            "p1": SimpleNamespace(functions=[1, 2]),
            "p2": SimpleNamespace(functions=[3]),
        }
    )
    service_monitor.orchestrator = SimpleNamespace(
        task_dispatcher=SimpleNamespace(kernel=kernel)
    )
    service = ServiceInfo(name="Semantic Kernel", service_type="orchestrator")
    await service_monitor._check_semantic_kernel_service(service)
    assert service.status == ServiceStatus.ONLINE
    assert "3 funkcji" in (service.error_message or "")


def test_get_memory_metrics(service_monitor):
    """Test pobierania metryk pamięci RAM i VRAM."""
    # Mock psutil
    with patch("venom_core.core.service_monitor.psutil") as mock_psutil:
        mock_memory = MagicMock()
        mock_memory.used = 8 * 1024**3  # 8 GB
        mock_memory.total = 16 * 1024**3  # 16 GB
        mock_memory.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_memory

        # Mock shutil.which to return None (no nvidia-smi)
        with patch("venom_core.core.service_monitor.shutil.which") as mock_which:
            mock_which.return_value = None

            metrics = service_monitor.get_memory_metrics()

            assert "memory_usage_mb" in metrics
            assert "memory_total_mb" in metrics
            assert "memory_usage_percent" in metrics
            assert metrics["memory_usage_mb"] > 0
            assert metrics["memory_total_mb"] > 0
            assert metrics["memory_usage_percent"] == pytest.approx(50.0)
            # GPU metrics powinny być None gdy nvidia-smi niedostępne
            assert metrics["vram_usage_mb"] is None
            assert metrics["vram_total_mb"] is None
            assert metrics["vram_usage_percent"] is None


def test_get_memory_metrics_with_gpu(service_monitor):
    """Test pobierania metryk pamięci z GPU."""
    # Mock psutil
    with patch("venom_core.core.service_monitor.psutil") as mock_psutil:
        mock_memory = MagicMock()
        mock_memory.used = 8 * 1024**3
        mock_memory.total = 16 * 1024**3
        mock_memory.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_memory

        # Mock shutil.which to return nvidia-smi path
        with patch("venom_core.core.service_monitor.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/nvidia-smi"

            # Mock subprocess dla nvidia-smi (symuluj GPU)
            with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = "2048, 8192\n"  # 2 GB used, 8 GB total
                mock_run.return_value = mock_result

                metrics = service_monitor.get_memory_metrics()

                assert metrics["memory_usage_mb"] > 0
                assert metrics["vram_usage_mb"] == pytest.approx(2048.0)
                assert metrics["vram_total_mb"] == pytest.approx(8192.0)
                assert metrics["vram_usage_percent"] == pytest.approx(25.0)


def test_parse_nvidia_smi_output_filters_invalid_rows(service_monitor):
    parsed = service_monitor._parse_nvidia_smi_output(
        "2048, 8192\ninvalid\n1000, xyz\n4096, 8192\n"
    )
    assert parsed == [(2048.0, 8192.0), (4096.0, 8192.0)]


@pytest.mark.asyncio
async def test_check_http_service_without_endpoint_sets_unknown(service_monitor):
    service = ServiceInfo(name="No Endpoint API", service_type="api", endpoint=None)
    await service_monitor._check_http_service(service)
    assert service.status == ServiceStatus.UNKNOWN
    assert service.error_message == "Brak endpointu"


@pytest.mark.asyncio
async def test_check_docker_service_timeout_sets_offline(service_monitor, monkeypatch):
    service = ServiceInfo(name="Docker Daemon", service_type="docker")

    process = AsyncMock()
    process.communicate.return_value = (b"", b"")
    process.returncode = 0

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    )

    async def _wait_for_timeout(awaitable, timeout):
        # AsyncMock(side_effect=TimeoutError) nie awaituje przekazanej coroutine,
        # co zostawia "coroutine was never awaited". Ten helper zachowuje
        # semantykę wait_for: najpierw await, potem timeout.
        _ = timeout
        await awaitable
        raise asyncio.TimeoutError

    monkeypatch.setattr("asyncio.wait_for", _wait_for_timeout)

    await service_monitor._check_docker_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message == "Timeout"


@pytest.mark.asyncio
async def test_check_docker_service_missing_binary_sets_offline(
    service_monitor, monkeypatch
):
    service = ServiceInfo(name="Docker Daemon", service_type="docker")

    async def _raise_file_not_found(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("asyncio.create_subprocess_exec", _raise_file_not_found)

    await service_monitor._check_docker_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message == "Docker nie zainstalowany"


@pytest.mark.asyncio
async def test_check_local_database_service_chroma_missing_dependency_branch(
    service_monitor, monkeypatch
):
    service = ServiceInfo(
        name="ChromaDB",
        service_type="database",
        description="chroma vector db",
    )
    monkeypatch.setattr("venom_core.core.service_monitor.chromadb", None)

    await service_monitor._check_local_database_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message == "chromadb nie jest zainstalowane"


@pytest.mark.asyncio
async def test_check_local_database_service_lancedb_missing_dependency_branch(
    service_monitor, monkeypatch
):
    service = ServiceInfo(name="LanceDB", service_type="database", description="vector")
    monkeypatch.setitem(sys.modules, "lancedb", None)

    await service_monitor._check_local_database_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message == "lancedb nie jest zainstalowane"


@pytest.mark.asyncio
async def test_check_local_database_service_lancedb_exception_branch(
    service_monitor, monkeypatch
):
    service = ServiceInfo(name="LanceDB", service_type="database", description="vector")
    fake_lancedb = ModuleType("lancedb")
    fake_lancedb.connect = MagicMock(side_effect=RuntimeError("boom-lancedb"))
    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)

    await service_monitor._check_local_database_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert "boom-lancedb" in (service.error_message or "")


def test_get_memory_metrics_tolerates_nvidia_timeout(service_monitor):
    with patch("venom_core.core.service_monitor.psutil") as mock_psutil:
        mock_memory = MagicMock()
        mock_memory.used = 2 * 1024**3
        mock_memory.total = 8 * 1024**3
        mock_memory.percent = 25.0
        mock_psutil.virtual_memory.return_value = mock_memory

        with patch("venom_core.core.service_monitor.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/nvidia-smi"
            with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(
                    cmd=["nvidia-smi"], timeout=5
                )
                metrics = service_monitor.get_memory_metrics()

    assert metrics["memory_usage_percent"] == pytest.approx(25.0)
    assert metrics["vram_usage_mb"] is None
    assert metrics["vram_total_mb"] is None


def test_get_memory_metrics_handles_called_process_error(service_monitor):
    with patch("venom_core.core.service_monitor.psutil") as mock_psutil:
        mock_memory = MagicMock()
        mock_memory.used = 2 * 1024**3
        mock_memory.total = 8 * 1024**3
        mock_memory.percent = 25.0
        mock_psutil.virtual_memory.return_value = mock_memory

        with patch("venom_core.core.service_monitor.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/nvidia-smi"
            with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    cmd=["nvidia-smi"], returncode=1
                )
                metrics = service_monitor.get_memory_metrics()

    assert metrics["memory_usage_percent"] == pytest.approx(25.0)
    assert metrics["vram_usage_mb"] is None
    assert metrics["vram_total_mb"] is None


def test_get_memory_metrics_handles_file_not_found(service_monitor):
    with patch("venom_core.core.service_monitor.psutil") as mock_psutil:
        mock_memory = MagicMock()
        mock_memory.used = 2 * 1024**3
        mock_memory.total = 8 * 1024**3
        mock_memory.percent = 25.0
        mock_psutil.virtual_memory.return_value = mock_memory

        with patch("venom_core.core.service_monitor.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/nvidia-smi"
            with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError
                metrics = service_monitor.get_memory_metrics()

    assert metrics["memory_usage_percent"] == pytest.approx(25.0)
    assert metrics["vram_usage_mb"] is None
    assert metrics["vram_total_mb"] is None


def test_get_memory_metrics_handles_nonzero_nvidia_exit(service_monitor):
    with patch("venom_core.core.service_monitor.psutil") as mock_psutil:
        mock_memory = MagicMock()
        mock_memory.used = 2 * 1024**3
        mock_memory.total = 8 * 1024**3
        mock_memory.percent = 25.0
        mock_psutil.virtual_memory.return_value = mock_memory

        with patch("venom_core.core.service_monitor.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/nvidia-smi"
            with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
                result = MagicMock()
                result.returncode = 1
                result.stdout = ""
                mock_run.return_value = result
                metrics = service_monitor.get_memory_metrics()

    assert metrics["memory_usage_percent"] == pytest.approx(25.0)
    assert metrics["vram_usage_mb"] is None
    assert metrics["vram_total_mb"] is None


def test_get_gpu_memory_usage_selects_highest_valid_value(service_monitor):
    with patch("venom_core.core.service_monitor.shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/nvidia-smi"
        with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "10\ninvalid\n2048\n1024\n"
            mock_run.return_value = result

            usage = service_monitor.get_gpu_memory_usage()

    assert usage == pytest.approx(2048.0)


def test_get_gpu_memory_usage_returns_none_without_binary(service_monitor):
    with patch("venom_core.core.service_monitor.shutil.which", return_value=None):
        assert service_monitor.get_gpu_memory_usage() is None


def test_get_gpu_memory_usage_handles_called_process_error(service_monitor):
    with patch("venom_core.core.service_monitor.shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/nvidia-smi"
        with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                cmd=["nvidia-smi"], returncode=1
            )
            assert service_monitor.get_gpu_memory_usage() is None


def test_get_gpu_memory_usage_handles_file_not_found(service_monitor):
    with patch("venom_core.core.service_monitor.shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/nvidia-smi"
        with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError
            assert service_monitor.get_gpu_memory_usage() is None


@pytest.mark.asyncio
async def test_check_docker_service_nonzero_exit_sets_stderr_message(
    service_monitor, monkeypatch
):
    service = ServiceInfo(name="Docker Daemon", service_type="docker")
    process = AsyncMock()
    process.returncode = 1
    process.communicate.return_value = (b"", b"daemon down")

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    )

    async def _wait_for_passthrough(awaitable, timeout):
        _ = timeout
        return await awaitable

    monkeypatch.setattr("asyncio.wait_for", _wait_for_passthrough)

    await service_monitor._check_docker_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message == "daemon down"


@pytest.mark.asyncio
async def test_check_docker_service_unexpected_exception_sets_trimmed_message(
    service_monitor, monkeypatch
):
    service = ServiceInfo(name="Docker Daemon", service_type="docker")

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("x" * 150)

    monkeypatch.setattr("asyncio.create_subprocess_exec", _raise)

    await service_monitor._check_docker_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert len(service.error_message or "") <= 100


@pytest.mark.asyncio
async def test_check_local_database_service_redis_online_and_missing_module(
    service_monitor, monkeypatch
):
    service = ServiceInfo(
        name="Redis",
        service_type="database",
        endpoint="redis://localhost:6379/0",
        description="redis",
    )
    fake_redis = ModuleType("redis.asyncio")
    fake_client = SimpleNamespace(ping=AsyncMock(return_value=True))
    fake_redis.from_url = lambda *_args, **_kwargs: fake_client
    fake_redis_pkg = ModuleType("redis")
    fake_redis_pkg.asyncio = fake_redis
    monkeypatch.setitem(sys.modules, "redis", fake_redis_pkg)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_redis)

    await service_monitor._check_local_database_service(service)
    assert service.status == ServiceStatus.ONLINE


@pytest.mark.asyncio
async def test_check_local_database_service_lancedb_online(
    monkeypatch, service_monitor
):
    service = ServiceInfo(name="LanceDB", service_type="database", description="vector")
    fake_lancedb = ModuleType("lancedb")
    fake_conn = SimpleNamespace(table_names=lambda: ["table1"])
    fake_lancedb.connect = MagicMock(return_value=fake_conn)
    monkeypatch.setitem(__import__("sys").modules, "lancedb", fake_lancedb)

    await service_monitor._check_local_database_service(service)

    assert service.status == ServiceStatus.ONLINE
    assert service.error_message is None


@pytest.mark.asyncio
async def test_check_local_database_service_chroma_exception_branch(
    service_monitor, monkeypatch
):
    service = ServiceInfo(
        name="ChromaDB", service_type="database", description="chroma"
    )
    fake_chroma = SimpleNamespace(
        Client=MagicMock(side_effect=RuntimeError("boom-chroma"))
    )
    monkeypatch.setattr("venom_core.core.service_monitor.chromadb", fake_chroma)

    await service_monitor._check_local_database_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert "boom-chroma" in (service.error_message or "")


@pytest.mark.asyncio
async def test_check_local_database_service_lancedb_online_branch(
    service_monitor, monkeypatch
):
    service = ServiceInfo(name="LanceDB", service_type="database")
    fake_lancedb = ModuleType("lancedb")
    fake_conn = SimpleNamespace(table_names=lambda: ["a"])
    fake_lancedb.connect = MagicMock(return_value=fake_conn)
    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)

    await service_monitor._check_local_database_service(service)
    assert service.status == ServiceStatus.ONLINE
    assert service.error_message is None


@pytest.mark.asyncio
async def test_check_mcp_service_generic_exception_branch(service_monitor, monkeypatch):
    fake_module = ModuleType("venom_core.skills.mcp_manager_skill")

    class RaisingManager:
        def __init__(self):
            raise RuntimeError("boom-mcp")

    fake_module.McpManagerSkill = RaisingManager
    monkeypatch.setitem(
        __import__("sys").modules, "venom_core.skills.mcp_manager_skill", fake_module
    )
    service = ServiceInfo(name="MCP Engine", service_type="mcp")

    await service_monitor._check_mcp_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert "Błąd MCP" in (service.error_message or "")


@pytest.mark.asyncio
async def test_check_semantic_kernel_service_exception_branch(service_monitor):
    service_monitor.orchestrator = SimpleNamespace(task_dispatcher=SimpleNamespace())
    service = ServiceInfo(name="Semantic Kernel", service_type="orchestrator")

    await service_monitor._check_semantic_kernel_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert "Błąd SK" in (service.error_message or "")


def test_get_gpu_memory_usage_handles_timeout_and_unexpected_exception(
    service_monitor, monkeypatch
):
    monkeypatch.setattr(
        "venom_core.core.service_monitor.shutil.which", lambda _x: "/bin/nvidia-smi"
    )

    def _timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["nvidia-smi"], timeout=5)

    monkeypatch.setattr("venom_core.core.service_monitor.subprocess.run", _timeout)
    assert service_monitor.get_gpu_memory_usage() is None

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom-gpu")

    monkeypatch.setattr("venom_core.core.service_monitor.subprocess.run", _boom)
    assert service_monitor.get_gpu_memory_usage() is None


def test_get_memory_metrics_handles_zero_vram_total(service_monitor):
    with patch("venom_core.core.service_monitor.psutil") as mock_psutil:
        mock_memory = MagicMock()
        mock_memory.used = 1 * 1024**3
        mock_memory.total = 8 * 1024**3
        mock_memory.percent = 12.5
        mock_psutil.virtual_memory.return_value = mock_memory

        with patch(
            "venom_core.core.service_monitor.shutil.which",
            return_value="/usr/bin/nvidia-smi",
        ):
            with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
                result = MagicMock()
                result.returncode = 0
                result.stdout = "100,0\n"
                mock_run.return_value = result
                metrics = service_monitor.get_memory_metrics()

    assert metrics["vram_usage_mb"] == pytest.approx(100.0)
    assert metrics["vram_total_mb"] == pytest.approx(0.0)
    assert metrics["vram_usage_percent"] is None


def test_get_gpu_memory_usage_returncode_zero_without_valid_values_returns_none(
    service_monitor,
):
    with patch(
        "venom_core.core.service_monitor.shutil.which",
        return_value="/usr/bin/nvidia-smi",
    ):
        with patch("venom_core.core.service_monitor.subprocess.run") as mock_run:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "not-a-number\n0\n"
            mock_run.return_value = result

            assert service_monitor.get_gpu_memory_usage() is None


@pytest.mark.asyncio
async def test_spawn_background_task_tracks_and_cleans_up(service_monitor, monkeypatch):
    """Spawned background task should be tracked and removed after completion."""
    task = asyncio.Future()

    def _create_task(coro):
        coro.close()
        return task

    monkeypatch.setattr(asyncio, "create_task", _create_task)

    service_monitor._spawn_background_task(asyncio.sleep(0))
    assert task in service_monitor._background_tasks

    task.set_result(None)
    await asyncio.sleep(0)
    assert task not in service_monitor._background_tasks


@pytest.mark.asyncio
async def test_check_service_health_dispatches_mcp(service_monitor):
    service = ServiceInfo(name="MCP Engine", service_type="mcp")
    with patch.object(
        service_monitor, "_check_mcp_service", new_callable=AsyncMock
    ) as mcp:
        await service_monitor._check_service_health(service)
    mcp.assert_awaited_once_with(service)


@pytest.mark.asyncio
async def test_check_service_health_dispatches_orchestrator(service_monitor):
    service = ServiceInfo(name="Kernel", service_type="orchestrator")
    with patch.object(
        service_monitor, "_check_semantic_kernel_service", new_callable=AsyncMock
    ) as sk:
        await service_monitor._check_service_health(service)
    sk.assert_awaited_once_with(service)


def test_get_memory_metrics_returncode_zero_with_empty_gpu_data(service_monitor):
    """nvidia-smi success with empty parse should keep GPU fields as None."""
    with (
        patch("venom_core.core.service_monitor.psutil.virtual_memory") as mock_vm,
        patch(
            "venom_core.core.service_monitor.shutil.which",
            return_value="/usr/bin/nvidia-smi",
        ),
        patch("venom_core.core.service_monitor.subprocess.run") as mock_run,
    ):
        mock_vm.return_value = SimpleNamespace(
            total=1024 * 1024, used=512 * 1024, percent=50.0
        )
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="")

        metrics = service_monitor.get_memory_metrics()

    assert metrics["vram_usage_mb"] is None
    assert metrics["vram_total_mb"] is None
    assert metrics["vram_usage_percent"] is None


def test_get_gpu_memory_usage_nonzero_returncode_returns_none(service_monitor):
    with (
        patch(
            "venom_core.core.service_monitor.shutil.which",
            return_value="/usr/bin/nvidia-smi",
        ),
        patch(
            "venom_core.core.service_monitor.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=""),
        ),
    ):
        assert service_monitor.get_gpu_memory_usage() is None


@pytest.mark.asyncio
async def test_check_health_handles_non_serviceinfo_results(service_monitor):
    service = service_monitor.registry.get_all_services()[0]
    with patch.object(
        service_monitor,
        "_check_service_health",
        new=AsyncMock(return_value=None),
    ):
        result = await service_monitor.check_health(service_name=service.name)
    assert len(result) == 1
    assert result[0] is service


@pytest.mark.asyncio
async def test_check_http_service_uses_default_provider_for_generic_api(
    service_monitor,
):
    captured = {"provider": None}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            captured["provider"] = kwargs.get("provider")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aget(self, *_args, **_kwargs):
            return SimpleNamespace(status_code=204)

    service = ServiceInfo(
        name="Custom API",
        service_type="api",
        endpoint="https://example.local/health",
    )
    with patch(
        "venom_core.core.service_monitor.TrafficControlledHttpClient", DummyClient
    ):
        await service_monitor._check_http_service(service)

    assert captured["provider"] == "service_monitor"
    assert service.status == ServiceStatus.ONLINE
