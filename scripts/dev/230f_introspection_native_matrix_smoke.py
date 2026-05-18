"""PR230 Faza 6 live-smoke matrix: native vs proxy internals.

Usage:
  python scripts/dev/230f_introspection_native_matrix_smoke.py \
    --base-url http://127.0.0.1:8000 \
    --prompt "Co to jest słońce?" \
    --model "google/gemma-4-E2B-it:vllm" \
    --model "qwen3.5:latest:ollama"
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.dev.model_introspection_221b_utils import request_json  # noqa: E402


@dataclass(slots=True)
class MatrixTarget:
    name: str
    runtime: str | None


def _parse_target(raw: str) -> MatrixTarget:
    parts = [chunk.strip() for chunk in raw.split(":") if chunk.strip()]
    if not parts:
        raise ValueError("empty model target")
    if len(parts) == 1:
        return MatrixTarget(name=parts[0], runtime=None)
    runtime = parts[-1]
    model = ":".join(parts[:-1])
    return MatrixTarget(name=model, runtime=runtime)


def _classify_internals(snapshot_payload: dict[str, Any]) -> dict[str, str]:
    analysis = (
        snapshot_payload.get("analysis") if isinstance(snapshot_payload, dict) else {}
    )
    capabilities = analysis.get("capabilities") if isinstance(analysis, dict) else {}
    if not isinstance(capabilities, dict):
        return {"attention": "missing", "saliency": "missing", "logit_lens": "missing"}

    def _row(name: str) -> str:
        row = capabilities.get(name)
        if not isinstance(row, dict):
            return "missing"
        availability = str(row.get("availability_class") or "unknown")
        reason = str(row.get("reason") or "n/a")
        source = str(row.get("source") or "n/a")
        status = str(row.get("status") or "n/a")
        return f"{availability} (source={source}, status={status}, reason={reason})"

    return {
        "attention": _row("attention"),
        "saliency": _row("saliency"),
        "logit_lens": _row("logit_lens"),
    }


def _activate_model(
    base_url: str, target: MatrixTarget, *, token: str | None
) -> tuple[bool, dict[str, Any]]:
    if not target.runtime:
        return False, {"message": "activation skipped (runtime not provided)"}
    payload: dict[str, Any] = {
        "name": target.name,
        "runtime": target.runtime,
        "switch_source": "ui",
    }
    if token:
        payload["ownership_token"] = token
    status, data = request_json(
        f"{base_url}/api/v1/models/activate",
        method="POST",
        payload=payload,
        timeout_sec=60.0,
    )
    ok = status == 200 and isinstance(data, dict) and bool(data.get("success"))
    return ok, data if isinstance(data, dict) else {"raw": data}


def _run_analysis(base_url: str, prompt: str) -> tuple[bool, dict[str, Any]]:
    status, data = request_json(
        f"{base_url}/api/v1/models/introspection/analyze",
        method="POST",
        payload={
            "prompt": prompt,
            "live_analysis_enabled": True,
            "max_tokens": 256,
            "temperature": 0.2,
            "top_p": 0.9,
        },
        timeout_sec=120.0,
    )
    ok = status == 200 and isinstance(data, dict) and bool(data.get("success"))
    snapshot = data.get("snapshot") if isinstance(data, dict) else None
    return ok, snapshot if isinstance(snapshot, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PR230 Faza 6 native/proxy live-smoke matrix"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--prompt", default="Co to jest słońce?")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Format: model[:runtime], np. google/gemma-4-E2B-it:vllm",
    )
    parser.add_argument("--ownership-token", default=None)
    parser.add_argument(
        "--output-json",
        default="test-results/230f/introspection_native_matrix_smoke.json",
    )
    args = parser.parse_args()

    targets_raw: list[str] = args.model or [
        "google/gemma-4-E2B-it:vllm",
        "qwen3.5:latest:ollama",
    ]
    targets: list[MatrixTarget] = []
    base_url = str(args.base_url).rstrip("/")
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "base_url": base_url,
        "prompt": args.prompt,
        "targets": [],
        "errors": [],
    }
    for raw in targets_raw:
        try:
            targets.append(_parse_target(raw))
        except ValueError as exc:
            report["errors"].append(f"invalid_target:{raw}:{exc}")

    for target in targets:
        entry: dict[str, Any] = {
            "model": target.name,
            "runtime": target.runtime,
            "activate_ok": False,
            "analyze_ok": False,
            "internals": {},
        }
        activate_ok, activate_payload = _activate_model(
            base_url,
            target,
            token=args.ownership_token,
        )
        entry["activate_ok"] = activate_ok
        entry["activate_payload"] = activate_payload
        if not activate_ok:
            report["errors"].append(f"activate_failed:{target.name}:{target.runtime}")
            report["targets"].append(entry)
            continue

        analyze_ok, snapshot_payload = _run_analysis(base_url, args.prompt)
        entry["analyze_ok"] = analyze_ok
        entry["internals"] = _classify_internals(snapshot_payload) if analyze_ok else {}
        if analyze_ok:
            analysis = snapshot_payload.get("analysis")
            if isinstance(analysis, dict):
                entry["trace_id"] = analysis.get("trace_id")
                capabilities = analysis.get("capabilities")
                if isinstance(capabilities, dict):
                    entry["internals_verdict"] = capabilities.get("internals_verdict")
                    entry["proxy_active"] = capabilities.get("proxy_active")
                    entry["available_count"] = capabilities.get("available_count")
                    entry["native_available_count"] = capabilities.get(
                        "native_available_count"
                    )
        else:
            report["errors"].append(f"analyze_failed:{target.name}:{target.runtime}")
        report["targets"].append(entry)

    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved: {output_json}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
