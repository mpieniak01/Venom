#!/usr/bin/env python3
"""202C.1 ONNX model selection audit for Gemma-3 runtime diagnostics."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import (
    dump_json,
    dump_text,
    http_json,
    pick_gemma3_model_with_reason,
    resolve_base_url,
    runtime_models_from_options,
    wait_backend_ready,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C.1 ONNX model selection audit")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--runtime", default="onnx")
    parser.add_argument(
        "--json-output",
        default="test-results/202c1/onnx_model_selection_audit.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/202c1/onnx_model_selection_audit.md",
    )
    return parser.parse_args()


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 202C.1 ONNX Model Selection Audit")
    lines.append("")
    lines.append(f"Generated at: {report.get('generated_at', '')}")
    lines.append(f"Base URL: {report.get('base_url', '')}")
    lines.append("")
    lines.append("## Selected Model")
    lines.append("")
    lines.append(f"- runtime: {report.get('runtime', '')}")
    lines.append(f"- selected_model: {report.get('selected_model', '')}")
    lines.append(f"- selected_score: {report.get('selected_score', 0)}")
    lines.append("")
    lines.append("## Candidate Ranking")
    lines.append("")
    for item in report.get("candidates", []):
        lines.append(
            f"- {item.get('model', '')}: score={item.get('score', 0)} reasons={','.join(item.get('reasons', []))}"
        )
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(
        f"- selected_is_not_test_artifact: {'pass' if report.get('kpi', {}).get('selected_is_not_test_artifact') else 'fail'}"
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
        "runtime": args.runtime,
        "errors": [],
    }

    if not wait_backend_ready(base_url, timeout_sec=30):
        report["errors"].append("backend_not_ready")
        dump_json((root / args.json_output).resolve(), report)
        return 1

    code, options_payload = http_json(
        f"{base_url}/api/v1/system/llm-runtime/options",
        timeout_sec=30.0,
    )
    if code != 200 or not isinstance(options_payload, dict):
        report["errors"].append("runtime_options_unavailable")
        dump_json((root / args.json_output).resolve(), report)
        return 1

    selected, selection = pick_gemma3_model_with_reason(options_payload, args.runtime)
    models = runtime_models_from_options(options_payload, args.runtime)
    candidates = list(selection.get("candidates", []))
    selected_payload = next(
        (item for item in candidates if item.get("model") == selected),
        {},
    )
    selected_lower = str(selected or "").lower()
    is_not_test_artifact = (
        "build-test" not in selected_lower
        and "good--" not in selected_lower
        and "dummy" not in selected_lower
    )

    report.update(
        {
            "model_count": len(models),
            "selected_model": selected,
            "selected_score": int(selected_payload.get("score", 0) or 0),
            "selected_reasons": selected_payload.get("reasons", []),
            "candidates": candidates,
            "kpi": {
                "selected_is_not_test_artifact": is_not_test_artifact,
            },
        }
    )

    json_path = (root / args.json_output).resolve()
    md_path = (root / args.md_output).resolve()
    dump_json(json_path, report)
    dump_text(md_path, _build_markdown(report))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
