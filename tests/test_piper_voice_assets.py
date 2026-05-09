from pathlib import Path


def test_darkman_piper_voice_asset_present():
    model_path = Path("data/models/piper/pl_PL-darkman-medium.onnx")
    config_path = Path("data/models/piper/pl_PL-darkman-medium.onnx.json")

    assert model_path.exists()
    assert model_path.stat().st_size > 10 * 1024 * 1024
    assert config_path.exists()
