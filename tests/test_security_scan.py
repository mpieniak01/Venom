"""Security qualification must fail closed on missing or partial scan evidence."""

import json
from unittest.mock import Mock

import pytest

from scripts.dev import security_delta_scan as scan


def command(code=0, payload=None):
    return scan.CmdResult(code == 0, code, json.dumps(payload), "")


def web_payload(total=0):
    return {
        "metadata": {
            "vulnerabilities": {
                "critical": total,
                "high": 0,
                "moderate": 0,
                "low": 0,
                "info": 0,
                "total": total,
            }
        }
    }


def report(complete=True, findings=0, pip_ok=True):
    audit = {"complete": complete, "vuln_total": findings}
    return {
        "python": {"pip_check": {"ok": pip_ok}, "pip_audit": dict(audit)},
        "web": {"npm_audit_prod": dict(audit)},
    }


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("complete,pip_ok", [(False, True), (True, False)])
def test_incomplete_evidence_fails_even_diagnostic_mode(strict, complete, pip_ok):
    assert scan.report_exit_code(report(complete=complete, pip_ok=pip_ok), strict) == 2


@pytest.mark.parametrize(
    "strict,findings,expected",
    [(False, 0, 0), (False, 1, 0), (True, 0, 0), (True, 1, 1)],
)
def test_complete_reports_distinguish_findings_from_execution(
    strict, findings, expected
):
    assert scan.report_exit_code(report(findings=findings), strict) == expected


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"dependencies": None},
        {"dependencies": [{"name": "private", "skip_reason": "not found"}]},
        {"dependencies": [{"name": "broken"}]},
        {"dependencies": [{"vulns": ["bad"]}]},
    ],
)
def test_invalid_or_skipped_python_dependencies_never_pass(payload):
    parsed = scan._json_or_none(json.dumps(payload))
    result = scan._audit_result(command(), scan._parse_python_audit(parsed))
    assert result["complete"] is False and result["status"] == "error"


def test_python_vulnerabilities_are_valid_evidence_with_exit_one():
    parsed = scan._parse_python_audit(
        {
            "dependencies": [
                {
                    "name": "example",
                    "version": "1",
                    "vulns": [{"id": "TEST-1", "fix_versions": ["2"]}],
                }
            ]
        }
    )
    result = scan._audit_result(command(1), parsed)
    assert result["complete"] and result["status"] == "findings"
    assert result["vuln_total"] == 1
    assert result["packages_with_vulns"][0]["vulns"][0]["id"] == "TEST-1"


@pytest.mark.parametrize(
    "code,total,complete",
    [(0, 0, True), (1, 1, True), (2, 0, False), (1, 0, False), (0, 1, False)],
)
def test_audit_exit_and_document_must_agree(code, total, complete):
    result = scan._audit_result(
        command(code), scan._parse_web_audit(web_payload(total))
    )
    assert result["complete"] is complete


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"error": {"code": "NETWORK"}},
        {"metadata": []},
        {"metadata": {"vulnerabilities": {}}},
    ],
)
def test_web_missing_or_error_payload_is_not_zero_findings(payload):
    assert scan._parse_web_audit(payload) is None


@pytest.mark.parametrize("value", [-1, True, "0", None])
def test_web_count_must_be_nonnegative_integer(value):
    payload = web_payload()
    payload["metadata"]["vulnerabilities"]["total"] = value
    assert scan._parse_web_audit(payload) is None


def test_inconsistent_severity_total_is_incomplete():
    payload = web_payload(1)
    payload["metadata"]["vulnerabilities"]["total"] = 2
    assert scan._parse_web_audit(payload) is None


def test_missing_scanner_returns_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        scan,
        "_run",
        lambda *a, **k: scan.CmdResult(False, 1, "", "No module named pip_audit"),
    )
    result = scan._scan_python(tmp_path)
    assert result["pip_audit"]["status"] == "unavailable"
    assert result["pip_audit"]["complete"] is False


@pytest.mark.parametrize(
    "error,expected",
    [
        (FileNotFoundError("missing"), 127),
        (scan.subprocess.TimeoutExpired("scanner", 180), 124),
    ],
)
def test_scanner_launch_failure_is_reported(monkeypatch, error, expected):
    monkeypatch.setattr(scan.subprocess, "run", Mock(side_effect=error))
    result = scan._run(["scanner"])
    assert result.returncode == expected and not result.ok


def test_malformed_json_is_not_empty_report():
    assert scan._json_or_none("{broken") is None
    assert scan._json_or_none("") is None


