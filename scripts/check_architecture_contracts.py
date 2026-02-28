#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Violation:
    rule_id: str
    file_path: str
    importer_module: str
    imported_module: str
    rule_description: str


def _matches_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def _load_contracts(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Contract file must be a JSON object.")
    if "rules" not in payload or not isinstance(payload["rules"], list):
        raise ValueError("Contract file must contain a 'rules' list.")
    return payload


def _module_name_from_path(file_path: Path, source_root: Path) -> str:
    rel = file_path.relative_to(source_root)
    if rel.name == "__init__.py":
        rel_parts = rel.parent.parts
    else:
        rel_parts = rel.with_suffix("").parts
    if not rel_parts:
        return source_root.name
    return ".".join((source_root.name, *rel_parts))


def _resolve_from_import(current_module: str, module: str | None, level: int) -> str:
    if level == 0:
        return module or ""

    package_parts = current_module.split(".")[:-1]
    up = level - 1
    if up > len(package_parts):
        return ""
    package_parts = package_parts[: len(package_parts) - up]
    if module:
        return ".".join([*package_parts, *module.split(".")])
    return ".".join(package_parts)


def _parse_imported_modules(file_path: Path, module_name: str) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_from_import(module_name, node.module, node.level)
            if resolved:
                imported.add(resolved)
    return sorted(imported)


def _rule_applies(importer_module: str, rule: dict[str, Any]) -> bool:
    from_prefixes = [str(v) for v in rule.get("from_prefixes", [])]
    if not from_prefixes:
        return False
    if not any(_matches_prefix(importer_module, prefix) for prefix in from_prefixes):
        return False
    except_prefixes = [str(v) for v in rule.get("except_from_prefixes", [])]
    if any(_matches_prefix(importer_module, prefix) for prefix in except_prefixes):
        return False
    return True


def evaluate_module_imports(
    importer_module: str, imported_modules: list[str], contracts: dict[str, Any]
) -> list[Violation]:
    violations: list[Violation] = []
    for rule in contracts["rules"]:
        if not isinstance(rule, dict):
            continue
        if not _rule_applies(importer_module, rule):
            continue
        forbidden_prefixes = [str(v) for v in rule.get("forbidden_import_prefixes", [])]
        for imported in imported_modules:
            if any(_matches_prefix(imported, prefix) for prefix in forbidden_prefixes):
                violations.append(
                    Violation(
                        rule_id=str(rule.get("id", "unknown_rule")),
                        file_path="",
                        importer_module=importer_module,
                        imported_module=imported,
                        rule_description=str(rule.get("description", "")),
                    )
                )
    return violations


def scan_source_tree(source_root: Path, contracts: dict[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    for file_path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in file_path.parts:
            continue
        module_name = _module_name_from_path(file_path, source_root)
        imported_modules = _parse_imported_modules(file_path, module_name)
        found = evaluate_module_imports(module_name, imported_modules, contracts)
        for violation in found:
            violations.append(
                Violation(
                    rule_id=violation.rule_id,
                    file_path=str(file_path),
                    importer_module=violation.importer_module,
                    imported_module=violation.imported_module,
                    rule_description=violation.rule_description,
                )
            )
    return violations


def _print_text_report(violations: list[Violation]) -> None:
    if not violations:
        print("✅ Architecture contracts check passed (no violations).")
        return
    print("❌ Architecture contract violations detected:")
    for item in violations:
        print(
            f"- [{item.rule_id}] {item.importer_module} -> {item.imported_module}"
            f" ({item.file_path})"
        )
        if item.rule_description:
            print(f"  rule: {item.rule_description}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate architecture dependency contracts."
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=Path("config/architecture/contracts.yaml"),
        help="Path to contracts file (JSON-compatible YAML).",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("venom_core"),
        help="Source root to scan.",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Report output format.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contracts = _load_contracts(args.contracts)
    violations = scan_source_tree(args.source_root, contracts)
    if args.output == "json":
        print(
            json.dumps(
                [
                    {
                        "rule_id": v.rule_id,
                        "file_path": v.file_path,
                        "importer_module": v.importer_module,
                        "imported_module": v.imported_module,
                        "rule_description": v.rule_description,
                    }
                    for v in violations
                ],
                ensure_ascii=True,
                indent=2,
            )
        )
    else:
        _print_text_report(violations)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
