"""Testy jednostkowe dla modułu Council (bez dependencies na pełny kernel)."""

import pytest

from venom_core.core.council import create_local_llm_config


def test_create_local_llm_config():
    """Test tworzenia konfiguracji lokalnego LLM."""
    config = create_local_llm_config()

    assert "config_list" in config
    assert len(config["config_list"]) > 0
    assert config["config_list"][0]["model"] == "llama3"
    assert config["config_list"][0]["api_key"] == "EMPTY"
    assert config["temperature"] == pytest.approx(0.7)


def test_create_local_llm_config_custom_params():
    """Test tworzenia konfiguracji z niestandardowymi parametrami."""
    config = create_local_llm_config(
        base_url="http://localhost:8080/v1",
        model="mixtral",
        temperature=0.5,
    )

    assert config["config_list"][0]["model"] == "mixtral"
    assert config["config_list"][0]["base_url"] == "http://localhost:8080/v1"
    assert config["temperature"] == pytest.approx(0.5)
    assert config["timeout"] == 120


def test_swarm_module_imports():
    """Test importowania modułu swarm."""
    from venom_core.core.swarm import VenomAgent, create_venom_agent_wrapper

    # Sprawdź że klasy/funkcje są dostępne
    assert callable(create_venom_agent_wrapper)
    assert isinstance(VenomAgent.__name__, str)


def test_create_local_llm_config_invalid_temperature_high():
    """Test walidacji temperatury - wartość za wysoka."""
    try:
        create_local_llm_config(temperature=1.5)
        assert False, "Powinien rzucić ValueError dla temperature > 1.0"
    except ValueError as e:
        assert "Temperature" in str(e)
        assert "0.0-1.0" in str(e)


def test_create_local_llm_config_invalid_temperature_low():
    """Test walidacji temperatury - wartość za niska."""
    try:
        create_local_llm_config(temperature=-0.1)
        assert False, "Powinien rzucić ValueError dla temperature < 0.0"
    except ValueError as e:
        assert "Temperature" in str(e)
        assert "0.0-1.0" in str(e)


def test_create_local_llm_config_invalid_base_url_empty():
    """Test walidacji base_url - pusty string."""
    try:
        create_local_llm_config(base_url="")
        assert False, "Powinien rzucić ValueError dla pustego base_url"
    except ValueError as e:
        assert "base_url" in str(e)


def test_create_local_llm_config_invalid_model_empty():
    """Test walidacji model - pusty string."""
    try:
        create_local_llm_config(model="")
        assert False, "Powinien rzucić ValueError dla pustego model"
    except ValueError as e:
        assert "model" in str(e)


def test_create_local_llm_config_edge_case_temperature_zero():
    """Test edge case - temperatura 0.0 powinna być akceptowana."""
    config = create_local_llm_config(temperature=0.0)
    assert config["temperature"] == pytest.approx(0.0)


def test_create_local_llm_config_edge_case_temperature_one():
    """Test edge case - temperatura 1.0 powinna być akceptowana."""
    config = create_local_llm_config(temperature=1.0)
    assert config["temperature"] == pytest.approx(1.0)
