from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_docker_cleanup_unknown_mode_returns_usage():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "docker_cleanup.sh"

    result = subprocess.run(
        ["bash", str(script), "invalid"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Usage:" in result.stdout


def test_docker_cleanup_blocked_in_preprod():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "docker_cleanup.sh"

    env = os.environ.copy()
    env["ENVIRONMENT_ROLE"] = "preprod"
    env["ALLOW_DATA_MUTATION"] = "0"
    result = subprocess.run(
        ["bash", str(script), "safe"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3
    assert "blocked for pre-prod" in result.stdout
