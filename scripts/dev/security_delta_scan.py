#!/usr/bin/env python3
"""Run lightweight security delta scan for Python and web dependencies.

This script is intentionally operational (not a hard gate):
- Python: `pip check` + optional `pip-audit -f json`
- Web: `npm audit --omit=dev --json` in `web-next/`

By default it exits with code 0 and prints a summary.
Use `--strict` to return non-zero when vulnerabilities are found.
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
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
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
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _scan_python(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"pip_check": {}, "pip_audit": {}}

    venv_python = root / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable
    pip_check = _run([python_cmd, "-m", "pip", "check"])
    result["pip_check"] = {
        "ok": pip_check.ok,
        "returncode": pip_check.returncode,
        "stdout": pip_check.stdout.strip(),
        "stderr": pip_check.stderr.strip(),
    }

    venv_pip_audit = root / ".venv" / "bin" / "pip-audit"
    pip_audit_cmd = (
        str(venv_pip_audit) if venv_pip_audit.exists() else shutil.which("pip-audit")
    )

    if not pip_audit_cmd:
        result["pip_audit"] = {
            "available": False,
            "note": "pip-audit not found in current environment",
            "vuln_total": None,
            "packages_with_vulns": [],
        }
        return result

    pip_audit = _run([pip_audit_cmd, "-f", "json"])
    payload = _json_or_none(pip_audit.stdout) or {"dependencies": []}

    packages_with_vulns: list[dict[str, Any]] = []
    vuln_total = 0
    for dep in payload.get("dependencies", []):
        vulns = dep.get("vulns") or []
        if not vulns:
            continue
        vuln_total += len(vulns)
        packages_with_vulns.append(
            {
                "name": dep.get("name"),
                "version": dep.get("version"),
                "vulns": [
                    {
                        "id": vuln.get("id"),
                        "fix_versions": vuln.get("fix_versions", []),
                    }
                    for vuln in vulns
                ],
            }
        )

    result["pip_audit"] = {
        "available": True,
        "ok": pip_audit.ok,
        "returncode": pip_audit.returncode,
        "stderr": pip_audit.stderr.strip(),
        "vuln_total": vuln_total,
        "packages_with_vulns": packages_with_vulns,
    }
    return result


def _scan_web(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"npm_audit_prod": {}}
    web_next = root / "web-next"
    package_json = web_next / "package.json"

    if not package_json.exists():
        result["npm_audit_prod"] = {
            "available": False,
            "note": "web-next/package.json not found",
            "vuln_total": None,
        }
        return result

    if shutil.which("npm") is None:
        result["npm_audit_prod"] = {
            "available": False,
            "note": "npm not found in PATH",
            "vuln_total": None,
        }
        return result

    npm_audit = _run(["npm", "audit", "--omit=dev", "--json"], cwd=web_next)
    payload = _json_or_none(npm_audit.stdout) or {"metadata": {"vulnerabilities": {}}}
    vulns = payload.get("metadata", {}).get("vulnerabilities", {})
    vuln_total = int(vulns.get("total", 0))

    result["npm_audit_prod"] = {
        "available": True,
        "ok": npm_audit.ok,
        "returncode": npm_audit.returncode,
        "stderr": npm_audit.stderr.strip(),
        "vuln_total": vuln_total,
        "severity": {
            "critical": int(vulns.get("critical", 0)),
            "high": int(vulns.get("high", 0)),
            "moderate": int(vulns.get("moderate", 0)),
            "low": int(vulns.get("low", 0)),
            "info": int(vulns.get("info", 0)),
        },
    }
    return result


def _build_report(root: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "python": _scan_python(root),
        "web": _scan_web(root),
    }
    return report


def _print_summary(report: dict[str, Any]) -> None:
    py = report["python"]
    web = report["web"]

    pip_check_ok = py["pip_check"].get("ok", False)
    pip_audit_total = py["pip_audit"].get("vuln_total")
    npm_total = web["npm_audit_prod"].get("vuln_total")

    print("Security delta scan summary")
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
        help="Return non-zero when vulnerabilities are found.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    report = _build_report(root)
    _print_summary(report)

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
        print(f"- report_json: {args.out_json}")

    if not args.strict:
        return 0

    py_total = report["python"]["pip_audit"].get("vuln_total") or 0
    npm_total = report["web"]["npm_audit_prod"].get("vuln_total") or 0
    return 1 if (py_total + npm_total) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
