import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import venom_core.main as core_main
from venom_core.api.routes.system import (
    _generate_external_map,
    _generate_internal_map,
    _get_method_signatures,
    _iter_routes,
    _update_runtime_statuses,
    router,
)
from venom_core.api.schemas.system import (
    ApiConnection,
    ConnectionProtocol,
    ConnectionStatus,
)


# Setup a dummy app for testing route discovery
@pytest.fixture
def mock_app():
    app = FastAPI()

    # Define some dummy routes matching our prefixes
    router_sys = APIRouter()

    @router_sys.get("/api/v1/system/status")
    def status():
        pass

    @router_sys.post("/api/v1/system/services/{name}/restart")
    def restart(name: str):
        pass

    @router_sys.post("/api/v1/chat")
    def chat():
        pass

    app.include_router(router_sys)
    return app


def test_get_method_signatures(mock_app):
    # Test discovery for system status
    methods = _get_method_signatures(mock_app, "/api/v1/system/status")
    assert "GET /api/v1/system/status" in methods

    # Test discovery for services (parameterized)
    methods = _get_method_signatures(mock_app, "/api/v1/system/services")
    assert "POST /api/v1/system/services/{name}/restart" in methods

    # Test unknown prefix
    methods = _get_method_signatures(mock_app, "/api/v1/unknown")
    assert len(methods) == 0


def test_iter_routes_flattens_included_router_wrappers():
    router = APIRouter()

    @router.get("/wrapped")
    def _wrapped():
        return {"ok": True}

    original_wrapper = SimpleNamespace(original_router=router)
    included_wrapper = SimpleNamespace(
        include_context=SimpleNamespace(included_router=router)
    )

    routes = list(_iter_routes([original_wrapper, included_wrapper]))
    assert [route.path for route in routes] == ["/wrapped", "/wrapped"]


def test_generate_internal_map(mock_app):
    # Mock request.app
    mock_request = MagicMock()
    mock_request.app = mock_app

    internal = _generate_internal_map(mock_request)

    # Check if we found System Status API
    system_status = next(
        (c for c in internal if c.target_component == "System Status API"), None
    )
    assert system_status is not None
    assert "GET /api/v1/system/status" in system_status.methods

    # Check if we found Frontend (Next.js) which maps to /api/v1/chat
    frontend = next(
        (c for c in internal if c.target_component == "Frontend (Next.js)"), None
    )
    assert frontend is not None
    assert "POST /api/v1/chat" in frontend.methods
    # Verify WS/SSE are present (hardcoded in logic)
    assert "WS /ws/events" in frontend.methods


def test_generate_external_map():
    # Helper to test config-driven map
    with (
        patch("venom_core.config.SETTINGS.LLM_SERVICE_TYPE", "local"),
        patch(
            "venom_core.config.SETTINGS.LLM_LOCAL_ENDPOINT", "http://localhost:11434"
        ),
    ):
        external = _generate_external_map()
        local_llm = next(
            (c for c in external if "Local LLM" in c.target_component), None
        )
        assert local_llm is not None
        assert local_llm.source_type == "local"

    with (
        patch("venom_core.config.SETTINGS.AI_MODE", "CLOUD"),
        patch("venom_core.config.SETTINGS.HYBRID_CLOUD_PROVIDER", "openai"),
    ):
        external = _generate_external_map()
        cloud_llm = next(
            (c for c in external if "Cloud LLM" in c.target_component), None
        )
        assert cloud_llm is not None
        assert cloud_llm.source_type == "cloud"


def test_update_runtime_statuses():
    # Create some dummy connections
    connections = [
        ApiConnection(
            source_component="System Monitor",
            target_component="OpenAI API",  # Should map to offline
            protocol=ConnectionProtocol.HTTP,
            status=ConnectionStatus.UNKNOWN,
            direction="bidirectional",
            auth_type="none",
            source_type="local",
            description="test",
            is_critical=False,
            methods=[],
        ),
        ApiConnection(
            source_component="System Monitor",
            target_component="Redis",  # Should be online
            protocol=ConnectionProtocol.HTTP,
            status=ConnectionStatus.UNKNOWN,
            direction="bidirectional",
            auth_type="none",
            source_type="local",
            description="test",
            is_critical=False,
            methods=[],
        ),
        ApiConnection(
            source_component="System Monitor",
            target_component="Agents API",  # Unknown service
            protocol=ConnectionProtocol.HTTP,
            status=ConnectionStatus.UNKNOWN,
            direction="bidirectional",
            auth_type="none",
            source_type="local",
            description="test",
            is_critical=False,
            methods=[],
        ),
    ]

    # Mock ServiceMonitor
    mock_monitor = MagicMock()

    # Define mock services
    class MockService:
        def __init__(self, name, status_val):
            self.name = name
            self.status = MagicMock()
            self.status.value = status_val
            self.error_message = None

    mock_monitor.get_all_services.return_value = [
        MockService("OpenAI API", "offline"),
        MockService("Redis", "online"),
    ]

    _update_runtime_statuses(connections, mock_monitor)

    assert connections[0].status == ConnectionStatus.DOWN
    assert connections[1].status == ConnectionStatus.OK
    assert (
        connections[2].status == ConnectionStatus.UNKNOWN
    )  # Not in service map/monitor


