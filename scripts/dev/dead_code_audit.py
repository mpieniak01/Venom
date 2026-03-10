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
import re
import subprocess
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
VULTURE_MESSAGE_SYMBOL_RE = re.compile(r"'([^']+)'")
VULTURE_LINE_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): (?P<message>.+?)(?: \((?P<confidence>\d+)% confidence\))?$"
)


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
    source: str = "heuristic"
    symbol: str | None = None
    confidence: int | None = None


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


def _extract_vulture_symbol(message: str) -> str | None:
    match = VULTURE_MESSAGE_SYMBOL_RE.search(message)
    if match is None:
        return None
    return str(match.group(1) or "").strip() or None


def _is_vulture_allowlisted(
    *,
    file_path: str,
    line: int,
    symbol: str | None,
    allowlist: set[str],
) -> bool:
    file_dir = Path(file_path).parent.as_posix()
    line_rule = f"{file_path}:{line}"
    wildcard_line_rule = f"{file_dir}/*:{line}"
    if line_rule in allowlist or wildcard_line_rule in allowlist:
        return True
    if not symbol:
        return False
    exact_rule = f"{file_path}:{symbol}"
    wildcard_rule = f"{file_dir}/*:{symbol}"
    return exact_rule in allowlist or wildcard_rule in allowlist


def _is_allowlisted(defn: Definition, allowlist: set[str]) -> bool:
    key_exact = f"{defn.path}:{defn.name}"
    key_wildcard = f"{Path(defn.path).parent.as_posix()}/*:{defn.name}"
    return key_exact in allowlist or key_wildcard in allowlist


def _run_vulture(
    *,
    root: Path,
    scan_paths: list[str],
    min_confidence: int,
    timeout_sec: int,
    vulture_bin: str,
) -> tuple[list[Finding], str | None, bool]:
    cmd = [vulture_bin] if vulture_bin.strip() else [sys.executable, "-m", "vulture"]
    cmd.extend(scan_paths)
    cmd.extend(["--min-confidence", str(min_confidence)])
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=max(1, timeout_sec),
        )
    except FileNotFoundError:
        return [], "vulture executable not found (install in .venv).", False
    except subprocess.TimeoutExpired:
        return [], f"vulture timeout after {max(1, timeout_sec)}s.", True

    output = "\n".join(
        [part for part in (completed.stdout, completed.stderr) if part.strip()]
    )
    if completed.returncode == 1 and "No module named vulture" in output:
        return [], "vulture is not installed in .venv.", False

    findings: list[Finding] = []
    parse_warnings: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = VULTURE_LINE_RE.match(line)
        if match is None:
            parse_warnings.append(line)
            continue
        message = str(match.group("message") or "").strip()
        symbol = _extract_vulture_symbol(message)
        confidence_raw = str(match.group("confidence") or "").strip()
        confidence = int(confidence_raw) if confidence_raw.isdigit() else None
        findings.append(
            Finding(
                type="vulture_unused_symbol",
                source="vulture",
                path=str(match.group("path") or "").strip(),
                line=int(match.group("line") or "0"),
                message=message,
                symbol=symbol,
                confidence=confidence,
            )
        )
    if completed.returncode not in (0, 1, 3):
        return [], f"vulture failed with exit={completed.returncode}.", True
    if parse_warnings:
        return findings, f"vulture parse warnings: {len(parse_warnings)} line(s).", True
    return findings, None, True


def run_audit(
    *,
    root: Path,
    scan_paths: Iterable[str],
    allowlist: set[str],
    with_vulture: bool = False,
    vulture_allowlist: set[str] | None = None,
    vulture_min_confidence: int = 80,
    vulture_timeout_sec: int = 30,
    vulture_bin: str = "",
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
        "findings_vulture_unused_symbol": 0,
    }
    vulture_report: dict[str, object] = {
        "enabled": with_vulture,
        "available": False,
        "error": None,
        "allowlist_size": len(vulture_allowlist or set()),
        "findings_total": 0,
    }
    if with_vulture:
        vulture_findings, vulture_error, vulture_available = _run_vulture(
            root=root,
            scan_paths=list(scan_paths),
            min_confidence=vulture_min_confidence,
            timeout_sec=vulture_timeout_sec,
            vulture_bin=vulture_bin,
        )
        vulture_allow = vulture_allowlist or set()
        filtered_vulture: list[Finding] = []
        for finding in vulture_findings:
            if _is_vulture_allowlisted(
                file_path=finding.path,
                line=finding.line,
                symbol=finding.symbol,
                allowlist=vulture_allow,
            ):
                continue
            filtered_vulture.append(finding)
        findings_sorted.extend(
            sorted(filtered_vulture, key=lambda item: (item.path, item.line, item.type))
        )
        vulture_report["available"] = vulture_available
        vulture_report["error"] = vulture_error
        vulture_report["findings_total"] = len(filtered_vulture)
        summary["findings_vulture_unused_symbol"] = len(filtered_vulture)
        summary["findings_total"] = len(findings_sorted)

    return {
        "root": str(root),
        "scan_paths": list(scan_paths),
        "allowlist_size": len(allowlist),
        "parse_errors": parse_errors,
        "vulture": vulture_report,
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
        f"unreachable_statement={summary['findings_unreachable_statement']}, "
        f"vulture_unused_symbol={summary['findings_vulture_unused_symbol']}"
    )
    vulture = report.get("vulture")
    if isinstance(vulture, dict):
        print(
            f"- vulture: enabled={vulture.get('enabled')} "
            f"available={vulture.get('available')} "
            f"findings={vulture.get('findings_total')}"
        )
        if vulture.get("error"):
            print(f"  * vulture note: {vulture.get('error')}")

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
        "--with-vulture",
        action="store_true",
        help="Include vulture-based analysis as an additional soft signal.",
    )
    parser.add_argument(
        "--vulture-allowlist",
        default="config/dead_code_vulture_allowlist.txt",
        help="Allowlist for vulture findings: path.py:symbol, dir/*:symbol or path.py:line.",
    )
    parser.add_argument(
        "--vulture-min-confidence",
        type=int,
        default=80,
        help="Vulture minimum confidence (default: 80).",
    )
    parser.add_argument(
        "--vulture-timeout-sec",
        type=int,
        default=30,
        help="Vulture timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--vulture-bin",
        default="",
        help="Optional vulture executable path (default: python -m vulture).",
    )
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
    vulture_allowlist = _load_allowlist((root / args.vulture_allowlist).resolve())
    report = run_audit(
        root=root,
        scan_paths=scan_paths,
        allowlist=allowlist,
        with_vulture=args.with_vulture,
        vulture_allowlist=vulture_allowlist,
        vulture_min_confidence=max(1, min(100, args.vulture_min_confidence)),
        vulture_timeout_sec=max(1, args.vulture_timeout_sec),
        vulture_bin=args.vulture_bin,
    )

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
