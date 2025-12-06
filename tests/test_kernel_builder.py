"""Testy jednostkowe dla KernelBuilder."""

import pytest
from pydantic_settings import BaseSettings

from venom_core.execution.kernel_builder import KernelBuilder


class MockSettings(BaseSettings):
    """Mockowa konfiguracja do testów."""

    LLM_SERVICE_TYPE: str = "local"
    LLM_LOCAL_ENDPOINT: str = "http://localhost:11434/v1"
    LLM_MODEL_NAME: str = "phi3:latest"
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
    """Test budowania kernela Azure - powinno rzucić NotImplementedError."""
    settings = MockSettings(
        LLM_SERVICE_TYPE="azure",
        LLM_MODEL_NAME="gpt-4",
    )
    builder = KernelBuilder(settings=settings)

    with pytest.raises(NotImplementedError, match="Azure OpenAI nie jest jeszcze"):
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