def test_caching_logic():
    # Test that caching works

    # Use TestClient to trigger the endpoint
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # We patch where it's DEFINED, not where it is imported inside the function
    # Because sys.modules has it.
    with (
        patch("venom_core.api.routes.system._generate_internal_map") as mock_gen,
        patch("venom_core.api.routes.system._update_runtime_statuses"),
        patch("venom_core.api.routes.system_deps.get_service_monitor"),
    ):
        mock_gen.return_value = []  # Return empty list

        # Reset cache in case other tests messed with it (though unrelated here, good practice)
        from venom_core.api.routes import system

        previous_cache = getattr(system, "_API_MAP_CACHE", None)
        previous_time = getattr(system, "_LAST_CACHE_TIME", 0)

        try:
            system._API_MAP_CACHE = None
            system._LAST_CACHE_TIME = 0

            # First call: should generate
            client.get("/api/v1/system/api-map")
            assert mock_gen.call_count == 1

            # Second call: should use cache
            client.get("/api/v1/system/api-map")
            assert mock_gen.call_count == 1

            # Mock time moving forward past TTL
            with patch("time.time", return_value=time.time() + system._CACHE_TTL + 1):
                client.get("/api/v1/system/api-map")
                assert mock_gen.call_count == 2
        finally:
            system._API_MAP_CACHE = previous_cache
            system._LAST_CACHE_TIME = previous_time


