#!/usr/bin/env python3
"""Run lightweight security delta scan for Python and web dependencies.

This script is intentionally operational (not a hard gate):
- Python: `pip check` + optional `pip-audit -f json`
- Web: `npm audit --omit=dev --json` in `web-next/`

Exit 2 means a failed or incomplete scan, including a failed pip check.
A complete scan exits 0 by default; --strict additionally exits 1 for findings.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CmdResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str


def _run(cmd: list[str], cwd: Path | None = None) -> CmdResult:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            check=False,
            timeout=180,
        )
    except OSError as exc:
        return CmdResult(False, 127, "", str(exc))
    except subprocess.TimeoutExpired:
        return CmdResult(False, 124, "", "scanner_timeout")
    return CmdResult(
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _json_or_none(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def _scan_python(root: Path, python_cmd: str | None = None) -> dict[str, Any]:
    # Audit exactly the requested interpreter. A checkout's .venv may belong to
    # another release and PATH may contain a scanner from a different profile.
    python_cmd = python_cmd or sys.executable
    result: dict[str, Any] = {
        "interpreter": python_cmd,
        "pip_check": {},
        "pip_audit": {},
    }
    pip_check = _run([python_cmd, "-m", "pip", "check"])
    result["pip_check"] = {
        "ok": pip_check.ok,
        "returncode": pip_check.returncode,
        "stdout": pip_check.stdout.strip(),
        "stderr": pip_check.stderr.strip(),
    }

    pip_audit = _run([python_cmd, "-m", "pip_audit", "-f", "json"])
    if "No module named pip_audit" in pip_audit.stderr:
        result["pip_audit"] = {
            "available": False,
            "complete": False,
            "status": "unavailable",
            "note": "pip-audit not installed in selected interpreter",
            "vuln_total": None,
            "packages_with_vulns": [],
        }
        return result

    payload = _json_or_none(pip_audit.stdout)
    details = _parse_python_audit(payload)
    return {**result, "pip_audit": _audit_result(pip_audit, details)}


def _parse_python_audit(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None or not isinstance(payload.get("dependencies"), list):
        return None
    packages = []
    for dependency in payload["dependencies"]:
        if not isinstance(dependency, dict) or dependency.get("skip_reason"):
            return None
        if not all(
            isinstance(dependency.get(key), str) and dependency[key]
            for key in ("name", "version")
        ):
            return None
        vulnerabilities = dependency.get("vulns")
        if not isinstance(vulnerabilities, list):
            return None
        if any(
            not isinstance(row, dict) or not row.get("id") for row in vulnerabilities
        ):
            return None
        if vulnerabilities:
            packages.append(
                {
                    "name": dependency.get("name"),
                    "version": dependency.get("version"),
                    "vulns": [
                        {"id": row["id"], "fix_versions": row.get("fix_versions", [])}
                        for row in vulnerabilities
                    ],
                }
            )
    return {
        "vuln_total": sum(len(row["vulns"]) for row in packages),
        "packages_with_vulns": packages,
    }


def _audit_result(command: CmdResult, details: dict[str, Any] | None) -> dict[str, Any]:
    complete = details is not None and (
        (command.returncode == 0 and details["vuln_total"] == 0)
        or (command.returncode == 1 and details["vuln_total"] > 0)
    )
    status = "error"
    if complete:
        status = "findings" if details["vuln_total"] else "pass"
    result: dict[str, Any] = {
        "available": True,
        "ok": command.ok,
        "returncode": command.returncode,
        "stderr": command.stderr.strip(),
        "complete": complete,
        "status": status,
        "vuln_total": None,
    }
    if details is not None:
        result.update(details)
    return result


def _scan_web(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"npm_audit_prod": {}}
    web_next = root / "web-next"
    package_json = web_next / "package.json"

    if not package_json.exists():
        result["npm_audit_prod"] = {
            "available": False,
            "complete": False,
            "status": "unavailable",
            "note": "web-next/package.json not found",
            "vuln_total": None,
        }
        return result

    if shutil.which("npm") is None:
        result["npm_audit_prod"] = {
            "available": False,
            "complete": False,
            "status": "unavailable",
            "note": "npm not found in PATH",
            "vuln_total": None,
        }
        return result

    npm_audit = _run(["npm", "audit", "--omit=dev", "--json"], cwd=web_next)
    return {
        "npm_audit_prod": _audit_result(
            npm_audit, _parse_web_audit(_json_or_none(npm_audit.stdout))
        )
    }


def _parse_web_audit(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None or payload.get("error"):
        return None
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    vulnerabilities = metadata.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return None
    names = ("critical", "high", "moderate", "low", "info")
    for name in (*names, "total"):
        value = vulnerabilities.get(name)
        if type(value) is not int or value < 0:
            return None
    if sum(vulnerabilities[name] for name in names) != vulnerabilities["total"]:
        return None
    return {
        "vuln_total": vulnerabilities["total"],
        "severity": {name: vulnerabilities[name] for name in names},
    }


def report_exit_code(report: dict[str, Any], strict: bool) -> int:
    """Separate completeness from findings; diagnostic mode never hides errors."""
    audits = (report["python"]["pip_audit"], report["web"]["npm_audit_prod"])
    if not report["python"]["pip_check"].get("ok") or any(
        audit.get("complete") is not True for audit in audits
    ):
        return 2
    return int(strict and any(audit["vuln_total"] > 0 for audit in audits))


def _build_report(root: Path, python_cmd: str | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "python": _scan_python(root)
        if python_cmd is None
        else _scan_python(root, python_cmd),
        "web": _scan_web(root),
    }
    report["complete"] = report_exit_code(report, False) != 2
    report["status"] = "error"
    if report["complete"]:
        report["status"] = "findings" if report_exit_code(report, True) == 1 else "pass"
    return report


def _print_summary(report: dict[str, Any]) -> None:
    py = report["python"]
    web = report["web"]

    pip_check_ok = py["pip_check"].get("ok", False)
    pip_audit_total = py["pip_audit"].get("vuln_total")
    npm_total = web["npm_audit_prod"].get("vuln_total")

    print("Security delta scan summary")
    print(f"- status: {report['status']}")
    print(f"- complete: {report['complete']}")
    print(f"- generated_at_utc: {report['generated_at_utc']}")
    print(f"- pip_check_ok: {pip_check_ok}")
    print(f"- pip_audit_vuln_total: {pip_audit_total}")
    print(f"- npm_audit_prod_vuln_total: {npm_total}")

    packages = py["pip_audit"].get("packages_with_vulns", [])
    if packages:
        print("- python_packages_with_vulns:")
        for pkg in packages:
            print(f"  - {pkg['name']}=={pkg['version']}")
            for vuln in pkg.get("vulns", []):
                fixes = ",".join(vuln.get("fix_versions", [])) or "-"
                print(f"    - {vuln.get('id')} -> {fixes}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run security delta scan (python + web)."
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        help="Optional path to write full JSON report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 for findings; failed or incomplete scans always exit 2.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        help="Exact interpreter to audit; defaults to the interpreter running this script.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    report = (
        _build_report(root, str(args.python)) if args.python else _build_report(root)
    )
    _print_summary(report)

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
        print(f"- report_json: {args.out_json}")

    return report_exit_code(report, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
