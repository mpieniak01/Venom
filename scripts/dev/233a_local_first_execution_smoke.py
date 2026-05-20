#!/usr/bin/env python3
"""PR233A local-first execution smoke.

Checks practical readiness for:
- VS Code + Ollama daily surface
- Pi as lightweight terminal agent
- Codex CLI / IDE extension for shell+git feedback

Outputs:
- JSON report
- Markdown report
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

PREFERRED_MODELS = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:3b",
    "qwen3.5:latest",
]


@dataclass(slots=True)
class CmdResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def _cmd_to_dict(result: CmdResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _run_cmd(
    cmd: list[str], *, cwd: Path | None = None, timeout: float = 20.0
) -> CmdResult:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CmdResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=(proc.stdout or "").strip(),
            stderr=(proc.stderr or "").strip(),
        )
    except subprocess.TimeoutExpired as exc:
        return CmdResult(
            ok=False,
            exit_code=124,
            stdout=(exc.stdout or "").strip() if exc.stdout else "",
            stderr=f"timeout after {timeout}s",
        )


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> tuple[bool, int, dict[str, Any] | list[Any] | str]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if not body:
                return True, resp.status, {}
            try:
                return True, resp.status, json.loads(body)
            except json.JSONDecodeError:
                return True, resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            parsed: dict[str, Any] | list[Any] | str = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = body
        return False, exc.code, parsed
    except Exception as exc:  # noqa: BLE001
        return False, 0, str(exc)


def _detect_vscode_codex_extension() -> dict[str, Any]:
    base = Path.home() / ".vscode-server" / "extensions"
    if not base.exists():
        base = Path.home() / ".vscode" / "extensions"
        if not base.exists():
            return {
                "found": False,
                "path": None,
                "note": "~/.vscode-server/extensions and ~/.vscode/extensions missing",
            }
    matches = sorted(base.glob("openai.chatgpt-*"))
    if not matches:
        return {
            "found": False,
            "path": None,
            "note": "openai.chatgpt extension not found",
        }
    latest = matches[-1]
    codex_bin = latest / "bin" / "linux-x86_64" / "codex"
    return {
        "found": codex_bin.exists(),
        "path": str(codex_bin) if codex_bin.exists() else str(latest),
        "note": "codex binary discovered"
        if codex_bin.exists()
        else "chatgpt extension found, codex binary missing",
    }


def _pick_model(local_models: list[str]) -> str | None:
    local_set = set(local_models)
    for m in PREFERRED_MODELS:
        if m in local_set:
            return m
    return local_models[0] if local_models else None


def _run_codex_exec_smoke(model: str | None) -> CmdResult:
    if not model:
        return CmdResult(
            ok=False,
            exit_code=1,
            stdout="",
            stderr="no local model selected for codex exec smoke",
        )
    return _run_cmd(
        [
            "codex",
            "exec",
            "--oss",
            "--local-provider",
            "ollama",
            "--model",
            model,
            "--cd",
            str(REPO_ROOT),
            "--sandbox",
            "workspace-write",
            "Powiedz tylko OK.",
        ],
        cwd=REPO_ROOT,
        timeout=90.0,
    )


def _md_bool(value: bool) -> str:
    return "PASS" if value else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(description="PR233A local-first smoke runner")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--json-output", default="test-results/233a/local_first_execution_smoke.json"
    )
    parser.add_argument(
        "--md-output", default="test-results/233a/local_first_execution_smoke.md"
    )
    parser.add_argument(
        "--prompt", default="Napisz jedno zdanie: local-first smoke passed."
    )
    args = parser.parse_args()

    started = time.time()
    report: dict[str, Any] = {
        "scope": "pr233a-local-first-execution-smoke",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "ollama_url": args.ollama_url,
        "checks": {},
        "summary": {},
    }

    # tool availability
    tools = {
        "ollama": shutil.which("ollama"),
        "pi": shutil.which("pi"),
        "codex": shutil.which("codex"),
        "git": shutil.which("git"),
        "ps": shutil.which("ps"),
    }
    report["checks"]["tool_paths"] = tools

    # versions
    versions: dict[str, Any] = {}
    versions["ollama"] = (
        _cmd_to_dict(_run_cmd(["ollama", "--version"]))
        if tools["ollama"]
        else {"ok": False, "exit_code": 127, "stdout": "", "stderr": "not found"}
    )
    versions["codex"] = (
        _cmd_to_dict(_run_cmd(["codex", "--version"]))
        if tools["codex"]
        else {"ok": False, "exit_code": 127, "stdout": "", "stderr": "not found"}
    )
    versions["pi"] = (
        _cmd_to_dict(_run_cmd(["pi", "--version"]))
        if tools["pi"]
        else {"ok": False, "exit_code": 127, "stdout": "", "stderr": "not found"}
    )
    report["checks"]["tool_versions"] = versions

    # vscode extension detect
    report["checks"]["codex_ide_extension"] = _detect_vscode_codex_extension()

    # shell smoke
    shell: dict[str, Any] = {}
    shell["ls"] = _cmd_to_dict(_run_cmd(["ls", "-la", "."], cwd=REPO_ROOT))
    shell["ps"] = _cmd_to_dict(
        _run_cmd(["ps", "-eo", "pid,comm,%mem,%cpu", "--sort=-%mem"], cwd=REPO_ROOT)
    )
    shell["git_status"] = _cmd_to_dict(
        _run_cmd(["git", "status", "--short", "--branch"], cwd=REPO_ROOT)
    )
    shell["git_diff_shortstat"] = _cmd_to_dict(
        _run_cmd(["git", "diff", "--shortstat"], cwd=REPO_ROOT)
    )
    report["checks"]["shell_smoke"] = shell

    # env profile hints
    profile = {
        "ACTIVE_LLM_SERVER": os.environ.get("ACTIVE_LLM_SERVER", "<unset>"),
        "OLLAMA_NO_CLOUD": os.environ.get("OLLAMA_NO_CLOUD", "<unset>"),
        "VENOM_PAUSE_BACKGROUND_TASKS": os.environ.get(
            "VENOM_PAUSE_BACKGROUND_TASKS", "<unset>"
        ),
        "OLLAMA_CONTEXT_LENGTH": os.environ.get("OLLAMA_CONTEXT_LENGTH", "<unset>"),
    }
    report["checks"]["env_profile"] = profile

    # ollama connectivity and models
    ok_tags, status_tags, payload_tags = _http_json(
        f"{args.ollama_url.rstrip('/')}/api/tags", timeout=20.0
    )
    local_models: list[str] = []
    if isinstance(payload_tags, dict):
        models = payload_tags.get("models")
        if isinstance(models, list):
            for item in models:
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    local_models.append(item["name"])
    model_pick = _pick_model(local_models)
    report["checks"]["ollama_tags"] = {
        "ok": ok_tags,
        "status": status_tags,
        "local_models_count": len(local_models),
        "preferred_models_found": [
            m for m in PREFERRED_MODELS if m in set(local_models)
        ],
        "selected_model_for_smoke": model_pick,
    }

    # local model smoke
    model_smoke: dict[str, Any] = {
        "ok": False,
        "status": 0,
        "response_excerpt": "",
        "error": "",
    }
    if model_pick:
        ok_gen, status_gen, payload_gen = _http_json(
            f"{args.ollama_url.rstrip('/')}/api/generate",
            method="POST",
            payload={"model": model_pick, "prompt": args.prompt, "stream": False},
            timeout=60.0,
        )
        model_smoke["ok"] = bool(ok_gen and status_gen == 200)
        model_smoke["status"] = status_gen
        if isinstance(payload_gen, dict):
            response_text = str(payload_gen.get("response") or "")
            model_smoke["response_excerpt"] = response_text[:220]
            if not response_text:
                model_smoke["error"] = "empty response"
        else:
            model_smoke["error"] = str(payload_gen)[:220]
    else:
        model_smoke["error"] = "no local models discovered"
    report["checks"]["local_model_smoke"] = model_smoke

    # codex exec smoke
    codex_exec_result = _run_codex_exec_smoke(model_pick)
    codex_exec_smoke = _cmd_to_dict(codex_exec_result)
    codex_exec_smoke["response_excerpt"] = codex_exec_smoke["stdout"][-240:]
    report["checks"]["codex_exec_smoke"] = codex_exec_smoke

    # summary
    gate_items = {
        "ollama_available": bool(tools["ollama"]),
        "codex_cli_available": bool(tools["codex"]),
        "pi_available": bool(tools["pi"]),
        "pi_cli_responds": bool(versions["pi"].get("ok")),
        "ollama_reachable": bool(ok_tags and status_tags == 200),
        "local_model_response": bool(model_smoke["ok"]),
        "codex_exec_response": bool(codex_exec_result.ok),
        "shell_ls": bool(shell["ls"]["ok"]),
        "shell_ps": bool(shell["ps"]["ok"]),
        "shell_git_status": bool(shell["git_status"]["ok"]),
    }
    report["summary"] = {
        "checks": gate_items,
        "pass_count": sum(1 for v in gate_items.values() if v),
        "total_count": len(gate_items),
        "overall": "PASS" if all(gate_items.values()) else "PARTIAL",
        "duration_sec": round(time.time() - started, 2),
    }

    # write outputs
    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR233A Local-First Execution Smoke",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Overall: **{report['summary']['overall']}** ({report['summary']['pass_count']}/{report['summary']['total_count']})",
        "",
        "## Gate Checks",
    ]
    for key, value in gate_items.items():
        md_lines.append(f"- `{key}`: **{_md_bool(bool(value))}**")
    md_lines.extend(
        [
            "",
            "## Tool Paths",
            f"- `ollama`: `{tools['ollama']}`",
            f"- `pi`: `{tools['pi']}`",
            f"- `codex`: `{tools['codex']}`",
            "",
            "## Selected Model",
            f"- selected: `{model_pick}`",
            f"- model smoke: **{_md_bool(bool(model_smoke['ok']))}**",
            f"- codex exec smoke: **{_md_bool(bool(codex_exec_result.ok))}**",
            "",
            "## Shell Smoke",
            f"- `ls`: **{_md_bool(bool(shell['ls']['ok']))}**",
            f"- `ps`: **{_md_bool(bool(shell['ps']['ok']))}**",
            f"- `git_status`: **{_md_bool(bool(shell['git_status']['ok']))}**",
            f"- `git_diff_shortstat`: **{_md_bool(bool(shell['git_diff_shortstat']['ok']))}**",
            "",
            f"JSON: `{json_path}`",
        ]
    )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")

    return 0 if report["summary"]["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
