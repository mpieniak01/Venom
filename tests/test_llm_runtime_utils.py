import asyncio

import pytest

import venom_core.utils.llm_runtime as llm_runtime
from tests.helpers.url_fixtures import (
    LOCALHOST_8000,
    LOCALHOST_8001,
    LOCALHOST_8001_V1,
    LOCALHOST_11434,
    http_url,
)


class DummySettings:
    def __init__(
        self,
        service_type="local",
        mode="LOCAL",
        model_name="model-x",
        endpoint=LOCALHOST_8000,
        azure_endpoint=None,
    ):
        self.LLM_SERVICE_TYPE = service_type
        self.AI_MODE = mode
        self.LLM_MODEL_NAME = model_name
        self.LLM_LOCAL_ENDPOINT = endpoint
        self.AZURE_OPENAI_ENDPOINT = azure_endpoint


def test_infer_local_provider_variants():
    assert llm_runtime.infer_local_provider("") == "local"
    assert llm_runtime.infer_local_provider(LOCALHOST_11434) == "ollama"
    assert llm_runtime.infer_local_provider(http_url("vllm.local")) == "vllm"
    assert llm_runtime.infer_local_provider(http_url("onnx.local")) == "onnx"
    assert llm_runtime.infer_local_provider(http_url("lmstudio.local")) == "lmstudio"
    assert llm_runtime.infer_local_provider(LOCALHOST_8001) == "vllm"
    assert llm_runtime.infer_local_provider(http_url("custom.local")) == "local"


def test_runtime_hash_and_id_are_stable():
    hash_1 = llm_runtime.compute_llm_config_hash(
        "OpenAI", "HTTPS://API.EXAMPLE/V1", "Model-X"
    )
    hash_2 = llm_runtime.compute_llm_config_hash(
        "openai", "https://api.example/v1", "model-x"
    )
    assert hash_1 == hash_2
    assert len(hash_1) == 12

    assert (
        llm_runtime.compute_runtime_id("openai", "https://api.example/v1")
        == "openai@https://api.example/v1"
    )
    assert llm_runtime.compute_runtime_id(None, None) == "local@local"


def test_get_active_llm_runtime_variants():
    runtime = llm_runtime.get_active_llm_runtime(
        DummySettings(service_type="openai", endpoint=None)
    )
    assert runtime.provider == "openai"
    assert runtime.endpoint.endswith("/v1")

    runtime = llm_runtime.get_active_llm_runtime(
        DummySettings(service_type="google", endpoint=None)
    )
    assert runtime.provider == "google-gemini"

    runtime = llm_runtime.get_active_llm_runtime(
        DummySettings(
            service_type="azure", endpoint=None, azure_endpoint="https://azure.example"
        )
    )
    assert runtime.provider == "azure-openai"
    assert runtime.endpoint == "https://azure.example"

    runtime = llm_runtime.get_active_llm_runtime(
        DummySettings(service_type="local", endpoint=LOCALHOST_11434)
    )
    assert runtime.provider == "ollama"

    runtime = llm_runtime.get_active_llm_runtime(
        DummySettings(service_type="onnx", endpoint=None)
    )
    assert runtime.provider == "onnx"
    assert runtime.endpoint is None


def test_format_runtime_label_and_health_url():
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="foo/bar",
        endpoint=LOCALHOST_8001_V1,
        service_type="local",
        mode="LOCAL",
    )
    label = llm_runtime.format_runtime_label(runtime)
    assert "bar" in label
    assert "localhost:8001" in label

    assert llm_runtime._build_health_url(runtime).endswith("/v1/models")
    assert (
        llm_runtime._build_health_url(
            llm_runtime.LLMRuntimeInfo(
                provider="vllm",
                model_name="x",
                endpoint="http://localhost:8001/models",
                service_type="local",
                mode="LOCAL",
            )
        )
        == "http://localhost:8001/models"
    )
    assert (
        llm_runtime._build_health_url(
            llm_runtime.LLMRuntimeInfo(
                provider="vllm",
                model_name="x",
                endpoint="http://localhost:8001/v1/",
                service_type="local",
                mode="LOCAL",
            )
        )
        == "http://localhost:8001/v1/models"
    )
    assert llm_runtime._build_health_url(
        llm_runtime.LLMRuntimeInfo(
            provider="ollama",
            model_name="x",
            endpoint=LOCALHOST_11434,
            service_type="local",
            mode="LOCAL",
        )
    ).endswith("/api/tags")
    assert (
        llm_runtime._build_health_url(
            llm_runtime.LLMRuntimeInfo(
                provider="onnx",
                model_name="x",
                endpoint=None,
                service_type="onnx",
                mode="LOCAL",
            )
        )
        is None
    )


def test_format_runtime_label_without_endpoint_uses_local():
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="onnx",
        model_name="acme/model",
        endpoint=None,
        service_type="onnx",
        mode="LOCAL",
    )
    assert llm_runtime.format_runtime_label(runtime) == "model · onnx @ local"


def test_build_chat_completions_url_variants():
    base_runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="x",
        endpoint="http://localhost:8001",
        service_type="local",
        mode="LOCAL",
    )
    assert (
        llm_runtime._build_chat_completions_url(base_runtime)
        == "http://localhost:8001/v1/chat/completions"
    )

    with_v1 = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="x",
        endpoint="http://localhost:8001/v1",
        service_type="local",
        mode="LOCAL",
    )
    assert (
        llm_runtime._build_chat_completions_url(with_v1)
        == "http://localhost:8001/v1/chat/completions"
    )

    already_full = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="x",
        endpoint="http://localhost:8001/v1/chat/completions",
        service_type="local",
        mode="LOCAL",
    )
    assert (
        llm_runtime._build_chat_completions_url(already_full)
        == "http://localhost:8001/v1/chat/completions"
    )

    assert (
        llm_runtime._build_chat_completions_url(
            llm_runtime.LLMRuntimeInfo(
                provider="vllm",
                model_name="x",
                endpoint=None,
                service_type="local",
                mode="LOCAL",
            )
        )
        is None
    )


