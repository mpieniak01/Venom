#!/usr/bin/env python3
"""Heuristic dead-code audit for Python modules.

Scope:
- private top-level definitions that appear to have no references,
- unreachable statements after terminal instructions.

This is intentionally heuristic and should be treated as a review aid.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_SCAN_PATHS = ("venom_core", "scripts")
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}
IGNORE_MARKER = "dead-code: ignore"


@dataclass(frozen=True)
class Definition:
    path: str
    line: int
    kind: str
    name: str
    has_decorator: bool
    ignored: bool


@dataclass(frozen=True)
class Finding:
    type: str
    path: str
    line: int
    message: str


def _iter_python_files(root: Path, scan_paths: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for rel in scan_paths:
        base = (root / rel).resolve()
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if not path.is_file():
                continue
            rel_path = path.relative_to(root)
            parts = set(rel_path.parts)
            if DEFAULT_EXCLUDE_DIRS.intersection(parts):
                continue
            if rel_path.parts and rel_path.parts[0] == "tests":
                continue
            files.append(path)
    return sorted(files)


def _line_has_ignore_marker(source_lines: list[str], line: int) -> bool:
    if line <= 0 or line > len(source_lines):
        return False
    return IGNORE_MARKER in source_lines[line - 1]


def _collect_definitions(file_path: Path, source: str, root: Path) -> list[Definition]:
    tree = ast.parse(source, filename=str(file_path))
    source_lines = source.splitlines()
    definitions: list[Definition] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            if not name.startswith("_") or name.startswith("__"):
                continue
            has_decorator = bool(getattr(node, "decorator_list", []))
            definitions.append(
                Definition(
                    path=str(file_path.relative_to(root)),
                    line=node.lineno,
                    kind=type(node).__name__,
                    name=name,
                    has_decorator=has_decorator,
                    ignored=_line_has_ignore_marker(source_lines, node.lineno),
                )
            )
    return definitions


def _collect_reference_counter(file_path: Path, source: str) -> dict[str, int]:
    tree = ast.parse(source, filename=str(file_path))
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            counts[node.id] = counts.get(node.id, 0) + 1
        elif isinstance(node, ast.Attribute):
            counts[node.attr] = counts.get(node.attr, 0) + 1
    return counts


def _walk_unreachable(
    statements: list[ast.stmt],
    file_rel: str,
    findings: list[Finding],
) -> None:
    terminated = False
    for stmt in statements:
        if terminated:
            findings.append(
                Finding(
                    type="unreachable_statement",
                    path=file_rel,
                    line=getattr(stmt, "lineno", 0),
                    message="Statement after terminal instruction (return/raise/break/continue).",
                )
            )
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            terminated = True

        for nested_attr in ("body", "orelse", "finalbody"):
            nested = getattr(stmt, nested_attr, None)
            if isinstance(nested, list) and nested and isinstance(nested[0], ast.stmt):
                _walk_unreachable(nested, file_rel, findings)
        handlers = getattr(stmt, "handlers", None)
        if isinstance(handlers, list):
            for handler in handlers:
                if isinstance(handler, ast.ExceptHandler) and handler.body:
                    _walk_unreachable(handler.body, file_rel, findings)


def _collect_unreachable(file_path: Path, source: str, root: Path) -> list[Finding]:
    tree = ast.parse(source, filename=str(file_path))
    findings: list[Finding] = []
    _walk_unreachable(tree.body, str(file_path.relative_to(root)), findings)
    return findings


def _load_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    rules: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rules.add(line)
    return rules


def _is_allowlisted(defn: Definition, allowlist: set[str]) -> bool:
    key_exact = f"{defn.path}:{defn.name}"
    key_wildcard = f"{Path(defn.path).parent.as_posix()}/*:{defn.name}"
    return key_exact in allowlist or key_wildcard in allowlist


def run_audit(
    root: Path, scan_paths: Iterable[str], allowlist: set[str]
) -> dict[str, object]:
    py_files = _iter_python_files(root, scan_paths)
    definitions: list[Definition] = []
    ref_counts: dict[str, int] = {}
    findings: list[Finding] = []
    parse_errors: list[str] = []

    for file_path in py_files:
        try:
            source = file_path.read_text(encoding="utf-8")
            definitions.extend(_collect_definitions(file_path, source, root))
            file_counts = _collect_reference_counter(file_path, source)
            for key, value in file_counts.items():
                ref_counts[key] = ref_counts.get(key, 0) + value
            findings.extend(_collect_unreachable(file_path, source, root))
        except SyntaxError as err:
            parse_errors.append(
                f"{file_path.relative_to(root)}:{err.lineno}: {err.msg}"
            )
        except UnicodeDecodeError:
            parse_errors.append(f"{file_path.relative_to(root)}: non-utf8 encoding")

    for definition in definitions:
        if definition.has_decorator or definition.ignored:
            continue
        if _is_allowlisted(definition, allowlist):
            continue
        if ref_counts.get(definition.name, 0) == 0:
            findings.append(
                Finding(
                    type="unused_private_definition",
                    path=definition.path,
                    line=definition.line,
                    message=f"{definition.kind} `{definition.name}` has no references in scanned scope.",
                )
            )

    findings_sorted = sorted(
        findings, key=lambda item: (item.path, item.line, item.type)
    )
    summary = {
        "files_scanned": len(py_files),
        "private_definitions_scanned": len(definitions),
        "parse_errors": len(parse_errors),
        "findings_total": len(findings_sorted),
        "findings_unused_private_definition": sum(
            1 for f in findings_sorted if f.type == "unused_private_definition"
        ),
        "findings_unreachable_statement": sum(
            1 for f in findings_sorted if f.type == "unreachable_statement"
        ),
    }
    return {
        "root": str(root),
        "scan_paths": list(scan_paths),
        "allowlist_size": len(allowlist),
        "parse_errors": parse_errors,
        "summary": summary,
        "findings": [asdict(f) for f in findings_sorted],
    }


def _print_text_report(report: dict[str, object], show_limit: int) -> None:
    summary = report["summary"]
    print("Dead-code audit (heuristic)")
    print(f"- files scanned: {summary['files_scanned']}")
    print(f"- private definitions scanned: {summary['private_definitions_scanned']}")
    print(f"- findings total: {summary['findings_total']}")
    print(
        "- findings by type: "
        f"unused_private_definition={summary['findings_unused_private_definition']}, "
        f"unreachable_statement={summary['findings_unreachable_statement']}"
    )

    parse_errors = report["parse_errors"]
    if parse_errors:
        print(f"- parse errors: {len(parse_errors)}")
        for entry in parse_errors[:show_limit]:
            print(f"  * {entry}")

    findings = report["findings"]
    if findings:
        print("\nTop findings:")
        for item in findings[:show_limit]:
            print(f"- {item['path']}:{item['line']} [{item['type']}] {item['message']}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Heuristic dead-code audit for Python code."
    )
    parser.add_argument("--root", default=".", help="Repository root path (default: .)")
    parser.add_argument(
        "--paths",
        default=",".join(DEFAULT_SCAN_PATHS),
        help="Comma-separated scan roots relative to repo root (default: venom_core,scripts)",
    )
    parser.add_argument(
        "--allowlist",
        default="config/dead_code_allowlist.txt",
        help="Allowlist file with rules 'path.py:symbol' or 'dir/*:symbol'.",
    )
    parser.add_argument(
        "--show-limit", type=int, default=50, help="Max findings to print in text mode."
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return exit code 1 when findings exist.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    scan_paths = [item.strip() for item in args.paths.split(",") if item.strip()]
    allowlist = _load_allowlist((root / args.allowlist).resolve())
    report = run_audit(root, scan_paths, allowlist)

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        _print_text_report(report, show_limit=max(1, args.show_limit))

    has_findings = report["summary"]["findings_total"] > 0
    if args.fail_on_findings and has_findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
