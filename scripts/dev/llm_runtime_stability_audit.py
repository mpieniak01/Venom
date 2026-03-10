#!/usr/bin/env python3
"""Manual LLM runtime lifecycle stability audit.

Scope:
- Runtime switching (ollama/vllm/onnx) via /api/v1/system/llm-servers/active
- Model activation and switching (when runtime exposes >=2 models)
- Runtime unload via /api/v1/models/unload-all
- Optional stack lifecycle cycle: make start|start2 -> audit -> make stop
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class RuntimeAuditResult:
    runtime: str
    ok: bool
    selected_primary_model: str | None
    selected_secondary_model: str | None
    steps: list[str]
    errors: list[str]


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_sec: float = 20.0,
) -> tuple[int, dict[str, Any] | list[Any] | None]:
    data_bytes: bytes | None = None
    headers: dict[str, str] = {}
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url=url, method=method, data=data_bytes, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return int(resp.status), None
            try:
                return int(resp.status), json.loads(raw)
            except json.JSONDecodeError:
                return int(resp.status), {"raw": raw}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if raw.strip():
            try:
                return int(exc.code), json.loads(raw)
            except json.JSONDecodeError:
                return int(exc.code), {"raw": raw}
        return int(exc.code), None
    except (error.URLError, TimeoutError) as exc:
        return 0, {"error": str(exc)}


def _wait_backend_ready(base_url: str, timeout_sec: int = 120) -> bool:
    status_url = f"{base_url.rstrip('/')}/api/v1/system/status"
    for _ in range(max(1, timeout_sec)):
        code, _payload = _http_json(status_url, timeout_sec=2.0)
        if code == 200:
            return True
        time.sleep(1)
    return False


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _env_value(name: str, env_file_values: dict[str, str], default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    if name in env_file_values:
        return env_file_values[name]
    return default


def _runtime_models_from_options(
    options_payload: dict[str, Any], runtime_id: str
) -> list[str]:
    runtimes = options_payload.get("runtimes")
    if not isinstance(runtimes, list):
        return []
    target = next(
        (
            item
            for item in runtimes
            if str(item.get("runtime_id") or "").strip().lower() == runtime_id
        ),
        None,
    )
    if not isinstance(target, dict):
        return []
    models_raw = target.get("models")
    if not isinstance(models_raw, list):
        return []
    models: list[str] = []
    for item in models_raw:
        if not isinstance(item, dict):
            continue
        model_name = str(item.get("name") or "").strip()
        if model_name:
            models.append(model_name)
    dedup: list[str] = []
    seen: set[str] = set()
    for model in models:
        lowered = model.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        dedup.append(model)
    return dedup


def _pick_model(
    *,
    available_models: list[str],
    preferred_patterns: list[str],
    exclude: str | None = None,
) -> str | None:
    if not available_models:
        return None
    excluded = str(exclude or "").strip().lower()
    filtered = [
        model
        for model in available_models
        if not excluded or model.strip().lower() != excluded
    ]
    if not filtered:
        return None
    for pattern in preferred_patterns:
        token = pattern.strip().lower()
        if not token:
            continue
        for model in filtered:
            lowered = model.lower()
            if lowered == token or token in lowered:
                return model
    return filtered[0]


def _run_make(root: Path, target: str) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["make", "--no-print-directory", target],
            cwd=str(root),
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError as exc:
        return False, f"make failed to start: {exc}"
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        tail = "\n".join(output.splitlines()[-40:])
        return False, f"make {target} failed (exit={completed.returncode}):\n{tail}"
    return True, output


def _activate_server(
    base_url: str,
    *,
    runtime: str,
    model: str | None,
    timeout_sec: float,
) -> tuple[bool, str]:
    payload: dict[str, Any] = {"server_name": runtime}
    if model:
        payload["model"] = model
    code, body = _http_json(
        f"{base_url.rstrip('/')}/api/v1/system/llm-servers/active",
        method="POST",
        payload=payload,
        timeout_sec=timeout_sec,
    )
    if code != 200:
        return False, f"activate failed status={code} body={body}"
    return True, "ok"


def _verify_active_server(
    base_url: str,
    *,
    runtime: str,
    model: str | None,
    strict_model: bool = True,
) -> tuple[bool, str]:
    code, body = _http_json(
        f"{base_url.rstrip('/')}/api/v1/system/llm-servers/active",
        timeout_sec=20.0,
    )
    if code != 200 or not isinstance(body, dict):
        return False, f"cannot read active server status={code} body={body}"
    active_server = str(body.get("active_server") or "").strip().lower()
    if active_server != runtime:
        return False, f"active_server={active_server} expected={runtime}"
    if model and strict_model:
        active_model = str(body.get("active_model") or "").strip().lower()
        if active_model and model.strip().lower() != active_model:
            # Alias/canonical mappings may differ. Accept substring relation.
            if (
                model.strip().lower() not in active_model
                and active_model not in model.strip().lower()
            ):
                return False, f"active_model={active_model} expected~={model}"
    return True, "ok"


def _wait_active_server(
    base_url: str, *, runtime: str, timeout_sec: int = 180
) -> tuple[bool, str]:
    deadline = time.time() + max(1, timeout_sec)
    while time.time() < deadline:
        ok, message = _verify_active_server(
            base_url, runtime=runtime, model=None, strict_model=False
        )
        if ok:
            return True, "ok"
        time.sleep(2)
    return False, f"active server did not switch to {runtime} in {timeout_sec}s"


def _unload_all(base_url: str) -> tuple[bool, str]:
    code, body = _http_json(
        f"{base_url.rstrip('/')}/api/v1/models/unload-all",
        method="POST",
        payload={},
        timeout_sec=60.0,
    )
    if code != 200:
        return False, f"unload-all failed status={code} body={body}"
    return True, "ok"


def _audit_runtime(
    *,
    base_url: str,
    runtime: str,
    options_payload: dict[str, Any],
    preferred_patterns: list[str],
) -> RuntimeAuditResult:
    steps: list[str] = []
    errors: list[str] = []
    available_models = _runtime_models_from_options(options_payload, runtime)

    primary = _pick_model(
        available_models=available_models, preferred_patterns=preferred_patterns
    )
    if runtime != "onnx" and primary is None:
        return RuntimeAuditResult(
            runtime=runtime,
            ok=False,
            selected_primary_model=None,
            selected_secondary_model=None,
            steps=steps,
            errors=["no_models_available_for_runtime"],
        )

    activation_timeout = 180.0 if runtime == "vllm" else 90.0
    ok, message = _activate_server(
        base_url,
        runtime=runtime,
        model=primary,
        timeout_sec=activation_timeout,
    )
    steps.append(f"activate:{runtime}:{primary or 'default'}")
    if not ok:
        wait_ok, wait_message = _wait_active_server(
            base_url, runtime=runtime, timeout_sec=int(activation_timeout)
        )
        if not wait_ok:
            errors.append(message)
            errors.append(wait_message)
            return RuntimeAuditResult(
                runtime=runtime,
                ok=False,
                selected_primary_model=primary,
                selected_secondary_model=None,
                steps=steps,
                errors=errors,
            )

    ok, message = _verify_active_server(
        base_url,
        runtime=runtime,
        model=primary,
        strict_model=(runtime != "onnx"),
    )
    steps.append("verify_active")
    if not ok:
        errors.append(message)

    ok, message = _unload_all(base_url)
    steps.append("unload_all")
    if not ok:
        errors.append(message)

    secondary = _pick_model(
        available_models=available_models,
        preferred_patterns=preferred_patterns,
        exclude=primary,
    )
    if secondary and runtime != "onnx":
        ok, message = _activate_server(
            base_url,
            runtime=runtime,
            model=secondary,
            timeout_sec=activation_timeout,
        )
        steps.append(f"switch_model:{secondary}")
        if not ok:
            wait_ok, wait_message = _wait_active_server(
                base_url, runtime=runtime, timeout_sec=int(activation_timeout)
            )
            if not wait_ok:
                errors.append(message)
                errors.append(wait_message)
        else:
            ok, message = _verify_active_server(
                base_url, runtime=runtime, model=secondary
            )
            if not ok:
                errors.append(message)
            ok, message = _unload_all(base_url)
            steps.append("unload_all_after_switch")
            if not ok:
                errors.append(message)
    elif secondary and runtime == "onnx":
        steps.append("switch_model:skipped_for_onnx_in_process_runtime")

    return RuntimeAuditResult(
        runtime=runtime,
        ok=not errors,
        selected_primary_model=primary,
        selected_secondary_model=secondary,
        steps=steps,
        errors=errors,
    )


def _fetch_runtime_options(base_url: str) -> tuple[bool, dict[str, Any] | None, str]:
    code, body = _http_json(
        f"{base_url.rstrip('/')}/api/v1/system/llm-runtime/options",
        timeout_sec=40.0,
    )
    if code != 200 or not isinstance(body, dict):
        return False, None, f"runtime/options failed status={code} body={body}"
    return True, body, "ok"


def _print_text_report(report: dict[str, Any]) -> None:
    print("LLM runtime stability audit")
    print(f"- base_url: {report['base_url']}")
    print(f"- stack_cycle: {report['stack_cycle']}")
    print(f"- preferred_models: {', '.join(report['preferred_models'])}")
    print(f"- runtime_count: {len(report['runtime_results'])}")
    for item in report["runtime_results"]:
        print(
            f"  * runtime={item['runtime']} ok={item['ok']} "
            f"primary={item['selected_primary_model']} secondary={item['selected_secondary_model']}"
        )
        for step in item["steps"]:
            print(f"    - step: {step}")
        for err in item["errors"]:
            print(f"    - error: {err}")
    if report["errors"]:
        print("- global_errors:")
        for err in report["errors"]:
            print(f"  * {err}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual lifecycle stability audit for local LLM runtimes."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root (for optional stack cycles).",
    )
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument(
        "--base-url",
        default="",
        help="Backend API base URL (default resolved from HOST_DISPLAY/PORT).",
    )
    parser.add_argument(
        "--runtimes",
        default="ollama,vllm,onnx",
        help="Comma-separated runtime ids to audit.",
    )
    parser.add_argument(
        "--preferred-models",
        default="gemma3,gemma-3,gemma2,gemma",
        help="Comma-separated model preference patterns.",
    )
    parser.add_argument(
        "--stack-cycle",
        choices=("none", "start", "start2", "both"),
        default="none",
        help="Optional stack lifecycle cycle before audit.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on-errors", action="store_true")
    return parser.parse_args()


def _run_single_audit(
    *,
    base_url: str,
    runtimes: list[str],
    preferred_models: list[str],
) -> tuple[list[RuntimeAuditResult], list[str]]:
    errors: list[str] = []
    ok, payload, message = _fetch_runtime_options(base_url)
    if not ok or payload is None:
        return [], [message]

    results: list[RuntimeAuditResult] = []
    for runtime in runtimes:
        result = _audit_runtime(
            base_url=base_url,
            runtime=runtime,
            options_payload=payload,
            preferred_patterns=preferred_models,
        )
        results.append(result)
    return results, errors


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (root / env_file).resolve()
    env_values = _read_env_file(env_file)

    host_display = _env_value("HOST_DISPLAY", env_values, "127.0.0.1")
    port = _env_value("PORT", env_values, "8000")
    base_url = args.base_url.strip() or f"http://{host_display}:{port}"

    runtimes = [
        item.strip().lower() for item in args.runtimes.split(",") if item.strip()
    ]
    preferred_models = [
        item.strip() for item in args.preferred_models.split(",") if item.strip()
    ]
    global_errors: list[str] = []
    all_results: list[RuntimeAuditResult] = []
    cycle_targets: list[str]
    if args.stack_cycle == "both":
        cycle_targets = ["start", "start2"]
    elif args.stack_cycle == "none":
        cycle_targets = []
    else:
        cycle_targets = [args.stack_cycle]

    if cycle_targets:
        for target in cycle_targets:
            ok, message = _run_make(root, target)
            if not ok:
                global_errors.append(message)
                continue
            if not _wait_backend_ready(base_url):
                global_errors.append(
                    f"backend not ready after make {target} at {base_url}"
                )
                _run_make(root, "stop")
                continue
            results, errors = _run_single_audit(
                base_url=base_url,
                runtimes=runtimes,
                preferred_models=preferred_models,
            )
            all_results.extend(results)
            global_errors.extend(errors)
            ok, message = _run_make(root, "stop")
            if not ok:
                global_errors.append(message)
    else:
        if not _wait_backend_ready(base_url, timeout_sec=30):
            global_errors.append(
                "backend is not ready; start stack first (make start or make start2)"
            )
        else:
            results, errors = _run_single_audit(
                base_url=base_url,
                runtimes=runtimes,
                preferred_models=preferred_models,
            )
            all_results.extend(results)
            global_errors.extend(errors)

    report = {
        "base_url": base_url,
        "env_file": str(env_file),
        "stack_cycle": args.stack_cycle,
        "preferred_models": preferred_models,
        "runtime_results": [asdict(item) for item in all_results],
        "errors": global_errors,
    }

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        _print_text_report(report)

    has_runtime_errors = any(not item.ok for item in all_results)
    has_errors = bool(global_errors) or has_runtime_errors
    if args.fail_on_errors and has_errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
