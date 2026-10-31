"""Isolation and provider preservation for the canonical stack entry point."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.dev import stack_profile as stack


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".env.dev").write_text(
        "ENVIRONMENT_ROLE=dev\nACTIVE_LLM_SERVER=ollama\nLLM_MODEL_NAME=operator-model\n"
    )
    (tmp_path / ".env.preprod").write_text("ENVIRONMENT_ROLE=preprod\n")
    return tmp_path


@pytest.mark.parametrize("profile", ["full", "light"])
@pytest.mark.parametrize("role", ["dev", "preprod"])
def test_four_combinations_isolate_without_switching_model(root, profile, role):
    config = stack.resolve(root, {"PROFILE": profile, "ENVIRONMENT": role})
    assert config["PROFILE"] == profile
    assert config["VENOM_RUNTIME_PROFILE"] == profile
    assert config["START_WEB_MODE"] == "turbo"
    assert config["ENVIRONMENT_ROLE"] == role
    assert config["DB_SCHEMA"] == role
    if role == "dev":
        assert config["ACTIVE_LLM_SERVER"] == "ollama"
        assert config["LLM_MODEL_NAME"] == "operator-model"
    else:
        dev = stack.resolve(root, {})
        for key in (
            "MEMORY_ROOT",
            "STATE_FILE_PATH",
            "VENOM_LOG_DIR",
            "BACKEND_LOG",
            "WEB_LOG",
            "PID_FILE",
            "WEB_PID_FILE",
            "PORT",
            "WEB_PORT",
            "NEXT_DIST_DIR",
        ):
            assert config[key] != dev[key]
        assert config["ALLOW_DATA_MUTATION"] == "false"


def test_light_keeps_local_provider_and_audio_configuration(root):
    path = root / ".env.dev"
    path.write_text(
        path.read_text()
        + "ENABLE_AUDIO_INTERFACE=true\nAUDIO_DEVICE=cuda\nWHISPER_MODEL_SIZE=medium\n"
    )
    config = stack.resolve(root, {"PROFILE": "light"})
    assert config["ACTIVE_LLM_SERVER"] == "ollama"
    assert config["AUDIO_DEVICE"] == "cuda"
    assert config["WHISPER_MODEL_SIZE"] == "medium"
    assert config["VENOM_PAUSE_BACKGROUND_TASKS"] == "true"
    assert config["LLM_WARMUP_ON_STARTUP"] == "false"


@pytest.mark.parametrize(
    "key,value",
    [
        ("MEMORY_ROOT", "data/memory"),
        ("STATE_FILE_PATH", "data/memory/state_dump.json"),
        ("VENOM_LOG_DIR", "logs"),
        ("BACKEND_LOG", "logs/backend.log"),
        ("PID_FILE", ".venom.pid"),
        ("NEXT_DIST_DIR", ".next"),
        ("CACHE_NAMESPACE", "venom"),
        ("QUEUE_NAMESPACE", "venom"),
        ("DB_SCHEMA", "dev"),
        ("PORT", "8000"),
        ("WEB_PORT", "3000"),
        ("STORAGE_PREFIX", ""),
    ],
)
def test_preprod_rejects_resources_shared_with_dev(root, key, value):
    with pytest.raises(ValueError, match="overlaps|isolated"):
        stack.resolve(root, {"ENVIRONMENT": "preprod", key: value})


def test_preprod_rejects_symlink_to_dev_database(root):
    (root / "data/memory").mkdir(parents=True)
    (root / "other").symlink_to(root / "data/memory")
    with pytest.raises(ValueError, match="MEMORY_ROOT"):
        stack.resolve(root, {"ENVIRONMENT": "preprod", "MEMORY_ROOT": "other"})


@pytest.mark.parametrize(
    "extra",
    [
        {"ENVIRONMENT": "bad"},
        {"PROFILE": "unknown"},
        {"ENVIRONMENT": "preprod", "ENV_FILE": ".env.dev"},
        {"PORT": "3000"},
        {"ENVIRONMENT": "preprod", "START_MODE": "prod"},
    ],
)
def test_invalid_contract_is_rejected_before_start(root, extra):
    with pytest.raises(ValueError):
        stack.resolve(root, extra)


def test_missing_and_reserved_environment_do_not_start(root):
    with pytest.raises(ValueError, match="Missing configuration"):
        stack.resolve(root, {"ENVIRONMENT": "prod"})
    (root / ".env.prod").write_text("")
    with pytest.raises(ValueError, match="reserved"):
        stack.resolve(root, {"ENVIRONMENT": "prod"})
    config = stack.resolve(root, {"ENVIRONMENT": "prod", "PROD_START_CONFIRM": "yes"})
    assert config["START_MODE"] == "prod"


def test_full_preserves_custom_paths_and_secrets_are_not_printed(root):
    config = stack.resolve(
        root,
        {
            "OPENROUTER_API_KEY": "private",
            "MEMORY_ROOT": "custom",
            "PORT": "8800",
            "WEB_PORT": "3300",
        },
    )
    assert config["MEMORY_ROOT"] == str(root / "custom")
    assert config["PORT"] == "8800"
    assert "private" not in str(stack.public_plan(config))


def test_profile_switch_does_not_create_another_database(root):
    for role in ("dev", "preprod"):
        full = stack.resolve(root, {"ENVIRONMENT": role, "PROFILE": "full"})
        light = stack.resolve(root, {"ENVIRONMENT": role, "PROFILE": "light"})
        for key in stack.PATH_DEFAULTS:
            assert full[key] == light[key]


def test_no_profile_can_disable_preprod_readonly(root):
    config = stack.resolve(
        root, {"ENVIRONMENT": "preprod", "ALLOW_DATA_MUTATION": "true"}
    )
    assert config["ALLOW_DATA_MUTATION"] == "false"


def test_stop_validates_all_owners_before_signalling(root, monkeypatch):
    config = stack.resolve(root, {})
    owner = Mock(side_effect=[123, ValueError("other environment")])
    monkeypatch.setattr(stack, "owned_pid", owner)
    kill = Mock()
    monkeypatch.setattr(os, "kill", kill)
    with pytest.raises(ValueError, match="other environment"):
        stack.stop(root, config)
    kill.assert_not_called()


def test_stale_pid_file_has_no_live_owner(root):
    config = stack.resolve(root, {})
    Path(config["PID_FILE"]).write_text("99999999")
    assert stack.owned_pid(root, config, "PID_FILE") is None
    stack.stop(root, config)
    assert not Path(config["PID_FILE"]).exists()


"""Additional lifecycle ownership regression tests use only local child processes."""


def test_unverified_same_directory_pid_is_never_killed(root):
    config = stack.resolve(root, {})
    Path(config["PID_FILE"]).write_text(str(os.getpid()))
    with pytest.raises(ValueError, match="Cannot verify"):
        stack.owned_pid(root, config, "PID_FILE")


def test_identity_rejects_reused_pid_and_wrong_environment(root):
    import json

    config = stack.resolve(root, {})
    Path(config["PID_FILE"]).write_text(str(os.getpid()))
    stack.record_pid(root, config, "PID_FILE")
    assert stack.owned_pid(root, config, "PID_FILE") == os.getpid()
    for changed in ({"ENVIRONMENT": "preprod"}, {"PROFILE": "light"}):
        with pytest.raises(ValueError, match="identity|Different profile"):
            stack.owned_pid(root, {**config, **changed}, "PID_FILE", reuse=True)
    path = Path(config["PID_FILE"] + ".identity.json")
    record = json.loads(path.read_text())
    record["stamp"] = "0"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="identity"):
        stack.owned_pid(root, config, "PID_FILE")


def test_stop_drains_grandchildren_without_touching_foreign_process(root):
    import subprocess
    import sys
    import time

    config = stack.resolve(root, {})
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess,time; subprocess.Popen(['sleep','60']); time.sleep(60)",
        ]
    )
    foreign = subprocess.Popen(["sleep", "60"])
    try:
        Path(config["PID_FILE"]).write_text(str(child.pid))
        stack.record_pid(root, config, "PID_FILE")
        for _ in range(100):
            tree = stack.descendants(child.pid)
            if tree:
                break
            time.sleep(0.01)
        assert tree
        stack.stop(root, config, ("PID_FILE",))
        child.wait(timeout=2)
        assert not any(stack.running(pid) for pid in tree)
        assert foreign.poll() is None
    finally:
        if child.poll() is None:
            child.terminate()
        foreign.terminate()
        child.wait()
        foreign.wait()


def test_preprod_ui_cannot_proxy_to_dev(root):
    with pytest.raises(ValueError, match="API_PROXY_TARGET"):
        stack.resolve(
            root,
            {"ENVIRONMENT": "preprod", "API_PROXY_TARGET": "http://127.0.0.1:8000"},
        )


def test_preprod_overrides_legacy_browser_bypass_urls(root):
    config = stack.resolve(
        root,
        {"ENVIRONMENT": "preprod", "NEXT_PUBLIC_API_BASE": "http://localhost:8000"},
    )
    assert config["NEXT_PUBLIC_API_BASE"] == ""
    assert config["NEXT_PUBLIC_WS_BASE"] == ""


@pytest.mark.parametrize("role", ["dev", "preprod"])
@pytest.mark.parametrize("profile", ["full", "light"])
def test_make_api_resolves_environment_before_loading_dotenv(
    root, monkeypatch, role, profile
):
    import json
    import socket
    import subprocess
    import sys

    repo = stack.ROOT
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    fake = root / "uvicorn"
    fake.write_text(
        f"#!{sys.executable}\n"
        + """import http.server,json,os,sys
