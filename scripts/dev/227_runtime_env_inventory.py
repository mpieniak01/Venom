#!/usr/bin/env python3
"""PR227: inventory of runtime state readers/writers and env mutation points.

Outputs:
- JSON report (machine-friendly)
- Markdown report (human-friendly)
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_rg(pattern: str, scope: list[str]) -> list[dict[str, str | int]]:
    cmd = [
        "rg",
        "-n",
        "--no-heading",
        "--color",
        "never",
        pattern,
        *scope,
        "-g",
        "!**/.venv/**",
    ]
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"rg failed for pattern: {pattern}\n{proc.stderr}")
    rows: list[dict[str, str | int]] = []
    for line in proc.stdout.splitlines():
        # file:line:content
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        path, line_no, content = parts
        rows.append(
            {
                "path": path,
                "line": int(line_no),
                "snippet": content.strip(),
            }
        )
    return rows


def _md_table(rows: list[dict[str, str | int]]) -> str:
    if not rows:
        return "_Brak wynikow._\n"
    lines = ["| Plik | Linia | Fragment |", "|---|---:|---|"]
    for row in rows:
        path = str(row["path"]).replace("|", "\\|")
        line_no = row["line"]
        snippet = str(row["snippet"]).replace("|", "\\|")
        lines.append(f"| `{path}` | {line_no} | `{snippet}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="PR227 runtime/env inventory")
    parser.add_argument(
        "--json-output",
        default="test-results/diagnostics/227_runtime_env_inventory.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/diagnostics/227_runtime_env_inventory.md",
    )
    args = parser.parse_args()

    scope = ["venom_core", "scripts", "make", "web-next", "Makefile"]

    sections: dict[str, dict[str, object]] = {
        "runtime_live_reads": {
            "pattern": r"get_active_llm_runtime\(",
            "description": "Miejsca pobierajace live runtime.",
        },
        "settings_runtime_reads": {
            "pattern": r"SETTINGS\.LLM_MODEL_NAME|SETTINGS\.ACTIVE_LLM_SERVER|getattr\(SETTINGS,\s*\"LLM_MODEL_NAME\"|getattr\(SETTINGS,\s*\"ACTIVE_LLM_SERVER\"",
            "description": "Miejsca czytajace runtime bezposrednio z SETTINGS.",
        },
        "config_runtime_reads": {
            "pattern": r"config\.get\(\"LLM_MODEL_NAME\"\)|config\.get\(\"ACTIVE_LLM_SERVER\"\)",
            "description": "Miejsca czytajace runtime z persisted config.",
        },
        "env_mutation_calls": {
            "pattern": r"config_manager\.update_config\(",
            "description": "Miejsca posredniego zapisu do aktywnego ENV_FILE.",
        },
        "direct_settings_mutation": {
            "pattern": r"SETTINGS\.LLM_MODEL_NAME\s*=|SETTINGS\.ACTIVE_LLM_SERVER\s*=",
            "description": "Bezposrednie mutacje runtime settings in-memory.",
        },
        "env_file_resolution": {
            "pattern": r"ENV_FILE|\.env\.dev|\.env\.preprod|\.env\.local",
            "description": "Rozwiazywanie i uzycie plikow env.",
        },
    }

    results: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "sections": {},
    }

    md_lines = [
        "# 227 - Inwentaryzacja runtime/env",
        "",
        f"Generacja: `{datetime.now(timezone.utc).isoformat()}`",
        "",
    ]

    total_hits = 0
    for key, meta in sections.items():
        pattern = str(meta["pattern"])
        rows = _run_rg(pattern, scope)
        total_hits += len(rows)
        results["sections"][key] = {
            "description": meta["description"],
            "pattern": pattern,
            "count": len(rows),
            "hits": rows,
        }
        md_lines.append(f"## {key}")
        md_lines.append("")
        md_lines.append(f"- Opis: {meta['description']}")
        md_lines.append(f"- Pattern: `{pattern}`")
        md_lines.append(f"- Trafienia: **{len(rows)}**")
        md_lines.append("")
        md_lines.append(_md_table(rows))
        md_lines.append("")

    results["summary"] = {"total_hits": total_hits, "sections_count": len(sections)}
    md_lines.append("## Podsumowanie")
    md_lines.append("")
    md_lines.append(f"- Sekcji: **{len(sections)}**")
    md_lines.append(f"- Laczna liczba trafien: **{total_hits}**")
    md_lines.append("")

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"✅ JSON: {json_path}")
    print(f"✅ MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
