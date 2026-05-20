#!/usr/bin/env python3
"""PR233A feedback-analysis probe for local models."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MODELS = [
    "deepseek-r1:8b",
    "qwen2.5-coder:7b",
    "gemma4:latest",
]

PROMPT = (
    "Przeanalizuj feedback code review i zwroc TYLKO JSON: "
    "{overall_assessment:string, issues:[{id,severity,root_cause,fix}], tests:[string], confidence:0..1}. "
    "Feedback: 'Regression: switch runtime zapisuje config zanim probe potwierdzi lifecycle; "
    "brak retry guard; brak testu dla rollback po failed switch.'"
)

EXPECTED = ["lifecycle", "retry", "rollback"]


def _call_model(base_url: str, model: str, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": PROMPT,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    started = time.time()
    out: dict[str, Any] = {
        "model": model,
        "ok": False,
        "valid_schema": False,
        "coverage_3": 0,
        "issues_count": 0,
        "tests_count": 0,
        "latency_sec": 0.0,
        "error": "",
    }
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = str(body.get("response") or "").strip()
        out["ok"] = True
        if text:
            parsed = json.loads(text)
            out["valid_schema"] = all(
                k in parsed
                for k in ["overall_assessment", "issues", "tests", "confidence"]
            )
            if isinstance(parsed.get("issues"), list):
                out["issues_count"] = len(parsed["issues"])
            if isinstance(parsed.get("tests"), list):
                out["tests_count"] = len(parsed["tests"])
            blob = json.dumps(parsed, ensure_ascii=False).lower()
            out["coverage_3"] = sum(1 for key in EXPECTED if key in blob)
        else:
            out["error"] = "empty response"
    except (TimeoutError, urllib.error.URLError) as exc:
        out["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    finally:
        out["latency_sec"] = round(time.time() - started, 2)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe local models for feedback-analysis quality"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument(
        "--json-output",
        default="test-results/233a/local_feedback_probe.json",
    )
    args = parser.parse_args()

    results = [_call_model(args.base_url, model, args.timeout) for model in args.models]
    results.sort(
        key=lambda r: (
            r["valid_schema"],
            r["coverage_3"],
            r["issues_count"],
            -r["latency_sec"],
        ),
        reverse=True,
    )

    out_path = REPO_ROOT / args.json_output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
