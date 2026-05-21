#!/usr/bin/env python3
"""PR242 probe: AS-IS routing matrix snapshot for native-web and VS Code chat."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(path: str) -> str:
    file_path = REPO_ROOT / path
    return file_path.read_text(encoding="utf-8") if file_path.exists() else ""


def _case(
    channel: str,
    prompt: str,
    expected_route: str,
    route_detected: bool,
    evidence_detected: bool,
    summary_detected: bool,
    note: str,
) -> dict[str, object]:
    passed = route_detected and evidence_detected and summary_detected
    return {
        "channel": channel,
        "prompt": prompt,
        "expected_route": expected_route,
        "route_detected": route_detected,
        "evidence_detected": evidence_detected,
        "summary_detected": summary_detected,
        "result": "PASS" if passed else "FAIL",
        "note": note,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PR242 AS-IS routing matrix probe")
    parser.add_argument(
        "--json-output",
        default="test-results/242/as_is_routing_matrix.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/242/as_is_routing_matrix.md",
    )
    args = parser.parse_args()

    integrator_text = _load("venom_core/agents/integrator.py")
    extension_text = _load("tools/vscode-chat-executor/src/extension.ts")
    extension_core_text = _load(
        "tools/vscode-chat-executor/src/core/command-execution.ts"
    )
    chat_send_text = _load("web-next/components/cockpit/chat-send-helpers.ts")

    cases: list[dict[str, object]] = [
        _case(
            channel="native-web",
            prompt="sprawdz status git",
            expected_route="repo_truth_fast_path",
            route_detected="sprawdz status git" in integrator_text,
            evidence_detected="REPO_ROOT=" in integrator_text,
            summary_detected="Interpretacja:" in integrator_text,
            note="Static check of IntegratorAgent repo-truth formatter.",
        ),
        _case(
            channel="native-web",
            prompt="sprawd status git",
            expected_route="repo_truth_typo_tolerant",
            route_detected="sprawd status git" in integrator_text,
            evidence_detected="REPO_ROOT=" in integrator_text,
            summary_detected="Interpretacja:" in integrator_text,
            note="Typo-tolerant marker should be explicitly supported.",
        ),
        _case(
            channel="native-web",
            prompt="sprawdz wersje pythona",
            expected_route="command_execution_loop",
            route_detected="forcedIntent" in chat_send_text,
            evidence_detected="duration_seconds" in chat_send_text,
            summary_detected="steps" in chat_send_text,
            note="Current UI path stores metadata but does not prove executor loop yet.",
        ),
        _case(
            channel="vscode-chat",
            prompt="@venom-agent sprawdz status git",
            expected_route="venom_git_status",
            route_detected=(
                "venom_git_status" in extension_text
                or "venom_git_status" in extension_core_text
            ),
            evidence_detected=(
                "REPO_ROOT=" in extension_text or "REPO_ROOT=" in extension_core_text
            ),
            summary_detected=(
                "Nie generuj listy komend jako finalnej odpowiedzi" in extension_text
                or "Nie generuj listy komend jako finalnej odpowiedzi"
                in extension_core_text
            ),
            note="Static check for participant tool and response contract text.",
        ),
    ]

    verdict = "pass" if all(c["result"] == "PASS" for c in cases) else "fail"
    result = {
        "scope": "pr242-as-is-routing-matrix",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "cases": cases,
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR242 AS-IS Routing Matrix",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "| channel | prompt | expected_route | route | evidence | summary | result | note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in cases:
        md_lines.append(
            "| {channel} | {prompt} | {expected_route} | {route} | {evidence} | {summary} | {result} | {note} |".format(
                channel=case["channel"],
                prompt=case["prompt"],
                expected_route=case["expected_route"],
                route="yes" if case["route_detected"] else "no",
                evidence="yes" if case["evidence_detected"] else "no",
                summary="yes" if case["summary_detected"] else "no",
                result=case["result"],
                note=case["note"],
            )
        )
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
