#!/usr/bin/env python3
"""202C LoRA contract audit for ONNX runtime viability."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import dump_json, http_json, resolve_base_url, wait_backend_ready


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C LoRA contract audit")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--target-model", default="gemma-3-4b-it")
    parser.add_argument(
        "--json-output",
        default="test-results/202c/lora_contract_audit.json",
    )
    parser.add_argument(
        "--probe-deploy",
        action="store_true",
        help="Try live adapter deploy probe against ONNX runtime (uses first adapter).",
    )
    return parser.parse_args()


def _find_trainable_entry(
    model_catalog: dict[str, Any], target_model: str
) -> dict[str, Any] | None:
    trainable = model_catalog.get("trainable_models")
    if not isinstance(trainable, list):
        return None
    target = target_model.strip().lower()
    for item in trainable:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("model_id") or "").strip().lower()
        if model_id == target:
            return item
        if target in model_id or model_id in target:
            return item
    return None


def _read_source_contract(repo_root: Path) -> dict[str, Any]:
    adapter_runtime_path = (
        repo_root / "venom_core/services/academy/adapter_runtime_service.py"
    )
    trainable_catalog_path = (
        repo_root / "venom_core/services/academy/trainable_catalog_service.py"
    )
    task_validator_path = (
        repo_root / "venom_core/core/orchestrator/task_pipeline/task_validator.py"
    )

    contract: dict[str, Any] = {
        "adapter_runtime_service": str(adapter_runtime_path),
        "trainable_catalog_service": str(trainable_catalog_path),
        "task_validator": str(task_validator_path),
        "signals": {},
    }

    try:
        adapter_text = adapter_runtime_path.read_text(encoding="utf-8")
    except OSError as exc:
        adapter_text = ""
        contract["signals"]["adapter_runtime_read_error"] = str(exc)
    try:
        catalog_text = trainable_catalog_path.read_text(encoding="utf-8")
    except OSError as exc:
        catalog_text = ""
        contract["signals"]["trainable_catalog_read_error"] = str(exc)
    try:
        validator_text = task_validator_path.read_text(encoding="utf-8")
    except OSError as exc:
        validator_text = ""
        contract["signals"]["task_validator_read_error"] = str(exc)

    contract["signals"].update(
        {
            "onnx_runtime_not_supported_reason_present": "runtime_not_supported:onnx"
            in adapter_text,
            "onnx_inference_only_reason_present": "ONNX runtime artifacts are inference-only"
            in catalog_text,
            "onnx_standard_orchestrator_block_present": "Runtime ONNX nie jest jeszcze obs"
            in validator_text,
        }
    )
    return contract


def _probe_live_deploy(
    *,
    base_url: str,
    target_model: str,
) -> dict[str, Any]:
    adapters_code, adapters_payload = http_json(
        f"{base_url}/api/v1/academy/adapters", timeout_sec=30.0
    )
    if adapters_code != 200 or not isinstance(adapters_payload, list):
        return {
            "attempted": False,
            "status": adapters_code,
            "reason": "adapters_unavailable",
            "payload": adapters_payload,
        }
    if not adapters_payload:
        return {
            "attempted": False,
            "status": 200,
            "reason": "no_adapters_available",
            "payload": None,
        }

    first = adapters_payload[0] if isinstance(adapters_payload[0], dict) else {}
    adapter_id = str(first.get("adapter_id") or "").strip()
    adapter_path = str(first.get("adapter_path") or "").strip()
    if not adapter_id or not adapter_path:
        return {
            "attempted": False,
            "status": 200,
            "reason": "adapter_payload_incomplete",
            "payload": first,
        }

    body = {
        "adapter_id": adapter_id,
        "adapter_path": adapter_path,
        "runtime_id": "onnx",
        "model_id": target_model,
        "deploy_to_chat_runtime": True,
    }
    activate_code, activate_payload = http_json(
        f"{base_url}/api/v1/academy/adapters/activate",
        method="POST",
        payload=body,
        timeout_sec=90.0,
    )

    # Cleanup best-effort in case activation changed state.
    http_json(
        f"{base_url}/api/v1/academy/adapters/deactivate",
        method="POST",
        payload={},
        timeout_sec=45.0,
    )

    reason = ""
    if isinstance(activate_payload, dict):
        detail = activate_payload.get("detail")
        if isinstance(detail, dict):
            reason = str(detail.get("reason") or detail.get("reason_code") or "")
        elif isinstance(detail, str):
            reason = detail

    return {
        "attempted": True,
        "status": activate_code,
        "reason": reason,
        "payload": activate_payload,
        "adapter_id": adapter_id,
    }


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
        "target_model": args.target_model,
        "errors": [],
    }

    if not wait_backend_ready(base_url, timeout_sec=30):
        report["errors"].append("backend_not_ready")
        dump_json((root / args.json_output).resolve(), report)
        return 1

    code, options_payload = http_json(
        f"{base_url}/api/v1/system/llm-runtime/options", timeout_sec=30.0
    )
    options = options_payload if isinstance(options_payload, dict) else {}

    model_catalog = options.get("model_catalog") if isinstance(options, dict) else {}
    if not isinstance(model_catalog, dict):
        model_catalog = {}

    trainable_entry = _find_trainable_entry(model_catalog, args.target_model)
    runtime_compatibility = (
        dict(trainable_entry.get("runtime_compatibility") or {})
        if isinstance(trainable_entry, dict)
        else {}
    )

    adapters_audit_code, adapters_audit_payload = http_json(
        f"{base_url}/api/v1/academy/adapters/audit?runtime_id=onnx&model_id={args.target_model}",
        timeout_sec=30.0,
    )

    source_contract = _read_source_contract(root)
    live_probe = (
        _probe_live_deploy(base_url=base_url, target_model=args.target_model)
        if args.probe_deploy
        else {
            "attempted": False,
            "reason": "skipped_probe_deploy",
        }
    )

    report.update(
        {
            "endpoint_status": {
                "runtime_options": code,
                "adapters_audit": adapters_audit_code,
            },
            "target_model_trainable_entry": trainable_entry,
            "runtime_compatibility": runtime_compatibility,
            "onnx_runtime_target_supported": bool(runtime_compatibility.get("onnx")),
            "academy_adapters_audit": adapters_audit_payload,
            "source_contract": source_contract,
            "live_deploy_probe": live_probe,
            "lora_pipeline_path_assessment": {
                "direct_adapter_deploy_to_onnx": False,
                "indirect_train_merge_convert_infer_path": "requires external conversion flow validation",
            },
            "contract_table": {
                "trainable_base_model_present": trainable_entry is not None,
                "onnx_runtime_compatibility_flag": bool(
                    runtime_compatibility.get("onnx")
                ),
                "adapter_deploy_runtime_supported": False,
                "adapter_runtime_reason_code_present": bool(
                    source_contract.get("signals", {}).get(
                        "onnx_runtime_not_supported_reason_present"
                    )
                ),
            },
        }
    )

    dump_json((root / args.json_output).resolve(), report)
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
