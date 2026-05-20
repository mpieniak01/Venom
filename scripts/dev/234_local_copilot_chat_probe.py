#!/usr/bin/env python3
"""PR234 probe for local Copilot Chat truthfulness and tool-use behavior.

The probe compares a model answer against actual repository facts and records
whether the response looks like:
- exact / truthful
- partial
- hallucinated
- refusal
- empty / broken

It supports two channels:
- direct: plain Ollama generation
- agent: Codex exec with the local Ollama provider

The goal is to diagnose whether the local chat surface is returning real
workspace facts or only producing a textual imitation of them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS = [
    "qwen2.5-coder:7b",
]
DEFAULT_CHANNELS = ["agent", "direct"]
DEFAULT_PROMPT_VARIANTS = ["branch", "status", "diff"]


@dataclass(slots=True)
class CmdResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def _run_cmd(cmd: list[str], *, timeout: float = 120.0) -> CmdResult:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
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
    timeout: float = 30.0,
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


def _repo_facts() -> dict[str, str]:
    branch = _run_cmd(["git", "branch", "--show-current"]).stdout.strip()
    status = _run_cmd(["git", "status", "--short", "--branch"]).stdout.strip()
    diff_shortstat = _run_cmd(["git", "diff", "--shortstat"]).stdout.strip()
    head = _run_cmd(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    return {
        "branch": branch,
        "status_short_branch": status,
        "diff_shortstat": diff_shortstat,
        "head": head,
    }


def _task_specs(facts: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "name": "branch",
            "command": "git branch --show-current",
            "expected": facts["branch"],
        },
        {
            "name": "status",
            "command": "git status --short --branch",
            "expected": facts["status_short_branch"],
        },
        {
            "name": "diff",
            "command": "git diff --shortstat",
            "expected": facts["diff_shortstat"],
        },
    ]


def _normalize(text: str) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = [line for line in lines if line.strip()]
    return "\n".join(cleaned).strip()


def _refusal_marker(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in [
            "nie mam możliwości",
            "nie mogę bezpośrednio",
            "nie mogę używać narzędzi",
            "nie mogę użyć narzędzi",
            "i can't execute",
            "cannot execute",
            "no direct access",
            "no możliwości",
            "brak dostępu",
            "proszę o podanie dokładnych instrukcji",
        ]
    )


def _tool_unavailable_marker(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in [
            "does not support tools",
            "invalid_request_error",
            "tool support is not available",
        ]
    )


def _hallucinated_clean(text: str, facts: dict[str, str]) -> bool:
    lowered = text.lower()
    if not facts["status_short_branch"].strip():
        return False
    dirty_markers = [
        "working tree clean",
        "tree clean",
        "repo jest czyste",
        "środowisko jest czyste",
        "wszystko zostało pomyślnie zcommitowane",
        "nothing to commit",
    ]
    return any(marker in lowered for marker in dirty_markers)


def _classify(
    text: str,
    facts: dict[str, str],
    expected: str,
    *,
    channel: str,
    stderr: str = "",
    aux_text: str = "",
) -> dict[str, Any]:
    normalized = _normalize(text)
    stderr_norm = _normalize(stderr)
    aux_norm = _normalize(aux_text)
    expected_norm = _normalize(expected)
    exact = normalized == expected_norm
    refusal = _refusal_marker(normalized)
    tool_unavailable = (
        _tool_unavailable_marker(normalized)
        or _tool_unavailable_marker(stderr_norm)
        or _tool_unavailable_marker(aux_norm)
    )
    partial = bool(normalized) and not exact and expected_norm in normalized
    if exact:
        label = "exact"
    elif tool_unavailable:
        label = "tool_unavailable"
    elif refusal:
        label = "refusal"
    elif _hallucinated_clean(normalized, facts):
        label = "hallucinated"
    elif partial:
        label = "partial"
    elif normalized:
        label = "hallucinated"
    else:
        label = "empty"

    return {
        "label": label,
        "exact": exact,
        "refusal": refusal,
        "tool_unavailable": tool_unavailable,
        "hallucinated_clean": _hallucinated_clean(normalized, facts),
        "used_tools_likely": exact and channel != "direct",
        "response_excerpt": normalized[:400],
    }


def _prompt(repo_root: str, task: dict[str, str]) -> str:
    return (
        f"Sprawdz w workspace {repo_root} wynik komendy `{task['command']}`.\n"
        "Uzyj narzedzi, nie zgaduj.\n"
        "Zwróć tylko dokładny wynik komendy bez interpretacji, bez markdown i bez dodatkowego tekstu.\n"
        "Jesli nie mozesz uzyc narzedzi, napisz tylko jedno zdanie, ze nie mozesz ich uzyc."
    )


def _direct_generate(
    base_url: str, model: str, prompt: str, timeout: float = 90.0
) -> CmdResult:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return CmdResult(
            ok=True,
            exit_code=0,
            stdout=str(body.get("response") or "").strip(),
            stderr="",
        )
    except Exception as exc:  # noqa: BLE001
        return CmdResult(ok=False, exit_code=1, stdout="", stderr=str(exc))


def _agent_exec(
    model: str, prompt: str, *, ignore_rules: bool = False, timeout: float = 120.0
) -> CmdResult:
    codex = shutil.which("codex")
    if not codex:
        return CmdResult(ok=False, exit_code=127, stdout="", stderr="codex not found")
    cmd = [
        codex,
        "exec",
        "--json",
        "--oss",
        "--local-provider",
        "ollama",
        "-m",
        model,
        "--cd",
        str(REPO_ROOT),
        "--sandbox",
        "workspace-write",
    ]
    if ignore_rules:
        cmd.append("--ignore-rules")
    cmd.append(prompt)
    return _run_cmd(cmd, timeout=timeout)


def _extract_agent_message(stdout: str) -> str:
    for line in stdout.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "item.completed":
            item = payload.get("item") or {}
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text") or ""
                if isinstance(text, str):
                    return text.strip()
    return ""


def _run_case(
    channel: str,
    model: str,
    prompt: str,
    expected: str,
    facts: dict[str, str],
    *,
    ollama_url: str,
    ignore_rules: bool,
) -> dict[str, Any]:
    if channel == "direct":
        start = datetime.now(timezone.utc)
        result = _direct_generate(ollama_url, model, prompt)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        classification = _classify(
            result.stdout, facts, expected, channel=channel, stderr=result.stderr
        )
        return {
            "channel": channel,
            "ok": result.ok,
            "exit_code": result.exit_code,
            "elapsed_sec": round(elapsed, 2),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "expected": expected,
            **classification,
        }

    start = datetime.now(timezone.utc)
    result = _agent_exec(model, prompt, ignore_rules=ignore_rules)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    agent_message = _extract_agent_message(result.stdout)
    classification = _classify(
        agent_message,
        facts,
        expected,
        channel=channel,
        stderr=result.stderr,
        aux_text=result.stdout,
    )
    return {
        "channel": channel + ("_ignore_rules" if ignore_rules else ""),
        "ok": result.ok,
        "exit_code": result.exit_code,
        "elapsed_sec": round(elapsed, 2),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "agent_message": agent_message,
        "expected": expected,
        **classification,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PR234 local Copilot Chat diagnostics probe"
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--channels", nargs="*", default=DEFAULT_CHANNELS)
    parser.add_argument("--prompt-variants", nargs="*", default=DEFAULT_PROMPT_VARIANTS)
    parser.add_argument(
        "--ignore-rules",
        action="store_true",
        help="Also run agent channel with --ignore-rules",
    )
    parser.add_argument(
        "--shell-only",
        action="store_true",
        help="Only record shell truth and skip model calls",
    )
    parser.add_argument(
        "--json-output", default="test-results/234/chat_diagnostics.json"
    )
    parser.add_argument("--md-output", default="test-results/234/chat_diagnostics.md")
    args = parser.parse_args()

    facts = _repo_facts()
    report: dict[str, Any] = {
        "scope": "pr234-local-copilot-chat-diagnostics",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "facts": facts,
        "models": args.models,
        "channels": args.channels,
        "prompt_variants": args.prompt_variants,
        "ignore_rules_requested": args.ignore_rules,
        "shell_only": args.shell_only,
        "cases": [],
    }

    for model in args.models:
        for prompt_variant in args.prompt_variants:
            task = next(
                (item for item in _task_specs(facts) if item["name"] == prompt_variant),
                None,
            )
            if task is None:
                continue
            prompt = _prompt(str(REPO_ROOT), task)
            for channel in args.channels:
                case = {
                    "model": model,
                    "channel": channel,
                    "prompt_variant": prompt_variant,
                    "command": task["command"],
                    "prompt": prompt,
                    "expected": task["expected"],
                }
                case["runs"] = []
                if args.shell_only:
                    case["runs"].append(
                        {
                            "channel": channel,
                            "ok": True,
                            "exit_code": 0,
                            "elapsed_sec": 0.0,
                            "stdout": "",
                            "stderr": "",
                            "label": "skipped",
                            "exact": False,
                            "expected": task["expected"],
                            "refusal": False,
                            "tool_unavailable": False,
                            "hallucinated_clean": False,
                            "used_tools_likely": False,
                            "response_excerpt": "shell-only baseline",
                        }
                    )
                elif channel == "direct":
                    case["runs"].append(
                        _run_case(
                            "direct",
                            model,
                            prompt,
                            task["expected"],
                            facts,
                            ollama_url=args.ollama_url,
                            ignore_rules=False,
                        )
                    )
                else:
                    case["runs"].append(
                        _run_case(
                            "agent",
                            model,
                            prompt,
                            task["expected"],
                            facts,
                            ollama_url=args.ollama_url,
                            ignore_rules=False,
                        )
                    )
                    if args.ignore_rules:
                        case["runs"].append(
                            _run_case(
                                "agent",
                                model,
                                prompt,
                                task["expected"],
                                facts,
                                ollama_url=args.ollama_url,
                                ignore_rules=True,
                            )
                        )

                summary = {
                    "exact_runs": sum(1 for run in case["runs"] if run["exact"]),
                    "refusal_runs": sum(1 for run in case["runs"] if run["refusal"]),
                    "tool_unavailable_runs": sum(
                        1 for run in case["runs"] if run.get("tool_unavailable")
                    ),
                    "hallucinated_runs": sum(
                        1 for run in case["runs"] if run["label"] == "hallucinated"
                    ),
                    "partial_runs": sum(
                        1 for run in case["runs"] if run["label"] == "partial"
                    ),
                    "skipped_runs": sum(
                        1 for run in case["runs"] if run["label"] == "skipped"
                    ),
                    "ok_runs": sum(1 for run in case["runs"] if run["ok"]),
                }
                case["summary"] = summary
                report["cases"].append(case)

    for case in report["cases"]:
        exact = case["summary"]["exact_runs"]
        refusal = case["summary"]["refusal_runs"]
        hallucinated = case["summary"]["hallucinated_runs"]
        case["score"] = exact * 10 - hallucinated * 5 - refusal * 2

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR234 Local Copilot Chat Diagnostics",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Repo branch: `{facts['branch']}`",
        f"Git status: `{facts['status_short_branch']}`",
        f"Git diff shortstat: `{facts['diff_shortstat'] or '<empty>'}`",
        "",
    ]
    for case in report["cases"]:
        md_lines.extend(
            [
                f"## {case['channel']} / {case['model']} / {case['prompt_variant']}",
                f"- command: `{case['command']}`",
                f"- expected: `{case['expected']}`",
                f"- exact_runs: `{case['summary']['exact_runs']}`",
                f"- refusal_runs: `{case['summary']['refusal_runs']}`",
                f"- tool_unavailable_runs: `{case['summary']['tool_unavailable_runs']}`",
                f"- hallucinated_runs: `{case['summary']['hallucinated_runs']}`",
                f"- partial_runs: `{case['summary']['partial_runs']}`",
                f"- skipped_runs: `{case['summary']['skipped_runs']}`",
                f"- ok_runs: `{case['summary']['ok_runs']}`",
                f"- score: `{case['score']}`",
            ]
        )
        for run in case["runs"]:
            md_lines.extend(
                [
                    f"  - label: `{run['label']}`",
                    f"  - exact: `{run['exact']}`",
                    f"  - expected: `{run['expected']}`",
                    f"  - refusal: `{run['refusal']}`",
                    f"  - tool_unavailable: `{run.get('tool_unavailable', False)}`",
                    f"  - used_tools_likely: `{run['used_tools_likely']}`",
                    f"  - response_excerpt: `{run['response_excerpt']}`",
                ]
            )
        md_lines.append("")
    md_lines.extend(
        [
            f"JSON: `{json_path}`",
            "",
            "Interpretation:",
            "- `exact` means the model returned branch/status/diff that matched the real repo facts.",
            "- `refusal` means the model declined to execute the repo check.",
            "- `tool_unavailable` means the channel or model could not support tools in this setup.",
            "- `hallucinated` means the response looked like an imitation or contradicted real repo state.",
            "- `used_tools_likely` is a diagnostic heuristic, not proof.",
        ]
    )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
