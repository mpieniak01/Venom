#!/usr/bin/env python3
"""202C.1 Generate LoRA->ONNX path PoC report from current audit artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import dump_json, dump_text


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C.1 LoRA to ONNX path PoC report")
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--lora-audit-json",
        default="test-results/202c/lora_contract_audit.json",
    )
    parser.add_argument(
        "--onnx-selection-json",
        default="test-results/202c1/onnx_model_selection_audit.json",
    )
    parser.add_argument(
        "--json-output",
        default="test-results/202c1/lora_to_onnx_path_poc.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/202c1/lora_to_onnx_path_poc.md",
    )
    return parser.parse_args()


def _safe_load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True, "_path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_error": str(exc), "_path": str(path)}
    if not isinstance(payload, dict):
        return {"_error": "payload_not_object", "_path": str(path)}
    return payload


def _build_md(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 202C.1 LoRA to ONNX Path PoC")
    lines.append("")
    lines.append(f"Generated at: {report.get('generated_at', '')}")
    lines.append("")
    lines.append("## Contract State")
    lines.append("")
    lines.append(
        f"- direct_adapter_deploy_to_onnx: {'supported' if report.get('contract', {}).get('direct_adapter_deploy_to_onnx') else 'not_supported'}"
    )
    lines.append(
        f"- onnx_runtime_compatibility_flag: {report.get('contract', {}).get('onnx_runtime_compatibility_flag')}"
    )
    lines.append("")
    lines.append("## Reproducible Path")
    lines.append("")
    for step in report.get("path_steps", []):
        lines.append(f"- {step}")
    lines.append("")
    lines.append("## Selected ONNX Target")
    lines.append("")
    lines.append(f"- model: {report.get('onnx_target', {}).get('selected_model', '')}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(
        f"- path_documented: {'pass' if report.get('kpi', {}).get('path_documented') else 'fail'}"
    )
    lines.append(
        f"- direct_deploy_gap_acknowledged: {'pass' if report.get('kpi', {}).get('direct_deploy_gap_acknowledged') else 'fail'}"
    )
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    lora_audit = _safe_load((root / args.lora_audit_json).resolve())
    onnx_selection = _safe_load((root / args.onnx_selection_json).resolve())

    contract_table = (
        lora_audit.get("contract_table", {}) if isinstance(lora_audit, dict) else {}
    )

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract": {
            "direct_adapter_deploy_to_onnx": bool(
                contract_table.get("adapter_deploy_runtime_supported")
            ),
            "onnx_runtime_compatibility_flag": bool(
                contract_table.get("onnx_runtime_compatibility_flag")
            ),
        },
        "onnx_target": {
            "selected_model": onnx_selection.get("selected_model"),
            "selected_reasons": onnx_selection.get("selected_reasons", []),
        },
        "path_steps": [
            "Train LoRA on HF base model (gemma-3-4b-it) outside ONNX runtime.",
            "Merge adapter with base model to produce merged HF checkpoint.",
            "Convert merged checkpoint to ONNX artifact using approved export path.",
            "Register ONNX artifact in local model registry and select it as ONNX runtime model.",
            "Run functional and performance validation on ONNX runtime before rollout.",
        ],
        "kpi": {
            "path_documented": True,
            "direct_deploy_gap_acknowledged": not bool(
                contract_table.get("adapter_deploy_runtime_supported")
            ),
        },
        "inputs": {
            "lora_audit": lora_audit,
            "onnx_selection": onnx_selection,
        },
    }

    json_path = (root / args.json_output).resolve()
    md_path = (root / args.md_output).resolve()
    dump_json(json_path, report)
    dump_text(md_path, _build_md(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
