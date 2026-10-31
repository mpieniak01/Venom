from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_env_contract(
    script: Path, snippet: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", "-lc", f'set -euo pipefail\nsource "{script}"\n{snippet}\n'],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_env_contract_get_precedence(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "lib" / "env_contract.sh"
    env_file = tmp_path / ".env.dev"
    env_file.write_text("TEST_KEY=file-value\n", encoding="utf-8")

    from_env = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_get TEST_KEY default-value "{env_file}")"',
        {"TEST_KEY": "env-value"},
    )
    assert from_env.returncode == 0, from_env.stderr
    assert from_env.stdout == "env-value"

    from_file = _run_env_contract(
        script,
        f'unset TEST_KEY\nprintf "%s" "$(env_contract_get TEST_KEY default-value "{env_file}")"',
    )
    assert from_file.returncode == 0, from_file.stderr
    assert from_file.stdout == "file-value"

    from_default = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_get MISSING_KEY default-value "{env_file}")"',
    )
    assert from_default.returncode == 0, from_default.stderr
    assert from_default.stdout == "default-value"

    from_env_empty = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_get TEST_KEY default-value "{env_file}")"',
        {"TEST_KEY": ""},
    )
    assert from_env_empty.returncode == 0, from_env_empty.stderr
    assert from_env_empty.stdout == ""


def test_env_contract_origin_reports_source(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "lib" / "env_contract.sh"
    env_file = tmp_path / ".env.dev"
    env_file.write_text("ORIGIN_KEY=file-source\n", encoding="utf-8")

    from_env = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_origin ORIGIN_KEY "{env_file}" "fallback")"',
        {"ORIGIN_KEY": "env-source"},
    )
    assert from_env.returncode == 0, from_env.stderr
    assert from_env.stdout == "env"

    from_file = _run_env_contract(
        script,
        f'unset ORIGIN_KEY\nprintf "%s" "$(env_contract_origin ORIGIN_KEY "{env_file}" "fallback")"',
    )
    assert from_file.returncode == 0, from_file.stderr
    assert from_file.stdout == "file"

    from_default = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_origin MISSING_ORIGIN "{env_file}" "fallback")"',
    )
    assert from_default.returncode == 0, from_default.stderr
    assert from_default.stdout == "default"

    from_env_empty = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_origin ORIGIN_KEY "{env_file}" "fallback")"',
        {"ORIGIN_KEY": ""},
    )
    assert from_env_empty.returncode == 0, from_env_empty.stderr
    assert from_env_empty.stdout == "env"


