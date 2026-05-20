#!/usr/bin/env python3
"""Audit THE_CHAT EN/PL drift against the canonical chat operator contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

HEADING_RE = re.compile(r"^##\s+(.+)$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
FORBIDDEN_PATTERNS = (
    "make local-first-",
    "config/chat_operator/",
    "venom_operator_tool_profile",
    "operator tool profile",
    "decision gate",
)

EXPECTED_EN_HEADINGS = [
    "Role",
    "What it is for",
    "Main integrations",
    "Operating rules",
    "Handled intents",
    "See also",
]

EXPECTED_PL_HEADINGS = [
    "Rola",
    "Do czego służy",
    "Główne integracje",
    "Zasady działania",
    "Obsługiwane intencje",
    "Zobacz też",
]

EXPECTED_LINKS = {
    "CHAT_OPERATOR.md",
    "CHAT_SESSION.md",
    "THE_RESEARCHER.md",
    "MEMORY_LAYER_GUIDE.md",
    "INTENT_RECOGNITION.md",
}


@dataclass(frozen=True)
class ChatDocAuditResult:
    doc: str
    headings: list[str]
    links: list[str]
    issues: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit THE_CHAT EN/PL against the canonical chat operator contract."
    )
    parser.add_argument(
        "--en-doc",
        default="docs/THE_CHAT.md",
        help="Path to the English THE_CHAT document.",
    )
    parser.add_argument(
        "--pl-doc",
        default="docs/PL/THE_CHAT.md",
        help="Path to the Polish THE_CHAT document.",
    )
    parser.add_argument(
        "--out-json",
        default="test-results/238f/the_chat_docs_drift_audit.json",
        help="JSON report path.",
    )
    parser.add_argument(
        "--out-md",
        default="test-results/238f/the_chat_docs_drift_audit.md",
        help="Markdown report path.",
    )
    return parser.parse_args()


def extract_headings(text: str) -> list[str]:
    return [
        match.group(1).strip()
        for line in text.splitlines()
        if (match := HEADING_RE.match(line.strip()))
    ]


def extract_links(text: str) -> list[str]:
    return [target for _label, target in LINK_RE.findall(text)]


def audit_doc(path: Path, expected_headings: list[str]) -> ChatDocAuditResult:
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    headings = extract_headings(text)
    links = extract_links(text)

    if headings != expected_headings:
        issues.append(f"unexpected headings: {headings!r}")

    for pattern in FORBIDDEN_PATTERNS:
        if pattern in text:
            issues.append(f"forbidden pattern present: {pattern}")

    missing_links = sorted(link for link in EXPECTED_LINKS if link not in links)
    if missing_links:
        issues.append("missing see-also links: " + ", ".join(missing_links))

    if "CHAT_OPERATOR.md" not in links or "CHAT_SESSION.md" not in links:
        issues.append("missing operator delegation links")

    return ChatDocAuditResult(
        doc=str(path.as_posix()),
        headings=headings,
        links=links,
        issues=issues,
    )


def render_md(
    scope: str,
    verdict: str,
    generated_at_utc: str,
    results: list[ChatDocAuditResult],
    issues: list[str],
) -> str:
    lines = [
        "# THE_CHAT drift audit",
        "",
        f"- scope: `{scope}`",
        f"- generated_at_utc: `{generated_at_utc}`",
        f"- verdict: `{verdict}`",
        "",
        "## Results",
    ]
    for result in results:
        lines.append(f"### {result.doc}")
        lines.append(f"- headings: `{', '.join(result.headings)}`")
        lines.append(f"- links: `{', '.join(result.links)}`")
        if result.issues:
            lines.extend(f"- issue: {issue}" for issue in result.issues)
        else:
            lines.append("- issue: none")
    lines.append("")
    lines.append("## Issues")
    lines.extend(f"- {issue}" for issue in issues) if issues else lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    en_path = repo_root / args.en_doc
    pl_path = repo_root / args.pl_doc

    issues: list[str] = []
    results: list[ChatDocAuditResult] = []

    if not en_path.exists():
        issues.append(f"missing doc: {args.en_doc}")
    else:
        results.append(audit_doc(en_path, EXPECTED_EN_HEADINGS))

    if not pl_path.exists():
        issues.append(f"missing doc: {args.pl_doc}")
    else:
        results.append(audit_doc(pl_path, EXPECTED_PL_HEADINGS))

    if len(results) == 2:
        if (
            results[0].headings != EXPECTED_EN_HEADINGS
            or results[1].headings != EXPECTED_PL_HEADINGS
        ):
            issues.append("heading structure mismatch between EN and PL")
        if {link for link in results[0].links if link in EXPECTED_LINKS} != {
            link for link in results[1].links if link in EXPECTED_LINKS
        }:
            issues.append("core see-also links differ between EN and PL")

    for result in results:
        issues.extend(result.issues)

    verdict = "pass" if not issues else "fail"
    generated_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "scope": "pr238f-the-chat-docs-drift-audit",
        "generated_at_utc": generated_at_utc,
        "en_doc": args.en_doc,
        "pl_doc": args.pl_doc,
        "verdict": verdict,
        "issues": issues,
        "results": [asdict(result) for result in results],
    }

    out_json = repo_root / args.out_json
    out_md = repo_root / args.out_md
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    out_md.write_text(
        render_md(payload["scope"], verdict, generated_at_utc, results, issues),
        encoding="utf-8",
    )

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nSaved JSON: {out_json}")
    print(f"Saved MD:   {out_md}")
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
