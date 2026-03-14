#!/usr/bin/env python3
"""202C runtime inventory and Gemma-3 availability audit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _202c_common import (
    GEMMA3_TOKENS,
    dump_json,
    dump_text,
    get_active_runtime,
    http_json,
    resolve_base_url,
    runtime_models_from_options,
    wait_backend_ready,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="202C runtime inventory snapshot")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--base-url", default="")
    parser.add_argument(
        "--json-output",
        default="test-results/202c/runtime_inventory.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/202c/runtime_inventory.md",
    )
    return parser.parse_args()


def _gemma3_presence(models: list[str]) -> dict[str, Any]:
    gemma_models = [
        name for name in models if any(token in name.lower() for token in GEMMA3_TOKENS)
    ]
    aliases = sorted(
        {name.split(":", 1)[0].strip() for name in gemma_models if ":" in name}
    )
    canonicals = sorted({name for name in gemma_models if "-" in name})
    return {
        "available": bool(gemma_models),
        "count": len(gemma_models),
        "models": gemma_models,
        "aliases": aliases,
        "canonicals": canonicals,
    }


def _build_contract_issues(
    *,
    options_payload: dict[str, Any],
    servers_payload: dict[str, Any],
    active_payload: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    runtimes = (
        options_payload.get("runtimes") if isinstance(options_payload, dict) else []
    )
    runtime_ids: set[str] = set()
    if isinstance(runtimes, list):
        for item in runtimes:
            if not isinstance(item, dict):
                continue
            runtime_id = str(item.get("runtime_id") or "").strip().lower()
            if runtime_id:
                runtime_ids.add(runtime_id)

    servers = (
        servers_payload.get("servers") if isinstance(servers_payload, dict) else []
    )
    server_ids = {
        str(item.get("name") or "").strip().lower()
        for item in servers
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }

    missing_in_servers = sorted(runtime_ids.difference(server_ids))
    for runtime_id in missing_in_servers:
        if runtime_id == "onnx":
            continue
        issues.append(f"runtime_missing_in_servers:{runtime_id}")

    active_runtime = str(active_payload.get("active_server") or "").strip().lower()
    if active_runtime and active_runtime not in runtime_ids:
        issues.append(f"active_runtime_not_in_options:{active_runtime}")

    for runtime_id in sorted(runtime_ids):
        models = runtime_models_from_options(options_payload, runtime_id)
        if not models:
            issues.append(f"runtime_has_no_models:{runtime_id}")
            continue
        lower_models = [name.lower() for name in models]
        has_alias = any("gemma3:" in name for name in lower_models)
        has_canonical = any("gemma-3" in name for name in lower_models)
        if has_alias and not has_canonical:
            issues.append(f"gemma3_alias_without_canonical:{runtime_id}")
        if has_canonical and not has_alias and runtime_id == "ollama":
            issues.append(f"gemma3_canonical_without_alias:{runtime_id}")

    return issues


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 202C Runtime Inventory")
    lines.append("")
    lines.append(f"Generated at: {report['generated_at']}")
    lines.append(f"Base URL: {report['base_url']}")
    lines.append("")
    lines.append("## Runtime Matrix")
    lines.append("")
    lines.append("| Runtime | Configured | Available | Active | Models | Gemma-3 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in report["runtime_inventory"]:
        lines.append(
            "| {runtime_id} | {configured} | {available} | {active} | {model_count} | {gemma3} |".format(
                runtime_id=row["runtime_id"],
                configured="yes" if row.get("configured") else "no",
                available="yes" if row.get("available") else "no",
                active="yes" if row.get("active") else "no",
                model_count=row.get("model_count", 0),
                gemma3="yes" if row.get("gemma3", {}).get("available") else "no",
            )
        )
    lines.append("")
    lines.append("## Contract Issues")
    lines.append("")
    issues = report.get("contract_issues", [])
    if not issues:
        lines.append("- none")
    else:
        for issue in issues:
            lines.append(f"- {issue}")
    lines.append("")
    lines.append("## Active Runtime")
    lines.append("")
    active = report.get("active", {})
    lines.append(f"- active_server: {active.get('active_server', '')}")
    lines.append(f"- active_model: {active.get('active_model', '')}")
    lines.append(f"- runtime_id: {active.get('runtime_id', '')}")
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[2]
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (root / env_file).resolve()

    base_url = resolve_base_url(env_file=env_file, explicit=args.base_url)
    if not wait_backend_ready(base_url, timeout_sec=30):
        report = {
            "ok": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "base_url": base_url,
            "error": "backend_not_ready",
            "runtime_inventory": [],
            "contract_issues": ["backend_not_ready"],
        }
        dump_json((root / args.json_output).resolve(), report)
        dump_text(
            (root / args.md_output).resolve(),
            "# 202C Runtime Inventory\n\nBackend not ready.",
        )
        return 1

    options_code, options_payload = http_json(
        f"{base_url}/api/v1/system/llm-runtime/options", timeout_sec=30.0
    )
    servers_code, servers_payload = http_json(
        f"{base_url}/api/v1/system/llm-servers", timeout_sec=30.0
    )
    active_code, active_payload_raw = get_active_runtime(base_url)

    options = options_payload if isinstance(options_payload, dict) else {}
    servers = servers_payload if isinstance(servers_payload, dict) else {}
    active = active_payload_raw if isinstance(active_payload_raw, dict) else {}

    runtime_rows: list[dict[str, Any]] = []
    runtimes = options.get("runtimes") if isinstance(options, dict) else []
    if isinstance(runtimes, list):
        for item in runtimes:
            if not isinstance(item, dict):
                continue
            runtime_id = str(item.get("runtime_id") or "").strip().lower()
            if not runtime_id:
                continue
            models = runtime_models_from_options(options, runtime_id)
            runtime_rows.append(
                {
                    "runtime_id": runtime_id,
                    "configured": bool(item.get("configured")),
                    "available": bool(item.get("available")),
                    "status": str(item.get("status") or ""),
                    "reason": item.get("reason"),
                    "active": bool(item.get("active")),
                    "model_count": len(models),
                    "models": models,
                    "gemma3": _gemma3_presence(models),
                }
            )

    contract_issues = _build_contract_issues(
        options_payload=options,
        servers_payload=servers,
        active_payload=active,
    )

    report = {
        "ok": options_code == 200 and servers_code == 200 and active_code == 200,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "endpoint_status": {
            "options": options_code,
            "servers": servers_code,
            "active": active_code,
        },
        "active": {
            "active_server": str(active.get("active_server") or ""),
            "active_model": str(active.get("active_model") or ""),
            "runtime_id": str(active.get("runtime_id") or ""),
        },
        "runtime_inventory": runtime_rows,
        "contract_issues": contract_issues,
        "raw": {
            "options": options,
            "servers": servers,
            "active": active,
        },
    }

    json_path = (root / args.json_output).resolve()
    md_path = (root / args.md_output).resolve()
    dump_json(json_path, report)
    dump_text(md_path, _build_markdown(report))

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
