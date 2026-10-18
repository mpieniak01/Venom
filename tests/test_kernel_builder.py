"""Testy jednostkowe dla KernelBuilder."""

from unittest.mock import MagicMock

import pytest
from pydantic_settings import BaseSettings

from tests.helpers.url_fixtures import LOCALHOST_11434_V1
from venom_core.execution.kernel_builder import KernelBuilder, _safe_find_spec


class MockSettings(BaseSettings):
    """Mockowa konfiguracja do testów."""

    LLM_SERVICE_TYPE: str = "local"
    LLM_LOCAL_ENDPOINT: str = LOCALHOST_11434_V1
    LLM_MODEL_NAME: str = "phi3:latest"
    LLM_LOCAL_API_KEY: str = "venom-local"
    OPENAI_API_KEY: str = ""


def test_kernel_builder_initialization():
    """Test inicjalizacji KernelBuilder."""
    builder = KernelBuilder()
    assert builder.settings is not None


def test_kernel_builder_with_custom_settings():
    """Test inicjalizacji KernelBuilder z custom settings."""
    custom_settings = MockSettings()
    builder = KernelBuilder(settings=custom_settings)
    assert builder.settings == custom_settings


def test_kernel_builder_local_configuration():
    """Test budowania kernela z konfiguracją lokalną."""
    settings = MockSettings(
        LLM_SERVICE_TYPE="local",
        LLM_LOCAL_ENDPOINT=LOCALHOST_11434_V1,
        LLM_MODEL_NAME="phi3:latest",
    )
    builder = KernelBuilder(settings=settings)
    kernel = builder.build_kernel()

    assert kernel is not None
    # Sprawdź czy serwis został dodany
    services = list(kernel.services.values())
    assert len(services) > 0


def test_kernel_builder_openai_configuration():
    """Test budowania kernela z konfiguracją OpenAI."""
    settings = MockSettings(
        LLM_SERVICE_TYPE="openai",
        LLM_MODEL_NAME="gpt-4o",
        OPENAI_API_KEY="sk-test-key-12345",
    )
    builder = KernelBuilder(settings=settings)
    kernel = builder.build_kernel()

    assert kernel is not None
    services = list(kernel.services.values())
    assert len(services) > 0


def test_kernel_builder_openai_without_api_key():
    """Test budowania kernela OpenAI bez API key - powinno rzucić ValueError."""
    settings = MockSettings(
        LLM_SERVICE_TYPE="openai",
        LLM_MODEL_NAME="gpt-4o",
        OPENAI_API_KEY="",  # Brak klucza
    )
    builder = KernelBuilder(settings=settings)

    with pytest.raises(ValueError, match="OPENAI_API_KEY jest wymagany"):
        builder.build_kernel()


def test_kernel_builder_azure_not_implemented():
    """Test budowania kernela Azure bez credentials - powinno rzucić NotImplementedError."""
    settings = MockSettings(
        LLM_SERVICE_TYPE="azure",
        LLM_MODEL_NAME="gpt-4",
    )
    builder = KernelBuilder(settings=settings)

    with pytest.raises(NotImplementedError, match="Azure OpenAI wymaga konfiguracji"):
        builder.build_kernel()


def test_kernel_builder_azure_with_credentials():
    """Test budowania kernela Azure z credentials - obecnie nie zaimplementowane."""

    class AzureSettings(MockSettings):
        AZURE_OPENAI_ENDPOINT: str = "https://test.openai.azure.com/"
        AZURE_OPENAI_KEY: str = "test-azure-key"

    settings = AzureSettings(
        LLM_SERVICE_TYPE="azure",
        LLM_MODEL_NAME="gpt-4",
    )
    builder = KernelBuilder(settings=settings)

    # Nawet z credentials, Azure nie jest jeszcze w pełni zaimplementowany
    with pytest.raises(NotImplementedError, match="Azure OpenAI connector"):
        builder.build_kernel()


def test_kernel_builder_invalid_service_type():
    """Test budowania kernela z niepoprawnym typem serwisu."""
    settings = MockSettings(
        LLM_SERVICE_TYPE="invalid_type",
        LLM_MODEL_NAME="phi3:latest",
    )
    builder = KernelBuilder(settings=settings)

    with pytest.raises(ValueError, match="Nieznany typ serwisu LLM"):
        builder.build_kernel()


