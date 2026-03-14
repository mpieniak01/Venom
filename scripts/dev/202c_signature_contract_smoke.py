#!/usr/bin/env python3
"""202C.6 Live smoke for adapter chat-signature contract."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import (
    dump_json,
    dump_text,
    http_json,
    resolve_base_url,
    wait_backend_ready,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C.6 signature contract smoke")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--adapter-id", default="smoke_signature_contract")
    parser.add_argument("--runtime-id", default="ollama")
    parser.add_argument("--model-id", default="gemma3:latest")
    parser.add_argument("--mismatch-model-id", default="gemma3:4b")
    parser.add_argument(
        "--json-output", default="test-results/202c6/signature_contract_smoke.json"
    )
    parser.add_argument(
        "--md-output", default="test-results/202c6/signature_contract_smoke.md"
    )
    parser.add_argument("--keep-fixture", action="store_true")
    return parser.parse_args()


def _write_fixture(*, root: Path, adapter_id: str) -> tuple[Path, Path]:
    adapter_root = (root / "data/models" / adapter_id).resolve()
    adapter_dir = (adapter_root / "adapter").resolve()
    adapter_dir.mkdir(parents=True, exist_ok=True)

    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "gemma-3-4b-it"}, ensure_ascii=True),
        encoding="utf-8",
    )

    metadata = {
        "metadata_version": 2,
        "adapter_id": adapter_id,
        "base_model": "gemma-3-4b-it",
        "effective_base_model": "gemma-3-4b-it",
        "effective_runtime_id": "ollama",
        "source_flow": "smoke",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parameters": {"runtime_id": "ollama"},
    }
    (adapter_root / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return adapter_root, adapter_dir


def _expect_reason(payload: Any, expected: str) -> bool:
    if not isinstance(payload, dict):
        return False
    detail = payload.get("detail")
    if not isinstance(detail, dict):
        return False
    reason = str(detail.get("reason_code") or detail.get("reason") or "").strip()
    return reason == expected


def _build_md(report: dict[str, Any]) -> str:
    checks = report.get("checks", {}) if isinstance(report.get("checks"), dict) else {}
    calls = report.get("calls", {}) if isinstance(report.get("calls"), dict) else {}
    lines: list[str] = []
    lines.append("# 202C.6 Signature Contract Smoke")
    lines.append("")
    lines.append(f"Generated at: {report.get('generated_at', '')}")
    lines.append(f"Base URL: {report.get('base_url', '')}")
    lines.append(f"Adapter ID: {report.get('adapter_id', '')}")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    for key in (
        "sign_endpoint_active",
        "unsigned_requires_signature",
        "mismatch_detected_after_sign",
        "contract_smoke_passed",
    ):
        lines.append(f"- {key}: {'pass' if checks.get(key) else 'fail'}")
    lines.append("")
    lines.append("## Status Codes")
    lines.append("")
    lines.append(
        f"- unsigned_activate: {calls.get('unsigned_activate', {}).get('status')}"
    )
    lines.append(f"- sign: {calls.get('sign', {}).get('status')}")
    lines.append(
        f"- mismatch_after_sign: {calls.get('mismatch_after_sign', {}).get('status')}"
    )
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[2]
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (root / env_file).resolve()
    base_url = resolve_base_url(env_file=env_file, explicit=args.base_url)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "adapter_id": args.adapter_id,
        "runtime_id": args.runtime_id,
        "model_id": args.model_id,
        "mismatch_model_id": args.mismatch_model_id,
        "calls": {},
        "checks": {},
        "errors": [],
    }

    if not wait_backend_ready(base_url, timeout_sec=45):
        report["errors"].append("backend_not_ready")
        dump_json((root / args.json_output).resolve(), report)
        dump_text((root / args.md_output).resolve(), _build_md(report))
        return 1

    fixture_root, fixture_adapter = _write_fixture(
        root=root, adapter_id=args.adapter_id
    )
    try:
        unsigned_payload = {
            "adapter_id": args.adapter_id,
            "adapter_path": str(fixture_adapter),
            "runtime_id": args.runtime_id,
            "model_id": args.model_id,
            "deploy_to_chat_runtime": True,
            "require_chat_signature": True,
        }
        unsigned_status, unsigned_body = http_json(
            f"{base_url}/api/v1/academy/adapters/activate",
            method="POST",
            payload=unsigned_payload,
            timeout_sec=90.0,
        )
        report["calls"]["unsigned_activate"] = {
            "status": unsigned_status,
            "payload": unsigned_body,
        }

        sign_status, sign_body = http_json(
            f"{base_url}/api/v1/academy/adapters/{args.adapter_id}/sign",
            method="POST",
            payload={
                "runtime_id": args.runtime_id,
                "model_id": args.model_id,
                "signer": "202c-smoke",
                "conversion_mode": "gguf",
            },
            timeout_sec=90.0,
        )
        report["calls"]["sign"] = {
            "status": sign_status,
            "payload": sign_body,
        }

        mismatch_payload = dict(unsigned_payload)
        mismatch_payload["model_id"] = args.mismatch_model_id
        mismatch_status, mismatch_body = http_json(
            f"{base_url}/api/v1/academy/adapters/activate",
            method="POST",
            payload=mismatch_payload,
            timeout_sec=90.0,
        )
        report["calls"]["mismatch_after_sign"] = {
            "status": mismatch_status,
            "payload": mismatch_body,
        }

        # Cleanup runtime state best-effort.
        http_json(
            f"{base_url}/api/v1/academy/adapters/deactivate",
            method="POST",
            payload={},
            timeout_sec=45.0,
        )

        checks = {
            "sign_endpoint_active": sign_status == 200,
            "unsigned_requires_signature": unsigned_status == 400
            and _expect_reason(unsigned_body, "ADAPTER_NOT_SIGNED_FOR_CHAT"),
            "mismatch_detected_after_sign": mismatch_status == 400
            and _expect_reason(mismatch_body, "ADAPTER_SIGNATURE_MODEL_MISMATCH"),
        }
        checks["contract_smoke_passed"] = bool(
            checks["sign_endpoint_active"]
            and checks["unsigned_requires_signature"]
            and checks["mismatch_detected_after_sign"]
        )
        report["checks"] = checks

        if not checks["contract_smoke_passed"]:
            report["errors"].append("signature_contract_smoke_failed")
    finally:
        if not args.keep_fixture:
            shutil.rmtree(fixture_root, ignore_errors=True)

    dump_json((root / args.json_output).resolve(), report)
    dump_text((root / args.md_output).resolve(), _build_md(report))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
