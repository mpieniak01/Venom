#!/usr/bin/env python3
"""PR235 decision gate.

Aggregates probe outputs and validates the final local-agent architecture
decision contract for VS Code workflows.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"missing_file:{path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{path}:{exc.msg}"
    if not isinstance(payload, dict):
        return None, f"invalid_root:{path}"
    return payload, None


def _as_non_empty_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _collect_chat_stats(chat_report: dict[str, Any]) -> dict[str, int | bool]:
    cases = (
        chat_report.get("cases") if isinstance(chat_report.get("cases"), list) else []
    )
    total = len(cases)
    exact = 0
    refusal = 0
    hallucinated = 0
    skipped = 0
    tool_unavailable = 0
    for case in cases:
        if not isinstance(case, dict):
            continue
        summary = case.get("summary") if isinstance(case.get("summary"), dict) else {}
        exact += int(summary.get("exact_runs") or 0)
        refusal += int(summary.get("refusal_runs") or 0)
        hallucinated += int(summary.get("hallucinated_runs") or 0)
        skipped += int(summary.get("skipped_runs") or 0)
        tool_unavailable += int(summary.get("tool_unavailable_runs") or 0)
    return {
        "cases_total": total,
        "exact_runs": exact,
        "refusal_runs": refusal,
        "hallucinated_runs": hallucinated,
        "skipped_runs": skipped,
        "tool_unavailable_runs": tool_unavailable,
        "all_cases_skipped": bool(total > 0 and skipped == total),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PR235 decision gate")
    parser.add_argument(
        "--contract", default="config/chat_operator/decision_gate_contract.json"
    )
    parser.add_argument(
        "--chat-report", default="test-results/234/chat_diagnostics.json"
    )
    parser.add_argument(
        "--vscode-agent-report", default="test-results/235/vscode_agent_probe.json"
    )
    parser.add_argument(
        "--utility-report", default="test-results/235/utility_models_probe.json"
    )
    parser.add_argument(
        "--workspace-report", default="test-results/235/workspace_context_probe.json"
    )
    parser.add_argument("--strict-repo-truth", action="store_true")
    parser.add_argument("--json-output", default="test-results/235/decision_gate.json")
    parser.add_argument("--md-output", default="test-results/235/decision_gate.md")
    args = parser.parse_args()

    issues: list[str] = []
    risks: list[str] = []

    contract, err = _read_json(REPO_ROOT / args.contract)
    if err:
        issues.append(err)
        contract = {}

    chat_report, err = _read_json(REPO_ROOT / args.chat_report)
    if err:
        issues.append(err)
        chat_report = {}

    vscode_report, err = _read_json(REPO_ROOT / args.vscode_agent_report)
    if err:
        issues.append(err)
        vscode_report = {}

    utility_report, err = _read_json(REPO_ROOT / args.utility_report)
    if err:
        issues.append(err)
        utility_report = {}

    workspace_report, err = _read_json(REPO_ROOT / args.workspace_report)
    if err:
        issues.append(err)
        workspace_report = {}

    operator_model = _as_non_empty_str(
        (contract or {}).get("operator_model_local_first")
    )
    utility_strategy = _as_non_empty_str((contract or {}).get("utility_model_strategy"))
    utility_model = _as_non_empty_str((contract or {}).get("utility_model"))
    utility_small_model = _as_non_empty_str((contract or {}).get("utility_small_model"))
    agents_window_policy = _as_non_empty_str(
        (contract or {}).get("agents_window_policy")
    )
    repo_truth_policy = _as_non_empty_str((contract or {}).get("repo_truth_policy"))

    if not operator_model:
        issues.append("contract.operator_model_local_first_missing")
    if utility_strategy not in {"copilot-defaults", "local-models"}:
        issues.append("contract.utility_model_strategy_invalid")
    if not utility_model:
        issues.append("contract.utility_model_missing")
    if not utility_small_model:
        issues.append("contract.utility_small_model_missing")
    if utility_model and utility_small_model and utility_model == utility_small_model:
        issues.append("contract.utility_models_identical")
    if agents_window_policy not in {"supported-sessions-only", "supported-and-remote"}:
        issues.append("contract.agents_window_policy_invalid")
    if repo_truth_policy not in {"tool-first-required", "model-direct-allowed"}:
        issues.append("contract.repo_truth_policy_invalid")

    vs_summary = (
        vscode_report.get("summary")
        if isinstance(vscode_report.get("summary"), dict)
        else {}
    )
    if int(vs_summary.get("failed") or 0) > 0:
        issues.append("vscode_agent_probe_failed")

    utility_result = (
        utility_report.get("result")
        if isinstance(utility_report.get("result"), dict)
        else {}
    )
    if utility_result.get("verdict") != "pass":
        issues.append("utility_models_probe_failed")

    workspace_result = (
        workspace_report.get("result")
        if isinstance(workspace_report.get("result"), dict)
        else {}
    )
    if workspace_result.get("verdict") != "pass":
        issues.append("workspace_context_probe_failed")

    chat_stats = _collect_chat_stats(chat_report)
    if chat_stats["cases_total"] == 0:
        issues.append("chat_diagnostics_missing_cases")
    if chat_stats["all_cases_skipped"]:
        risks.append("chat_diagnostics_currently_shell_only")
    if int(chat_stats["exact_runs"]) == 0:
        if args.strict_repo_truth:
            issues.append("no_exact_repo_truth_response_in_model_runs")
        else:
            risks.append("no_exact_repo_truth_response_in_model_runs")

    verdict = "pass" if not issues else "fail"

    result = {
        "scope": "pr235-decision-gate",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "issues": issues,
        "risks": risks,
        "decision": {
            "operator_model_local_first": operator_model,
            "utility_model_strategy": utility_strategy,
            "utility_model": utility_model,
            "utility_small_model": utility_small_model,
            "agents_window_policy": agents_window_policy,
            "repo_truth_policy": repo_truth_policy,
        },
        "inputs": {
            "contract": str((REPO_ROOT / args.contract).resolve()),
            "chat_report": str((REPO_ROOT / args.chat_report).resolve()),
            "vscode_agent_report": str(
                (REPO_ROOT / args.vscode_agent_report).resolve()
            ),
            "utility_report": str((REPO_ROOT / args.utility_report).resolve()),
            "workspace_report": str((REPO_ROOT / args.workspace_report).resolve()),
        },
        "chat_stats": chat_stats,
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR235 Decision Gate",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "## Decision",
        f"- operator_model_local_first: `{operator_model}`",
        f"- utility_model_strategy: `{utility_strategy}`",
        f"- utility_model: `{utility_model}`",
        f"- utility_small_model: `{utility_small_model}`",
        f"- agents_window_policy: `{agents_window_policy}`",
        f"- repo_truth_policy: `{repo_truth_policy}`",
        "",
        "## Chat Stats",
        f"- cases_total: `{chat_stats['cases_total']}`",
        f"- exact_runs: `{chat_stats['exact_runs']}`",
        f"- refusal_runs: `{chat_stats['refusal_runs']}`",
        f"- hallucinated_runs: `{chat_stats['hallucinated_runs']}`",
        f"- skipped_runs: `{chat_stats['skipped_runs']}`",
        f"- tool_unavailable_runs: `{chat_stats['tool_unavailable_runs']}`",
        "",
        "## Issues",
    ]
    if issues:
        for issue in issues:
            md_lines.append(f"- `{issue}`")
    else:
        md_lines.append("- `<none>`")

    md_lines.extend(["", "## Risks"])
    if risks:
        for risk in risks:
            md_lines.append(f"- `{risk}`")
    else:
        md_lines.append("- `<none>`")

    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")

    return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
