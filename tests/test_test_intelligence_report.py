from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/test_intelligence_report.py")


def _write_group(path: Path, tests: list[str]) -> None:
    path.write_text("\n".join(tests) + "\n", encoding="utf-8")


def _write_junit(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="3" failures="1">
    <testcase classname="tests.test_alpha" name="test_fast_ok" file="tests/test_alpha.py" time="0.05" />
    <testcase classname="tests.test_beta" name="test_slow_ci" file="tests/test_beta.py" time="2.40" />
    <testcase classname="tests.test_gamma" name="test_fail_new_code" file="tests/test_gamma.py" time="0.10">
      <failure message="boom">traceback</failure>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )


def test_test_intelligence_report_json_output(tmp_path: Path) -> None:
    ci_lite = tmp_path / "ci-lite.txt"
    new_code = tmp_path / "sonar-new-code.txt"
    junit = tmp_path / "python-junit.xml"
    lastfailed = tmp_path / "lastfailed.json"
    history = tmp_path / "history.jsonl"

    _write_group(ci_lite, ["tests/test_beta.py"])
    _write_group(new_code, ["tests/test_alpha.py", "tests/test_gamma.py"])
    _write_junit(junit)
    lastfailed.write_text(json.dumps({"tests/test_delta.py::test_prev_fail": True}))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--junit-xml",
            str(junit),
            "--ci-lite-group",
            str(ci_lite),
            "--new-code-group",
            str(new_code),
            "--lastfailed",
            str(lastfailed),
            "--slow-threshold",
            "1.0",
            "--fast-threshold",
            "0.2",
            "--min-tests-for-promotion",
            "1",
            "--top-n",
            "5",
            "--output",
            "json",
            "--history-file",
            str(history),
            "--append-history",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["files_count"] == 3
    assert payload["summary"]["ci_lite_files"] == 1
    assert payload["summary"]["new_code_files"] == 2
    assert payload["recommendations"]["consider_demotion_from_ci_lite"] == [
        "tests/test_beta.py"
    ]
    assert payload["recommendations"]["promote_to_ci_lite"] == ["tests/test_alpha.py"]
    assert "tests/test_gamma.py" in payload["recommendations"]["flaky_candidates"]
    assert "tests/test_delta.py" in payload["recommendations"]["flaky_candidates"]
    assert payload["trend"]["history_file"] == str(history)
    assert payload["trend"]["history_points_before_append"] == 0
    assert payload["trend"]["history_appended"] is True
    assert history.exists()


def test_test_intelligence_report_text_output(tmp_path: Path) -> None:
    ci_lite = tmp_path / "ci-lite.txt"
    new_code = tmp_path / "sonar-new-code.txt"
    junit = tmp_path / "python-junit.xml"

    _write_group(ci_lite, ["tests/test_beta.py"])
    _write_group(new_code, ["tests/test_alpha.py"])
    _write_junit(junit)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--junit-xml",
            str(junit),
            "--ci-lite-group",
            str(ci_lite),
            "--new-code-group",
            str(new_code),
            "--history-file",
            str(tmp_path / "history.jsonl"),
            "--append-history",
            "0",
            "--output",
            "text",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Test intelligence report" in result.stdout
    assert "top impact files" in result.stdout
    assert "runtime trend" in result.stdout