from pathlib import Path
Path(os.environ["CAPTURE"]).write_text(json.dumps({k:os.environ.get(k) for k in (
"ENVIRONMENT_ROLE","VENOM_RUNTIME_PROFILE","VENOM_PAUSE_BACKGROUND_TASKS",
"ALLOW_DATA_MUTATION","MEMORY_ROOT","VENOM_LOG_DIR")}))
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.end_headers();self.wfile.write(b'{}')
    def log_message(self,*args): pass
http.server.HTTPServer(('127.0.0.1',int(sys.argv[sys.argv.index('--port')+1])),Handler).serve_forever()
"""
    )
    fake.chmod(0o700)
    capture = root / "capture.json"
    pid = root / "api.pid"
    env_file = root / f".env.{role}"
    env_file.write_text(env_file.read_text() + "VENOM_PAUSE_BACKGROUND_TASKS=false\n")
    child_env = dict(os.environ)
    for key in (*stack.public_plan(stack.resolve(root, {})), "API_PROXY_TARGET"):
        child_env.pop(key, None)
    command = [
        "make",
        "--no-print-directory",
        f"ENVIRONMENT={role}",
        f"PROFILE={profile}",
        f"ENV_FILE={env_file}",
        f"PORT={port}",
        f"WEB_PORT={port + 1}",
        f"UVICORN={fake}",
        f"PID_FILE={pid}",
        f"BACKEND_LOG={root}/logs/api.log",
        f"CAPTURE={capture}",
    ]
    try:
        result = subprocess.run(
            [*command, "api"],
            cwd=repo,
            env=child_env,
            check=False,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr.decode()
        import time

        time.sleep(0.3)  # Launcher has exited; the recorded API owner must persist.
        owner = int(pid.read_text())
        assert stack.running(owner)
        identity_path = Path(str(pid) + ".identity.json")
        before_identity = identity_path.read_bytes()
        assert json.loads(before_identity)["pid"] == owner
        before_capture = capture.stat().st_mtime_ns
        repeated = subprocess.run(
            [*command, "api"],
            cwd=repo,
            env=child_env,
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert repeated.returncode == 0, repeated.stderr.decode()
        assert int(pid.read_text()) == owner
        assert identity_path.read_bytes() == before_identity
        assert capture.stat().st_mtime_ns == before_capture
        assert stack.running(owner)
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
            assert response.status == 200
        data = json.loads(capture.read_text())
        assert data["ENVIRONMENT_ROLE"] == role
        assert data["VENOM_RUNTIME_PROFILE"] == profile
        assert data["VENOM_PAUSE_BACKGROUND_TASKS"] == (
            "true" if profile == "light" else "false"
        )
        assert data["VENOM_LOG_DIR"].endswith(
            "logs/preprod" if role == "preprod" else "logs"
        )
        if role == "preprod":
            assert data["ALLOW_DATA_MUTATION"] == "false"
    finally:
        subprocess.run(
            [*command, "api-stop"],
            cwd=repo,
            env=child_env,
            check=pid.exists(),
            capture_output=True,
            timeout=30,
        )
    assert not pid.exists()


def test_preflight_foreign_listener_is_preserved(root):
    import socket

    config = stack.resolve(root, {})
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        config["PORT"] = str(listener.getsockname()[1])
        with pytest.raises(ValueError, match="unowned"):
            stack.preflight(root, config)
        assert listener.fileno() >= 0


def test_shared_runtime_guard_rejects_second_engine(root):
    config = stack.resolve(root, {})
    Path(config["PID_FILE"]).write_text(str(os.getpid()))
    stack.record_pid(
        root, {**config, "VENOM_STARTED_LOCAL_RUNTIME": "ollama"}, "PID_FILE"
    )
    with pytest.raises(ValueError, match="different local runtime"):
        stack.check_shared_runtime(
            root, {**config, "VENOM_STARTED_LOCAL_RUNTIME": "multi_runtime"}
        )
    stack.check_shared_runtime(root, {**config, "VENOM_STARTED_LOCAL_RUNTIME": "none"})


def test_concurrent_starts_are_serialized_before_api_record(root):
    import subprocess
    import sys
    import time

    marker = root / "locked"
    release = root / "release"
    code = """import sys,time
