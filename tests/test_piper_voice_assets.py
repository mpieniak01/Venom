from pathlib import Path

import pytest


def test_darkman_piper_voice_asset_present():
    model_path = Path("data/models/piper/pl_PL-darkman-medium.onnx")
    config_path = Path("data/models/piper/pl_PL-darkman-medium.onnx.json")

    if not model_path.exists() or not config_path.exists():
        pytest.skip("Piper darkman voice asset is optional in clean checkouts.")

    assert model_path.exists()
    assert model_path.stat().st_size > 10 * 1024 * 1024
    assert config_path.exists()
