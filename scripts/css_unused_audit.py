#!/usr/bin/env python3
"""Heuristic audit for unused CSS classes/ids in legacy templates and JS."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CLASS_SELECTOR_RE = re.compile(r"(?<![\w-])\.([a-zA-Z_][\w-]*)")
ID_SELECTOR_RE = re.compile(r"(?<![\w-])#([a-zA-Z_][\w-]*)")
CLASS_ATTR_RE = re.compile(r"\bclass(?:Name)?\s*=\s*[\"']([^\"']+)[\"']")
ID_ATTR_RE = re.compile(r"\bid\s*=\s*[\"']([^\"']+)[\"']")
CLASSLIST_RE = re.compile(r"classList\.(?:add|remove|toggle|contains)\(([^)]*)\)")
STRING_RE = re.compile(r"[\"']([^\"']+)[\"']")
QUERY_SELECTOR_RE = re.compile(r"querySelector(All)?\(\s*[\"']([^\"']+)[\"']\s*\)")
GET_ELEMENT_BY_ID_RE = re.compile(r"getElementById\(\s*[\"']([^\"']+)[\"']\s*\)")


def extract_css_selectors(text: str) -> tuple[set[str], set[str]]:
    classes = set(CLASS_SELECTOR_RE.findall(text))
    ids = set(ID_SELECTOR_RE.findall(text))
    return classes, ids


def extract_used_selectors(text: str) -> tuple[set[str], set[str]]:
    classes: set[str] = set()
    ids: set[str] = set()

    for match in CLASS_ATTR_RE.finditer(text):
        classes.update(filter(None, match.group(1).split()))

    for match in ID_ATTR_RE.finditer(text):
        ids.add(match.group(1).strip())

    for match in CLASSLIST_RE.finditer(text):
        for literal in STRING_RE.findall(match.group(1)):
            classes.update(filter(None, literal.split()))

    for match in QUERY_SELECTOR_RE.finditer(text):
        selector = match.group(2)
        classes.update(CLASS_SELECTOR_RE.findall(selector))
        ids.update(ID_SELECTOR_RE.findall(selector))

    for match in GET_ELEMENT_BY_ID_RE.finditer(text):
        ids.add(match.group(1).strip())

    return classes, ids


def gather_files(root: Path) -> dict[str, list[Path]]:
    css_files = [root / "web-next/app/globals.css"]

    scan_files: list[Path] = []
    scan_files.extend(root.glob("web-next/**/*.tsx"))
    scan_files.extend(root.glob("web-next/**/*.ts"))
    scan_files.extend(root.glob("web-next/**/*.jsx"))
    scan_files.extend(root.glob("web-next/**/*.js"))
    scan_files.extend(root.glob("web-next/**/*.mdx"))

    skip_dirs = {"node_modules", ".next", "dist", "build", ".turbo"}

    return {
        "css": [p for p in css_files if p.exists()],
        "scan": [
            p
            for p in scan_files
            if p.exists()
            and p.is_file()
            and not any(part in skip_dirs for part in p.parts)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit unused CSS selectors (heuristic)."
    )
    parser.add_argument("--root", default=".", help="Repo root (default: .)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on-unused", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files = gather_files(root)

    used_classes: set[str] = set()
    used_ids: set[str] = set()

    for file_path in files["scan"]:
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="latin-1")
        classes, ids = extract_used_selectors(text)
        used_classes.update(classes)
        used_ids.update(ids)

    report = {
        "root": str(root),
        "files": [],
        "summary": {
            "total_unused_classes": 0,
            "total_unused_ids": 0,
            "note": "Heuristic scan; dynamic selectors or runtime-injected classes may be missed.",
        },
    }

    for css_file in files["css"]:
        text = css_file.read_text(encoding="utf-8")
        css_classes, css_ids = extract_css_selectors(text)
        unused_classes = sorted(css_classes - used_classes)
        unused_ids = sorted(css_ids - used_ids)

        report["files"].append(
            {
                "path": str(css_file.relative_to(root)),
                "unused_classes": unused_classes,
                "unused_ids": unused_ids,
            }
        )

        report["summary"]["total_unused_classes"] += len(unused_classes)
        report["summary"]["total_unused_ids"] += len(unused_ids)

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print("CSS unused selector audit (heuristic)")
        for item in report["files"]:
            print(
                f"- {item['path']}: {len(item['unused_classes'])} classes, {len(item['unused_ids'])} ids"
            )
        print(
            f"Total unused classes: {report['summary']['total_unused_classes']}, "
            f"unused ids: {report['summary']['total_unused_ids']}"
        )

    if args.fail_on_unused and (
        report["summary"]["total_unused_classes"] > 0
        or report["summary"]["total_unused_ids"] > 0
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
