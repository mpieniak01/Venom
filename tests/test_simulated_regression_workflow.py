"""Contract checks for the hosted, isolated simulated regression workflow."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github/workflows/simulated-regression.yml"
)


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(job: str, name: str) -> str:
    for item in _workflow()["jobs"][job]["steps"]:
        if item.get("name") == name:
            return item["run"]
    raise AssertionError(f"missing step {job}/{name}")


def test_trigger_scope_and_all_shell_steps_are_valid():
    flow = _workflow()
    assert flow["on"]["push"]["branches"] == ["main"]
    assert "schedule" in flow["on"]
    assert "workflow_dispatch" in flow["on"]
    assert "--run-integration" not in _step(
        "backend", "Run simulated groups in isolated network namespace"
    )
    for job in flow["jobs"].values():
        assert job["runs-on"] == "ubuntu-latest"
        for step in job["steps"]:
            if "run" in step:
                result = subprocess.run(
                    ["bash", "-n"], input=step["run"], capture_output=True, text=True
                )
                assert result.returncode == 0, (step.get("name"), result.stderr)


@pytest.mark.parametrize(
    ("job", "name"),
    [
        ("backend", "Run simulated groups in isolated network namespace"),
        ("frontend", "Run mocked browser profiles in isolated network namespace"),
    ],
)
def test_namespace_failure_stops_the_job_before_tests(
    tmp_path: Path, job: str, name: str
):
    binary = tmp_path / "bin"
    binary.mkdir()
    sudo = binary / "sudo"
    sudo.write_text(
        '#!/bin/sh\nprintf attempted > "$GITHUB_WORKSPACE/called"\nexit 77\n',
        encoding="utf-8",
    )
    sudo.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{binary}:{os.environ['PATH']}",
        "GITHUB_WORKSPACE": str(tmp_path),
    }
    result = subprocess.run(
        ["bash", "-c", _step(job, name)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 77, result.stderr
    assert (tmp_path / "called").read_text() == "attempted"


def _browser_summary(tmp_path: Path, expected: int, skipped: int):
    directory = tmp_path / "web-next/test-results/simulated-regression"
    directory.mkdir(parents=True)
    stats = {"expected": expected, "unexpected": 0, "flaky": 0, "skipped": skipped}
    for name in ("smoke", "functional"):
        (directory / f"{name}.json").write_text(
            json.dumps({"stats": stats}), encoding="utf-8"
        )
    result = subprocess.run(
        [
            "bash",
            "-c",
            _step("frontend", "Summarize browser results including skipped tests"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    summary = json.loads(
        (directory / "browser-summary.json").read_text(encoding="utf-8")
    )
    return result, summary


def test_browser_report_does_not_call_all_skipped_a_pass(tmp_path: Path):
    result, summary = _browser_summary(tmp_path, expected=0, skipped=4)
    assert result.returncode == 1
    assert summary["profiles"]["smoke"]["status"] == "skipped"
    assert summary["profiles"]["smoke"]["skipped"] == 4
    assert summary["physical_e2e"] == "not_run"


def test_browser_report_keeps_skips_visible_with_real_passes(tmp_path: Path):
    result, summary = _browser_summary(tmp_path, expected=3, skipped=2)
    assert result.returncode == 1
    assert summary["profiles"]["functional"]["status"] == "partial"
    assert summary["profiles"]["functional"]["skipped"] == 2
    assert summary["physical_e2e"] == "not_run"


def test_browser_report_all_passed_is_success(tmp_path: Path):
    result, summary = _browser_summary(tmp_path, expected=3, skipped=0)
    assert result.returncode == 0
    assert summary["profiles"]["functional"]["status"] == "passed"


def test_browser_profiles_continue_after_smoke_failure():
    script = _step(
        "frontend", "Run mocked browser profiles in isolated network namespace"
    )
    begin = script.index("result=0")
    end = script.index("output_dir=", begin)
    calls = script[begin:end] + 'exit "$result"'
    stub = 'run_profile() { echo "$1"; [ "$1" != smoke ]; }\n'
    result = subprocess.run(
        ["bash", "-e", "-c", stub + calls], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 1
    assert result.stdout.splitlines() == ["smoke", "functional"]


def test_browser_reports_survive_next_playwright_cleanup(tmp_path: Path):
    import getpass

    script = _step(
        "frontend", "Run mocked browser profiles in isolated network namespace"
    )
    begin = script.index("run_profile() {")
    end = script.index('exit "$result"', begin) + len('exit "$result"')
    binary = tmp_path / "bin"
    binary.mkdir()
    id_tool = binary / "id"
    id_tool.write_text('#!/bin/sh\nprintf "separate-group\\n"\n', encoding="utf-8")
    id_tool.chmod(0o755)
    install = binary / "install"
    install.write_text(
        '#!/bin/sh\n[ "$4" = -g ] && [ "$5" = separate-group ] || exit 1\nmkdir -p "$6"\n',
        encoding="utf-8",
    )
    install.chmod(0o755)
    runuser = binary / "runuser"
    runuser.write_text('#!/bin/sh\nshift 3\nexec "$@"\n', encoding="utf-8")
    runuser.chmod(0o755)
    npm = binary / "npm"
    npm.write_text(
        "#!/bin/sh\nrm -rf web-next/test-results\n"
        'printf "{}" > "$PLAYWRIGHT_JSON_OUTPUT_NAME"\n',
        encoding="utf-8",
    )
    npm.chmod(0o755)
    report_dir = tmp_path / "web-next/.simulated-regression-reports"
    report_dir.mkdir(parents=True)
    path = f"{binary}:{os.environ['PATH']}"
    env = {
        **os.environ,
        "PATH": path,
        "runner_path": path,
        "runner_home": str(tmp_path),
        "runner_user": getpass.getuser(),
        "workspace": str(tmp_path),
        "report_dir": str(report_dir),
    }
    result = subprocess.run(
        ["bash", "-e", "-c", script[begin:end]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    output = tmp_path / "web-next/test-results/simulated-regression"
    assert (output / "smoke.json").read_text() == "{}"
    assert (output / "functional.json").read_text() == "{}"
