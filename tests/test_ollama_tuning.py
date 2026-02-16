from __future__ import annotations

from types import SimpleNamespace

from venom_core.utils.ollama_tuning import (
    PROFILE_BALANCED,
    PROFILE_LOW_VRAM,
    build_ollama_runtime_options,
    resolve_ollama_tuning_profile,
)


def _settings(**kwargs):
    defaults = {
        "VENOM_OLLAMA_PROFILE": PROFILE_BALANCED,
        "OLLAMA_CONTEXT_LENGTH": 0,
        "OLLAMA_NUM_PARALLEL": 0,
        "OLLAMA_MAX_QUEUE": 0,
        "OLLAMA_FLASH_ATTENTION": True,
        "OLLAMA_KV_CACHE_TYPE": "",
        "LLM_KEEP_ALIVE": "5m",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_resolve_ollama_tuning_profile_uses_profile_defaults():
    resolved = resolve_ollama_tuning_profile(_settings())
    assert resolved["profile"] == PROFILE_BALANCED
    assert resolved["context_length"] == 32768
    assert resolved["num_parallel"] == 2
    assert resolved["max_queue"] == 256
    assert resolved["kv_cache_type"] == "q8_0"
    assert resolved["keep_alive"] == "5m"


def test_resolve_ollama_tuning_profile_applies_env_overrides():
    resolved = resolve_ollama_tuning_profile(
        _settings(
            VENOM_OLLAMA_PROFILE=PROFILE_LOW_VRAM,
            OLLAMA_CONTEXT_LENGTH=24576,
            OLLAMA_NUM_PARALLEL=3,
            OLLAMA_MAX_QUEUE=222,
            OLLAMA_KV_CACHE_TYPE="q6_k",
            OLLAMA_FLASH_ATTENTION=False,
            LLM_KEEP_ALIVE="40m",
        )
    )
    assert resolved["profile"] == PROFILE_LOW_VRAM
    assert resolved["context_length"] == 24576
    assert resolved["num_parallel"] == 3
    assert resolved["max_queue"] == 222
    assert resolved["kv_cache_type"] == "q6_k"
    assert resolved["flash_attention"] is False
    assert resolved["keep_alive"] == "40m"


def test_build_ollama_runtime_options_maps_to_ollama_api_format():
    options = build_ollama_runtime_options(_settings())
    assert options["num_ctx"] == 32768
    assert options["num_parallel"] == 2
    assert options["num_queue"] == 256
    assert options["flash_attention"] is True
    assert options["kv_cache_type"] == "q8_0"
