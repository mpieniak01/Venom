#!/usr/bin/env python3
"""202C Gemma-3 functional parity: Ollama baseline vs ONNX candidate."""

from __future__ import annotations

import argparse
import difflib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import (
    activate_runtime,
    contains_policy_block,
    dump_json,
    get_active_runtime,
    http_json,
    load_prompts_jsonl,
    normalize_text,
    pick_gemma3_model_with_reason,
    resolve_base_url,
    semantic_similarity_heuristic,
    stream_simple_chat,
    wait_backend_ready,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C Gemma-3 functional parity")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--baseline-runtime", default="ollama")
    parser.add_argument("--candidate-runtime", default="onnx")
    parser.add_argument(
        "--prompts",
        default="tests/data/202c/gemma3_eval_prompts.jsonl",
    )
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--json-output",
        default="test-results/202c/gemma3_functional_parity.json",
    )
    parser.add_argument("--exact-match-threshold", type=float, default=0.85)
    parser.add_argument("--semantic-match-threshold", type=float, default=0.55)
    parser.add_argument("--hard-semantic-kpi", type=float, default=0.90)
    parser.add_argument(
        "--judge-runtime",
        default="",
        help="Optional runtime for LLM-as-judge scoring, e.g. ollama",
    )
    parser.add_argument("--judge-max-samples", type=int, default=0)
    return parser.parse_args()


