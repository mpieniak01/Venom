#!/usr/bin/env python3
"""202C decision aggregator: ONNX-first go/no-go recommendation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import dump_json, dump_text


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C decision report aggregator")
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--inventory-json",
        default="test-results/202c/runtime_inventory.json",
    )
    parser.add_argument(
        "--functional-json",
        default="test-results/202c/gemma3_functional_parity.json",
    )
    parser.add_argument(
        "--perf-json",
        default="test-results/202c/perf_onnx_vs_ollama.json",
    )
    parser.add_argument(
        "--soak-json",
        default="test-results/202c/switch_soak_report.json",
    )
    parser.add_argument(
        "--lora-json",
        default="test-results/202c/lora_contract_audit.json",
    )
    parser.add_argument(
        "--functional-judge-json",
        default="test-results/202c2/functional_semantic_parity_judge.json",
    )
    parser.add_argument(
        "--automation-matrix-json",
        default="test-results/202c4/automation_perf_matrix.json",
    )
    parser.add_argument(
        "--json-output",
        default="test-results/202c/decision_report.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/202c/decision_report.md",
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


def _to_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _recommendation(
    *,
    quality_ok: bool,
    success_ok: bool,
    perf_ok: bool,
    soak_ok: bool,
    lora_gap: bool,
) -> tuple[str, str]:
    if quality_ok and success_ok and perf_ok and soak_ok and not lora_gap:
        return "A", "ONNX-first now"
    if quality_ok and success_ok and perf_ok and soak_ok and lora_gap:
        return "C", "ONNX for selected workloads only"
    return "B", "3-stack with ONNX growth"


def _build_md(report: dict[str, Any]) -> str:
    gates = report.get("gates", {})
    recommendation = report.get("recommendation", {})
    lines: list[str] = []
    lines.append("# 202C Decision Report")
    lines.append("")
    lines.append(f"Generated at: {report.get('generated_at', '')}")
    lines.append(
        f"Recommendation: {recommendation.get('code', '')} - {recommendation.get('label', '')}"
    )
    lines.append("")
    lines.append("## Gates")
    lines.append("")
    for key, value in gates.items():
        lines.append(f"- {key}: {'pass' if value else 'fail'}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for note in report.get("notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()

    inventory = _safe_load((root / args.inventory_json).resolve())
    functional = _safe_load((root / args.functional_json).resolve())
    perf = _safe_load((root / args.perf_json).resolve())
    soak = _safe_load((root / args.soak_json).resolve())
    lora = _safe_load((root / args.lora_json).resolve())
    functional_judge = _safe_load((root / args.functional_judge_json).resolve())
    automation_matrix = _safe_load((root / args.automation_matrix_json).resolve())

    quality_parity = _to_float(
        functional.get("metrics", {}).get("quality_parity_score"),
        0.0,
    )
    success_delta = _to_float(
        functional.get("metrics", {}).get("task_success_rate", {}).get("delta"),
        -1.0,
    )
    p95_ratio = _to_float(
        perf.get("derived", {}).get("p95_ratio_candidate_vs_baseline"),
        99.0,
    )
    judge_equivalent_rate = _to_float(
        functional_judge.get("metrics", {})
        .get("judge_metrics", {})
        .get("equivalent_rate"),
        0.0,
    )
    automation_best_ratio = _to_float(
        automation_matrix.get("best_profile", {}).get("p95_ratio"),
        99.0,
    )

    soak_critical = soak.get("critical_failures")
    soak_ok = isinstance(soak_critical, list) and len(soak_critical) == 0

    lora_contract = lora.get("contract_table", {}) if isinstance(lora, dict) else {}
    lora_gap = not bool(lora_contract.get("onnx_runtime_compatibility_flag"))

    gates = {
        "quality_parity_ge_0_95": quality_parity >= 0.95,
        "judge_equivalent_rate_ge_0_80": judge_equivalent_rate >= 0.80,
        "task_success_delta_ge_-0_02": success_delta >= -0.02,
        "p95_latency_ratio_le_1_25": p95_ratio <= 1.25,
        "automation_best_ratio_le_1_25": automation_best_ratio <= 1.25,
        "switch_soak_no_critical_failures": soak_ok,
        "lora_runtime_contract_closed": not lora_gap,
    }

    rec_code, rec_label = _recommendation(
        quality_ok=(
            gates["quality_parity_ge_0_95"] or gates["judge_equivalent_rate_ge_0_80"]
        ),
        success_ok=gates["task_success_delta_ge_-0_02"],
        perf_ok=(
            gates["p95_latency_ratio_le_1_25"] or gates["automation_best_ratio_le_1_25"]
        ),
        soak_ok=gates["switch_soak_no_critical_failures"],
        lora_gap=lora_gap,
    )

    notes: list[str] = []
    if inventory.get("_missing"):
        notes.append("Missing runtime inventory report.")
    if functional.get("_missing"):
        notes.append("Missing functional parity report.")
    if perf.get("_missing"):
        notes.append("Missing performance report.")
    if soak.get("_missing"):
        notes.append("Missing switch soak report.")
    if lora.get("_missing"):
        notes.append("Missing LoRA contract audit report.")
    if functional_judge.get("_missing"):
        notes.append("Missing judge-based functional parity report.")
    if automation_matrix.get("_missing"):
        notes.append("Missing automation tuning matrix report.")
    if lora_gap:
        notes.append(
            "LoRA ONNX deploy contract remains open (expected in current architecture)."
        )
    if gates["judge_equivalent_rate_ge_0_80"]:
        notes.append(
            "Judge-based parity for ONNX is acceptable for selected workloads."
        )
    if gates["automation_best_ratio_le_1_25"]:
        notes.append(
            "Automation workload meets p95 ratio target with tuned ONNX profile."
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gates": gates,
        "derived": {
            "quality_parity_score": quality_parity,
            "judge_equivalent_rate": judge_equivalent_rate,
            "global_p95_ratio": p95_ratio,
            "automation_best_ratio": automation_best_ratio,
        },
        "recommendation": {
            "code": rec_code,
            "label": rec_label,
        },
        "inputs": {
            "inventory": inventory,
            "functional": functional,
            "functional_judge": functional_judge,
            "perf": perf,
            "soak": soak,
            "lora": lora,
            "automation_matrix": automation_matrix,
        },
        "notes": notes,
    }

    json_path = (root / args.json_output).resolve()
    md_path = (root / args.md_output).resolve()
    dump_json(json_path, report)
    dump_text(md_path, _build_md(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
