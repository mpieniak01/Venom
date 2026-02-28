from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/check_test_lane_contracts.py")


def _write_contracts(path: Path) -> None:
    payload = {
        "version": 1,
        "lanes": [
            {"id": "ci-lite"},
            {"id": "new-code"},
        ],
        "groups": [
            {
                "id": "ci-lite",
                "group_file": "config/pytest-groups/ci-lite.txt",
                "default_lane": "ci-lite",
                "allowed_lanes": ["ci-lite"],
                "default_rationale": "Fast baseline lane.",
            },
            {
                "id": "sonar-new-code",
                "group_file": "config/pytest-groups/sonar-new-code.txt",
                "default_lane": "new-code",
                "allowed_lanes": ["new-code", "ci-lite"],
                "default_rationale": "Coverage lane.",
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_assignments(path: Path) -> None:
    payload = {
        "version": 1,
        "overrides": [
            {
                "group": "sonar-new-code",
                "test": "tests/test_sample.py",
                "lane": "ci-lite",
                "rationale": "Promoted to ci-lite for faster regression signal.",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_lane_contracts_pass_for_valid_config(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "config" / "pytest-groups").mkdir(parents=True)
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "pytest-groups" / "ci-lite.txt").write_text(
        "tests/test_sample.py\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "pytest-groups" / "sonar-new-code.txt").write_text(
        "tests/test_sample.py\n",
        encoding="utf-8",
    )

    contracts_path = tmp_path / "lane_contracts.yaml"
    assignments_path = tmp_path / "lane_assignments.yaml"
    _write_contracts(contracts_path)
    _write_assignments(assignments_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--contracts",
            str(contracts_path),
            "--assignments",
            str(assignments_path),
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "passed" in result.stdout.lower()


def test_lane_contracts_fail_when_override_lane_is_not_allowed(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "config" / "pytest-groups").mkdir(parents=True)
    (tmp_path / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "pytest-groups" / "ci-lite.txt").write_text(
        "tests/test_sample.py\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "pytest-groups" / "sonar-new-code.txt").write_text(
        "tests/test_sample.py\n",
        encoding="utf-8",
    )

    contracts_path = tmp_path / "lane_contracts.yaml"
    _write_contracts(contracts_path)

    assignments_path = tmp_path / "lane_assignments.yaml"
    assignments_path.write_text(
        json.dumps(
            {
                "version": 1,
                "overrides": [
                    {
                        "group": "ci-lite",
                        "test": "tests/test_sample.py",
                        "lane": "new-code",
                        "rationale": "Invalid promotion.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--contracts",
            str(contracts_path),
            "--assignments",
            str(assignments_path),
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "not allowed for group" in result.stdout