def _run_runtime_generation(
    *,
    base_url: str,
    runtime_id: str,
    model_name: str,
    prompts: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    ok, message, activation_payload = activate_runtime(base_url, runtime_id, model_name)
    if not ok:
        return {
            "runtime_id": runtime_id,
            "selected_model": model_name,
            "activation_ok": False,
            "activation_message": message,
            "activation_payload": activation_payload,
            "results": [],
        }

    results: list[dict[str, Any]] = []
    for item in prompts:
        response = stream_simple_chat(
            base_url,
            prompt=item["prompt"],
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        results.append(
            {
                "id": item["id"],
                "category": item["category"],
                "ok": response.ok,
                "latency_ms": round(response.latency_ms, 2),
                "event_count": response.event_count,
                "error": response.error,
                "response": response.text,
            }
        )
    return {
        "runtime_id": runtime_id,
        "selected_model": model_name,
        "activation_ok": True,
        "activation_message": "ok",
        "activation_payload": activation_payload,
        "results": results,
    }


def _index_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("id") or "").strip()
        if key:
            out[key] = item
    return out


def _llm_judge_sample(
    *,
    base_url: str,
    judge_model: str,
    prompt: str,
    baseline: str,
    candidate: str,
) -> dict[str, Any]:
    judge_prompt = (
        "You are a strict semantic evaluator.\n"
        'Return only JSON: {"score": <0..1>, "label": "equivalent|different", "reason": "..."}.\n'
        "Task prompt:\n"
        f"{prompt}\n\n"
        "Baseline answer:\n"
        f"{baseline}\n\n"
        "Candidate answer:\n"
        f"{candidate}\n"
    )
    result = stream_simple_chat(
        base_url,
        prompt=judge_prompt,
        model=judge_model,
        max_tokens=180,
        temperature=0.0,
        timeout_sec=120.0,
    )
    if not result.ok:
        return {
            "ok": False,
            "score": 0.0,
            "label": "error",
            "reason": result.error or "judge_failed",
        }
    payload = result.text.strip()

    def _try_parse_json(raw: str) -> Any | None:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    parsed = _try_parse_json(payload)
    if parsed is None:
        # Common judge outputs include fenced JSON blocks.
        fenced = re.search(
            r"```(?:json)?\s*(.*?)\s*```", payload, re.IGNORECASE | re.DOTALL
        )
        if fenced:
            parsed = _try_parse_json(fenced.group(1).strip())

    if parsed is None:
        # Fallback: try the first object/array-like fragment.
        obj_match = re.search(r"(\{[\s\S]*\})", payload)
        arr_match = re.search(r"(\[[\s\S]*\])", payload)
        fragment = (
            obj_match.group(1)
            if obj_match
            else (arr_match.group(1) if arr_match else "")
        )
        if fragment:
            parsed = _try_parse_json(fragment)

    if parsed is None:
        return {
            "ok": False,
            "score": 0.0,
            "label": "unparseable",
            "reason": payload[:240],
        }
    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "score": 0.0,
            "label": "unparseable",
            "reason": payload[:240],
        }
    score = 0.0
    try:
        score = float(parsed.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    return {
        "ok": True,
        "score": max(0.0, min(1.0, score)),
        "label": str(parsed.get("label") or ""),
        "reason": str(parsed.get("reason") or ""),
    }


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[2]
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (root / env_file).resolve()

    base_url = resolve_base_url(env_file=env_file, explicit=args.base_url)
    prompts_path = (root / args.prompts).resolve()
    prompts = load_prompts_jsonl(prompts_path)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "baseline_runtime": args.baseline_runtime,
        "candidate_runtime": args.candidate_runtime,
        "prompts_path": str(prompts_path),
        "prompt_count": len(prompts),
        "metrics": {},
        "comparisons": [],
        "errors": [],
    }

    if not wait_backend_ready(base_url, timeout_sec=30):
        report["errors"].append("backend_not_ready")
        dump_json((root / args.json_output).resolve(), report)
        return 1

    options_code, options_payload = http_json(
        f"{base_url}/api/v1/system/llm-runtime/options", timeout_sec=30.0
    )
    if options_code != 200 or not isinstance(options_payload, dict):
        report["errors"].append("runtime_options_unavailable")
        dump_json((root / args.json_output).resolve(), report)
        return 1

    baseline_model, baseline_model_selection = pick_gemma3_model_with_reason(
        options_payload, args.baseline_runtime
    )
    candidate_model, candidate_model_selection = pick_gemma3_model_with_reason(
        options_payload, args.candidate_runtime
    )
    if not baseline_model:
        report["errors"].append("baseline_model_missing")
    if not candidate_model:
        report["errors"].append("candidate_model_missing")
    if report["errors"]:
        dump_json((root / args.json_output).resolve(), report)
        return 1

    baseline_result = _run_runtime_generation(
        base_url=base_url,
        runtime_id=args.baseline_runtime,
        model_name=str(baseline_model),
        prompts=prompts,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    candidate_result = _run_runtime_generation(
        base_url=base_url,
        runtime_id=args.candidate_runtime,
        model_name=str(candidate_model),
        prompts=prompts,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    baseline_map = _index_by_id(baseline_result.get("results", []))
    candidate_map = _index_by_id(candidate_result.get("results", []))

    compared = 0
    exact_matched = 0
    semantic_matched = 0
    policy_blocks_baseline = 0
    policy_blocks_candidate = 0
    empty_baseline = 0
    empty_candidate = 0
    success_baseline = 0
    success_candidate = 0
    category_stats: dict[str, dict[str, int]] = {}
    judge_total = 0
    judge_ok = 0
    judge_equivalent = 0
    judge_score_sum = 0.0

    judge_runtime = args.judge_runtime.strip().lower()
    judge_model = ""
    judge_selection: dict[str, Any] = {}
    judge_samples_left = max(0, int(args.judge_max_samples))
    judge_activation: dict[str, Any] | None = None
    if judge_runtime:
        judge_model, judge_selection = pick_gemma3_model_with_reason(
            options_payload, judge_runtime
        )
        if judge_model and judge_samples_left > 0:
            j_ok, j_msg, j_payload = activate_runtime(
                base_url, judge_runtime, judge_model
            )
            judge_activation = {
                "ok": j_ok,
                "message": j_msg,
                "payload": j_payload,
            }
            if not j_ok:
                report["errors"].append("judge_runtime_activation_failed")
                judge_model = ""
                judge_samples_left = 0

    for prompt in prompts:
        prompt_id = prompt["id"]
        b = baseline_map.get(prompt_id, {})
        c = candidate_map.get(prompt_id, {})

        b_text = str(b.get("response") or "")
        c_text = str(c.get("response") or "")
        b_norm = normalize_text(b_text)
        c_norm = normalize_text(c_text)

        exact_similarity = (
            difflib.SequenceMatcher(a=b_norm, b=c_norm).ratio()
            if (b_norm or c_norm)
            else 0.0
        )
        semantic_similarity = semantic_similarity_heuristic(b_text, c_text)
        exact_match = exact_similarity >= args.exact_match_threshold
        semantic_match = semantic_similarity >= args.semantic_match_threshold
        mismatch_reason = ""
        if not semantic_match:
            if exact_similarity < 0.20 and semantic_similarity < 0.20:
                mismatch_reason = "major_content_divergence"
            elif semantic_similarity < args.semantic_match_threshold:
                mismatch_reason = "semantic_below_threshold"

        compared += 1
        if exact_match:
            exact_matched += 1
        if semantic_match:
            semantic_matched += 1

        b_ok = bool(b.get("ok"))
        c_ok = bool(c.get("ok"))
        if b_ok:
            success_baseline += 1
        if c_ok:
            success_candidate += 1

        if contains_policy_block(b_text):
            policy_blocks_baseline += 1
        if contains_policy_block(c_text):
            policy_blocks_candidate += 1

        if not b_text.strip():
            empty_baseline += 1
        if not c_text.strip():
            empty_candidate += 1

        category = str(prompt.get("category") or "general")
        stats = category_stats.setdefault(
            category,
            {"count": 0, "exact_match": 0, "semantic_match": 0},
        )
        stats["count"] += 1
        if exact_match:
            stats["exact_match"] += 1
        if semantic_match:
            stats["semantic_match"] += 1

        judge_payload: dict[str, Any] | None = None
        if judge_runtime and judge_model and judge_samples_left > 0:
            judge_payload = _llm_judge_sample(
                base_url=base_url,
                judge_model=judge_model,
                prompt=prompt["prompt"],
                baseline=b_text,
                candidate=c_text,
            )
            judge_total += 1
            if judge_payload.get("ok"):
                judge_ok += 1
                judge_score = float(judge_payload.get("score") or 0.0)
                judge_score_sum += judge_score
                if (
                    judge_score >= 0.7
                    or str(judge_payload.get("label") or "").strip().lower()
                    == "equivalent"
                ):
                    judge_equivalent += 1
            judge_samples_left -= 1

        report["comparisons"].append(
            {
                "id": prompt_id,
                "category": prompt["category"],
                "exact_similarity": round(exact_similarity, 4),
                "semantic_similarity": round(semantic_similarity, 4),
                "exact_match": exact_match,
                "semantic_match": semantic_match,
                "mismatch_reason": mismatch_reason or None,
                "baseline": {
                    "ok": b_ok,
                    "latency_ms": b.get("latency_ms"),
                    "policy_block": contains_policy_block(b_text),
                    "empty": not bool(b_text.strip()),
                    "error": b.get("error"),
                },
                "candidate": {
                    "ok": c_ok,
                    "latency_ms": c.get("latency_ms"),
                    "policy_block": contains_policy_block(c_text),
                    "empty": not bool(c_text.strip()),
                    "error": c.get("error"),
                },
                "judge": judge_payload,
            }
        )

    exact_match_rate = (exact_matched / compared) if compared else 0.0
    semantic_match_rate = (semantic_matched / compared) if compared else 0.0
    baseline_policy_rate = (policy_blocks_baseline / compared) if compared else 0.0
    candidate_policy_rate = (policy_blocks_candidate / compared) if compared else 0.0
    baseline_empty_rate = (empty_baseline / compared) if compared else 0.0
    candidate_empty_rate = (empty_candidate / compared) if compared else 0.0

    report["baseline_run"] = baseline_result
    report["candidate_run"] = candidate_result
    report["model_selection"] = {
        "baseline": baseline_model_selection,
        "candidate": candidate_model_selection,
        "judge": judge_selection if judge_runtime else None,
    }
    report["judge_activation"] = judge_activation
    report["metrics"] = {
        "compared": compared,
        "exact_match_threshold": args.exact_match_threshold,
        "semantic_match_threshold": args.semantic_match_threshold,
        "exact_match_rate": round(exact_match_rate, 4),
        "semantic_match_rate": round(semantic_match_rate, 4),
        "quality_parity_score": round(semantic_match_rate, 4),
        "policy_block_rate": {
            "baseline": round(baseline_policy_rate, 4),
            "candidate": round(candidate_policy_rate, 4),
            "delta": round(candidate_policy_rate - baseline_policy_rate, 4),
        },
        "empty_response_rate": {
            "baseline": round(baseline_empty_rate, 4),
            "candidate": round(candidate_empty_rate, 4),
            "delta": round(candidate_empty_rate - baseline_empty_rate, 4),
        },
        "task_success_rate": {
            "baseline": round((success_baseline / compared) if compared else 0.0, 4),
            "candidate": round((success_candidate / compared) if compared else 0.0, 4),
            "delta": round(
                ((success_candidate - success_baseline) / compared)
                if compared
                else 0.0,
                4,
            ),
        },
        "kpi_pass": {
            "semantic_match_rate": semantic_match_rate >= args.hard_semantic_kpi,
            "empty_response_delta_le_0_01": (candidate_empty_rate - baseline_empty_rate)
            <= 0.01,
            "task_success_delta_ge_-0_02": (
                (success_candidate - success_baseline) / compared if compared else 0.0
            )
            >= -0.02,
        },
        "category_metrics": {
            category: {
                "count": stats["count"],
                "exact_match_rate": round(
                    (stats["exact_match"] / stats["count"]) if stats["count"] else 0.0,
                    4,
                ),
                "semantic_match_rate": round(
                    (stats["semantic_match"] / stats["count"])
                    if stats["count"]
                    else 0.0,
                    4,
                ),
            }
            for category, stats in category_stats.items()
        },
        "judge_metrics": {
            "enabled": bool(judge_runtime and judge_model),
            "runtime": judge_runtime if judge_runtime else None,
            "samples_requested": max(0, int(args.judge_max_samples)),
            "samples_scored": judge_total,
            "ok_count": judge_ok,
            "equivalent_count": judge_equivalent,
            "equivalent_rate": round(
                (judge_equivalent / judge_total) if judge_total else 0.0, 4
            ),
            "mean_score": round((judge_score_sum / judge_ok) if judge_ok else 0.0, 4),
        },
    }

    active_code, active_payload = get_active_runtime(base_url)
    report["active_after_run"] = (
        active_payload if active_code == 200 else {"status": active_code}
    )

    output_path = (root / args.json_output).resolve()
    dump_json(output_path, report)

    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