def test_main_voice_helpers_cover_branching_contracts(monkeypatch, tmp_path):
    monkeypatch.setattr(core_main.SETTINGS, "VOICE_ROUTE_PROFILE", "GEMMA4")
    monkeypatch.setattr(core_main.SETTINGS, "AUDIO_DECODER_PROFILE", "HYBRID")
    monkeypatch.setattr(
        core_main.SETTINGS, "AUDIO_DECODER_CHAIN", "gemma_native,whisper"
    )

    assert core_main._normalize_voice_route_profile(" venom-agent ") == "venom-agent"
    assert core_main._normalize_voice_route_profile("unknown") == "auto"
    assert core_main._normalize_audio_decoder_profile("hybrid") == "hybrid"
    assert core_main._normalize_audio_decoder_profile("bad") == "auto"
    assert core_main._normalize_audio_decoder_id(" native_audio ") == "gemma_native"
    assert core_main._normalize_audio_decoder_id("missing") == ""
    assert core_main._normalize_audio_decoder_chain(None) == []
    assert core_main._normalize_audio_decoder_chain(
        "gemma_native,whisper,gemma_native"
    ) == [
        "gemma_native",
        "faster_whisper",
    ]
    assert core_main._normalize_audio_decoder_chain(["faster_whisper", "unknown"]) == [
        "faster_whisper"
    ]
    assert (
        core_main._effective_audio_decoder_chain(
            "chat_tekstowy", "hybrid", ["gemma_native"]
        )
        == []
    )
    assert core_main._effective_audio_decoder_chain(
        "runtime_lokalny", "hybrid", []
    ) == ["faster_whisper"]
    assert core_main._effective_audio_decoder_chain("auto", "hybrid", []) == [
        "gemma_native",
        "faster_whisper",
    ]

    snapshot = core_main._voice_route_config_snapshot()
    assert snapshot["voice_route_profile"] == "gemma4"
    assert snapshot["audio_decoder_profile"] == "hybrid"
    assert snapshot["audio_decoder_chain"] == ["gemma_native", "faster_whisper"]
    assert snapshot["audio_decoder_chain_effective"] == [
        "gemma_native",
        "faster_whisper",
    ]

    core_main._validate_voice_route_contract(
        voice_route_profile="auto",
        audio_decoder_profile="hybrid",
        audio_decoder_chain=["gemma_native", "faster_whisper"],
    )
    with pytest.raises(core_main.HTTPException):
        core_main._validate_voice_route_contract(
            voice_route_profile="chat_tekstowy",
            audio_decoder_profile="hybrid",
            audio_decoder_chain=["gemma_native"],
        )
    with pytest.raises(core_main.HTTPException):
        core_main._validate_voice_route_contract(
            voice_route_profile="gemma4",
            audio_decoder_profile="faster_whisper",
            audio_decoder_chain=["faster_whisper"],
        )
    with pytest.raises(core_main.HTTPException):
        core_main._validate_voice_route_contract(
            voice_route_profile="runtime_lokalny",
            audio_decoder_profile="gemma_native",
            audio_decoder_chain=[],
        )

    session_root = tmp_path / "voice"
    session_dir = session_root / "session-1"
    session_dir.mkdir(parents=True)
    wav_path = session_dir / core_main.VOICE_SESSION_WAV_FILENAME
    wav_path.write_bytes(b"RIFF")
    monkeypatch.setattr(core_main, "VOICE_SESSION_ROOT", session_root)
    monkeypatch.setattr(core_main, "audio_stream_handler", None)
    monkeypatch.setattr(
        core_main,
        "collect_latest_voice_session_record",
        lambda _root: {"session_id": "from-fs"},
    )
    assert core_main._resolve_voice_session_wav_path("session-1") == wav_path.resolve()
    with pytest.raises(core_main.HTTPException):
        core_main._resolve_voice_session_wav_path("../evil")
    assert core_main._get_latest_voice_session_record() == {"session_id": "from-fs"}
    monkeypatch.setattr(
        core_main,
        "audio_stream_handler",
        SimpleNamespace(
            get_latest_voice_session=lambda: {"session_id": "from-handler"}
        ),
    )
    assert core_main._get_latest_voice_session_record() == {
        "session_id": "from-handler"
    }

    request_local = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    request_remote = SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"))
    core_main._require_localhost_request(request_local)
    with pytest.raises(core_main.HTTPException):
        core_main._require_localhost_request(request_remote)

    storage_root = tmp_path / "storage"
    repo_root = tmp_path / "repo"
    (storage_root / "data" / "models" / "piper").mkdir(parents=True)
    monkeypatch.setattr(core_main.SETTINGS, "STORAGE_PREFIX", str(storage_root))
    monkeypatch.setattr(core_main.SETTINGS, "REPO_ROOT", str(repo_root))
    assert (
        core_main._get_piper_models_root()
        == (storage_root / "data" / "models" / "piper").resolve()
    )
    monkeypatch.setattr(core_main.SETTINGS, "STORAGE_PREFIX", str(tmp_path / "missing"))
    assert (
        core_main._get_piper_models_root()
        == (repo_root / "data" / "models" / "piper").resolve()
    )

    piper_root = tmp_path / "models" / "piper"
    piper_root.mkdir(parents=True)
    valid_model = piper_root / "pl_PL-test.onnx"
    valid_model.write_text("fake")
    monkeypatch.setattr(core_main, "_get_piper_models_root", lambda: piper_root)
    models = core_main._list_available_tts_models()
    assert models == [
        {
            "id": "pl_PL-test.onnx",
            "label": "pl_PL-test",
            "path": str(valid_model.resolve()),
        }
    ]
    monkeypatch.setattr(
        core_main,
        "_list_available_tts_models",
        lambda: [{"id": "model.onnx", "label": "model", "path": str(valid_model)}],
    )
    assert core_main._resolve_tts_model_path("model.onnx") == valid_model.resolve()
    with pytest.raises(core_main.HTTPException):
        core_main._resolve_tts_model_path("")
    with pytest.raises(core_main.HTTPException):
        core_main._resolve_tts_model_path("missing.onnx")

    monkeypatch.setattr(core_main.SETTINGS, "GEMMA4_AUDIO_ENABLED", True)
    monkeypatch.setattr(core_main.SETTINGS, "GEMMA4_AUDIO_SUPPORTS_AUDIO", False)
    monkeypatch.setattr(core_main.SETTINGS, "GEMMA4_AUDIO_SUPPORTS_TEXT", True)
    monkeypatch.setattr(
        core_main.SETTINGS, "GEMMA4_AUDIO_REASONING_SUMMARY_ENABLED", True
    )
    monkeypatch.setattr(
        core_main.SETTINGS, "GEMMA4_AUDIO_EMOTION_DETECTION_ENABLED", False
    )
    capabilities = core_main._build_gemma4_runtime_capabilities()
    pipeline = core_main._build_gemma4_voice_pipeline()
    whisper_caps = core_main._build_whisper_fallback_runtime_capabilities("vllm")
    whisper_pipeline = core_main._build_whisper_fallback_voice_pipeline("vllm")
    gemma_snapshot = core_main._build_gemma4_voice_runtime_snapshot(
        SimpleNamespace(
            runtime_id="multi_runtime@localhost",
            provider="multi_runtime",
            model_name="google/gemma-4-E2B-it",
            endpoint="http://127.0.0.1:8014",
            config_hash="cfg123",
        )
    )
    whisper_snapshot = core_main._build_whisper_fallback_voice_runtime_snapshot(
        SimpleNamespace(
            runtime_id="vllm@localhost",
            provider="vllm",
            model_name="qwen3.5:latest",
            endpoint="http://localhost:8000",
            config_hash="abc",
        )
    )

    assert capabilities["compatibility_profile"] == "multi_runtime_native"
    assert capabilities["probes"]["health"]["status"] == "verified"
    assert pipeline["tts"] == "piper"
    assert whisper_caps["fallbacks"]["tts"] == "piper"
    assert whisper_pipeline["stt"] == "faster_whisper"
    assert gemma_snapshot["voice_pipeline"]["profile"] == "multi_runtime_native"
    assert whisper_snapshot["voice_pipeline"]["profile"] == "whisper_llm_piper_fallback"

    assert core_main._parse_iso_datetime(None) is None
    assert core_main._parse_iso_datetime("2026-05-24T09:10:00Z") == datetime(
        2026, 5, 24, 9, 10, tzinfo=UTC
    )
    assert (
        core_main._same_runtime_identity(
            " Ollama ",
            " Qwen3.5:Latest ",
            "ollama",
            "qwen3.5:latest",
        )
        is True
    )
    assert core_main._same_runtime_identity(None, "m", "ollama", "m") is None
    assert (
        core_main._runtime_switch_state_label(
            runtime_switch_gate={"in_progress": True},
            last_runtime_switch=None,
        )
        == "switching"
    )
    assert (
        core_main._runtime_switch_state_label(
            runtime_switch_gate=None,
            last_runtime_switch={"reason": "switch error: denied"},
        )
        == "failed"
    )
    assert (
        core_main._runtime_switch_state_label(
            runtime_switch_gate=None,
            last_runtime_switch={"reason": "manual switch"},
        )
        == "ready"
    )
    assert (
        core_main._runtime_switch_state_label(
            runtime_switch_gate=None,
            last_runtime_switch=None,
        )
        == "idle"
    )

    monkeypatch.setattr(
        core_main,
        "get_last_runtime_switch_event",
        lambda: {"at_utc": "2026-05-24T09:10:00Z"},
    )
    alignment = core_main._build_voice_runtime_alignment(
        runtime_snapshot={"provider": "ollama", "model_name": "qwen3.5:latest"},
        latest_session={
            "audio_runtime_provider": "ollama",
            "audio_runtime_model": "qwen3.5:latest",
            "created_at": "2026-05-24T09:12:00Z",
        },
    )
    assert alignment["latest_session_before_runtime_switch"] is False
    assert alignment["response_runtime_fresh"] is True
    assert alignment["response_runtime_matches_active"] is True

    runtime_state = core_main._build_voice_runtime_state(
        runtime_snapshot={"runtime_id": "ollama@localhost", "provider": "ollama"},
        latest_session={
            "audio_runtime_provider": "ollama",
            "audio_runtime_model": "qwen3.5:latest",
            "pipeline_id": "whisper_llm_piper",
            "created_at": "2026-05-24T09:12:00Z",
        },
        runtime_alignment=alignment,
        runtime_switch_gate={"in_progress": True, "to_runtime": "multi_runtime"},
        last_runtime_switch={"model": "qwen3.5:latest", "reason": "manual switch"},
    )
    assert runtime_state["switch"]["state"] == "switching"
    assert runtime_state["selected"]["source"] == "switch_target"
    assert runtime_state["response"]["matches_active"] is True
    assert core_main._normalize_datetime_utc(datetime(2026, 5, 24, 9, 10)) == datetime(
        2026, 5, 24, 9, 10, tzinfo=UTC
    )
    assert (
        core_main._is_session_before_switch(
            session_created_at="2026-05-24T09:00:00Z",
            switch_at="2026-05-24T09:10:00Z",
        )
        is True
    )

    monkeypatch.setattr(
        core_main,
        "orchestrator",
        SimpleNamespace(
            task_dispatcher=SimpleNamespace(kernel="kernel", skill_manager="skills")
        ),
    )
    assert core_main._get_orchestrator_kernel() == "kernel"
    assert core_main._get_orchestrator_skill_manager() == "skills"
    assert core_main._extract_available_local_models(
        [
            {"provider": "local", "name": "alpha"},
            {"provider": "remote", "name": "beta"},
        ],
        "local",
    ) == {"alpha"}
    assert (
        core_main._select_startup_model({"alpha", "beta"}, "alpha", "beta") == "alpha"
    )


