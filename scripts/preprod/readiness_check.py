#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_PREPROD = {
    "ENVIRONMENT_ROLE": "preprod",
    "DB_SCHEMA": "preprod",
    "CACHE_NAMESPACE": "preprod",
    "QUEUE_NAMESPACE": "preprod",
    "STORAGE_PREFIX": "preprod",
    "ALLOW_DATA_MUTATION": {"0", "false"},
}


def parse_env_file(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def validate_preprod_env(env: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for key, expected in EXPECTED_PREPROD.items():
        actual = env.get(key)
        if isinstance(expected, set):
            normalized = (actual or "").strip().lower()
            if normalized not in expected:
                errors.append(
                    f"{key}: expected one of {sorted(expected)}, got '{actual}'"
                )
        elif actual != expected:
            errors.append(f"{key}: expected '{expected}', got '{actual}'")
    return errors


def extract_backup_timestamp(output: str) -> str | None:
    for line in output.splitlines():
        if line.startswith("Backup timestamp:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return value
    return None


def _run_make(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "--no-print-directory", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _check(
    checks: list[dict[str, Any]],
    name: str,
    status: str,
    details: str,
    output: str = "",
) -> None:
    checks.append(
        {
            "name": name,
            "status": status,
            "details": details,
            "output": output[-4000:] if output else "",
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run preprod readiness checklist automation."
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env.preprod"))
    parser.add_argument("--actor", default="unknown")
    parser.add_argument("--ticket", default="N/A")
    parser.add_argument(
        "--run-audit", type=int, default=1, help="Run preprod-audit (1/0)."
    )
    parser.add_argument(
        "--dry-run", type=int, default=0, help="Only config checks, no make calls."
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Output report path. Default: logs/preprod_readiness_<UTC>.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = datetime.now(timezone.utc)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output_json or Path("logs") / f"preprod_readiness_{stamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []
    overall_ok = True
    backup_ts: str | None = None

    if not args.env_file.exists():
        _check(
            checks,
            "preprod_env_file",
            "fail",
            f"Missing env file: {args.env_file}",
        )
        overall_ok = False
    else:
        env = parse_env_file(args.env_file)
        mismatches = validate_preprod_env(env)
        if mismatches:
            _check(
                checks,
                "preprod_env_contract",
                "fail",
                " ; ".join(mismatches),
            )
            overall_ok = False
        else:
            _check(
                checks, "preprod_env_contract", "pass", "Preprod guard env validated."
            )

    if not args.dry_run and overall_ok:
        backup_result = _run_make(["preprod-backup"])
        if backup_result.returncode != 0:
            _check(
                checks,
                "preprod_backup",
                "fail",
                "make preprod-backup failed",
                backup_result.stdout + "\n" + backup_result.stderr,
            )
            overall_ok = False
        else:
            backup_ts = extract_backup_timestamp(backup_result.stdout)
            if not backup_ts:
                _check(
                    checks,
                    "preprod_backup_timestamp",
                    "fail",
                    "Could not parse backup timestamp.",
                    backup_result.stdout,
                )
                overall_ok = False
            else:
                _check(
                    checks,
                    "preprod_backup",
                    "pass",
                    f"Backup created with TS={backup_ts}",
                    backup_result.stdout,
                )

    if not args.dry_run and overall_ok and backup_ts:
        verify_result = _run_make([f"TS={backup_ts}", "preprod-verify"])
        if verify_result.returncode != 0:
            _check(
                checks,
                "preprod_verify",
                "fail",
                "make preprod-verify failed",
                verify_result.stdout + "\n" + verify_result.stderr,
            )
            overall_ok = False
        else:
            _check(
                checks,
                "preprod_verify",
                "pass",
                f"Verify + smoke passed for TS={backup_ts}",
                verify_result.stdout,
            )

    if bool(args.run_audit) and not args.dry_run:
        audit_result = _run_make(
            [
                f"ACTOR={args.actor}",
                "ACTION=preprod-readiness-check",
                f"TICKET={args.ticket}",
                f"RESULT={'OK' if overall_ok else 'FAIL'}",
                "preprod-audit",
            ]
        )
        if audit_result.returncode == 0:
            _check(
                checks,
                "preprod_audit",
                "pass",
                "Audit entry appended.",
                audit_result.stdout,
            )
        else:
            _check(
                checks,
                "preprod_audit",
                "fail",
                "make preprod-audit failed",
                audit_result.stdout + "\n" + audit_result.stderr,
            )
            overall_ok = False

    report = {
        "ts_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": bool(args.dry_run),
        "status": "pass" if overall_ok else "fail",
        "env_file": str(args.env_file),
        "backup_timestamp": backup_ts,
        "checks": checks,
    }
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Preprod readiness: {report['status'].upper()}")
    print(f"Report: {output_path}")
    if backup_ts:
        print(f"Backup timestamp: {backup_ts}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
