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
    assert config["PROFILE"] == config["VENOM_RUNTIME_PROFILE"] == profile
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
