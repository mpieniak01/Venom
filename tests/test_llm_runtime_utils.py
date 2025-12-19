import pytest

import venom_core.utils.llm_runtime as llm_runtime


class DummySettings:
    def __init__(
        self,
        service_type="local",
        mode="LOCAL",
        model_name="model-x",
        endpoint="http://localhost:8000",
        azure_endpoint=None,
    ):
        self.LLM_SERVICE_TYPE = service_type
        self.AI_MODE = mode
        self.LLM_MODEL_NAME = model_name
        self.LLM_LOCAL_ENDPOINT = endpoint
        self.AZURE_OPENAI_ENDPOINT = azure_endpoint


def test_infer_local_provider_variants():
    assert llm_runtime.infer_local_provider("") == "local"
    assert llm_runtime.infer_local_provider("http://localhost:11434") == "ollama"
    assert llm_runtime.infer_local_provider("http://vllm.local") == "vllm"
    assert llm_runtime.infer_local_provider("http://lmstudio.local") == "lmstudio"
    assert llm_runtime.infer_local_provider("http://localhost:8001") == "vllm"


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
        DummySettings(service_type="local", endpoint="http://localhost:11434")
    )
    assert runtime.provider == "ollama"


def test_format_runtime_label_and_health_url():
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="foo/bar",
        endpoint="http://localhost:8001/v1",
        service_type="local",
        mode="LOCAL",
    )
    label = llm_runtime.format_runtime_label(runtime)
    assert "bar" in label
    assert "localhost:8001" in label

    assert llm_runtime._build_health_url(runtime).endswith("/v1/models")
    assert llm_runtime._build_health_url(
        llm_runtime.LLMRuntimeInfo(
            provider="ollama",
            model_name="x",
            endpoint="http://localhost:11434",
            service_type="local",
            mode="LOCAL",
        )
    ).endswith("/api/tags")


@pytest.mark.asyncio
async def test_probe_runtime_status_success(monkeypatch):
    class DummyResponse:
        status_code = 200

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
        endpoint="http://localhost:8001",
        service_type="local",
        mode="LOCAL",
    )

    status, error = await llm_runtime.probe_runtime_status(runtime)

    assert status == "online"
    assert error is None


@pytest.mark.asyncio
async def test_probe_runtime_status_failure(monkeypatch):
    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, _url):
            raise llm_runtime.httpx.HTTPError("boom")

    monkeypatch.setattr(
        llm_runtime.httpx, "AsyncClient", lambda timeout=5.0: DummyClient()
    )
    runtime = llm_runtime.LLMRuntimeInfo(
        provider="vllm",
        model_name="model-x",
        endpoint="http://localhost:8001",
        service_type="local",
        mode="LOCAL",
    )

    status, error = await llm_runtime.probe_runtime_status(runtime)

    assert status == "offline"
    assert "boom" in error