from pathlib import Path
from scripts.dev.stack_profile import startup_lock
root=Path(sys.argv[1])
with startup_lock(root):
    (root/'locked').touch()
    while not (root/'release').exists(): time.sleep(0.01)
"""
    child = subprocess.Popen([sys.executable, "-c", code, str(root)], cwd=stack.ROOT)
    try:
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.02)
        assert marker.exists()
        contender = stack.startup_lock(root)
        with pytest.raises(ValueError, match="startup is in progress"):
            contender.__enter__()
    finally:
        release.touch()
        child.wait(timeout=5)
    with stack.startup_lock(root):
        pass


@pytest.mark.parametrize(
    "target",
    ["http://localhost:8000", "http://LOCALHOST:8000/", "http://127.0.0.1:8000"],
)
def test_loopback_proxy_alias_preserves_own_listener(root, target):
    config = stack.resolve(root, {"PORT": "8000", "API_PROXY_TARGET": target})
    assert config["API_PROXY_TARGET"] == "http://127.0.0.1:8000"


@pytest.mark.parametrize(
    "target",
    [
        "http://other.example:8000",
        "http://localhost:8001",
        "https://localhost:8000",
        "http://user:pass@localhost:8000",
        "http://localhost:8000/api",
        "http://localhost:8000?target=dev",
        "http://localhost:8000#dev",
        "http://localhost:8000/ ",
        "http://127.0.0.1:8000@other.example",
    ],
)
def test_proxy_alias_normalization_never_accepts_foreign_or_credentialed_target(
    root, target
):
    with pytest.raises(ValueError, match="API_PROXY_TARGET"):
        stack.resolve(root, {"PORT": "8000", "API_PROXY_TARGET": target})


def test_preprod_only_configuration_uses_safe_dev_defaults_for_comparison(root):
    (root / ".env.dev").unlink()
    result = stack.resolve(root, {"ENVIRONMENT": "preprod"})
    assert result["ENV_FILE"] == str(root / ".env.preprod")
    assert result["DB_SCHEMA"] == "preprod"
    assert result["MEMORY_ROOT"] == str(root / "data/memory/preprod")
    with pytest.raises(ValueError, match="MEMORY_ROOT overlaps"):
        stack.resolve(root, {"ENVIRONMENT": "preprod", "MEMORY_ROOT": "data/memory"})
    assert not (root / ".env.dev").exists()


def test_web_build_can_use_example_but_actual_start_requires_config(root):
    (root / ".env.dev").unlink()
    example = root / ".env.dev.example"
    example.write_text("ENVIRONMENT_ROLE=dev\n")
    build = stack.resolve(root, {}, allow_example=True)
    assert build["ENV_FILE"] == str(example)
    with pytest.raises(ValueError, match="Missing configuration"):
        stack.resolve(root, {})
    with pytest.raises(ValueError, match="Missing configuration"):
        stack.resolve(root, {"ENV_FILE": ".env.typo"}, allow_example=True)
    assert not (root / ".env.dev").exists()


def test_importing_stack_contract_does_not_require_python_site_packages(tmp_path):
    import subprocess
    import sys

    code = (
        "from pathlib import Path; from scripts.dev.stack_profile import resolve; "
        f"assert resolve(Path({str(tmp_path)!r}), {{'ENVIRONMENT':'dev'}}, require_env_file=False)['PROFILE']=='full'"
    )
    result = subprocess.run(
        [sys.executable, "-S", "-c", code],
        cwd=stack.ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", ["start_stack.sh", "start_stack_low_memory.sh"])
@pytest.mark.parametrize("selection", ["fallback", "venv", "explicit"])
def test_direct_shell_delegation_selects_usable_interpreter(
    tmp_path, script, selection
):
    import shutil
    import subprocess

    for relative in (f"scripts/dev/{script}", "scripts/lib/python_contract.sh"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stack.ROOT / relative, target)
    if script == "start_stack.sh":
        shutil.copyfile(
            stack.ROOT / "scripts/lib/env_contract.sh",
            tmp_path / "scripts/lib/env_contract.sh",
        )
    binaries = tmp_path / "bin"
    binaries.mkdir()
    capture = tmp_path / "capture.txt"
    fallback = binaries / "python3"
    fake = '#!/bin/sh\nprintf "%s\\n" "$0" "$@" > "$CAPTURE"\n'
    fallback.write_text(fake)
    fallback.chmod(0o700)
    env = dict(os.environ, PATH=f"{binaries}:/usr/bin:/bin", CAPTURE=str(capture))
    env.pop("PYTHON_BIN", None)
    env.pop("VENOM_STACK_RESOLVED", None)
    expected = fallback
    if selection != "fallback":
        expected = tmp_path / (
            ".venv/bin/python" if selection == "venv" else "chosen-python"
        )
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(fake)
        expected.chmod(0o700)
        if selection == "explicit":
            env["PYTHON_BIN"] = str(expected)
    result = subprocess.run(
        ["bash", str(tmp_path / "scripts/dev" / script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert capture.read_text().splitlines() == [
        str(expected),
        str(tmp_path / "scripts/dev/stack_profile.py"),
        "start",
    ]


def test_proxy_port_zero_is_rejected_before_start(root):
    with pytest.raises(ValueError, match="API_PROXY_TARGET port"):
        stack.resolve(root, {"PORT": "0"})


@pytest.fixture
def stop_receipts(root, monkeypatch):
    import json

    from scripts.dev import qualification_process, runtime_teardown

    config = stack.resolve(root, {})
    pid_path = Path(config["PID_FILE"])
    receipt = Path(str(pid_path) + ".identity.json")
    pid_path.write_text("1234\n")
    receipt.write_text(json.dumps({"pid": 1234, "stamp": "original"}))
    monkeypatch.setattr(stack, "owned_pid", lambda *_args: 1234)
    monkeypatch.setattr(
        qualification_process, "identity", lambda _pid: {"start_ticks": "original"}
    )
    retire = Mock()
    monkeypatch.setattr(runtime_teardown, "stop_engines", retire)
    return config, pid_path, receipt, retire


@pytest.mark.parametrize("replace_key", ["pid", "identity"])
def test_stop_preserves_receipt_replaced_while_original_api_retires(
    root, stop_receipts, replace_key
):
    config, pid_path, receipt, retire = stop_receipts
    changed = pid_path if replace_key == "pid" else receipt
    payload = b"5678\n" if replace_key == "pid" else b'{"pid":5678,"stamp":"successor"}'
    retire.side_effect = lambda _owners: changed.write_bytes(payload)
    with pytest.raises(ValueError, match="receipt changed"):
        stack.stop(root, config, ("PID_FILE",))
    assert changed.read_bytes() == payload
    assert pid_path.exists()
    assert receipt.exists()
    retire.assert_called_once()


@pytest.mark.parametrize("replace_key", ["pid", "identity"])
def test_stop_detects_byte_identical_atomic_receipt_replacement(
    root, stop_receipts, replace_key
):
    config, pid_path, receipt, retire = stop_receipts
    changed = pid_path if replace_key == "pid" else receipt
    original = changed.read_bytes()
    inode = changed.stat().st_ino

    def replace(_owners):
        temporary = changed.with_name(changed.name + ".replacement")
        temporary.write_bytes(original)
        temporary.replace(changed)

    retire.side_effect = replace
    with pytest.raises(ValueError, match="receipt changed"):
        stack.stop(root, config, ("PID_FILE",))
    assert changed.read_bytes() == original
    assert changed.stat().st_ino != inode
    assert pid_path.exists()
    assert receipt.exists()


def test_stale_stop_preserves_records_created_during_owner_check(
    root, stop_receipts, monkeypatch
):
    config, pid_path, receipt, retire = stop_receipts
    pid_path.write_text("99999999\n")

    def stale_owner(*_args):
        pid_path.write_text("5678\n")
        receipt.write_text('{"pid":5678,"stamp":"successor"}')
        return None

    monkeypatch.setattr(stack, "owned_pid", stale_owner)
    with pytest.raises(ValueError, match="receipt changed"):
        stack.stop(root, config, ("PID_FILE",))
    assert pid_path.read_text() == "5678\n"
    assert "successor" in receipt.read_text()
    retire.assert_not_called()


def test_stop_rechecks_snapshot_after_process_identity_probe(
    root, stop_receipts, monkeypatch
):
    from scripts.dev import qualification_process

    config, pid_path, receipt, retire = stop_receipts

    def observed(_pid):
        receipt.write_text('{"pid":5678,"stamp":"successor"}')
        return {"start_ticks": "original"}

    monkeypatch.setattr(qualification_process, "identity", observed)
    with pytest.raises(ValueError, match="receipt changed"):
        stack.stop(root, config, ("PID_FILE",))
    assert pid_path.exists()
    assert "successor" in receipt.read_text()
    retire.assert_not_called()


def test_stop_rechecks_remaining_receipt_before_unlink(
    root, stop_receipts, monkeypatch
):
    config, pid_path, receipt, _retire = stop_receipts
    original_unlink = Path.unlink

    def after_pid_unlink(path, *args, **kwargs):
        result = original_unlink(path, *args, **kwargs)
        if path == pid_path:
            receipt.write_text('{"pid":5678,"stamp":"successor"}')
        return result

    monkeypatch.setattr(Path, "unlink", after_pid_unlink)
    with pytest.raises(ValueError, match="receipt changed"):
        stack.stop(root, config, ("PID_FILE",))
    assert "successor" in receipt.read_text()


def test_stop_removes_unchanged_retired_receipt_pair(root, stop_receipts):
    config, pid_path, receipt, retire = stop_receipts
    stack.stop(root, config, ("PID_FILE",), expected={"PID_FILE": (1234, "original")})
    assert not pid_path.exists()
    assert not receipt.exists()
    retire.assert_called_once()


@pytest.mark.parametrize("expected", [(5678, "original"), (1234, "other-start")])
def test_stop_rejects_different_expected_owner_before_signalling(
    root, stop_receipts, expected
):
    config, pid_path, receipt, retire = stop_receipts
    before = (pid_path.read_bytes(), receipt.read_bytes())
    with pytest.raises(ValueError, match="Expected stop owner changed"):
        stack.stop(root, config, ("PID_FILE",), expected={"PID_FILE": expected})
    assert (pid_path.read_bytes(), receipt.read_bytes()) == before
    retire.assert_not_called()


def test_stop_expected_owner_requires_original_receipt_pair(
    root, stop_receipts, monkeypatch
):
    config, pid_path, receipt, retire = stop_receipts
    receipt.unlink()
    monkeypatch.setattr(stack, "owned_pid", lambda *_args: None)
    with pytest.raises(
        ValueError, match="Expected stop owner has no captured receipts"
    ):
        stack.stop(
            root, config, ("PID_FILE",), expected={"PID_FILE": (1234, "original")}
        )
    assert pid_path.exists()
    assert not receipt.exists()
    retire.assert_not_called()


def test_stop_rejects_symlink_receipt_before_owner_probe(
    root, stop_receipts, monkeypatch
):
    config, pid_path, receipt, retire = stop_receipts
    target = receipt.with_name("foreign-receipt")
    receipt.rename(target)
    receipt.symlink_to(target)
    owner = Mock()
    monkeypatch.setattr(stack, "owned_pid", owner)
    with pytest.raises(ValueError, match="Cannot verify stop receipt"):
        stack.stop(root, config, ("PID_FILE",))
    assert pid_path.exists()
    assert target.exists()
    assert receipt.is_symlink()
    owner.assert_not_called()
    retire.assert_not_called()


def test_stale_expected_owner_rejects_mismatched_identity_pid(
    root, stop_receipts, monkeypatch
):
    config, pid_path, receipt, retire = stop_receipts
    receipt.write_text('{"pid":5678,"stamp":"original"}')
    monkeypatch.setattr(stack, "owned_pid", lambda *_args: None)
    with pytest.raises(ValueError, match="Expected stop owner changed"):
        stack.stop(
            root, config, ("PID_FILE",), expected={"PID_FILE": (1234, "original")}
        )
    assert pid_path.exists()
    assert "5678" in receipt.read_text()
    retire.assert_not_called()
