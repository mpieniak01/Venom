from __future__ import annotations

from types import SimpleNamespace

import pytest

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
        "LLM_KEEP_ALIVE": "-1",
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
    assert resolved["keep_alive"] == "-1"


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


@pytest.mark.parametrize(
    "configured,expected",
    [("-1", -1), ("0", 0), ("120", 120), (-1, -1), ("5m", "5m"), ("-10m", "-10m")],
)
def test_keep_alive_numeric_seconds_are_json_numbers(configured, expected):
    from venom_core.utils.ollama_tuning import normalize_ollama_keep_alive

    actual = normalize_ollama_keep_alive(configured)
    assert actual == expected
    assert type(actual) is type(expected)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "forever",
        "5min",
        "1.5",
        "1h-2m",
        "1e3s",
        "NaN",
        "1d",
        True,
        None,
        1.5,
        "9" * 129,
        "2562047h47m16.854775808s",
        9223372037,
    ],
)
def test_keep_alive_rejects_invalid_or_overflowing_values_before_transport(value):
    from venom_core.utils.ollama_tuning import normalize_ollama_keep_alive

    with pytest.raises(ValueError):
        normalize_ollama_keep_alive(value)


@pytest.mark.parametrize(
    "value",
    [
        "1h30m",
        "-1.5h",
        ".5s",
        "1.s",
        "1us",
        "1µs",
        "1μs",
        "0.9ns0.9ns",
        "2562047h47m16.854775807s",
        "-2562047h47m16.854775808s",
    ],
)
def test_keep_alive_preserves_valid_go_duration_grammar(value):
    from venom_core.utils.ollama_tuning import normalize_ollama_keep_alive

    assert normalize_ollama_keep_alive(value) == value


@pytest.mark.parametrize("value", ["١٢s", "１２m", "١٢", "１.５s", "1s٢m"])
def test_keep_alive_rejects_non_ascii_digits(value):
    from venom_core.utils.ollama_tuning import normalize_ollama_keep_alive

    with pytest.raises(ValueError, match="invalid_ollama_keep_alive"):
        normalize_ollama_keep_alive(value)
