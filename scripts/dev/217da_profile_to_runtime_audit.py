"""Audit mapping from profile contract to daemon runtime parameters."""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _extract_update_params_fields(engine_path: Path) -> set[str]:
    tree = ast.parse(engine_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "MultiRuntimeDaemon":
            continue
        for class_node in node.body:
            if (
                isinstance(class_node, ast.FunctionDef)
                and class_node.name == "update_params"
            ):
                fields: set[str] = set()
                for arg in class_node.args.args:
                    if arg.arg != "self":
                        fields.add(arg.arg)
                return fields
    return set()


def _extract_apply_matrix_fields(service_path: Path) -> dict[str, str]:
    tree = ast.parse(service_path.read_text(encoding="utf-8"))
    for node in tree.body:
        target_name: str | None = None
        value_node: ast.AST | None = None

        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                target_name = target.id
                value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value

        if target_name != "APPLY_MATRIX":
            continue
        if not isinstance(value_node, ast.Dict):
            continue

        matrix: dict[str, str] = {}
        for key_node, mode_node in zip(value_node.keys, value_node.values):
            if not isinstance(key_node, ast.Constant) or not isinstance(
                mode_node, ast.Constant
            ):
                continue
            if isinstance(key_node.value, str) and isinstance(mode_node.value, str):
                matrix[key_node.value] = mode_node.value
        return matrix
    return {}


def main() -> None:
    engine_path = REPO_ROOT / "services" / "multi_runtime" / "engine.py"
    profile_service_path = (
        REPO_ROOT / "venom_core" / "services" / "multi_runtime_profile_service.py"
    )
    daemon_fields = _extract_update_params_fields(engine_path)
    apply_matrix = _extract_apply_matrix_fields(profile_service_path)

    profile_fields = set(apply_matrix.keys())
    live_or_reload_fields = {
        field
        for field, mode in apply_matrix.items()
        if mode in {"live", "soft_reload", "hard_restart"}
    }

    report = {
        "phase": "217DA/F0",
        "daemon_update_params_fields": sorted(daemon_fields),
        "profile_fields": sorted(profile_fields),
        "accepted_profile_fields": sorted(live_or_reload_fields),
        "mapped_live_fields": sorted(live_or_reload_fields & daemon_fields),
        "missing_in_daemon_update_params": sorted(
            live_or_reload_fields - daemon_fields
        ),
        "unsupported_profile_fields": sorted(
            field for field, mode in apply_matrix.items() if mode == "unsupported"
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
