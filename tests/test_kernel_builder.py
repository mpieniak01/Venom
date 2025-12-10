"""Testy jednostkowe dla KernelBuilder."""

import pytest
from pydantic_settings import BaseSettings

from venom_core.execution.kernel_builder import KernelBuilder


class MockSettings(BaseSettings):
    """Mockowa konfiguracja do testów."""

    LLM_SERVICE_TYPE: str = "local"
    LLM_LOCAL_ENDPOINT: str = "http://localhost:11434/v1"
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
        LLM_LOCAL_ENDPOINT="http://localhost:11434/v1",
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
        LLM_LOCAL_ENDPOINT="http://localhost:11434/v1",
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
    """Test budowania kernela Google Gemini - obecnie nie w pełni zaimplementowane."""

    class GoogleSettings(MockSettings):
        GOOGLE_API_KEY: str = "test-google-key"

    settings = GoogleSettings(
        LLM_SERVICE_TYPE="google",
        LLM_MODEL_NAME="gemini-1.5-pro",
    )
    builder = KernelBuilder(settings=settings)

    # Google Gemini wymaga biblioteki i dedykowanego connectora dla Semantic Kernel
    # Może rzucić ValueError (brak biblioteki) lub NotImplementedError (brak connectora)
    with pytest.raises((ValueError, NotImplementedError)):
        builder.build_kernel()


def test_kernel_builder_enable_grounding_parameter():
    """Test dodania parametru enable_grounding do _register_service."""
    from semantic_kernel import Kernel

    class GoogleSettings(MockSettings):
        GOOGLE_API_KEY: str = "test-google-key"

    settings = GoogleSettings(
        LLM_SERVICE_TYPE="google",
        LLM_MODEL_NAME="gemini-1.5-pro",
    )
    builder = KernelBuilder(settings=settings)
    kernel = Kernel()

    # Test że parametr enable_grounding jest akceptowany
    # Spodziewamy się NotImplementedError bo Google connector nie jest gotowy
    with pytest.raises((ValueError, NotImplementedError)):
        builder._register_service(kernel, "google", enable_grounding=True)

    # Parametr powinien być akceptowany bez błędu składniowego
    # Sprawdzamy tylko że funkcja przyjmuje parametr
    try:
        builder._register_service(kernel, "google", enable_grounding=False)
    except (ValueError, NotImplementedError):
        # To jest oczekiwane - Google nie jest jeszcze zaimplementowany
        pass
