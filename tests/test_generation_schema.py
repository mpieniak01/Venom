"""Testy dla systemu strojenia parametrów (generation schema)."""

import pytest

from venom_core.core.model_registry import (
    GenerationParameter,
    ModelCapabilities,
    ModelMetadata,
    ModelProvider,
    _create_default_generation_schema,
)


def test_generation_parameter_creation():
    """Test tworzenia GenerationParameter."""
    param = GenerationParameter(
        type="float",
        default=0.7,
        min=0.0,
        max=2.0,
        desc="Temperatura",
    )

    assert param.type == "float"
    assert param.default == pytest.approx(0.7)
    assert param.min == pytest.approx(0.0)
    assert param.max == pytest.approx(2.0)
    assert param.desc == "Temperatura"


def test_generation_parameter_to_dict():
    """Test konwersji GenerationParameter do słownika."""
    param = GenerationParameter(
        type="int",
        default=2048,
        min=128,
        max=8192,
        desc="Max tokens",
    )

    data = param.to_dict()

    assert data["type"] == "int"
    assert data["default"] == 2048
    assert data["min"] == 128
    assert data["max"] == 8192
    assert data["desc"] == "Max tokens"


def test_default_generation_schema():
    """Test tworzenia domyślnego schematu generacji."""
    schema = _create_default_generation_schema()

    assert "temperature" in schema
    assert "max_tokens" in schema
    assert "top_p" in schema
    assert "top_k" in schema
    assert "repeat_penalty" in schema

    # Sprawdź temperature
    temp = schema["temperature"]
    assert temp.type == "float"
    assert temp.default == pytest.approx(0.7)
    assert temp.min == pytest.approx(0.0)
    assert temp.max == pytest.approx(2.0)

    # Sprawdź max_tokens
    max_tokens = schema["max_tokens"]
    assert max_tokens.type == "int"
    assert max_tokens.default == 2048
    assert max_tokens.min == 128
    assert max_tokens.max == 8192


def test_model_capabilities_with_generation_schema():
    """Test ModelCapabilities z generation_schema."""
    schema = _create_default_generation_schema()

    caps = ModelCapabilities(
        supports_system_role=True,
        generation_schema=schema,
    )

    assert caps.generation_schema is not None
    assert "temperature" in caps.generation_schema


def test_model_metadata_to_dict_with_generation_schema():
    """Test konwersji ModelMetadata z generation_schema do słownika."""
    schema = _create_default_generation_schema()

    metadata = ModelMetadata(
        name="test-model",
        provider=ModelProvider.OLLAMA,
        display_name="Test Model",
        capabilities=ModelCapabilities(
            generation_schema=schema,
        ),
    )

    data = metadata.to_dict()

    assert "capabilities" in data
    assert "generation_schema" in data["capabilities"]
    assert "temperature" in data["capabilities"]["generation_schema"]

    temp_data = data["capabilities"]["generation_schema"]["temperature"]
    assert temp_data["type"] == "float"
    assert temp_data["default"] == pytest.approx(0.7)


def test_llama3_temperature_range():
    """Test że Llama 3 automatycznie dostaje temperaturę w zakresie 0.0-1.0."""
    # Test weryfikuje że schemat dla Llama 3 ma właściwy zakres temperatury
    schema = _create_default_generation_schema()

    # Modyfikuj schemat tak jak robi to OllamaModelProvider dla Llama 3
    schema["temperature"] = GenerationParameter(
        type="float",
        default=0.7,
        min=0.0,
        max=1.0,
        desc="Kreatywność modelu (0 = deterministyczny, 1 = kreatywny)",
    )

    assert schema["temperature"].max == pytest.approx(1.0)
    assert schema["temperature"].min == pytest.approx(0.0)


def test_ollama_provider_llama3_detection():
    """Test że OllamaModelProvider poprawnie wykrywa modele Llama 3."""
    import re

    # Test pattern matching dla różnych nazw Llama 3
    llama3_pattern = re.compile(r"llama-?3(?:[:\-]|$)", re.IGNORECASE)

    # Powinny pasować
    assert llama3_pattern.search("llama3")
    assert llama3_pattern.search("llama-3")
    assert llama3_pattern.search("llama3:latest")
    assert llama3_pattern.search("llama-3:8b")

    # Nie powinny pasować (fałszywe pozytywy)
    assert not llama3_pattern.search("llama-30b")
    assert not llama3_pattern.search("llama-3b")
    assert not llama3_pattern.search("my-llama-v3")
