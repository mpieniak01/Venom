from __future__ import annotations

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
