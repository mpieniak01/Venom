from __future__ import annotations

import pytest

from venom_core.services import system_llm_service as svc


def test_runtime_profile_name_and_allowed_servers():
    assert svc.runtime_profile_name("LIGHT") == "light"
    assert svc.runtime_profile_name("bad") == "full"

    assert svc.allowed_local_servers(
        profile="light", onnx_enabled=True
    ) == svc.allowed_local_servers(profile="full", onnx_enabled=True)
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
@pytest.mark.parametrize(
    "policy,scheme", [("force_http", "http"), ("force_https", "https")]
)
async def test_worker_probe_requires_real_cuda_health_before_catalog(
    monkeypatch, health, policy, scheme
):
    import httpx

    from venom_core.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "URL_SCHEME_POLICY", policy)
    calls = []
    original = httpx.AsyncClient

    def handler(request):
        calls.append(request.url.path)
        assert request.url.scheme == scheme
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
        assert result["ready"]
        assert result["models"] == ["served-exact"]
        assert calls == ["/health", "/v1/models"]
    else:
        assert not result["ready"]
        assert result["models"] == []
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
    assert not result["ready"]
    assert result["error"] == "onnx_worker_models_invalid"


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
    assert not result["ready"]
    assert result["status"] == "offline"
    assert "private" not in str(result)


@pytest.mark.parametrize("component", ["explicit", "components_dir", "default"])
def test_vllm_component_configuration_needs_no_application_sdk(
    monkeypatch, tmp_path, component
):
    repo = tmp_path / "repository"
    root = (
        tmp_path / "components"
        if component == "components_dir"
        else repo / ".venv-components"
    )
    interpreter = root / "vllm/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("#!/bin/sh\nexit 0\n")
    interpreter.chmod(0o700)
    monkeypatch.setattr(
        svc, "__file__", str(repo / "venom_core/services/system_llm_service.py")
    )
    kwargs = {
        "component_python": str(interpreter) if component == "explicit" else "",
        "components_dir": str(root) if component == "components_dir" else "",
    }
    assert svc.is_vllm_worker_configured("http://127.0.0.1:8067/v1", **kwargs)
    interpreter.chmod(0o600)
    assert not svc.is_vllm_worker_configured("http://127.0.0.1:8067/v1", **kwargs)
    interpreter.unlink()
    assert not svc.is_vllm_worker_configured("http://127.0.0.1:8067/v1", **kwargs)


@pytest.mark.parametrize(
    "endpoint",
    ["", "file:///model", "http://host:bad/v1", "http://user:secret@host/v1"],
)
def test_vllm_configured_command_still_requires_valid_endpoint(endpoint):
    assert not svc.is_vllm_worker_configured(endpoint, start_command="owned start")


def test_vllm_explicit_command_is_configuration_not_sdk_or_health(monkeypatch):
    def unexpected(*args):
        raise AssertionError(
            "No SDK lookup or command execution during configuration check"
        )

    monkeypatch.setattr(svc.importlib.util, "find_spec", unexpected)
    monkeypatch.setattr(svc.shutil, "which", unexpected)
    assert svc.is_vllm_worker_configured(
        "http://127.0.0.1:8067/v1", start_command="owned start"
    )
