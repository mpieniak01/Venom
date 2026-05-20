#!/usr/bin/env python3
"""Validate Venom agent configuration files and prompt contracts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    print(
        "ERROR: PyYAML is required to run scripts/dev/233c_agent_config_validate.py.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / ".github" / "agents"
PROMPTS_DIR = REPO_ROOT / ".github" / "prompts"
INSTRUCTIONS_DIR = REPO_ROOT / ".github" / "instructions"
REPORT_DIR = REPO_ROOT / "test-results" / "233c"

ALLOWED_AGENT_TARGETS = {"vscode", "github-copilot"}


@dataclass(slots=True)
class Violation:
    path: str
    severity: str
    code: str
    message: str


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str, list[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text, ["missing_frontmatter"]

    end_index = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_index = idx
            break

    if end_index is None:
        return None, "", ["unterminated_frontmatter"]

    raw_frontmatter = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :]).strip()
    try:
        payload = yaml.safe_load(raw_frontmatter) or {}
    except Exception as exc:  # noqa: BLE001
        return None, body, [f"invalid_yaml:{exc}"]

    if not isinstance(payload, dict):
        return None, body, ["frontmatter_not_mapping"]

    return payload, body, []


def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_string_list(
    value: Any, *, code: str, path: str, violations: list[Violation]
) -> None:
    if not isinstance(value, list) or not value:
        violations.append(
            Violation(
                path=path,
                severity="error",
                code=code,
                message="expected non-empty list",
            )
        )
        return
    for index, item in enumerate(value):
        if not _is_non_empty_text(item):
            violations.append(
                Violation(
                    path=path,
                    severity="error",
                    code=code,
                    message=f"item[{index}] must be a non-empty string",
                )
            )


def _validate_agent_file(
    path: Path,
    known_agent_names: set[str],
    known_agent_files: set[str],
    duplicate_agent_names: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    payload, body, parse_errors = _split_frontmatter(_load_text(path))
    for err in parse_errors:
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="frontmatter",
                message=err,
            )
        )
    if payload is None:
        return violations

    name = payload.get("name") or path.stem
    if not _is_non_empty_text(name):
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="agent.name",
                message="missing or empty agent name",
            )
        )
    elif str(name) in duplicate_agent_names:
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="agent.name.duplicate",
                message=f"duplicate agent name: {name}",
            )
        )

    description = payload.get("description")
    if not _is_non_empty_text(description):
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="agent.description",
                message="missing or empty agent description",
            )
        )

    if not body:
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="agent.body",
                message="agent body is empty",
            )
        )

    tools = payload.get("tools")
    if tools is not None:
        _validate_string_list(
            tools, code="agent.tools", path=str(path), violations=violations
        )

    agents = payload.get("agents")
    if agents is not None:
        _validate_string_list(
            agents, code="agent.agents", path=str(path), violations=violations
        )
        if isinstance(agents, list):
            for ref in agents:
                if not _is_non_empty_text(ref):
                    continue
                ref_text = str(ref)
                if (
                    ref_text not in known_agent_names
                    and ref_text not in known_agent_files
                ):
                    violations.append(
                        Violation(
                            path=str(path),
                            severity="error",
                            code="agent.agents.reference",
                            message=f"unknown subagent reference: {ref_text}",
                        )
                    )

    target = payload.get("target")
    if target is not None:
        if not _is_non_empty_text(target) or str(target) not in ALLOWED_AGENT_TARGETS:
            violations.append(
                Violation(
                    path=str(path),
                    severity="error",
                    code="agent.target",
                    message=f"expected one of {sorted(ALLOWED_AGENT_TARGETS)}",
                )
            )

    model = payload.get("model")
    if model is not None and not (
        _is_non_empty_text(model)
        or (isinstance(model, list) and all(_is_non_empty_text(item) for item in model))
    ):
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="agent.model",
                message="model must be a non-empty string or a list of non-empty strings",
            )
        )

    return violations


def _validate_prompt_file(
    path: Path, known_agent_names: set[str], known_agent_files: set[str]
) -> list[Violation]:
    violations: list[Violation] = []
    payload, body, parse_errors = _split_frontmatter(_load_text(path))
    for err in parse_errors:
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="frontmatter",
                message=err,
            )
        )
    if payload is None:
        return violations

    description = payload.get("description")
    if not _is_non_empty_text(description):
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="prompt.description",
                message="missing or empty prompt description",
            )
        )

    if not body:
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="prompt.body",
                message="prompt body is empty",
            )
        )

    agent_ref = payload.get("agent")
    if not _is_non_empty_text(agent_ref):
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="prompt.agent",
                message="missing or empty agent reference",
            )
        )
    else:
        agent_ref_text = str(agent_ref)
        if (
            agent_ref_text not in known_agent_names
            and agent_ref_text not in known_agent_files
        ):
            violations.append(
                Violation(
                    path=str(path),
                    severity="error",
                    code="prompt.agent.reference",
                    message=f"unknown agent reference: {agent_ref_text}",
                )
            )

    tools = payload.get("tools")
    if tools is not None:
        _validate_string_list(
            tools, code="prompt.tools", path=str(path), violations=violations
        )

    model = payload.get("model")
    if model is not None and not (
        _is_non_empty_text(model)
        or (isinstance(model, list) and all(_is_non_empty_text(item) for item in model))
    ):
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="prompt.model",
                message="model must be a non-empty string or a list of non-empty strings",
            )
        )

    return violations


def _validate_instruction_file(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    text = _load_text(path)
    lowered = text.lower()

    if not text.strip():
        violations.append(
            Violation(
                path=str(path),
                severity="error",
                code="instruction.empty",
                message="instruction file is empty",
            )
        )

    if path.name.endswith(".instructions.md"):
        payload, body, parse_errors = _split_frontmatter(text)
        for err in parse_errors:
            violations.append(
                Violation(
                    path=str(path),
                    severity="error",
                    code="instruction.frontmatter",
                    message=err,
                )
            )
        if payload is not None:
            apply_to = payload.get("applyTo")
            if not _is_non_empty_text(apply_to):
                violations.append(
                    Violation(
                        path=str(path),
                        severity="error",
                        code="instruction.applyTo",
                        message="missing or empty applyTo frontmatter",
                    )
                )
            if not body:
                violations.append(
                    Violation(
                        path=str(path),
                        severity="error",
                        code="instruction.body",
                        message="instruction body is empty",
                    )
                )

    if "polski" not in lowered and "polish" not in lowered:
        violations.append(
            Violation(
                path=str(path),
                severity="warn",
                code="instruction.language",
                message="missing explicit Polish language directive",
            )
        )

    return violations


def _discover_files() -> dict[str, list[Path]]:
    agent_files = sorted(
        path for path in AGENTS_DIR.glob("*.md") if path.name not in {"README.md"}
    )
    prompt_files = sorted(PROMPTS_DIR.glob("*.prompt.md"))
    instruction_files = sorted(
        [
            REPO_ROOT / "AGENTS.md",
            REPO_ROOT / "docs" / "AGENTS.md",
            REPO_ROOT / "docs" / "PL" / "AGENTS.md",
        ]
        + list((REPO_ROOT / ".github" / "instructions").glob("*.instructions.md"))
        + [REPO_ROOT / ".github" / "copilot-instructions.md"]
    )
    return {
        "agents": agent_files,
        "prompts": prompt_files,
        "instructions": instruction_files,
    }


def validate_repository() -> dict[str, Any]:
    files = _discover_files()
    known_agent_names: set[str] = set()
    known_agent_files: set[str] = set()
    agent_name_counts: dict[str, int] = {}
    for path in files["agents"]:
        text = _load_text(path)
        payload, _, _ = _split_frontmatter(text)
        known_agent_files.add(path.stem)
        resolved_name = path.stem
        if payload and _is_non_empty_text(payload.get("name")):
            resolved_name = str(payload["name"])
        known_agent_names.add(resolved_name)
        agent_name_counts[resolved_name] = agent_name_counts.get(resolved_name, 0) + 1

    duplicate_agent_names = {
        name for name, count in agent_name_counts.items() if count > 1
    }

    violations: list[Violation] = []
    for path in files["agents"]:
        violations.extend(
            _validate_agent_file(
                path,
                known_agent_names,
                known_agent_files,
                duplicate_agent_names,
            )
        )
    for path in files["prompts"]:
        violations.extend(
            _validate_prompt_file(path, known_agent_names, known_agent_files)
        )
    for path in files["instructions"]:
        violations.extend(_validate_instruction_file(path))

    warnings = [item for item in violations if item.severity == "warn"]
    errors = [item for item in violations if item.severity == "error"]

    summary = {
        "repo_root": str(REPO_ROOT),
        "agents": [str(path.relative_to(REPO_ROOT)) for path in files["agents"]],
        "prompts": [str(path.relative_to(REPO_ROOT)) for path in files["prompts"]],
        "instructions": [
            str(path.relative_to(REPO_ROOT)) for path in files["instructions"]
        ],
        "warnings": len(warnings),
        "errors": len(errors),
        "violations": [asdict(item) for item in violations],
    }
    return summary


def _write_reports(report_dir: Path, summary: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "agent_config_validation.json"
    md_path = report_dir / "agent_config_validation.md"

    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        "# Agent config validation",
        "",
        f"- repo_root: `{summary['repo_root']}`",
        f"- agents: {len(summary['agents'])}",
        f"- prompts: {len(summary['prompts'])}",
        f"- instructions: {len(summary['instructions'])}",
        f"- warnings: {summary['warnings']}",
        f"- errors: {summary['errors']}",
        "",
        "## Files",
    ]
    for key in ("agents", "prompts", "instructions"):
        lines.append(f"### {key}")
        for item in summary[key]:
            lines.append(f"- `{item}`")
        lines.append("")
    lines.append("## Violations")
    if summary["violations"]:
        for item in summary["violations"]:
            lines.append(
                f"- [{item['severity']}] {item['path']} :: {item['code']} :: {item['message']}"
            )
    else:
        lines.append("- none")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate custom agents, prompt files and instruction contracts."
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=REPORT_DIR,
        help="Directory for JSON/Markdown validation reports.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not write JSON/Markdown reports.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = validate_repository()

    if not args.no_report:
        _write_reports(args.report_dir, summary)

    print("Agent config validation")
    print(f"- agents: {len(summary['agents'])}")
    print(f"- prompts: {len(summary['prompts'])}")
    print(f"- instructions: {len(summary['instructions'])}")
    print(f"- warnings: {summary['warnings']}")
    print(f"- errors: {summary['errors']}")

    if summary["warnings"]:
        print("\nWarnings:")
        for item in summary["violations"]:
            if item["severity"] == "warn":
                print(f"- {item['path']} :: {item['code']} :: {item['message']}")

    if summary["errors"]:
        print("\nErrors:")
        for item in summary["violations"]:
            if item["severity"] == "error":
                print(f"- {item['path']} :: {item['code']} :: {item['message']}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
