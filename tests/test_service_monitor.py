"""Testy dla modułu service_monitor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        endpoint="http://test.example.com",
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
        endpoint="http://test.example.com",
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


@pytest.mark.asyncio
async def test_check_http_service_online(service_monitor):
    """Test sprawdzania usługi HTTP która jest online."""
    test_service = ServiceInfo(
        name="Test HTTP Service",
        service_type="api",
        endpoint="http://test.example.com",
    )

    # Mock aiohttp session
    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        mock_session_class.return_value = mock_session

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
        endpoint="http://test.example.com",
    )

    # Mock aiohttp session - symuluj błąd połączenia
    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection refused")
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        mock_session_class.return_value = mock_session

        result = await service_monitor._check_service_health(test_service)

        assert result.status == ServiceStatus.OFFLINE
        assert result.error_message is not None


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
        endpoint="http://test.example.com",
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


def test_get_memory_metrics(service_monitor):
    """Test pobierania metryk pamięci RAM i VRAM."""
    # Mock psutil
    with patch("venom_core.core.service_monitor.psutil") as mock_psutil:
        mock_memory = MagicMock()
        mock_memory.used = 8 * 1024**3  # 8 GB
        mock_memory.total = 16 * 1024**3  # 16 GB
        mock_memory.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_memory

        # Mock subprocess dla nvidia-smi (symuluj brak GPU)
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.side_effect = FileNotFoundError()

            metrics = service_monitor.get_memory_metrics()

            assert "memory_usage_mb" in metrics
            assert "memory_total_mb" in metrics
            assert "memory_usage_percent" in metrics
            assert metrics["memory_usage_mb"] > 0
            assert metrics["memory_total_mb"] > 0
            assert metrics["memory_usage_percent"] == 50.0
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

        # Mock subprocess dla nvidia-smi (symuluj GPU)
        with patch("subprocess.run") as mock_subprocess:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "2048, 8192\n"  # 2 GB used, 8 GB total
            mock_subprocess.return_value = mock_result

            metrics = service_monitor.get_memory_metrics()

            assert metrics["memory_usage_mb"] > 0
            assert metrics["vram_usage_mb"] == 2048.0
            assert metrics["vram_total_mb"] == 8192.0
            assert metrics["vram_usage_percent"] == 25.0
