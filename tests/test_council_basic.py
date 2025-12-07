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
    assert config["temperature"] == 0.7


def test_create_local_llm_config_custom_params():
    """Test tworzenia konfiguracji z niestandardowymi parametrami."""
    config = create_local_llm_config(
        base_url="http://localhost:8080/v1",
        model="mixtral",
        temperature=0.5,
    )

    assert config["config_list"][0]["model"] == "mixtral"
    assert config["config_list"][0]["base_url"] == "http://localhost:8080/v1"
    assert config["temperature"] == 0.5
    assert config["timeout"] == 120


def test_swarm_module_imports():
    """Test importowania modułu swarm."""
    from venom_core.core.swarm import VenomAgent, create_venom_agent_wrapper

    # Sprawdź że klasy/funkcje są dostępne
    assert VenomAgent is not None
    assert create_venom_agent_wrapper is not None