def test_kernel_builder_case_insensitive_service_type():
    """Test że typ serwisu nie jest case-sensitive."""
    settings = MockSettings(
        LLM_SERVICE_TYPE="LOCAL",  # Uppercase
        LLM_LOCAL_ENDPOINT=LOCALHOST_11434_V1,
        LLM_MODEL_NAME="phi3:latest",
    )
    builder = KernelBuilder(settings=settings)
    kernel = builder.build_kernel()

    assert kernel is not None


def test_kernel_builder_google_without_api_key():
    """Test budowania kernela Google Gemini bez API key."""

    class GoogleSettings(MockSettings):
        GOOGLE_API_KEY: str = ""

    settings = GoogleSettings(
        LLM_SERVICE_TYPE="google",
        LLM_MODEL_NAME="gemini-1.5-pro",
    )
    builder = KernelBuilder(settings=settings)

    # Może rzucić ValueError o brakującej bibliotece lub o brakującym kluczu API
    with pytest.raises(ValueError):
        builder.build_kernel()


def test_kernel_builder_google_not_implemented():
    """Test budowania kernela Google Gemini (zależne od dostępnych optional deps)."""

    class GoogleSettings(MockSettings):
        GOOGLE_API_KEY: str = "test-google-key"

    settings = GoogleSettings(
        LLM_SERVICE_TYPE="google",
        LLM_MODEL_NAME="gemini-1.5-pro",
    )
    builder = KernelBuilder(settings=settings)

    # W środowiskach lite, optional deps Google mogą być niedostępne.
    # W takim przypadku oczekujemy kontrolowanego ValueError.
    try:
        kernel = builder.build_kernel()
    except ValueError:
        return

    assert kernel is not None
    services = list(kernel.services.values())
    assert len(services) > 0


def test_kernel_builder_enable_grounding_parameter():
    """Test dodania parametru enable_grounding do _register_service."""
    from venom_core.execution.maf_runtime import AgentRuntime as Kernel

    class GoogleSettings(MockSettings):
        GOOGLE_API_KEY: str = "test-google-key"

    settings = GoogleSettings(
        LLM_SERVICE_TYPE="google",
        LLM_MODEL_NAME="gemini-1.5-pro",
    )
    builder = KernelBuilder(settings=settings)
    kernel = Kernel()

    # Parametr powinien być akceptowany bez błędu składniowego.
    # W środowiskach bez optional deps oczekujemy kontrolowanego ValueError.
    try:
        builder._register_service(
            kernel, "google", service_id="google_grounding_on", enable_grounding=True
        )
        builder._register_service(
            kernel, "google", service_id="google_grounding_off", enable_grounding=False
        )
    except ValueError:
        pass


def test_register_google_service_registers_connector(monkeypatch):
    """_register_google_service rejestruje GoogleAIChatCompletion gdy deps są dostępne."""
    import venom_core.execution.kernel_builder as kbmod

    class GoogleSettings(MockSettings):
        GOOGLE_API_KEY: str = "test-google-key"

    settings = GoogleSettings(
        LLM_SERVICE_TYPE="google",
        LLM_MODEL_NAME="gemini-2.5-flash",
    )
    builder = KernelBuilder(settings=settings)
    from venom_core.execution.maf_runtime import AgentRuntime as Kernel

    kernel = MagicMock(spec=Kernel)

    fake_service = object()
    fake_connector = MagicMock(return_value=fake_service)
    monkeypatch.setattr(kbmod, "GOOGLE_AVAILABLE", True)
    monkeypatch.setattr(kbmod, "MafChatService", fake_connector)

    builder._register_google_service(
        kernel=kernel,
        service_id="google",
        model_name="gemini-2.5-flash",
        enable_grounding=True,
    )

    fake_connector.assert_called_once_with(
        service_id="google",
        ai_model_id="gemini-2.5-flash",
        api_key="test-google-key",
        base_url=kbmod.GEMINI_OPENAI_ENDPOINT,
    )
    kernel.add_service.assert_called_once_with(fake_service)


def test_safe_find_spec_returns_none_on_internal_error(monkeypatch):
    import venom_core.execution.kernel_builder as kbmod

    monkeypatch.setattr(
        kbmod.importlib.util,
        "find_spec",
        lambda _name: (_ for _ in ()).throw(ValueError("boom")),
    )
    assert _safe_find_spec("x.any") is None


