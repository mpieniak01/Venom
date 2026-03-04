#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "ERROR: PyYAML is required to run scripts/export_sonar_intended_architecture_payload.py. "
        "Install it with 'pip install PyYAML' and rerun."
    ) from exc


@dataclass(frozen=True)
class GroupRow:
    perspective: str
    path: str
    pattern_count: int


def _read_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Architecture config must be a mapping/object.")
    return payload


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


def _collect_groups(
    perspective: str,
    groups: Any,
    parent_path: str,
    out_rows: list[GroupRow],
) -> None:
    if not isinstance(groups, list):
        return
    for group in groups:
        if not isinstance(group, dict):
            continue
        label = _text(group.get("label")).strip()
        if not label:
            continue
        group_path = f"{parent_path}/{label}" if parent_path else label
        patterns = group.get("patterns")
        pattern_count = len(patterns) if isinstance(patterns, list) else 0
        out_rows.append(
            GroupRow(
                perspective=perspective,
                path=group_path,
                pattern_count=pattern_count,
            )
        )
        _collect_groups(perspective, group.get("groups"), group_path, out_rows)


def build_summary(payload: dict[str, Any]) -> dict[str, Any]:
    perspectives = payload.get("perspectives", [])
    top_constraints = payload.get("constraints", [])
    rows: list[GroupRow] = []
    perspective_rows: list[dict[str, Any]] = []

    if not isinstance(perspectives, list):
        perspectives = []
    if not isinstance(top_constraints, list):
        top_constraints = []

    for perspective in perspectives:
        if not isinstance(perspective, dict):
            continue
        label = _text(perspective.get("label")).strip()
        if not label:
            continue
        _collect_groups(label, perspective.get("groups"), label, rows)
        p_constraints = perspective.get("constraints", [])
        p_constraints_count = (
            len(p_constraints) if isinstance(p_constraints, list) else 0
        )
        perspective_rows.append(
            {
                "label": label,
                "description": _text(perspective.get("description")).strip(),
                "constraints_count": p_constraints_count,
            }
        )

    return {
        "perspectives_count": len(perspective_rows),
        "groups_count": len(rows),
        "constraints_count": len(top_constraints)
        + sum(int(item["constraints_count"]) for item in perspective_rows),
        "perspectives": perspective_rows,
        "groups": [
            {
                "perspective": row.perspective,
                "path": row.path,
                "pattern_count": row.pattern_count,
            }
            for row in rows
        ],
        "top_level_constraints_count": len(top_constraints),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Sonar architecture config summary payload for UI sync/review."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/architecture/sonar-architecture.yaml"),
        help="Path to Sonar architecture config file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test-results/sonar/architecture-summary.json"),
        help="Output JSON summary path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.config.exists():
        print(f"❌ Config file not found: {args.config}")
        return 1

    try:
        payload = _read_config(args.config)
        summary = build_summary(payload)
    except Exception as exc:
        print(f"❌ Failed to export summary: {exc}")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        "✅ Exported Sonar architecture summary to "
        f"{args.output} (perspectives={summary['perspectives_count']}, "
        f"groups={summary['groups_count']}, constraints={summary['constraints_count']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
