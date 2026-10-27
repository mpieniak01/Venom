from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "scripts/run-pytest-optimal.sh"


@pytest.fixture
def fake_checkout(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(RUNNER, scripts / RUNNER.name)
    venv_bin = tmp_path / ".venv/bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text("# fake venv\n", encoding="utf-8")
    fake = venv_bin / "pytest"
    fake.write_text(
        """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
report = next(value.split('=', 1)[1] for value in args if value.startswith('--junitxml='))
name = Path(report).stem
with Path(os.environ['FAKE_CALL_LOG']).open('a', encoding='utf-8') as f:
    f.write(json.dumps({'group': name, 'args': args, 'options': os.environ.get('PYTEST_ADDOPTS')}) + '\\n')
status = '<skipped />' if name == 'heavy' else ''
Path(report).write_text(f'<testsuites><testsuite><testcase name="t">{status}</testcase></testsuite></testsuites>', encoding='utf-8')
sys.exit(1 if name == os.environ.get('FAKE_FAIL_GROUP') else 0)
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    groups = tmp_path / "config/pytest-groups"
    groups.mkdir(parents=True)
    for group in ("fast", "long", "heavy"):
        (groups / f"{group}.txt").write_text(
            f"tests/test_{group}.py\n", encoding="utf-8"
        )
    (groups / "manual-long-running.txt").write_text("# comments\n", encoding="utf-8")
    return tmp_path


def _run(checkout: Path, *args: str, extra_env: dict[str, str] | None = None):
    environment = os.environ.copy()
    for key in (
        "PYTEST_GROUP_REPORT_DIR",
        "MANUAL_LONG_RUNNING_FILE",
        "PYTEST_FAST_WORKERS",
        "PYTEST_LONG_WORKERS",
        "PYTEST_HEAVY_WORKERS",
    ):
        environment.pop(key, None)
    environment.update(
        {
            "FAKE_CALL_LOG": str(checkout / "calls.jsonl"),
            "PYTEST_ADDOPTS": "--maxfail=2",
        }
    )
    environment.update(extra_env or {})
    return subprocess.run(
        ["bash", str(checkout / "scripts" / RUNNER.name), *args],
        cwd=checkout,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_plan_is_checkout_relative_and_does_not_run_pytest(fake_checkout: Path):
    result = _run(fake_checkout, "--plan")
    assert result.returncode == 0, result.stderr
    assert f"Checkout: {fake_checkout}" in result.stdout
    assert "fast: files=1 workers=4" in result.stdout
    assert "Marked physical tests: excluded" in result.stdout
    assert not (fake_checkout / "calls.jsonl").exists()


def test_reports_each_group_and_continues_after_failure(fake_checkout: Path):
    result = _run(
        fake_checkout, extra_env={"FAKE_FAIL_GROUP": "long", "PYTEST_FAST_WORKERS": "4"}
    )
    assert result.returncode == 1
    calls = [
        json.loads(line)
        for line in (fake_checkout / "calls.jsonl").read_text().splitlines()
    ]
    assert [call["group"] for call in calls] == ["fast", "long", "heavy"]
    assert all(call["options"] == "--maxfail=2" for call in calls)
    assert calls[0]["args"][calls[0]["args"].index("-n") + 1] == "4"
    assert "not live_venom" in calls[0]["args"][calls[0]["args"].index("-m") + 1]
    report_path = next(
        (fake_checkout / "test-results/test-groups").glob("run-*/summary.json")
    )
    report = json.loads(report_path.read_text())
    assert [row["status"] for row in report["groups"]] == [
        "PASS",
        "FAIL",
        "ALL_SKIPPED",
    ]
    assert report["groups"][2]["skipped"] == 1
    assert report["exit_code"] == 1
    assert report["total_seconds"] >= 0


def test_rejects_invalid_worker_count_without_running_tests(fake_checkout: Path):
    result = _run(fake_checkout, "--plan", extra_env={"PYTEST_FAST_WORKERS": "0"})
    assert result.returncode == 2
    assert "positive integers" in result.stderr
    assert not (fake_checkout / "calls.jsonl").exists()


def test_make_group_entry_preserves_explicit_api_without_inventing_a_port(tmp_path):
    source = Path(__file__).resolve().parents[1] / "make/tests.mk"
    (tmp_path / "make").mkdir()
    shutil.copy(source, tmp_path / "make/tests.mk")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "run-pytest-optimal.sh").write_text(
        'printf "api=%s\\n" "${VENOM_API_BASE-unset}"\n', encoding="utf-8"
    )
    environment = os.environ.copy()
    environment.pop("VENOM_API_BASE", None)
    default = subprocess.run(
        ["make", "-f", "make/tests.mk", "test"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert default.returncode == 0, default.stderr
    assert "api=unset" in default.stdout
    environment["VENOM_API_BASE"] = "http://127.0.0.1:8800"
    explicit = subprocess.run(
        ["make", "-f", "make/tests.mk", "test"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert explicit.returncode == 0, explicit.stderr
    assert "api=http://127.0.0.1:8800" in explicit.stdout


def test_all_skipped_group_fails_the_gate(fake_checkout: Path):
    result = _run(fake_checkout, "--group", "heavy")
    assert result.returncode == 1
    report_path = next(
        (fake_checkout / "test-results/test-groups").glob("run-*/summary.json")
    )
    report = json.loads(report_path.read_text())
    assert report["groups"][0]["status"] == "ALL_SKIPPED"
    assert report["exit_code"] == 1
