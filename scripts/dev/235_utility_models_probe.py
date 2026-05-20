#!/usr/bin/env python3
"""PR235 probe for chat utility model settings contract.

Validates whether VS Code settings define separate utility models for chat
lightweight flows (`chat.utilityModel`, `chat.utilitySmallModel`).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class ProbeResult:
    verdict: str
    issues: list[str]
    settings_path: str
    utility_model: str | None
    utility_small_model: str | None
    operator_model: str | None


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "settings_file_missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"settings_json_invalid:{exc.msg}"
    if not isinstance(payload, dict):
        return None, "settings_root_not_object"
    return payload, None


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _probe(settings: dict[str, Any], settings_path: Path) -> ProbeResult:
    utility_model = settings.get("chat.utilityModel")
    utility_small_model = settings.get("chat.utilitySmallModel")
    operator_model = settings.get("chat.model")

    issues: list[str] = []
    if not _non_empty(utility_model):
        issues.append("chat.utilityModel_missing_or_empty")
    if not _non_empty(utility_small_model):
        issues.append("chat.utilitySmallModel_missing_or_empty")

    if _non_empty(utility_model) and _non_empty(utility_small_model):
        if str(utility_model).strip() == str(utility_small_model).strip():
            issues.append("utility_and_utility_small_models_are_identical")

    if _non_empty(operator_model):
        op = str(operator_model).strip()
        if _non_empty(utility_model) and op == str(utility_model).strip():
            issues.append("operator_model_equals_utility_model")
        if _non_empty(utility_small_model) and op == str(utility_small_model).strip():
            issues.append("operator_model_equals_utility_small_model")

    verdict = "pass" if not issues else "fail"
    return ProbeResult(
        verdict=verdict,
        issues=issues,
        settings_path=str(settings_path),
        utility_model=str(utility_model).strip() if _non_empty(utility_model) else None,
        utility_small_model=(
            str(utility_small_model).strip()
            if _non_empty(utility_small_model)
            else None
        ),
        operator_model=str(operator_model).strip()
        if _non_empty(operator_model)
        else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="PR235 utility models settings probe")
    parser.add_argument("--settings-file", default=".vscode/settings.json")
    parser.add_argument(
        "--json-output", default="test-results/235/utility_models_probe.json"
    )
    parser.add_argument(
        "--md-output", default="test-results/235/utility_models_probe.md"
    )
    args = parser.parse_args()

    settings_path = (REPO_ROOT / args.settings_file).resolve()
    settings, load_error = _load_json(settings_path)

    if load_error:
        result = ProbeResult(
            verdict="fail",
            issues=[load_error],
            settings_path=str(settings_path),
            utility_model=None,
            utility_small_model=None,
            operator_model=None,
        )
    else:
        assert settings is not None
        result = _probe(settings, settings_path)

    report = {
        "scope": "pr235-chat-utility-models-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "result": {
            "verdict": result.verdict,
            "issues": result.issues,
            "settings_path": result.settings_path,
            "chat.utilityModel": result.utility_model,
            "chat.utilitySmallModel": result.utility_small_model,
            "chat.model": result.operator_model,
        },
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR235 Utility Models Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Settings file: `{result.settings_path}`",
        "",
        "## Verdict",
        f"- verdict: `{result.verdict}`",
        f"- chat.utilityModel: `{result.utility_model}`",
        f"- chat.utilitySmallModel: `{result.utility_small_model}`",
        f"- chat.model: `{result.operator_model}`",
        "",
        "## Issues",
    ]
    if result.issues:
        for issue in result.issues:
            md_lines.append(f"- `{issue}`")
    else:
        md_lines.append("- `<none>`")

    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")

    return 0 if result.verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
