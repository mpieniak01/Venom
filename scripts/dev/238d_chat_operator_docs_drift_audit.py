#!/usr/bin/env python3
"""Audit chat operator docs against the canonical make help surface."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MAKE_CMD_RE = re.compile(r"make\s+([A-Za-z0-9_.-]+(?:\|[A-Za-z0-9_.-]+)*)")
IGNORE_DOC_COMMANDS = {"help"}


@dataclass(frozen=True)
class AuditResult:
    scope: str
    generated_at_utc: str
    docs: list[str]
    help_commands: list[str]
    doc_commands: dict[str, list[str]]
    issues: list[str]
    verdict: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit chat operator docs against canonical make help."
    )
    parser.add_argument(
        "--docs",
        nargs="+",
        default=["docs/CHAT_OPERATOR.md", "docs/PL/CHAT_OPERATOR.md"],
        help="Docs files to audit.",
    )
    parser.add_argument(
        "--help-targets",
        nargs="+",
        default=["help", "local-first-help"],
        help="make targets used as the canonical help surface.",
    )
    parser.add_argument(
        "--out-json",
        default="test-results/238d/chat_operator_docs_drift_audit.json",
        help="JSON report path.",
    )
    parser.add_argument(
        "--out-md",
        default="test-results/238d/chat_operator_docs_drift_audit.md",
        help="Markdown report path.",
    )
    return parser.parse_args()


def run_make_target(target: str) -> str:
    proc = subprocess.run(
        ["make", "--no-print-directory", target],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"make {target} failed with exit code {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def extract_commands(text: str) -> set[str]:
    commands: set[str] = set()
    for match in MAKE_CMD_RE.finditer(text):
        payload = match.group(1)
        for part in payload.split("|"):
            if part:
                commands.add(part)
    return commands


def render_md(result: AuditResult) -> str:
    lines = [
        "# Chat operator docs drift audit",
        "",
        f"- scope: `{result.scope}`",
        f"- generated_at_utc: `{result.generated_at_utc}`",
        f"- verdict: `{result.verdict}`",
        "",
        "## Help surface",
    ]
    lines.extend(f"- `{cmd}`" for cmd in result.help_commands)
    lines.append("")
    lines.append("## Docs surface")
    for doc, commands in result.doc_commands.items():
        lines.append(f"### {doc}")
        lines.extend(f"- `{cmd}`" for cmd in commands)
        lines.append("")
    if result.issues:
        lines.append("## Issues")
        lines.extend(f"- {issue}" for issue in result.issues)
    else:
        lines.append("## Issues")
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    docs = [str(Path(doc).as_posix()) for doc in args.docs]

    help_commands: set[str] = set()
    for target in args.help_targets:
        help_commands.update(extract_commands(run_make_target(target)))

    doc_commands: dict[str, list[str]] = {}
    issues: list[str] = []
    all_doc_commands: set[str] = set()

    for doc in docs:
        path = repo_root / doc
        if not path.exists():
            issues.append(f"missing doc: {doc}")
            doc_commands[doc] = []
            continue
        commands = sorted(extract_commands(path.read_text(encoding="utf-8")))
        commands = [
            command for command in commands if command not in IGNORE_DOC_COMMANDS
        ]
        doc_commands[doc] = commands
        all_doc_commands.update(commands)

    missing_in_help = sorted(
        cmd for cmd in all_doc_commands if cmd not in help_commands
    )
    if missing_in_help:
        issues.append(
            "doc commands missing from help surface: " + ", ".join(missing_in_help)
        )

    if len(set(tuple(v) for v in doc_commands.values())) > 1:
        issues.append("docs are out of sync across locales")

    verdict = "pass" if not issues else "fail"
    result = AuditResult(
        scope="pr238d-chat-operator-docs-drift-audit",
        generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        docs=docs,
        help_commands=sorted(help_commands),
        doc_commands=doc_commands,
        issues=issues,
        verdict=verdict,
    )

    out_json = repo_root / args.out_json
    out_md = repo_root / args.out_md
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(
        json.dumps(result.__dict__, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    out_md.write_text(render_md(result), encoding="utf-8")

    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
    print(f"\nSaved JSON: {out_json}")
    print(f"Saved MD:   {out_md}")

    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
