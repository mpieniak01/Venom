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


@pytest.mark.parametrize("action", ["start", "stop"])
@pytest.mark.parametrize("source", ["file", "process", "default"])
def test_effective_variant_always_controls_engine_snapshot(
    tmp_path, monkeypatch, action, source
):
    """File-only Studio selection must use the same engine guards as process overrides."""
    import sys
    from contextlib import nullcontext

    from scripts.dev import runtime_teardown as rt
    from scripts.dev import stack_profile as sp
    from scripts.dev import startup_rollback as rollback

    (tmp_path / ".env.dev").write_text(
        "ENVIRONMENT_ROLE=dev\n"
        + ("" if source == "default" else "VENOM_VARIANT=studio\n")
    )
    monkeypatch.chdir(Path.cwd())
    monkeypatch.setattr(sp, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["stack_profile", action])
    monkeypatch.setattr(sp, "preflight", lambda *_: None)
    monkeypatch.setattr(sp, "startup_lock", lambda *_: nullcontext())
    monkeypatch.setenv("ENV_FILE", str(tmp_path / ".env.dev"))
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.delenv("VENOM_VARIANT", raising=False)
    if source == "process":
        monkeypatch.setenv("VENOM_VARIANT", "venom")
    expected = "studio" if source == "file" else "venom"
    peers, snapshots, starts, stops = [], [], [], []
    monkeypatch.setattr(
        sp,
        "check_variant_peers",
        lambda root, values: peers.append(values["VENOM_VARIANT"]),
    )
    monkeypatch.setattr(
        rt,
        "engine_owners",
        lambda root, values: snapshots.append(values["VENOM_VARIANT"]) or [],
    )
    monkeypatch.setattr(sp, "stop", lambda *_: stops.append("application"))
    monkeypatch.setattr(rt, "stop_engines", lambda owners: stops.append(owners))
    monkeypatch.setattr(
        rollback,
        "run_start_stack",
        lambda root, values, engines: starts.append((values, engines)),
    )
    sp.main()
    assert peers == [expected]
    assert snapshots
    assert set(snapshots) == {expected}
    if action == "start":
        assert (
            starts[0][1] == []
        )  # An empty engine snapshot differs from unmanaged None.
        assert starts[0][0].get("API_APP", "venom_core.main:app") == (
            "venom_core.studio_main:app"
            if expected == "studio"
            else "venom_core.main:app"
        )
    else:
        assert stops == ["application", []]
