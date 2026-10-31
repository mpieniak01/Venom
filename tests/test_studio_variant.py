"""Application selection must not create another data/queue namespace."""

from pathlib import Path

import pytest

from scripts.dev.stack_profile import public_plan, resolve


def settings(tmp_path: Path, variant: str, role: str = "dev"):
    (tmp_path / ".env.dev").write_text("ENVIRONMENT_ROLE=dev\n")
    (tmp_path / ".env.preprod").write_text("ENVIRONMENT_ROLE=preprod\n")
    return resolve(tmp_path, {"ENVIRONMENT": role, "VENOM_VARIANT": variant})


@pytest.mark.parametrize("role", ["dev", "preprod"])
def test_application_variant_shares_existing_environment_storage(tmp_path, role):
    full = settings(tmp_path, "venom", role)
    studio = settings(tmp_path, "studio", role)
    for key in [
        "MEMORY_ROOT",
        "STATE_FILE_PATH",
        "VENOM_RUNTIME_STATE_ROOT",
        "DB_SCHEMA",
        "CACHE_NAMESPACE",
        "QUEUE_NAMESPACE",
        "STORAGE_PREFIX",
        "PID_FILE",
        "WEB_PID_FILE",
    ]:
        assert studio[key] == full[key], key
    assert studio["WEB_DIR"] == str(tmp_path / "web-studio")
    assert studio["API_APP"] == "venom_core.studio_main:app"
    assert studio["VENOM_UI_READY_PATH"] == "/chat2"
    assert full["API_APP"] == "venom_core.main:app"
    assert full["NEXT_PUBLIC_FEATURE_CHAT2"] == "false"
    assert full["WEB_DIR"] == str(tmp_path / "web-next")
    assert public_plan(studio)["VENOM_VARIANT"] == "studio"


def test_invalid_application_variant_rejected(tmp_path):
    with pytest.raises(ValueError, match="VENOM_VARIANT"):
        settings(tmp_path, "other")


def test_studio_preserves_environment_separation(tmp_path):
    dev, preprod = settings(tmp_path, "studio"), settings(tmp_path, "studio", "preprod")
    for key in [
        "MEMORY_ROOT",
        "STATE_FILE_PATH",
        "DB_SCHEMA",
        "CACHE_NAMESPACE",
        "QUEUE_NAMESPACE",
        "PID_FILE",
        "WEB_PID_FILE",
    ]:
        assert dev[key] != preprod[key], key
