#!/usr/bin/env python3
"""Validate optional modules data policy and mutation guards."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from venom_core.core.module_data_policy import parse_module_data_policy_payload

MUTATING_DECORATORS = {"post", "put", "patch", "delete"}


@dataclass(frozen=True)
class Violation:
    manifest_path: str
    message: str


def _discover_manifests(repo_root: Path) -> list[Path]:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-files",
            "modules/*/module.json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        files = [
            repo_root / line.strip()
            for line in proc.stdout.splitlines()
            if line.strip()
        ]
        if files:
            return sorted(files)
    return sorted((repo_root / "modules").glob("*/module.json"))


def _resolve_router_file(manifest_path: Path, router_import: str) -> Path | None:
    module_path = router_import.split(":", maxsplit=1)[0].strip()
    if not module_path:
        return None
    parts = module_path.split(".")
    py_path = manifest_path.parent.joinpath(*parts).with_suffix(".py")
    if py_path.exists():
        return py_path
    init_path = manifest_path.parent.joinpath(*parts, "__init__.py")
    if init_path.exists():
        return init_path
    return None


def _has_mutating_routes(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            func = deco.func
            if isinstance(func, ast.Attribute) and func.attr in MUTATING_DECORATORS:
                return True
            if isinstance(func, ast.Attribute) and func.attr == "api_route":
                for kw in deco.keywords:
                    if kw.arg != "methods":
                        continue
                    value = kw.value
                    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                        continue
                    for item in value.elts:
                        if isinstance(item, ast.Constant) and isinstance(
                            item.value, str
                        ):
                            if item.value.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                                return True
    return False


def _guard_aliases(tree: ast.AST) -> set[str]:
    aliases = {"ensure_module_mutation_allowed"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "venom_core.core.module_data_policy":
            continue
        for imported in node.names:
            if imported.name == "ensure_module_mutation_allowed":
                aliases.add(imported.asname or imported.name)
    return aliases


def _has_guard_call(tree: ast.AST) -> bool:
    aliases = _guard_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in aliases:
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr in aliases:
            return True
    return False


def _validate_manifest(manifest_path: Path) -> list[Violation]:
    violations: list[Violation] = []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [Violation(str(manifest_path), f"cannot read manifest: {exc}")]

    if not isinstance(payload, dict):
        return [Violation(str(manifest_path), "manifest must be a JSON object")]

    module_id = str(payload.get("module_id", "")).strip() or "<missing_module_id>"
    backend = payload.get("backend")
    if not isinstance(backend, dict):
        return [Violation(str(manifest_path), "missing backend object")]

    _, policy_errors = parse_module_data_policy_payload(
        module_id=module_id,
        payload=backend.get("data_policy"),
    )
    for err in policy_errors:
        violations.append(Violation(str(manifest_path), err))

    router_import = str(backend.get("router_import", "")).strip()
    if not router_import:
        violations.append(
            Violation(str(manifest_path), "missing backend.router_import")
        )
        return violations

    router_file = _resolve_router_file(manifest_path, router_import)
    if router_file is None:
        violations.append(
            Violation(
                str(manifest_path),
                f"router module file not found for backend.router_import={router_import}",
            )
        )
        return violations

    try:
        tree = ast.parse(
            router_file.read_text(encoding="utf-8"), filename=str(router_file)
        )
    except Exception as exc:
        violations.append(
            Violation(
                str(manifest_path), f"cannot parse router file {router_file}: {exc}"
            )
        )
        return violations

    if _has_mutating_routes(tree) and not _has_guard_call(tree):
        violations.append(
            Violation(
                str(manifest_path),
                "router defines mutating endpoints but does not call "
                "ensure_module_mutation_allowed",
            )
        )
    return violations


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate optional module manifests for data-policy contract."
    )
    parser.add_argument(
        "--manifest",
        dest="manifests",
        action="append",
        default=[],
        help="Path to module.json (can be provided multiple times).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root for auto-discovery.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = args.repo_root.resolve()
    manifests = (
        [Path(item).resolve() for item in args.manifests]
        if args.manifests
        else _discover_manifests(repo_root)
    )
    if not manifests:
        print("ℹ️ No optional module manifests found. Skipping check.")
        return 0

    violations: list[Violation] = []
    for manifest in manifests:
        violations.extend(_validate_manifest(manifest))

    if violations:
        print("❌ Optional module contract violations detected:")
        for item in violations:
            print(f"- {item.manifest_path}: {item.message}")
        return 1

    print(f"✅ Optional module contracts check passed ({len(manifests)} manifests).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
