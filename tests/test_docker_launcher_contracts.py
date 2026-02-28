from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(script_rel: str, *args: str) -> subprocess.CompletedProcess[str]:
    script = REPO_ROOT / script_rel
    return subprocess.run(
        ["bash", str(script), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_venom_launcher_help() -> None:
    result = _run("scripts/docker/venom.sh", "--help")
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "--lang" in result.stdout
    assert "--profile" in result.stdout


def test_venom_launcher_rejects_invalid_profile_before_docker_calls() -> None:
    result = _run("scripts/docker/venom.sh", "--profile", "invalid", "--quick")
    assert result.returncode == 1
    assert "Unsupported profile" in result.stderr


def test_install_script_rejects_invalid_mode() -> None:
    result = _run("scripts/docker/install.sh", "--mode", "invalid")
    assert result.returncode == 1
    assert "Unsupported --mode value" in result.stderr


def test_uninstall_script_rejects_invalid_stack_before_docker_calls() -> None:
    result = _run("scripts/docker/uninstall.sh", "--stack", "invalid")
    assert result.returncode == 1
    assert "Unsupported --stack value" in result.stderr