def test_register_google_service_requires_key_when_google_available(monkeypatch):
    import venom_core.execution.kernel_builder as kbmod
    from venom_core.execution.maf_runtime import AgentRuntime as Kernel

    class GoogleSettings(MockSettings):
        GOOGLE_API_KEY: str = ""

    settings = GoogleSettings(LLM_SERVICE_TYPE="google", LLM_MODEL_NAME="gemini-x")
    builder = KernelBuilder(settings=settings)
    kernel = MagicMock(spec=Kernel)

    monkeypatch.setattr(kbmod, "GOOGLE_AVAILABLE", True)
    monkeypatch.setattr(kbmod, "MafChatService", MagicMock())

    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        builder._register_google_service(kernel, "google", "gemini-x", False)


def test_register_google_service_requires_maf_provider(monkeypatch):
    import venom_core.execution.kernel_builder as kbmod

    class GoogleSettings(MockSettings):
        GOOGLE_API_KEY: str = "test-google-key"

    builder = KernelBuilder(settings=GoogleSettings())
    monkeypatch.setattr(kbmod, "GOOGLE_AVAILABLE", False)
    with pytest.raises(ValueError, match="Provider MAF"):
        builder._register_google_service(MagicMock(), "google", "gemini-x", False)


def test_register_all_services_logs_openai_registration_failure(monkeypatch):
    settings = MockSettings(
        LLM_SERVICE_TYPE="local",
        OPENAI_API_KEY="sk-test-key",
    )
    builder = KernelBuilder(settings=settings, enable_multi_service=True)

    def _raise_on_openai(kernel, service_type, **kwargs):  # type: ignore[no-untyped-def]
        del kernel, kwargs
        if service_type == "openai":
            raise RuntimeError("openai-fail")
        return None

    monkeypatch.setattr(builder, "_register_service", _raise_on_openai)
    kernel = MagicMock()
    builder._register_all_services(kernel)


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", ["onnx", "active_local", "forced_local", "multi"])
@pytest.mark.parametrize(
    "policy,scheme", [("force_http", "http"), ("force_https", "https")]
)
async def test_onnx_factory_uses_explicit_worker_in_every_registration_mode(
    monkeypatch, selection, policy, scheme
):
    """A stale Ollama URL must never receive an ONNX request after local forcing."""

    from venom_core.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "URL_SCHEME_POLICY", policy)

    class OnnxSettings(MockSettings):
        ONNX_LLM_ENABLED: bool = True
        ONNX_LLM_ENDPOINT: str = "http://127.0.0.1:8068/v1"
        ACTIVE_LLM_SERVER: str = "onnx"
        AI_MODE: str = "LOCAL" if selection == "forced_local" else ""

    settings = OnnxSettings(
        LLM_SERVICE_TYPE="local" if selection == "active_local" else "onnx",
        LLM_MODEL_NAME="served-onnx-fixture",
    )
    runtime = KernelBuilder(
        settings=settings,
        enable_routing=False,
        enable_multi_service=selection == "multi",
    ).build_kernel()
    try:
        assert len(runtime.services) == 1
        service = next(iter(runtime.services.values()))
        assert service.ai_model_id == "served-onnx-fixture"
        assert str(service._owned_client.base_url) == f"{scheme}://127.0.0.1:8068/v1/"
    finally:
        await runtime.aclose()


@pytest.mark.parametrize(
    "enabled,endpoint,error",
    [
        (False, "http://127.0.0.1:8068/v1", "ONNX_LLM_ENABLED"),
        (True, "", "ONNX_LLM_ENDPOINT"),
        (True, "file:///model.onnx", "ONNX_LLM_ENDPOINT"),
        (True, "http://localhost:bad/v1", "ONNX_LLM_ENDPOINT"),
    ],
)
@pytest.mark.parametrize("service_type", ["local", "onnx"])
@pytest.mark.parametrize("multi", [False, True])
def test_onnx_invalid_configuration_fails_before_creating_any_client(
    monkeypatch, enabled, endpoint, error, service_type, multi
):
    from venom_core.execution import kernel_builder as module

    class OnnxSettings(MockSettings):
        ONNX_LLM_ENABLED: bool = enabled
        ONNX_LLM_ENDPOINT: str = endpoint
        ACTIVE_LLM_SERVER: str = "onnx"

    forbidden = MagicMock(side_effect=AssertionError("native/HTTP client created"))
    monkeypatch.setattr(module, "AsyncOpenAI", forbidden)
    with pytest.raises(ValueError, match=error):
        KernelBuilder(
            settings=OnnxSettings(LLM_SERVICE_TYPE=service_type),
            enable_routing=False,
            enable_multi_service=multi,
        ).build_kernel()
    forbidden.assert_not_called()
