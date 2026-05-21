#!/usr/bin/env python3
"""PR242 probe: native chat execution path and repo-root anchors."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel_path: str) -> str:
    path = REPO_ROOT / rel_path
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="PR242 native chat probe")
    parser.add_argument(
        "--json-output",
        default="test-results/242/native_chat_probe.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/242/native_chat_probe.md",
    )
    args = parser.parse_args()

    issues: list[str] = []
    integrator = _read("venom_core/agents/integrator.py")
    dispatcher = _read("venom_core/core/dispatcher.py")
    chat_helpers = _read("web-next/components/cockpit/chat-send-helpers.ts")

    if "sprawdz status git" not in integrator:
        issues.append("integrator_missing_repo_truth_marker")
    if "sprawd status git" not in integrator:
        issues.append("integrator_missing_typo_marker_sprawd_status_git")
    if "REPO_ROOT=" not in integrator:
        issues.append("integrator_missing_repo_root_output")
    if "get_short_status" not in integrator:
        issues.append("integrator_missing_get_short_status_call")
    if "VERSION_CONTROL" not in dispatcher:
        issues.append("dispatcher_missing_version_control_route")
    if "forcedIntent" not in chat_helpers:
        issues.append("chat_helpers_missing_forced_intent_signal")

    verdict = "pass" if not issues else "fail"
    result = {
        "scope": "pr242-native-chat-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "issues": issues,
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR242 Native Chat Probe",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "## Issues",
    ]
    if issues:
        md_lines.extend(f"- `{issue}`" for issue in issues)
    else:
        md_lines.append("- `<none>`")
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
