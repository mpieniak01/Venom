#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    print(
        "ERROR: PyYAML is required to run scripts/validate_sonar_architecture.py.\n"
        "Install it with 'pip install PyYAML' and rerun.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

ALLOWED_RELATIONS = {"deny", "exclusive-allow"}
ALLOWED_EXTENSIONS = {".json", ".yaml", ".yml"}


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Architecture config must be a mapping/object at root.")
    return payload


def _as_non_empty_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def _validate_pattern_list(name: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{name}: expected non-empty list of patterns.")
        return
    for index, item in enumerate(value):
        if _as_non_empty_text(item) is None:
            errors.append(f"{name}[{index}]: pattern must be a non-empty string.")


def _validate_constraint(node: Any, name: str, errors: list[str]) -> None:
    if not isinstance(node, dict):
        errors.append(f"{name}: constraint must be an object.")
        return
    _validate_pattern_list(f"{name}.from", node.get("from"), errors)
    _validate_pattern_list(f"{name}.to", node.get("to"), errors)

    relation = node.get("relation")
    if relation is None:
        return
    relation_text = _as_non_empty_text(relation)
    if relation_text is None or relation_text not in ALLOWED_RELATIONS:
        errors.append(
            f"{name}.relation: expected one of {sorted(ALLOWED_RELATIONS)}, got {relation!r}."
        )


def _validate_group(
    node: Any,
    name: str,
    errors: list[str],
    seen_paths: set[str],
    parent_path: str,
) -> None:
    if not isinstance(node, dict):
        errors.append(f"{name}: group must be an object.")
        return

    label = _as_non_empty_text(node.get("label"))
    if label is None:
        errors.append(f"{name}.label: required non-empty string.")
        label = "<invalid>"

    if "/" in label:
        errors.append(f"{name}.label: '/' is reserved for path separator.")

    group_path = f"{parent_path}/{label}" if parent_path else label
    if group_path in seen_paths:
        errors.append(f"{name}.label: duplicate group path '{group_path}'.")
    seen_paths.add(group_path)

    patterns = node.get("patterns")
    children = node.get("groups")

    if patterns is not None:
        _validate_pattern_list(f"{name}.patterns", patterns, errors)
    elif children is None:
        errors.append(
            f"{name}: group must define at least one of 'patterns' or 'groups'."
        )

    if children is None:
        children = []
    if not isinstance(children, list):
        errors.append(f"{name}.groups: expected list.")
        return
    for index, child in enumerate(children):
        _validate_group(
            child,
            f"{name}.groups[{index}]",
            errors,
            seen_paths,
            group_path,
        )


def _validate_perspective(
    node: Any,
    name: str,
    errors: list[str],
    seen_perspectives: set[str],
) -> tuple[int, int]:
    if not isinstance(node, dict):
        errors.append(f"{name}: perspective must be an object.")
        return (0, 0)

    label = _as_non_empty_text(node.get("label"))
    if label is None:
        errors.append(f"{name}.label: required non-empty string.")
        label = "<invalid>"
    if "/" in label:
        errors.append(f"{name}.label: '/' is reserved for path separator.")
    if label in seen_perspectives:
        errors.append(f"{name}.label: duplicate perspective label '{label}'.")
    seen_perspectives.add(label)

    groups = node.get("groups", [])
    if groups is None:
        groups = []
    if not isinstance(groups, list):
        errors.append(f"{name}.groups: expected list.")
        groups = []

    group_paths: set[str] = set()
    for index, group in enumerate(groups):
        _validate_group(
            group,
            f"{name}.groups[{index}]",
            errors,
            group_paths,
            label,
        )

    constraints = node.get("constraints", [])
    if constraints is None:
        constraints = []
    if not isinstance(constraints, list):
        errors.append(f"{name}.constraints: expected list.")
        constraints = []
    for index, constraint in enumerate(constraints):
        _validate_constraint(
            constraint,
            f"{name}.constraints[{index}]",
            errors,
        )

    return (len(group_paths), len(constraints))


def _validate_config(payload: dict[str, Any]) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []

    perspectives = payload.get("perspectives", [])
    if perspectives is None:
        perspectives = []
    if not isinstance(perspectives, list):
        errors.append("perspectives: expected list.")
        perspectives = []

    top_constraints = payload.get("constraints", [])
    if top_constraints is None:
        top_constraints = []
    if not isinstance(top_constraints, list):
        errors.append("constraints: expected list.")
        top_constraints = []
    for index, constraint in enumerate(top_constraints):
        _validate_constraint(constraint, f"constraints[{index}]", errors)

    seen_perspectives: set[str] = set()
    perspective_groups = 0
    perspective_constraints = 0
    for index, perspective in enumerate(perspectives):
        groups_count, constraints_count = _validate_perspective(
            perspective,
            f"perspectives[{index}]",
            errors,
            seen_perspectives,
        )
        perspective_groups += groups_count
        perspective_constraints += constraints_count

    if not perspectives and not top_constraints:
        errors.append("At least one of perspectives/constraints must be provided.")

    stats = {
        "perspectives": len(perspectives),
        "groups": perspective_groups,
        "constraints_top": len(top_constraints),
        "constraints_perspective": perspective_constraints,
    }
    return errors, stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Sonar architecture config structure (JSON/YAML)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/architecture/sonar-architecture.yaml"),
        help="Path to architecture config file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.config.suffix.lower() not in ALLOWED_EXTENSIONS:
        print(
            "❌ Unsupported file extension. Use .json, .yaml or .yml "
            f"(got {args.config.suffix!r})."
        )
        return 1
    if not args.config.exists():
        print(f"❌ Architecture config not found: {args.config}")
        return 1

    try:
        payload = _load_yaml_or_json(args.config)
    except Exception as exc:
        print(f"❌ Failed to parse architecture config {args.config}: {exc}")
        return 1

    errors, stats = _validate_config(payload)
    if errors:
        print("❌ Sonar architecture config validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "✅ Sonar architecture config validation passed "
        f"(perspectives={stats['perspectives']}, groups={stats['groups']}, "
        f"constraints={stats['constraints_top'] + stats['constraints_perspective']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
