from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

GEN_SCRIPT = Path("scripts/generate_test_catalog.py")
CHECK_SCRIPT = Path("scripts/check_test_catalog.py")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_generate_test_catalog_creates_expected_fields(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "test_sample.py",
        "from venom_core.api.routes import queue\n\n\ndef test_ok():\n    assert True\n",
    )
    _write(tmp_path / "config/pytest-groups/ci-lite.txt", "tests/test_sample.py\n")
    _write(
        tmp_path / "config/pytest-groups/sonar-new-code.txt",
        "tests/test_sample.py\n",
    )
    _write(tmp_path / "config/pytest-groups/long.txt", "")
    _write(tmp_path / "config/pytest-groups/heavy.txt", "")

    out = tmp_path / "config/testing/test_catalog.json"
    result = subprocess.run(
        [
            sys.executable,
            str(GEN_SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--output",
            str(out),
            "--write",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["tests"][0]["path"] == "tests/test_sample.py"
    assert payload["tests"][0]["domain"] in payload["allowed_domains"]
    assert payload["tests"][0]["test_type"] in payload["allowed_test_types"]
    assert payload["tests"][0]["intent"] in payload["allowed_intents"]
    assert isinstance(payload["tests"][0]["legacy_targeted"], bool)


def test_check_test_catalog_fails_when_test_is_missing_in_catalog(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "tests/test_alpha.py", "def test_ok():\n    assert True\n")
    _write(tmp_path / "config/pytest-groups/ci-lite.txt", "tests/test_alpha.py\n")
    _write(
        tmp_path / "config/pytest-groups/sonar-new-code.txt",
        "tests/test_alpha.py\n",
    )

    catalog = {
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
        "tests": [],
    }
    _write(
        tmp_path / "config/testing/test_catalog.json",
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--catalog",
            str(tmp_path / "config/testing/test_catalog.json"),
            "--repo-root",
            str(tmp_path),
            "--ci-lite-group",
            str(tmp_path / "config/pytest-groups/ci-lite.txt"),
            "--new-code-group",
            str(tmp_path / "config/pytest-groups/sonar-new-code.txt"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "missing in catalog" in result.stdout


def test_check_test_catalog_fails_for_legacy_misc_fastlane(tmp_path: Path) -> None:
    _write(tmp_path / "tests/test_pr_gate_api.py", "def test_ok():\n    assert True\n")
    _write(tmp_path / "config/pytest-groups/ci-lite.txt", "tests/test_pr_gate_api.py\n")
    _write(
        tmp_path / "config/pytest-groups/sonar-new-code.txt",
        "tests/test_pr_gate_api.py\n",
    )
    catalog = {
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
                "path": "tests/test_pr_gate_api.py",
                "domain": "misc",
                "test_type": "unit",
                "intent": "legacy_coverage",
                "primary_lane": "ci-lite",
                "allowed_lanes": ["ci-lite", "new-code"],
                "legacy_targeted": True,
                "rationale": "legacy",
            }
        ],
    }
    _write(
        tmp_path / "config/testing/test_catalog.json",
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--catalog",
            str(tmp_path / "config/testing/test_catalog.json"),
            "--repo-root",
            str(tmp_path),
            "--ci-lite-group",
            str(tmp_path / "config/pytest-groups/ci-lite.txt"),
            "--new-code-group",
            str(tmp_path / "config/pytest-groups/sonar-new-code.txt"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "split by domain" in result.stdout


def test_check_test_catalog_fails_when_release_catalog_entry_is_missing_in_release_groups(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "tests/test_release_only.py", "def test_ok():\n    assert True\n")
    _write(tmp_path / "config/pytest-groups/ci-lite.txt", "")
    _write(tmp_path / "config/pytest-groups/sonar-new-code.txt", "")
    _write(tmp_path / "config/pytest-groups/fast.txt", "")
    _write(tmp_path / "config/pytest-groups/long.txt", "")
    _write(tmp_path / "config/pytest-groups/heavy.txt", "")

    catalog = {
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
                "path": "tests/test_release_only.py",
                "domain": "api",
                "test_type": "unit",
                "intent": "regression",
                "primary_lane": "release",
                "allowed_lanes": ["release"],
                "legacy_targeted": False,
                "rationale": "release regression",
            }
        ],
    }
    _write(
        tmp_path / "config/testing/test_catalog.json",
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--catalog",
            str(tmp_path / "config/testing/test_catalog.json"),
            "--repo-root",
            str(tmp_path),
            "--ci-lite-group",
            str(tmp_path / "config/pytest-groups/ci-lite.txt"),
            "--new-code-group",
            str(tmp_path / "config/pytest-groups/sonar-new-code.txt"),
            "--fast-group",
            str(tmp_path / "config/pytest-groups/fast.txt"),
            "--long-group",
            str(tmp_path / "config/pytest-groups/long.txt"),
            "--heavy-group",
            str(tmp_path / "config/pytest-groups/heavy.txt"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "missing from fast/long/heavy groups" in result.stdout


def test_check_test_catalog_fails_when_release_group_contains_non_test_pattern(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "tests/test_release_ok.py", "def test_ok():\n    assert True\n")
    _write(tmp_path / "config/pytest-groups/ci-lite.txt", "")
    _write(tmp_path / "config/pytest-groups/sonar-new-code.txt", "")
    _write(tmp_path / "config/pytest-groups/fast.txt", "tests/verify_backend.py\n")
    _write(tmp_path / "config/pytest-groups/long.txt", "")
    _write(tmp_path / "config/pytest-groups/heavy.txt", "")

    catalog = {
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
                "path": "tests/test_release_ok.py",
                "domain": "api",
                "test_type": "unit",
                "intent": "regression",
                "primary_lane": "release",
                "allowed_lanes": ["release"],
                "legacy_targeted": False,
                "rationale": "release regression",
            }
        ],
    }
    _write(
        tmp_path / "config/testing/test_catalog.json",
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--catalog",
            str(tmp_path / "config/testing/test_catalog.json"),
            "--repo-root",
            str(tmp_path),
            "--ci-lite-group",
            str(tmp_path / "config/pytest-groups/ci-lite.txt"),
            "--new-code-group",
            str(tmp_path / "config/pytest-groups/sonar-new-code.txt"),
            "--fast-group",
            str(tmp_path / "config/pytest-groups/fast.txt"),
            "--long-group",
            str(tmp_path / "config/pytest-groups/long.txt"),
            "--heavy-group",
            str(tmp_path / "config/pytest-groups/heavy.txt"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "outside tests/**/test_*.py pattern" in result.stdout