def test_main_writes_error_evidence_and_returns_two(monkeypatch, tmp_path):
    data = report(complete=False)
    data.update(status="error", complete=False, generated_at_utc="test")
    data["python"]["pip_audit"]["packages_with_vulns"] = []
    monkeypatch.setattr(scan, "_build_report", lambda root: data)
    out = tmp_path / "result.json"
    monkeypatch.setattr(scan.sys, "argv", ["scan", "--strict", "--out-json", str(out)])
    assert scan.main() == 2
    assert json.loads(out.read_text())["complete"] is False


@pytest.mark.parametrize("findings", [0, 1])
def test_python_scan_records_complete_clean_or_vulnerable_graph(
    monkeypatch, tmp_path, findings
):
    dependencies = [{"name": "example", "version": "1", "vulns": []}]
    if findings:
        dependencies[0]["vulns"] = [{"id": "TEST-2", "fix_versions": ["2"]}]
    commands = iter(
        [
            scan.CmdResult(True, 0, "No broken requirements", ""),
            command(findings, {"dependencies": dependencies}),
        ]
    )
    monkeypatch.setattr(scan, "_run", lambda *a, **k: next(commands))
    monkeypatch.setattr(scan.shutil, "which", lambda name: "/qualified/pip-audit")
    result = scan._scan_python(tmp_path)
    assert result["pip_check"]["ok"]
    assert result["pip_audit"]["complete"]
    assert result["pip_audit"]["vuln_total"] == findings


def test_python_missing_package_identity_is_incomplete():
    assert scan._parse_python_audit({"dependencies": [{"vulns": []}]}) is None


@pytest.mark.parametrize("package_exists,npm_available", [(False, True), (True, False)])
def test_web_missing_inputs_are_explicit(
    monkeypatch, tmp_path, package_exists, npm_available
):
    if package_exists:
        (tmp_path / "web-next").mkdir()
        (tmp_path / "web-next/package.json").write_text("{}")
    monkeypatch.setattr(
        scan.shutil, "which", lambda name: "npm" if npm_available else None
    )
    assert scan._scan_web(tmp_path)["npm_audit_prod"]["complete"] is False


@pytest.mark.parametrize(
    "code,payload,complete",
    [
        (0, web_payload(), True),
        (1, web_payload(1), True),
        (2, {"error": {"code": "NETWORK"}}, False),
    ],
)
def test_web_scan_records_execution_and_evidence(
    monkeypatch, tmp_path, code, payload, complete
):
    (tmp_path / "web-next").mkdir()
    (tmp_path / "web-next/package.json").write_text("{}")
    monkeypatch.setattr(scan.shutil, "which", lambda name: "npm")
    monkeypatch.setattr(scan, "_run", lambda *a, **k: command(code, payload))
    assert scan._scan_web(tmp_path)["npm_audit_prod"]["complete"] is complete


@pytest.mark.parametrize(
    "complete,findings,status",
    [(False, 0, "error"), (True, 0, "pass"), (True, 1, "findings")],
)
def test_report_and_printed_summary_preserve_completeness(
    monkeypatch, tmp_path, capsys, complete, findings, status
):
    data = report(complete=complete, findings=findings)
    data["python"]["pip_audit"]["packages_with_vulns"] = [
        {
            "name": "example",
            "version": "1",
            "vulns": [{"id": "TEST-3", "fix_versions": ["2"]}],
        }
    ]
    monkeypatch.setattr(scan, "_scan_python", lambda root: data["python"])
    monkeypatch.setattr(scan, "_scan_web", lambda root: data["web"])
    result = scan._build_report(tmp_path)
    assert result["status"] == status and result["complete"] is complete
    scan._print_summary(result)
    assert f"- status: {status}" in capsys.readouterr().out


def test_python_audit_never_uses_checkout_or_path_interpreter(monkeypatch, tmp_path):
    commands = []

    def run(argv, **kwargs):
        commands.append(argv)
        if "check" in argv:
            return scan.CmdResult(True, 0, "OK", "")
        return command(0, {"dependencies": []})

    monkeypatch.setattr(scan, "_run", run)
    checkout_python = tmp_path / ".venv/bin/python"
    checkout_python.parent.mkdir(parents=True)
    checkout_python.write_text("unrelated interpreter")
    result = scan._scan_python(tmp_path, "/qualified/full/bin/python")
    assert result["interpreter"] == "/qualified/full/bin/python"
    assert commands == [
        ["/qualified/full/bin/python", "-m", "pip", "check"],
        ["/qualified/full/bin/python", "-m", "pip_audit", "-f", "json"],
    ]
    assert result["pip_audit"]["complete"]