@pytest.mark.asyncio
async def test_main_build_voice_runtime_snapshot_paths(monkeypatch):
    previous_cache = core_main._voice_runtime_snapshot_cache["entry"]
    try:
        monkeypatch.setattr(core_main.SETTINGS, "GEMMA4_AUDIO_ENABLED", True)
        monkeypatch.setattr(core_main.SETTINGS, "AUDIO_DECODER_PROFILE", "auto")
        monkeypatch.setattr(
            core_main,
            "get_active_llm_runtime",
            lambda: SimpleNamespace(
                runtime_id="multi_runtime@localhost",
                provider="multi_runtime",
                model_name="google/gemma-4-E2B-it",
                endpoint="http://127.0.0.1:8014",
                config_hash="cfg123",
            ),
        )
        gemma_snapshot = await core_main._build_voice_runtime_snapshot()
        assert gemma_snapshot["runtime_capabilities"]["compatibility_profile"] == (
            "multi_runtime_native"
        )
        assert gemma_snapshot["voice_pipeline"]["stt"] == "native_audio"

        monkeypatch.setattr(
            core_main,
            "get_active_llm_runtime",
            lambda: SimpleNamespace(
                runtime_id="vllm@localhost",
                provider="vllm",
                model_name="qwen3.5:latest",
                endpoint="http://localhost:8000",
                config_hash="abc",
            ),
        )
        fallback_snapshot = await core_main._build_voice_runtime_snapshot()
        assert fallback_snapshot["voice_pipeline"]["profile"] == (
            "whisper_llm_piper_fallback"
        )

        monkeypatch.setattr(
            core_main,
            "get_active_llm_runtime",
            lambda: SimpleNamespace(
                runtime_id="ollama@localhost",
                provider="ollama",
                model_name="qwen3.5:latest",
                endpoint="http://localhost:11434",
                config_hash="cfg-cache",
            ),
        )
        cache_key = core_main._voice_runtime_snapshot_cache_key(
            SimpleNamespace(
                provider="ollama",
                model_name="qwen3.5:latest",
                endpoint="http://localhost:11434",
                config_hash="cfg-cache",
            )
        )
        core_main._voice_runtime_snapshot_cache["entry"] = {
            "key": cache_key,
            "snapshot": {
                "runtime_id": "cached",
                "provider": "ollama",
                "model_name": "qwen3.5:latest",
                "voice_pipeline": {"stt": "cached"},
            },
            "captured_at": core_main.asyncio.get_running_loop().time(),
        }
        probe_mock = AsyncMock()
        monkeypatch.setattr(core_main, "probe_ollama_runtime_capabilities", probe_mock)
        cached_snapshot = await core_main._build_voice_runtime_snapshot()
        assert cached_snapshot["voice_pipeline"]["stt"] == "cached"
        probe_mock.assert_not_called()

        core_main._voice_runtime_snapshot_cache["entry"] = {
            "key": cache_key,
            "snapshot": {
                "runtime_id": "cached",
                "provider": "ollama",
                "model_name": "qwen3.5:latest",
                "voice_pipeline": {"stt": "stale"},
            },
            "captured_at": 0.0,
        }
        monkeypatch.setattr(
            core_main,
            "OllamaClient",
            lambda endpoint: SimpleNamespace(endpoint=endpoint),
        )
        monkeypatch.setattr(
            core_main,
            "probe_ollama_runtime_capabilities",
            AsyncMock(side_effect=RuntimeError("probe failed")),
        )
        refreshed_snapshot = await core_main._build_voice_runtime_snapshot()
        assert refreshed_snapshot["stale"] is True
        assert refreshed_snapshot["stale_reason"] == "probe failed"
        assert refreshed_snapshot["voice_pipeline"]["stt"] == "stale"
    finally:
        core_main._voice_runtime_snapshot_cache["entry"] = previous_cache
