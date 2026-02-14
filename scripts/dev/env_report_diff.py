#!/usr/bin/env python3
"""Compare two env audit JSON reports and summarize footprint deltas."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    val = float(abs(size))
    sign = "-" if size < 0 else ""
    for unit in units:
        if val < 1024 or unit == units[-1]:
            return f"{sign}{val:.1f} {unit}"
        val /= 1024
    return f"{size} B"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_latest_reports(logs_dir: Path) -> tuple[Path, Path]:
    files = sorted(logs_dir.glob("diag-env-*.json"))
    if len(files) < 2:
        raise FileNotFoundError("Need at least 2 diag-env-*.json reports in logs/")
    return files[-2], files[-1]


def _dir_map(report: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in report.get("artifacts", {}).get("directories", []):
        out[str(item.get("path"))] = int(item.get("size_bytes", 0))
    return out


def _build_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    bmap = _dir_map(before)
    amap = _dir_map(after)
    paths = sorted(set(bmap) | set(amap))

    rows = []
    total_before = 0
    total_after = 0
    for path in paths:
        b = bmap.get(path, 0)
        a = amap.get(path, 0)
        total_before += b
        total_after += a
        rows.append(
            {
                "path": path,
                "before_bytes": b,
                "after_bytes": a,
                "delta_bytes": a - b,
            }
        )

    rows.sort(key=lambda r: abs(r["delta_bytes"]), reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_before_bytes": total_before,
        "total_after_bytes": total_after,
        "total_delta_bytes": total_after - total_before,
        "rows": rows,
    }


def _to_markdown(diff: dict[str, Any], before_path: Path, after_path: Path) -> str:
    lines = [
        "# Env Audit Diff",
        "",
        f"Before: `{before_path}`",
        f"After: `{after_path}`",
        "",
        f"Total delta: **{_human_size(diff['total_delta_bytes'])}**",
        "",
        "| Path | Before | After | Delta |",
        "|---|---:|---:|---:|",
    ]

    for row in diff["rows"]:
        lines.append(
            f"| `{row['path']}` | {_human_size(row['before_bytes'])} | {_human_size(row['after_bytes'])} | {_human_size(row['delta_bytes'])} |"
        )

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two env audit JSON reports")
    parser.add_argument("--before", type=Path, default=None)
    parser.add_argument("--after", type=Path, default=None)
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.before and args.after:
        before_path, after_path = args.before, args.after
    else:
        try:
            before_path, after_path = _find_latest_reports(args.logs_dir)
        except FileNotFoundError as exc:
            print(f"❌ {exc}")
            return 1

    before = _load(before_path)
    after = _load(after_path)
    diff = _build_diff(before, after)

    out = args.output
    if out is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = args.logs_dir / f"diag-env-diff-{ts}.md"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_to_markdown(diff, before_path, after_path), encoding="utf-8")
    print(f"✅ Env diff written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
