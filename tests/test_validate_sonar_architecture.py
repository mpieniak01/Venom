from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/validate_sonar_architecture.py")


def test_validator_accepts_container_group_without_patterns(tmp_path: Path) -> None:
    config = tmp_path / "sonar-architecture.yaml"
    config.write_text(
        """
perspectives:
  - label: backend
    groups:
      - label: orchestrator
        groups:
          - label: core
            patterns:
              - venom_core.core.orchestrator.orchestrator_core
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "validation passed" in result.stdout.lower()


def test_validator_rejects_group_without_patterns_or_groups(tmp_path: Path) -> None:
    config = tmp_path / "sonar-architecture.yaml"
    config.write_text(
        """
perspectives:
  - label: backend
    groups:
      - label: empty_group
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "must define at least one of 'patterns' or 'groups'" in result.stdout
