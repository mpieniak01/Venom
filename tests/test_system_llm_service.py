from __future__ import annotations

import pytest

from venom_core.services import system_llm_service as svc


def test_runtime_profile_name_and_allowed_servers():
    assert svc.runtime_profile_name("LIGHT") == "light"
    assert svc.runtime_profile_name("bad") == "full"

    assert svc.allowed_local_servers(profile="light", onnx_enabled=True) == {"ollama"}
    assert svc.allowed_local_servers(profile="llm_off", onnx_enabled=True) == set()
    assert svc.allowed_local_servers(profile="full", onnx_enabled=False) == {
        "ollama",
        "vllm",
        "multi_runtime",
    }
    assert svc.allowed_local_servers(profile="full", onnx_enabled=True) == {
        "ollama",
        "vllm",
        "onnx",
        "multi_runtime",
    }


def test_installed_local_servers_composition():
    assert svc.installed_local_servers(
        ollama_installed=True,
        vllm_installed=False,
        onnx_installed=True,
    ) == {"ollama", "onnx", "multi_runtime"}


def test_provider_and_model_key_helpers():
    assert svc.normalize_runtime_provider("gem") == "google"
    assert svc.normalize_runtime_provider("google-gemini") == "google"
    assert svc.normalize_runtime_provider("openai") == "openai"

    assert svc.previous_model_key_for_server("ollama") == "PREVIOUS_MODEL_OLLAMA"
    assert svc.previous_model_key_for_server("vllm") == "PREVIOUS_MODEL_VLLM"
    assert svc.previous_model_key_for_server("onnx") == "PREVIOUS_MODEL_ONNX"


def test_dedupe_servers_by_name():
    payload = [
        {"name": "onnx", "id": 1},
        {"name": "ONNX", "id": 2},
        {"name": "ollama", "id": 3},
        {"name": "", "id": 4},
    ]

    deduped = svc.dedupe_servers_by_name(payload)

    assert deduped == [{"name": "onnx", "id": 1}, {"name": "ollama", "id": 3}]


def test_installed_binaries_detection(monkeypatch):
    monkeypatch.setattr(
        svc.shutil, "which", lambda name: "/bin/ok" if name == "ollama" else None
    )
    assert svc.is_ollama_installed() is True

    monkeypatch.setattr(svc.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        svc.importlib.util,
        "find_spec",
        lambda name: object() if name == "vllm" else None,
    )
    assert svc.is_vllm_installed() is True

    monkeypatch.setattr(svc.importlib.util, "find_spec", lambda _name: None)
    assert svc.is_vllm_installed() is False

    assert svc.is_onnx_worker_configured("http://127.0.0.1:8068/v1")
    assert not svc.is_onnx_worker_configured("")
    assert not svc.is_onnx_worker_configured("models/local.onnx")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "health",
    [
        {"status": "ok", "engine": "onnx-gpu", "device": "cuda"},
        {"status": "error", "engine": "onnx-gpu", "device": "cuda"},
        {"status": "ok", "engine": "onnx-gpu", "device": "cpu"},
        {"status": "ok", "engine": "other", "device": "cuda"},
        [],
    ],
)
async def test_worker_probe_requires_real_cuda_health_before_catalog(
    monkeypatch, health
):
    import httpx

    calls = []
    original = httpx.AsyncClient

    def handler(request):
        calls.append(request.url.path)
        assert request.headers["authorization"] == "Bearer fixture-key"
        return httpx.Response(
            200,
            json=health
            if request.url.path == "/health"
            else {"data": [{"id": "served-exact"}]},
        )

    monkeypatch.setattr(
        svc.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = await svc.inspect_onnx_worker(
        "http://fixture:8068/v1", api_key="fixture-key"
    )
    if health == {"status": "ok", "engine": "onnx-gpu", "device": "cuda"}:
        assert result["ready"] and result["models"] == ["served-exact"]
        assert calls == ["/health", "/v1/models"]
    else:
        assert not result["ready"] and result["models"] == []
        assert calls == ["/health"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data", [[], [{}], [{"id": ""}], [{"id": "x"}, {"id": "x"}], [{"id": " x"}], "bad"]
)
async def test_worker_probe_rejects_invalid_catalog(monkeypatch, data):
    import httpx

    original = httpx.AsyncClient

    def handler(request):
        return httpx.Response(
            200,
            json={"status": "ok", "engine": "onnx-gpu", "device": "cuda"}
            if request.url.path == "/health"
            else {"data": data},
        )

    monkeypatch.setattr(
        svc.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = await svc.inspect_onnx_worker("http://fixture:8068/v1")
    assert not result["ready"] and result["error"] == "onnx_worker_models_invalid"


@pytest.mark.asyncio
async def test_worker_probe_timeout_is_offline_not_empty_success(monkeypatch):
    import httpx

    original = httpx.AsyncClient

    def handler(request):
        raise httpx.ReadTimeout("private upstream detail", request=request)

    monkeypatch.setattr(
        svc.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = await svc.inspect_onnx_worker("http://fixture:8068/v1")
    assert not result["ready"] and result["status"] == "offline"
    assert "private" not in str(result)
