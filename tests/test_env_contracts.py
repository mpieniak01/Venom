import os


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


def test_gemma4_keys_present_in_env_dev():
    example = _read_env_keys(".env.dev.example")
    dev = _read_env_keys(".env.dev")

    gemma_keys = [k for k in example.keys() if k.startswith("GEMMA4_AUDIO_")]
    assert gemma_keys, "No GEMMA4_AUDIO_ keys found in .env.dev.example"

    missing = [k for k in gemma_keys if k not in dev]
    assert not missing, f"Missing GEMMA4_AUDIO keys in .env.dev: {missing}"
