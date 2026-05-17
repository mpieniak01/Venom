#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_JSON = Path("test-results/agent-context/brief.json")
DEFAULT_OUTPUT_MD = Path("test-results/agent-context/brief.md")


def _load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _load_catalog_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"tests_total": 0, "domains": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"tests_total": 0, "domains": []}
    tests = payload.get("tests", [])
    if not isinstance(tests, list):
        return {"tests_total": 0, "domains": []}
    domains = sorted(
        {
            str(item.get("domain", "misc"))
            for item in tests
            if isinstance(item, dict) and str(item.get("domain", "")).strip()
        }
    )
    return {"tests_total": len(tests), "domains": domains}


def _load_recent_session_index(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None
    for raw in reversed(lines):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        return {
            "ts": str(payload.get("ts") or payload.get("timestamp") or ""),
            "topic": str(payload.get("topic") or payload.get("title") or ""),
            "model": str(payload.get("model") or ""),
        }
    return None


def build_brief(
    *,
    repo_root: Path,
    codex_home: Path | None,
) -> dict[str, Any]:
    ci_lite = _load_lines(repo_root / "config/pytest-groups/ci-lite.txt")
    sonar_new_code = _load_lines(repo_root / "config/pytest-groups/sonar-new-code.txt")
    catalog = _load_catalog_summary(repo_root / "config/testing/test_catalog.json")

    codex: dict[str, Any] = {"session_index": None}
    if codex_home is not None:
        session_index = _load_recent_session_index(codex_home / "session_index.jsonl")
        codex["session_index"] = session_index

    return {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "coding-agent-brief",
        "knowledge_sources": [
            "docs/AGENTS.md",
            "docs/PL/AGENTS.md",
            "config/testing/test_catalog.json",
            "config/pytest-groups/ci-lite.txt",
            "config/pytest-groups/sonar-new-code.txt",
        ],
        "gate_commands": [
            "make test-catalog-check",
            "make test-groups-check",
            "make check-new-code-coverage-diagnostics",
            "make pr-fast",
        ],
        "docs_mcp_policy": {
            "openai_codex_questions": "Use official Docs MCP first, then local source-of-truth files.",
            "copy_policy": "Keep summaries short; avoid pasting long docs.",
        },
        "test_lanes": {
            "ci_lite_count": len(ci_lite),
            "sonar_new_code_count": len(sonar_new_code),
        },
        "catalog": catalog,
        "wsl_reuse": {
            "codex_home_checked": str(codex_home) if codex_home else None,
            "recent_session": codex["session_index"],
            "note": "Session index is advisory only; not a source of truth.",
        },
    }


def render_markdown(brief: dict[str, Any]) -> str:
    lane = brief["test_lanes"]
    catalog = brief["catalog"]
    recent = brief["wsl_reuse"]["recent_session"]
    recent_line = "n/a"
    if isinstance(recent, dict):
        recent_line = (
            f"topic={recent.get('topic') or '-'}; "
            f"model={recent.get('model') or '-'}; "
            f"ts={recent.get('ts') or '-'}"
        )
    lines = [
        "# Agent Context Brief",
        "",
        f"- Generated (UTC): {brief['generated_at_utc']}",
        f"- CI lane counts: ci-lite={lane['ci_lite_count']}, sonar-new-code={lane['sonar_new_code_count']}",
        f"- Test catalog: tests={catalog['tests_total']}, domains={len(catalog['domains'])}",
        f"- Recent local Codex session: {recent_line}",
        "",
        "## Gate Commands",
    ]
    for command in brief["gate_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(["", "## MCP Rule", "- For OpenAI/Codex topics: use Docs MCP first."])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate lightweight agent context brief."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root.",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path.home() / ".codex",
        help="Optional Codex home for lightweight local session hints.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_OUTPUT_JSON,
        help="Output JSON path.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DEFAULT_OUTPUT_MD,
        help="Output Markdown path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    codex_home = args.codex_home
    if codex_home is not None and not codex_home.exists():
        codex_home = None

    brief = build_brief(repo_root=repo_root, codex_home=codex_home)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_md.write_text(render_markdown(brief), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
