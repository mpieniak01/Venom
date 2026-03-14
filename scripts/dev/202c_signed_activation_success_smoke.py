#!/usr/bin/env python3
"""202C.7 Live smoke: discover compatible adapter, sign, activate (200), cleanup."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse

from _202c_common import (
    dump_json,
    dump_text,
    http_json,
    resolve_base_url,
    wait_backend_ready,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="202C.7 signed activation success smoke"
    )
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--runtime-id", default="ollama")
    parser.add_argument(
        "--json-output",
        default="test-results/202c7/signed_activation_success_smoke.json",
    )
    parser.add_argument(
        "--md-output", default="test-results/202c7/signed_activation_success_smoke.md"
    )
    return parser.parse_args()


def _runtime_models(options_payload: dict[str, Any], runtime_id: str) -> list[str]:
    runtimes = options_payload.get("runtimes")
    if not isinstance(runtimes, list):
        return []
    normalized = runtime_id.strip().lower()
    for runtime in runtimes:
        if not isinstance(runtime, dict):
            continue
        rid = str(runtime.get("runtime_id") or "").strip().lower()
        if rid != normalized:
            continue
        out: list[str] = []
        for model in runtime.get("models") or []:
            if not isinstance(model, dict):
                continue
            name = str(model.get("name") or model.get("id") or "").strip()
            if name:
                out.append(name)
        return out
    return []


def _find_compatible_pair(
    *, base_url: str, runtime_id: str
) -> tuple[str, str, str] | None:
    code, options = http_json(
        f"{base_url}/api/v1/system/llm-runtime/options", timeout_sec=45.0
    )
    if code != 200 or not isinstance(options, dict):
        return None
    models = _runtime_models(options, runtime_id)
    for model_id in models:
        qs = parse.urlencode({"runtime_id": runtime_id, "model_id": model_id})
        audit_code, audit_payload = http_json(
            f"{base_url}/api/v1/academy/adapters/audit?{qs}", timeout_sec=45.0
        )
        if audit_code != 200 or not isinstance(audit_payload, dict):
            continue
        adapters = audit_payload.get("adapters")
        if not isinstance(adapters, list):
            continue
        for adapter in adapters:
            if not isinstance(adapter, dict):
                continue
            if str(adapter.get("category") or "") != "compatible":
                continue
            adapter_id = str(adapter.get("adapter_id") or "").strip()
            adapter_path = str(adapter.get("adapter_path") or "").strip()
            if adapter_id and adapter_path:
                return adapter_id, adapter_path, model_id
    return None


def _build_md(report: dict[str, Any]) -> str:
    checks = report.get("checks", {}) if isinstance(report.get("checks"), dict) else {}
    lines: list[str] = []
    lines.append("# 202C.7 Signed Activation Success Smoke")
    lines.append("")
    lines.append(f"Generated at: {report.get('generated_at', '')}")
    lines.append(f"Base URL: {report.get('base_url', '')}")
    lines.append(f"Runtime: {report.get('runtime_id', '')}")
    lines.append(f"Adapter: {report.get('adapter_id', '')}")
    lines.append(f"Model: {report.get('model_id', '')}")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    for key in (
        "compatible_pair_found",
        "sign_ok",
        "activate_ok",
        "deactivate_ok",
        "signed_activation_success",
    ):
        lines.append(f"- {key}: {'pass' if checks.get(key) else 'fail'}")
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
        "runtime_id": args.runtime_id,
        "adapter_id": None,
        "adapter_path": None,
        "model_id": None,
        "calls": {},
        "checks": {},
        "errors": [],
    }

    if not wait_backend_ready(base_url, timeout_sec=45):
        report["errors"].append("backend_not_ready")
        dump_json((root / args.json_output).resolve(), report)
        dump_text((root / args.md_output).resolve(), _build_md(report))
        return 1

    pair = _find_compatible_pair(base_url=base_url, runtime_id=args.runtime_id)
    if pair is None:
        report["errors"].append("compatible_adapter_pair_not_found")
        report["checks"] = {
            "compatible_pair_found": False,
            "sign_ok": False,
            "activate_ok": False,
            "deactivate_ok": False,
            "signed_activation_success": False,
        }
        dump_json((root / args.json_output).resolve(), report)
        dump_text((root / args.md_output).resolve(), _build_md(report))
        return 1

    adapter_id, adapter_path, model_id = pair
    report["adapter_id"] = adapter_id
    report["adapter_path"] = adapter_path
    report["model_id"] = model_id

    sign_status, sign_payload = http_json(
        f"{base_url}/api/v1/academy/adapters/{adapter_id}/sign",
        method="POST",
        payload={
            "runtime_id": args.runtime_id,
            "model_id": model_id,
            "signer": "202c7-smoke",
            "conversion_mode": "gguf",
        },
        timeout_sec=90.0,
    )
    report["calls"]["sign"] = {"status": sign_status, "payload": sign_payload}

    activate_status, activate_payload = http_json(
        f"{base_url}/api/v1/academy/adapters/activate",
        method="POST",
        payload={
            "adapter_id": adapter_id,
            "adapter_path": adapter_path,
            "runtime_id": args.runtime_id,
            "model_id": model_id,
            "deploy_to_chat_runtime": True,
            "require_chat_signature": True,
        },
        timeout_sec=120.0,
    )
    report["calls"]["activate"] = {
        "status": activate_status,
        "payload": activate_payload,
    }

    deactivate_status, deactivate_payload = http_json(
        f"{base_url}/api/v1/academy/adapters/deactivate",
        method="POST",
        payload={},
        timeout_sec=90.0,
    )
    report["calls"]["deactivate"] = {
        "status": deactivate_status,
        "payload": deactivate_payload,
    }

    checks = {
        "compatible_pair_found": True,
        "sign_ok": sign_status == 200,
        "activate_ok": activate_status == 200,
        "deactivate_ok": deactivate_status == 200,
    }
    checks["signed_activation_success"] = bool(
        checks["compatible_pair_found"]
        and checks["sign_ok"]
        and checks["activate_ok"]
        and checks["deactivate_ok"]
    )
    report["checks"] = checks

    if not checks["signed_activation_success"]:
        report["errors"].append("signed_activation_success_smoke_failed")

    dump_json((root / args.json_output).resolve(), report)
    dump_text((root / args.md_output).resolve(), _build_md(report))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
