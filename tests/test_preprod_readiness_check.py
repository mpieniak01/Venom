from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/preprod/readiness_check.py")


def _write_env(path: Path, *, mutation: str = "0") -> None:
    path.write_text(
        "\n".join(
            [
                "ENVIRONMENT_ROLE=preprod",
                "DB_SCHEMA=preprod",
                "CACHE_NAMESPACE=preprod",
                "QUEUE_NAMESPACE=preprod",
                "STORAGE_PREFIX=preprod",
                f"ALLOW_DATA_MUTATION={mutation}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_readiness_dry_run_pass(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.preprod"
    report = tmp_path / "report.json"
    _write_env(env_file, mutation="0")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--env-file",
            str(env_file),
            "--dry-run",
            "1",
            "--run-audit",
            "0",
            "--output-json",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["dry_run"] is True
    assert any(item["name"] == "preprod_env_contract" for item in payload["checks"])


def test_readiness_dry_run_pass_with_false_mutation(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.preprod"
    report = tmp_path / "report.json"
    _write_env(env_file, mutation="false")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--env-file",
            str(env_file),
            "--dry-run",
            "1",
            "--run-audit",
            "0",
            "--output-json",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"


def test_readiness_dry_run_fails_on_invalid_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.preprod"
    report = tmp_path / "report.json"
    _write_env(env_file, mutation="1")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--env-file",
            str(env_file),
            "--dry-run",
            "1",
            "--run-audit",
            "0",
            "--output-json",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    contract = next(
        item for item in payload["checks"] if item["name"] == "preprod_env_contract"
    )
    assert "ALLOW_DATA_MUTATION" in contract["details"]