def test_env_contract_resolve_file_paths(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "lib" / "env_contract.sh"
    root_dir = tmp_path / "repo"
    root_dir.mkdir(parents=True)

    resolved = _run_env_contract(
        script,
        f'echo "$(env_contract_resolve_file ".env.dev" "{root_dir}")"\n'
        f'echo "$(env_contract_resolve_file "/tmp/absolute.env" "{root_dir}")"',
    )
    assert resolved.returncode == 0, resolved.stderr
    lines = resolved.stdout.strip().splitlines()
    assert lines[0] == f"{root_dir}/.env.dev"
    assert lines[1] == "/tmp/absolute.env"


def test_env_runner_preserves_command_values_without_shell_execution(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    marker = tmp_path / "must-not-exist"
    environment_file = tmp_path / "fixture.env"
    literal = f"$(touch {marker})"
    environment_file.write_text(
        f"COMMAND={literal}\nLIFECYCLE=python -m fixture --flag value\n"
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; env_contract_run "$2" "$3" "$2" -c \'import os,json;print(json.dumps([os.environ["COMMAND"],os.environ["LIFECYCLE"]]))\'',
            "fixture",
            str(root / "scripts/lib/env_contract.sh"),
            sys.executable,
            str(environment_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [literal, "python -m fixture --flag value"]
    assert not marker.exists()


def test_env_runner_never_falls_back_to_source_when_python_fails(tmp_path):
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    marker = tmp_path / "must-not-exist"
    environment_file = tmp_path / "fixture.env"
    environment_file.write_text(f"touch {marker}\n")
    unavailable = tmp_path / "unavailable-python"
    unavailable.write_text("#!/bin/sh\nexit 13\n")
    unavailable.chmod(0o700)
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; env_contract_run "$2" "$3" echo forbidden',
            "fixture",
            str(root / "scripts/lib/env_contract.sh"),
            str(unavailable),
            str(environment_file),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 13
    assert not marker.exists()


def test_default_stack_uses_turbo_with_explicit_webpack_escape_hatch(tmp_path):
    """Execute Make's real target/variable resolution without starting services."""
    root = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "make-fixture.mk"
    fixture.write_text(
        "ensure-env-file:\n\t@true\n"
        "_start:\n\t@printf 'mode=%s\\n' '$(START_WEB_MODE)'\n"
    )
    environment = os.environ.copy()
    environment.pop("START_WEB_MODE", None)
    expected_modes = {
        "start": "turbo",
        "start-dev": "turbo",
        "start-dev-turbo": "turbo",
        "start-dev-webpack": "webpack",
    }
    for target, expected in expected_modes.items():
        result = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-f",
                "Makefile",
                "-f",
                str(fixture),
                "WEB_APP_VERSION=fixture",
                target,
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f"mode={expected}", target


@pytest.fixture
def ollama_shell(tmp_path):
    """Exercise the real shell in a copied checkout with no real unit or daemon."""
    import shutil
    import signal

    source = Path(__file__).resolve().parents[1]
    root = tmp_path / "fixture checkout"
    (root / "scripts/llm").mkdir(parents=True)
    (root / "scripts/lib").mkdir()
    shutil.copy2(
        source / "scripts/llm/ollama_service.sh", root / "scripts/llm/ollama_service.sh"
    )
    shutil.copy2(
        source / "scripts/lib/env_contract.sh", root / "scripts/lib/env_contract.sh"
    )
    (root / "fixture.env").write_text("OLLAMA_BASE_URL=http://fixture.invalid:11434\n")
    commands = tmp_path / "commands"
    commands.mkdir()
    calls = tmp_path / "calls.log"
    child = tmp_path / "fake-child.pid"

    def executable(name, body):
        target = commands / name
        target.write_text("#!/bin/sh\nset -eu\n" + body)
        target.chmod(0o700)
        return target

    python = executable(
        "python3",
        """
# Token generation uses only the real interpreter's stdlib; runtime control stays fake.
if [ "$1" = "-c" ]; then exec "$FAKE_REAL_PYTHON" "$@"; fi
printf 'python|%s|%s|%s\n' "$PWD" "$ENV_FILE" "$*" >>"$FAKE_CALLS"
case "$3" in
  verify-ollama) exit "${FAKE_VERIFY_EXIT:-0}" ;;
  claim-ollama) printf 'claimed\n' >"$FAKE_ROOT/logs/ollama.pid.identity.json"; exit "${FAKE_CLAIM_EXIT:-0}" ;;
  stop-ollama) exit "${FAKE_STOP_EXIT:-0}" ;;
  *) exit 92 ;;
esac
""",
    )
    executable(
        "systemctl",
        """
printf 'systemctl|%s\n' "$*" >>"$FAKE_CALLS"
exit "${FAKE_SYSTEMCTL_EXIT:-0}"
""",
    )
    executable(
        "curl",
        """
printf 'curl|%s\n' "$*" >>"$FAKE_CALLS"
exit "${FAKE_HEALTH_EXIT:-1}"
""",
    )
    executable(
        "ollama",
        """
printf '%s\n' "$$" >"$FAKE_CHILD_PID"
exec /bin/sleep 30
""",
    )
    executable(
        "readlink",
        """
case "$2" in
  /proc/*/exe)
    count=0
    if [ -f "$FAKE_ROOT/exec-polls" ]; then count=$(cat "$FAKE_ROOT/exec-polls"); fi
    count=$((count+1)); printf '%s\n' "$count" >"$FAKE_ROOT/exec-polls"
    if [ "$count" -lt "${FAKE_READY_AFTER:-3}" ]; then printf '/usr/bin/nohup\n'; else printf '%s/ollama\n' "$FAKE_BIN"; fi
    ;;
  *) /usr/bin/readlink "$@" ;;
esac
""",
    )
    for name in ("pgrep", "pkill", "killall"):
        executable(name, 'printf "forbidden|%s\n" "$0" >>"$FAKE_CALLS"; exit 93\n')
    env = {
        "PATH": str(commands) + ":/usr/bin:/bin",
        "HOME": str(tmp_path),
        "ENV_FILE": "fixture.env",
        "PYTHON_BIN": str(python),
        "FAKE_CALLS": str(calls),
        "FAKE_ROOT": str(root),
        "FAKE_CHILD_PID": str(child),
        "FAKE_BIN": str(commands),
        "FAKE_REAL_PYTHON": sys.executable,
    }

    def run(action, changes=None):
        child_env = {**env, **(changes or {})}
        return subprocess.run(
            ["bash", str(root / "scripts/llm/ollama_service.sh"), action],
            cwd=tmp_path,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    try:
        yield root, calls, env, run
    finally:
        # Only the fake child written by our own executable is eligible for cleanup.
        if child.exists():
            pid = int(child.read_text())
            command = Path(f"/proc/{pid}/cmdline")
            if command.exists() and b"/bin/sleep" in command.read_bytes():
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass


@pytest.mark.parametrize("failure", [0, 31])
def test_ollama_healthy_runtime_is_verified_never_adopted(ollama_shell, failure):
    root, calls, _, run = ollama_shell
    result = run("start", {"FAKE_HEALTH_EXIT": "0", "FAKE_VERIFY_EXIT": str(failure)})
    assert result.returncode == failure
    records = calls.read_text().splitlines()
    assert len(records) == 2
    assert records[0].startswith("curl|")
    assert (
        records[1]
        == f"python|{root}|{root / 'fixture.env'}|-m scripts.dev.runtime_teardown verify-ollama"
    )
    assert not (root / "logs/ollama.pid").exists()


@pytest.mark.parametrize("scope,prefix", [("user", "--user "), ("system", "")])
def test_ollama_starts_only_explicit_systemd_unit(ollama_shell, scope, prefix):
    root, calls, _, run = ollama_shell
    (root / "fixture.env").write_text(
        f"OLLAMA_SYSTEMD_UNIT=fixture-ollama.service\nOLLAMA_SYSTEMD_SCOPE={scope}\n"
    )
    result = run("start")
    assert result.returncode == 0, result.stderr
    records = calls.read_text().splitlines()
    assert records[1] == f"systemctl|{prefix}start -- fixture-ollama.service"
    assert records[2].endswith("verify-ollama")
    assert len(records) == 3


@pytest.mark.parametrize("failure", [0, 29])
def test_ollama_stop_delegates_exclusively_and_propagates_refusal(
    ollama_shell, failure
):
    root, calls, _, run = ollama_shell
    (root / "logs").mkdir()
    pid_file = root / "logs/ollama.pid"
    pid_file.write_text(str(os.getpid()))
    result = run("stop", {"FAKE_STOP_EXIT": str(failure)})
    assert result.returncode == failure
    records = calls.read_text().splitlines()
    assert len(records) == 1
    assert records[0].endswith("stop-ollama")
    assert pid_file.read_text() == str(os.getpid())


def test_ollama_manual_spawn_claims_only_after_exec_and_never_discovers_unit(
    ollama_shell,
):
    root, calls, _, run = ollama_shell
    result = run("start")
    assert result.returncode == 0, result.stderr
    records = calls.read_text().splitlines()
    assert records[0].startswith("curl|")
    assert records[1].endswith("claim-ollama")
    assert len(records) == 2
    assert int((root / "exec-polls").read_text()) == 3
    assert (root / "logs/ollama.pid.identity.json").read_text() == "claimed\n"
    assert int((root / "logs/ollama.pid").read_text()) > 1


def test_ollama_unhealthy_existing_pid_must_have_verifiable_owner(ollama_shell):
    root, calls, _, run = ollama_shell
    (root / "logs").mkdir()
    pid_file = root / "logs/ollama.pid"
    pid_file.write_text(str(os.getpid()))
    result = run("start", {"FAKE_VERIFY_EXIT": "31"})
    assert result.returncode == 31
    assert calls.read_text().splitlines()[-1].endswith("verify-ollama")
    assert pid_file.read_text() == str(os.getpid())
    assert not (root / "logs/ollama.pid.identity.json").exists()


def test_ollama_restart_refuses_start_when_owned_stop_fails(ollama_shell):
    _, calls, _, run = ollama_shell
    result = run("restart", {"FAKE_STOP_EXIT": "29"})
    assert result.returncode == 29
    records = calls.read_text().splitlines()
    assert len(records) == 1
    assert records[0].endswith("stop-ollama")


def test_ollama_control_uses_existing_venv_and_never_sources_env(
    ollama_shell, tmp_path
):
    import shutil

    root, calls, env, run = ollama_shell
    marker = tmp_path / "must-not-exist"
    (root / "fixture.env").write_text(f"SHELL_TRAP=$(touch {marker})\n")
    interpreter = root / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    shutil.copy2(Path(env["PYTHON_BIN"]), interpreter)
    result = run("stop", {"PYTHON_BIN": ""})
    assert result.returncode == 0, result.stderr
    assert calls.read_text().strip().endswith("stop-ollama")
    assert not marker.exists()


@pytest.mark.parametrize("failure_stage", ["backend", "ui"])
def test_failed_backend_start_rollback_uses_original_token_not_current_pid_file(
    tmp_path,
    failure_stage,
):
    import json
    import shutil

    root = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "checkout"
    for relative in (
        "scripts/dev/start_stack.sh",
        "scripts/lib/env_contract.sh",
        "scripts/lib/python_contract.sh",
    ):
        target = fixture / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
    commands = tmp_path / "commands"
    commands.mkdir()
    calls = tmp_path / "calls"
    captured = tmp_path / "rollback.json"

    def executable(name, text):
        path = commands / name
        path.write_text("#!/bin/sh\nset -eu\n" + text)
        path.chmod(0o700)
        return path

    python = executable(
        "python",
        """
if [ "$1" = "-c" ]; then
  case "$2" in *uuid4*) printf 'fixture-ui-transaction\n' ;; esac
  exit 0
fi
if [ "$1" = "-m" ] && [ "$2" = "dotenv" ]; then
  while [ "$1" != "--" ]; do shift; done
  shift
  if [ "$1" = "node" ]; then exec "$@"; fi
  printf 'none\n'; exit 0
fi
if [ "$1" = "-m" ] && [ "$2" = "scripts.dev.startup_rollback" ]; then printf '%s' "$3" >"$CAPTURED"; printf 'rollback\n' >>"$CALLS"; exit 0; fi
case "$2" in
  runtime-check) exit 0 ;;
  launch-api) printf '99999999\n' >"$PID_FILE"; printf '{"pid":99999999,"stamp":"12345"}\n'; exit 0 ;;
  *) exit 91 ;;
esac
""",
    )
    executable(
        "curl",
        """
if [ -f "$PID_FILE" ]; then
  if [ "$FAKE_BACKEND_READY" = "1" ]; then exit 0; fi
  printf '199999999\n' >"$PID_FILE"
fi
exit 7
""",
    )
    executable(
        "node",
        """
if [ "$2" = "rollback" ]; then
  printf '%s' "$3" >"$UI_CAPTURED"
  printf 'ui-rollback\n' >>"$CALLS"
  exit 0
fi
printf 'ui-launch\n' >>"$CALLS"
exit 39
""",
    )
    executable("ls", "exit 0\n")
    executable("sleep", "exit 0\n")
    uvicorn = executable("uvicorn", "exit 94\n")
    env = {
        "PATH": str(commands) + ":/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PYTHON_BIN": str(python),
        "VENOM_STACK_RESOLVED": "1",
        "VENOM_VARIANT": "studio",
        "ENV_FILE": str(tmp_path / "fixture.env"),
        "UVICORN": str(uvicorn),
        "PID_FILE": str(fixture / "api.pid"),
        "WEB_PID_FILE": str(fixture / "web.pid"),
        "BACKEND_LOG": str(fixture / "backend.log"),
        "WEB_LOG": str(fixture / "web.log"),
        "CALLS": str(calls),
        "CAPTURED": str(captured),
        "UI_CAPTURED": str(tmp_path / "ui-token"),
        "FAKE_BACKEND_READY": "1" if failure_stage == "ui" else "0",
    }
    (tmp_path / "fixture.env").write_text("")
    result = subprocess.run(
        ["bash", str(fixture / "scripts/dev/start_stack.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    if failure_stage == "backend":
        assert "Backend nie wystartował" in result.stdout
    else:
        assert (tmp_path / "ui-token").read_text() == "fixture-ui-transaction"
    assert json.loads(captured.read_text()) == {"pid": 99999999, "stamp": "12345"}
    expected_pid = "99999999" if failure_stage == "ui" else "199999999"
    assert (fixture / "api.pid").read_text() == expected_pid + "\n"
    expected_calls = (
        "ui-launch\nui-rollback\nrollback\n" if failure_stage == "ui" else "rollback\n"
    )
    assert calls.read_text() == expected_calls
