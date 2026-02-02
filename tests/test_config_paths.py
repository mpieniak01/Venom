from pathlib import Path

from venom_core.utils.config_paths import resolve_config_path


def test_resolve_config_path_defaults_to_config_dir() -> None:
    assert resolve_config_path("pricing.yaml") == Path("config") / "pricing.yaml"


def test_resolve_config_path_respects_prefer_dir() -> None:
    assert (
        resolve_config_path("file.txt", prefer_dir="custom")
        == Path("custom") / "file.txt"
    )
