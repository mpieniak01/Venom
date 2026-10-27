#!/usr/bin/env python3
"""Read-only, conservative inventory of Python tests and their execution hints.

This tool parses source files; it never imports or executes test modules. It
cannot prove that a test is isolated, nor identify all indirect I/O or mocks.
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import sys
from pathlib import Path
from typing import Any

LIVE_MARKERS = frozenset(
    {
        "live_venom",
        "live_model",
        "requires_stack",
        "manual_llm",
        "requires_docker",
        "requires_docker_compose",
        "unsafe_direct_runtime",
        "live_state_file",
    }
)
GROUP_NAMES = ("ci-lite", "sonar-new-code", "fast", "long", "heavy")


def _marker_names(node: ast.AST) -> set[str]:
    markers: set[str] = set()
    for part in ast.walk(node):
        if (
            isinstance(part, ast.Attribute)
            and isinstance(part.value, ast.Attribute)
            and isinstance(part.value.value, ast.Name)
            and part.value.value.id == "pytest"
            and part.value.attr == "mark"
        ):
            markers.add(part.attr)
    return markers


def _qualname(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualname(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _qualname(node.func)
    return ""


class _SourceInventory(ast.NodeVisitor):
    def __init__(self) -> None:
        self.module_markers: set[str] = set()
        self.test_markers: list[dict[str, Any]] = []
        self.signals: list[dict[str, Any]] = []
        self._scopes: list[str] = []
        self._class_markers: list[set[str]] = []
        self._function_depth = 0
        self._aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._aliases[alias.asname or alias.name.split(".")[0]] = (
                alias.name if alias.asname else alias.name.split(".")[0]
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            for alias in node.names:
                if alias.name != "*":
                    self._aliases[alias.asname or alias.name] = (
                        f"{node.module}.{alias.name}"
                    )

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self._scopes and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in node.targets
        ):
            self.module_markers.update(_marker_names(node.value))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if (
            not self._scopes
            and isinstance(node.target, ast.Name)
            and node.target.id == "pytestmark"
            and node.value is not None
        ):
            self.module_markers.update(_marker_names(node.value))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        marks = set().union(*(_marker_names(d) for d in node.decorator_list))
        # Class bodies and decorators execute during module collection.
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._scopes.append(node.name)
        self._class_markers.append(marks)
        for statement in node.body:
            self.visit(statement)
        self._class_markers.pop()
        self._scopes.pop()

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        marks = set().union(*(_marker_names(d) for d in node.decorator_list))
        if node.name.startswith("test_"):
            inherited = set().union(*self._class_markers)
            self.test_markers.append(
                {
                    "name": "::".join([*self._scopes, node.name]),
                    "line": node.lineno,
                    "markers": sorted(inherited | marks),
                }
            )
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._visit_argument_defaults(node.args)
        self._scopes.append(node.name)
        self._function_depth += 1
        for statement in node.body:
            self.visit(statement)
        self._function_depth -= 1
        self._scopes.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def _visit_argument_defaults(self, arguments: ast.arguments) -> None:
        for default in (*arguments.defaults, *arguments.kw_defaults):
            if default is not None:
                self.visit(default)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_argument_defaults(node.args)
        self._function_depth += 1
        self.visit(node.body)
        self._function_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        raw = _qualname(node.func)
        first, dot, rest = raw.partition(".")
        name = self._aliases.get(first, first) + (dot + rest if dot else "")
        kind = ""
        if name.startswith(("httpx.", "requests.", "urllib.request.", "aiohttp.")):
            kind = "network_candidate"
        elif name.startswith(("socket.", "websockets.")):
            kind = "socket_candidate"
        elif name.startswith(("subprocess.", "asyncio.create_subprocess", "os.system")):
            kind = "process_candidate"
        elif not self._function_depth and any(
            token in name.lower() for token in ("available", "health", "probe")
        ):
            kind = "collection_probe_candidate"
        if kind:
            self.signals.append(
                {
                    "kind": kind,
                    "call": name,
                    "line": node.lineno,
                    "phase": "collection" if not self._function_depth else "execution",
                }
            )
        self.generic_visit(node)


def _read_groups(root: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for name in GROUP_NAMES:
        group = root / "config" / "pytest-groups" / f"{name}.txt"
        if not group.is_file():
            result[name] = set()
            continue
        result[name] = {
            value
            for line in group.read_text(encoding="utf-8").splitlines()
            if (value := line.strip()) and not value.startswith("#")
        }
    return result


def _layer_hint(path: str, entry: dict[str, Any]) -> tuple[str, str]:
    test_type = entry.get("test_type")
    if "/e2e/" in path or "_e2e" in Path(path).stem:
        return "e2e_candidate", "path_name_only"
    return {
        "unit": ("unit", "catalog_type"),
        "route_contract": ("contract", "catalog_type"),
        "service_contract": ("contract", "catalog_type"),
        "integration": ("integration", "catalog_type"),
        "perf": ("performance", "catalog_type"),
        "gate": ("gate", "catalog_type"),
    }.get(test_type, ("unknown", "unregistered_or_unknown_type"))


def _inventory_row(
    root: Path, path: str, entry: dict[str, Any], groups: dict[str, set[str]]
) -> dict[str, Any]:
    candidate = root / path
    resolved = candidate.resolve()
    tests_root = (root / "tests").resolve()
    if not resolved.is_relative_to(tests_root) or not Path(path).name.startswith(
        "test_"
    ):
        raise ValueError(f"invalid test path in inventory: {path}")
    if not candidate.is_file():
        raise ValueError(f"catalog test does not exist: {path}")
    try:
        source = candidate.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=path)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ValueError(f"cannot parse test {path}: {exc}") from exc
    visitor = _SourceInventory()
    visitor.visit(tree)
    module_live = visitor.module_markers & LIVE_MARKERS
    marked_nodes = [
        case["name"]
        for case in visitor.test_markers
        if set(case["markers"]) & LIVE_MARKERS
    ]
    if module_live:
        environment = "declared_live"
    elif marked_nodes:
        environment = "partly_declared_live"
    else:
        environment = "unknown"
    current_groups = [name for name in GROUP_NAMES if path in groups[name]]
    costs = [name for name in ("fast", "long", "heavy") if name in current_groups]
    layer, layer_basis = _layer_hint(path, entry)
    return {
        "path": path,
        "catalogued": bool(entry),
        "domain": entry.get("domain"),
        "catalog_test_type": entry.get("test_type"),
        "layer_hint": layer,
        "layer_basis": layer_basis,
        "environment": environment,
        "environment_basis": "explicit_pytest_markers_only",
        "cost_groups": costs,
        "groups": current_groups,
        "primary_lane": entry.get("primary_lane"),
        "allowed_lanes": entry.get("allowed_lanes", []),
        "module_markers": sorted(visitor.module_markers),
        "declared_live_nodes": marked_nodes,
        "signals": visitor.signals,
        "manual_review_required": True,
    }


def build_inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    catalog_path = root / "config" / "testing" / "test_catalog.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog root must be a JSON object")
    entries = payload.get("tests")
    if not isinstance(entries, list):
        raise ValueError("catalog must contain a tests array")
    indexed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("invalid catalog entry")
        path = entry["path"]
        if path in indexed:
            raise ValueError(f"duplicate catalog path: {path}")
        indexed[path] = entry
    discovered = {
        path.relative_to(root).as_posix()
        for path in (root / "tests").rglob("test_*.py")
        if path.is_file()
    }
    groups = _read_groups(root)
    paths = sorted(set(indexed) | discovered)
    rows = [_inventory_row(root, path, indexed.get(path, {}), groups) for path in paths]
    counts = collections.Counter(row["environment"] for row in rows)
    counts_layer = collections.Counter(row["layer_hint"] for row in rows)
    signal_counts = collections.Counter(
        signal["kind"] for row in rows for signal in row["signals"]
    )
    return {
        "schema_version": 1,
        "limitations": [
            "Static signals are candidates; mocks and indirect I/O require human review.",
            "No signal is not evidence that a test is simulated or safe.",
            "Module markers describe declarations, not validated runtime behavior.",
            "Tests outside tests/**/test_*.py and browser tests are not inventoried.",
        ],
        "summary": {
            "catalogued_files": len(indexed),
            "discovered_files": len(discovered),
            "unregistered_files": len(discovered - set(indexed)),
            "environment": dict(sorted(counts.items())),
            "layer_hint": dict(sorted(counts_layer.items())),
            "signal_counts": dict(sorted(signal_counts.items())),
            "files_with_signals": sum(bool(row["signals"]) for row in rows),
            "files_requiring_manual_review": len(rows),
        },
        "tests": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument("--output", type=Path, help="Write JSON to this explicit path")
    parser.add_argument("--summary", action="store_true", help="Print summary only")
    parser.add_argument(
        "--review",
        choices=("unknown", "signals", "unregistered", "declared-live"),
        help="Filter the detailed report for manual review",
    )
    parser.add_argument(
        "--fail-on-unregistered",
        action="store_true",
        help="Return 1 when discovered tests are missing from the catalog",
    )
    args = parser.parse_args(argv)
    try:
        report = build_inventory(args.root)
        if args.review:
            if args.review == "unknown":
                selected = [
                    row for row in report["tests"] if row["environment"] == "unknown"
                ]
            elif args.review == "signals":
                selected = [row for row in report["tests"] if row["signals"]]
            elif args.review == "unregistered":
                selected = [row for row in report["tests"] if not row["catalogued"]]
            else:
                selected = [
                    row for row in report["tests"] if row["environment"] != "unknown"
                ]
            report = {**report, "review_filter": args.review, "tests": selected}
        encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        if args.summary:
            print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
        elif not args.output:
            print(encoded, end="")
        if args.fail_on_unregistered and report["summary"]["unregistered_files"]:
            return 1
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"inventory error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
