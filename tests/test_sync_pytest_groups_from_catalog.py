from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SYNC_SCRIPT = Path("scripts/sync_pytest_groups_from_catalog.py")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_catalog() -> dict[str, object]:
    return {
        "version": 1,
        "meta": {"legacy_targeted_fastlane_max": 17},
        "allowed_domains": ["api", "misc"],
        "allowed_test_types": ["unit", "route_contract", "integration", "perf", "gate"],
        "allowed_intents": [
            "regression",
            "contract",
            "gate",
            "integration",
            "performance",
            "security",
            "legacy_coverage",
        ],
        "tests": [
            {
                "path": "tests/test_a.py",
                "domain": "api",
                "test_type": "unit",
                "intent": "regression",
                "primary_lane": "ci-lite",
                "allowed_lanes": ["ci-lite", "new-code", "release"],
                "legacy_targeted": False,
                "rationale": "a",
            },
            {
                "path": "tests/test_b_integration.py",
                "domain": "api",
                "test_type": "integration",
                "intent": "integration",
                "primary_lane": "release",
                "allowed_lanes": ["release"],
                "legacy_targeted": False,
                "rationale": "b",
            },
            {
                "path": "tests/perf/test_c_perf.py",
                "domain": "api",
                "test_type": "perf",
                "intent": "performance",
                "primary_lane": "release",
                "allowed_lanes": ["release"],
                "legacy_targeted": False,
                "rationale": "c",
            },
        ],
    }


def test_sync_pytest_groups_from_catalog_writes_expected_groups(tmp_path: Path) -> None:
    _write(tmp_path / "tests/test_a.py", "def test_ok():\n    assert True\n")
    _write(
        tmp_path / "tests/test_b_integration.py", "def test_ok():\n    assert True\n"
    )
    _write(tmp_path / "tests/perf/test_c_perf.py", "def test_ok():\n    assert True\n")
    _write(
        tmp_path / "config/testing/test_catalog.yaml",
        json.dumps(_minimal_catalog(), ensure_ascii=False, indent=2) + "\n",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SYNC_SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--catalog",
            str(tmp_path / "config/testing/test_catalog.yaml"),
            "--write",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    ci_lite = (tmp_path / "config/pytest-groups/ci-lite.txt").read_text(
        encoding="utf-8"
    )
    sonar = (tmp_path / "config/pytest-groups/sonar-new-code.txt").read_text(
        encoding="utf-8"
    )
    fast = (tmp_path / "config/pytest-groups/fast.txt").read_text(encoding="utf-8")
    long = (tmp_path / "config/pytest-groups/long.txt").read_text(encoding="utf-8")
    heavy = (tmp_path / "config/pytest-groups/heavy.txt").read_text(encoding="utf-8")

    assert "tests/test_a.py" in ci_lite
    assert "tests/test_a.py" in sonar
    assert "tests/test_a.py" in fast
    assert "tests/test_b_integration.py" in long
    assert "tests/perf/test_c_perf.py" in heavy

    light_alias = tmp_path / "config/pytest-groups/light.txt"
    assert light_alias.is_symlink()
    assert os.readlink(light_alias) == "fast.txt"


def test_sync_pytest_groups_from_catalog_check_detects_drift(tmp_path: Path) -> None:
    _write(tmp_path / "tests/test_a.py", "def test_ok():\n    assert True\n")
    _write(
        tmp_path / "tests/test_b_integration.py", "def test_ok():\n    assert True\n"
    )
    _write(tmp_path / "tests/perf/test_c_perf.py", "def test_ok():\n    assert True\n")
    _write(
        tmp_path / "config/testing/test_catalog.yaml",
        json.dumps(_minimal_catalog(), ensure_ascii=False, indent=2) + "\n",
    )
    _write(
        tmp_path / "config/pytest-groups/ci-lite.txt",
        "tests/test_unrelated.py\n",
    )
    _write(tmp_path / "config/pytest-groups/sonar-new-code.txt", "")
    _write(tmp_path / "config/pytest-groups/fast.txt", "")
    _write(tmp_path / "config/pytest-groups/long.txt", "")
    _write(tmp_path / "config/pytest-groups/heavy.txt", "")
    _write(tmp_path / "config/pytest-groups/light.txt", "")

    result = subprocess.run(
        [
            sys.executable,
            str(SYNC_SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--catalog",
            str(tmp_path / "config/testing/test_catalog.yaml"),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Group file differs from catalog-generated content" in result.stdout