@pytest.mark.asyncio
async def test_probe_runtime_status_onnx_ready():
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="onnx",
        model_name="phi",
        endpoint=None,
        service_type="onnx",
        mode="LOCAL",
    )
    status, error = await llm_runtime.probe_runtime_status(runtime)
    assert status == "ready"
    assert error is None


@pytest.mark.asyncio
async def test_probe_runtime_status_success(monkeypatch):
    class DummyResponse:
        status_code = 200

    class DummyClient:
        async def __aenter__(self):
            await asyncio.sleep(0)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await asyncio.sleep(0)
            return None

        async def get(self, _url):
            await asyncio.sleep(0)
            return DummyResponse()

    monkeypatch.setattr(
        llm_runtime.httpx, "AsyncClient", lambda timeout=5.0: DummyClient()
    )
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="model-x",
        endpoint=LOCALHOST_8001,
        service_type="local",
        mode="LOCAL",
    )

    status, error = await llm_runtime.probe_runtime_status(runtime)

    assert status == "online"
    assert error is None


@pytest.mark.asyncio
async def test_probe_runtime_status_non_local_service_is_ready():
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="openai",
        model_name="gpt-4.1-mini",
        endpoint="https://api.openai.com/v1",
        service_type="openai",
        mode="CLOUD",
    )
    status, error = await llm_runtime.probe_runtime_status(runtime)
    assert status == "ready"
    assert error is None


@pytest.mark.asyncio
async def test_probe_runtime_status_missing_local_endpoint_is_offline():
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="model-x",
        endpoint=None,
        service_type="local",
        mode="LOCAL",
    )
    status, error = await llm_runtime.probe_runtime_status(runtime)
    assert status == "offline"
    assert error == "Brak endpointu runtime"


@pytest.mark.asyncio
async def test_probe_runtime_status_failure(monkeypatch):
    class DummyClient:
        async def __aenter__(self):
            await asyncio.sleep(0)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await asyncio.sleep(0)
            return None

        async def get(self, _url):
            await asyncio.sleep(0)
            raise llm_runtime.httpx.HTTPError("boom")

    monkeypatch.setattr(
        llm_runtime.httpx, "AsyncClient", lambda timeout=5.0: DummyClient()
    )
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="model-x",
        endpoint=LOCALHOST_8001,
        service_type="local",
        mode="LOCAL",
    )

    status, error = await llm_runtime.probe_runtime_status(runtime)

    assert status == "offline"
    assert "boom" in error


@pytest.mark.asyncio
async def test_probe_runtime_status_degraded_for_http_error_code(monkeypatch):
    class DummyResponse:
        status_code = 503

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, _url):
            return DummyResponse()

    monkeypatch.setattr(
        llm_runtime.httpx, "AsyncClient", lambda timeout=5.0: DummyClient()
    )
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="model-x",
        endpoint=LOCALHOST_8001,
        service_type="local",
        mode="LOCAL",
    )
    status, error = await llm_runtime.probe_runtime_status(runtime)
    assert status == "degraded"
    assert error == "HTTP 503"


@pytest.mark.asyncio
async def test_probe_runtime_status_generic_exception_falls_back_to_offline(
    monkeypatch,
):
    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, _url):
            raise RuntimeError("unexpected")

    monkeypatch.setattr(
        llm_runtime.httpx, "AsyncClient", lambda timeout=5.0: DummyClient()
    )
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="model-x",
        endpoint=LOCALHOST_8001,
        service_type="local",
        mode="LOCAL",
    )
    status, error = await llm_runtime.probe_runtime_status(runtime)
    assert status == "offline"
    assert "unexpected" in error


@pytest.mark.asyncio
async def test_warmup_local_runtime_status_paths(monkeypatch):
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="model-x",
        endpoint=LOCALHOST_8001,
        service_type="local",
        mode="LOCAL",
    )

    class DummyResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    class DummyClient:
        def __init__(self, status_code):
            self._status_code = status_code

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, _url, json):
            assert json["model"] == "model-x"
            return DummyResponse(self._status_code)

    monkeypatch.setattr(
        llm_runtime.httpx, "AsyncClient", lambda timeout=5.0: DummyClient(200)
    )
    assert (
        await llm_runtime.warmup_local_runtime(
            runtime,
            prompt="warmup",
            timeout_seconds=5.0,
            max_tokens=8,
        )
        is True
    )

    monkeypatch.setattr(
        llm_runtime.httpx, "AsyncClient", lambda timeout=5.0: DummyClient(500)
    )
    assert (
        await llm_runtime.warmup_local_runtime(
            runtime,
            prompt="warmup",
            timeout_seconds=5.0,
            max_tokens=8,
        )
        is False
    )

    non_local = llm_runtime.LLMRuntimeInfo(
        provider="openai",
        model_name="gpt-4.1-mini",
        endpoint="https://api.openai.com/v1",
        service_type="openai",
        mode="CLOUD",
    )
    assert (
        await llm_runtime.warmup_local_runtime(
            non_local,
            prompt="warmup",
            timeout_seconds=5.0,
            max_tokens=8,
        )
        is False
    )
