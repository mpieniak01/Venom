#!/usr/bin/env python3
"""Audit operator manual EN/PL drift against the canonical chat operator contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.+)$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
FORBIDDEN_PATTERNS = (
    "make local-first-",
    "local-first-",
    "config/chat_operator/",
    "venom_operator_tool_profile",
    "VSCODE_AGENT",
)


@dataclass(frozen=True)
class ManualAuditResult:
    doc: str
    top_level_sections: list[str]
    section3_links: list[str]
    issues: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit operator manual EN/PL against canonical chat operator contract."
    )
    parser.add_argument(
        "--en-doc",
        default="docs/OPERATOR_MANUAL.md",
        help="Path to the English operator manual.",
    )
    parser.add_argument(
        "--pl-doc",
        default="docs/PL/OPERATOR_MANUAL.md",
        help="Path to the Polish operator manual.",
    )
    parser.add_argument(
        "--out-json",
        default="test-results/238e/operator_manual_docs_drift_audit.json",
        help="JSON report path.",
    )
    parser.add_argument(
        "--out-md",
        default="test-results/238e/operator_manual_docs_drift_audit.md",
        help="Markdown report path.",
    )
    return parser.parse_args()


def extract_top_level_sections(text: str) -> list[str]:
    sections: list[str] = []
    for line in text.splitlines():
        match = SECTION_RE.match(line.strip())
        if match:
            sections.append(match.group(1))
    return sections


def extract_section_3(text: str) -> str:
    lines = text.splitlines()
    capture = False
    block: list[str] = []
    for line in lines:
        if line.startswith("## 3."):
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture:
            block.append(line)
    return "\n".join(block)


def extract_links(text: str) -> list[str]:
    links: list[str] = []
    for _label, target in LINK_RE.findall(text):
        links.append(target)
    return links


def audit_doc(path: Path) -> ManualAuditResult:
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []

    sections = extract_top_level_sections(text)
    if sections != ["1", "2", "3"]:
        issues.append(f"unexpected top-level sections: {sections!r}")

    if any(pattern in text for pattern in FORBIDDEN_PATTERNS):
        issues.append(
            "manual contains chat-contract details that should live in CHAT_OPERATOR"
        )

    section3 = extract_section_3(text)
    if not section3:
        issues.append("missing Chat Operator section")

    section3_links = extract_links(section3)
    required_links = {"THE_CHAT.md", "CHAT_OPERATOR.md", "CHAT_SESSION.md"}
    missing_links = sorted(
        link for link in required_links if link not in section3_links
    )
    if missing_links:
        issues.append("missing section 3 links: " + ", ".join(missing_links))

    extra_links = [link for link in section3_links if link not in required_links]
    if extra_links:
        issues.append("unexpected extra links in section 3: " + ", ".join(extra_links))

    return ManualAuditResult(
        doc=str(path.as_posix()),
        top_level_sections=sections,
        section3_links=section3_links,
        issues=issues,
    )


def render_md(
    scope: str,
    verdict: str,
    generated_at_utc: str,
    results: list[ManualAuditResult],
    issues: list[str],
) -> str:
    lines = [
        "# Operator manual drift audit",
        "",
        f"- scope: `{scope}`",
        f"- generated_at_utc: `{generated_at_utc}`",
        f"- verdict: `{verdict}`",
        "",
        "## Results",
    ]
    for result in results:
        lines.append(f"### {result.doc}")
        lines.append(f"- top_level_sections: `{', '.join(result.top_level_sections)}`")
        lines.append(f"- section3_links: `{', '.join(result.section3_links)}`")
        if result.issues:
            lines.extend(f"- issue: {issue}" for issue in result.issues)
        else:
            lines.append("- issue: none")
    lines.append("")
    lines.append("## Issues")
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    en_path = repo_root / args.en_doc
    pl_path = repo_root / args.pl_doc

    issues: list[str] = []
    results: list[ManualAuditResult] = []

    if not en_path.exists():
        issues.append(f"missing doc: {args.en_doc}")
    else:
        results.append(audit_doc(en_path))

    if not pl_path.exists():
        issues.append(f"missing doc: {args.pl_doc}")
    else:
        results.append(audit_doc(pl_path))

    if len(results) == 2:
        if results[0].top_level_sections != results[1].top_level_sections:
            issues.append("EN/PL top-level section order differs")
        if results[0].section3_links.count("CHAT_OPERATOR.md") != results[
            1
        ].section3_links.count("CHAT_OPERATOR.md"):
            issues.append("EN/PL section 3 link structure differs")

    for result in results:
        issues.extend(result.issues)

    verdict = "pass" if not issues else "fail"
    generated_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "scope": "pr238e-operator-manual-docs-drift-audit",
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
