import os

import pytest


def _read_env_keys(path: str) -> dict:
    data = {}
    if not os.path.isfile(path):
        return data
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def _env_contract_source_path() -> str:
    return os.getenv("ENV_CONTRACT_SOURCE", ".env.dev")


def _apply_env_overrides(values: dict) -> dict:
    out = dict(values)
    override_map = {
        "ACTIVE_LLM_SERVER": "ENV_CONTRACT_ACTIVE_LLM_SERVER",
        "LLM_LOCAL_ENDPOINT": "ENV_CONTRACT_LLM_LOCAL_ENDPOINT",
        "VLLM_ENDPOINT": "ENV_CONTRACT_VLLM_ENDPOINT",
        "GEMMA4_AUDIO_ENDPOINT": "ENV_CONTRACT_GEMMA4_AUDIO_ENDPOINT",
    }
    for key, env_name in override_map.items():
        value = os.getenv(env_name, "").strip()
        if value:
            out[key] = value
    return out


def _assert_profile_contract(dev: dict, profile: str) -> None:
    normalized = profile.strip().lower()
    if normalized == "ollama":
        endpoint = dev.get("LLM_LOCAL_ENDPOINT", "").strip()
        ollama_direct = endpoint.startswith("http://localhost:11434")
        ollama_via_multi_runtime = endpoint.startswith("http://localhost:8014")
        assert ollama_direct or ollama_via_multi_runtime, endpoint
        return
    if normalized == "vllm":
        endpoint = dev.get("VLLM_ENDPOINT", "").strip()
        assert endpoint.startswith("http://localhost:8001"), endpoint
        return
    if normalized in {"multi_runtime", "multi-runtime", "gemma4_audio"}:
        endpoint = dev.get("LLM_LOCAL_ENDPOINT", "").strip()
        gemma_endpoint = dev.get("GEMMA4_AUDIO_ENDPOINT", "").strip()
        assert endpoint.startswith("http://localhost:8014"), endpoint
        assert gemma_endpoint.startswith("http://localhost:8014"), gemma_endpoint
        return
    raise AssertionError(f"Unsupported runtime profile: {profile}")


def _normalize_runtime_profile(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def test_gemma4_keys_present_in_env_dev():
    example = _read_env_keys(".env.dev.example")
    dev = _apply_env_overrides(_read_env_keys(_env_contract_source_path()))

    gemma_keys = [k for k in example.keys() if k.startswith("GEMMA4_AUDIO_")]
    assert gemma_keys, "No GEMMA4_AUDIO_ keys found in .env.dev.example"

    missing = [k for k in gemma_keys if k not in dev]
    assert not missing, f"Missing GEMMA4_AUDIO keys in .env.dev: {missing}"


def test_active_local_runtime_matches_endpoint_contract():
    dev = _apply_env_overrides(_read_env_keys(_env_contract_source_path()))
    active = dev.get("ACTIVE_LLM_SERVER", "").strip().lower()
    if not active:
        pytest.skip("ACTIVE_LLM_SERVER not set in selected env contract source.")
    _assert_profile_contract(dev, active)


@pytest.mark.parametrize("profile", ["ollama", "vllm", "multi_runtime"])
def test_runtime_profile_endpoint_contracts(profile: str):
    dev = _apply_env_overrides(_read_env_keys(_env_contract_source_path()))
    selected_profile = _normalize_runtime_profile(os.getenv("ENV_CONTRACT_PROFILE", ""))
    normalized = _normalize_runtime_profile(profile)
    if selected_profile:
        if normalized != selected_profile:
            pytest.skip(f"Profile {normalized} not selected by ENV_CONTRACT_PROFILE.")
    else:
        active = _normalize_runtime_profile(dev.get("ACTIVE_LLM_SERVER", ""))
        if normalized != active:
            pytest.skip(
                f"Profile {normalized} is not active ({active or 'unset'}). "
                "Use make test-env-contracts-* target to validate explicitly."
            )
    _assert_profile_contract(dev, profile)
