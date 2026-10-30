"""Operator-triggered release of local LLM workers, without deleting model files."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urlsplit

import httpx
import psutil
from fastapi import HTTPException

from venom_core.services.model_resources import (
    prepare_registered_models,
    release_barrier,
    release_registered_models,
    wait_for_model_work,
)
from venom_core.services.runtime_admission import (
    admitted_operation,
    get_runtime_admission,
)
from venom_core.services.runtime_switch_gate import (
    begin_runtime_switch,
    finish_runtime_switch,
    wait_for_runtime_requests_to_drain,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_OLLAMA_UNLOAD_TIMEOUT = 5.0

_LLM_RECOVERY_KINDS = frozenset(
    {
        "maf_generation",
        "maf_stream",
        "maf_validation",
        "simple_chat",
        "runtime_switch",
        "runtime_command",
    }
)

_LOCAL_RUNTIMES = frozenset({"ollama", "multi_runtime", "vllm", "onnx"})


async def _listening(endpoint: str) -> bool:
    parsed = urlsplit(endpoint)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("runtime_release_local_only")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(parsed.hostname, port), 2
        )
    except ConnectionRefusedError:
        return False
    writer.close()
    await writer.wait_closed()
    return True


async def _unload_ollama(endpoint: str) -> list[str]:
    base = endpoint.rstrip("/").removesuffix("/v1")
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(base + "/api/ps")
        response.raise_for_status()
        models = response.json()["models"]
        names = [item["name"] for item in models]
        for name in names:
            response = await client.post(
                base + "/api/generate",
                json={"model": name, "prompt": "", "stream": False, "keep_alive": 0},
            )
            response.raise_for_status()
        deadline = asyncio.get_running_loop().time() + _OLLAMA_UNLOAD_TIMEOUT
        while True:
            response = await client.get(base + "/api/ps")
            response.raise_for_status()
            if not response.json()["models"]:
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise ValueError("runtime_release_models_remaining")
            await asyncio.sleep(0.1)
    return names


async def _stop_worker(controller: Any, server: dict[str, Any]) -> None:
    if not server.get("supports", {}).get("stop"):
        raise ValueError("runtime_release_stop_unsupported")
    result = await controller.stop_for_cleanup(server["name"])
    if not result.ok:
        raise ValueError("runtime_release_stop_failed")
    for _ in range(30):
        if not await _listening(server["endpoint"]):
            return
        await asyncio.sleep(0.1)
    raise ValueError("runtime_release_worker_still_running")


def _release_error_code(error: Exception) -> str:
    # Keep URLs, credentials and provider responses out of API error codes.
    known_codes = {
        "runtime_release_local_only",
        "runtime_release_models_remaining",
        "runtime_release_stop_unsupported",
        "runtime_release_stop_failed",
        "runtime_release_worker_still_running",
    }
    if isinstance(error, ValueError) and str(error) in known_codes:
        return str(error)
    return "runtime_release_" + type(error).__name__


def _recover_uncertainty(admission, verified: bool, include_registered: bool) -> bool:
    if not verified:
        return False
    if not admission.enabled:
        return True
    if include_registered:
        return admission.recover(confirm_quiescent=lambda: True)
    return admission.recover(
        confirm_quiescent=lambda: True, allowed_operation_kinds=_LLM_RECOVERY_KINDS
    )


@admitted_operation("cleanup", mutation=True, cleanup=True)
async def _release_all_models(
    controller: Any,
    failures: list[dict[str, Any]],
    runtime_ids: set[str] | None = None,
    *,
    include_registered: bool = True,
) -> dict[str, Any]:
    """Release only under a host barrier; retain evidence on every partial failure."""
    results = []
    selected = _LOCAL_RUNTIMES if runtime_ids is None else runtime_ids
    servers = [s for s in controller.list_servers() if s["name"] in selected]
    for server in servers:
        result: dict[str, Any] = {
            "runtime": server["name"],
            "models": [],
            "verified": False,
        }
        try:
            if not await _listening(server["endpoint"]):
                result["state"] = "stopped"
            elif server["name"] == "ollama":
                result["models"] = await _unload_ollama(server["endpoint"])
                result["state"] = "idle"
            else:
                await _stop_worker(controller, server)
                result["state"] = "stopped"
            result["verified"] = True
        except Exception as exc:
            logger.opt(exception=True).warning(
                "Runtime release failed runtime={}", server["name"]
            )
            result["state"] = "failed"
            result["error"] = _release_error_code(exc)
        results.append(result)
    local_results = (
        await asyncio.to_thread(release_registered_models) if include_registered else []
    )
    results.extend(
        {
            **row,
            "runtime": row["category"],
            "state": "unloaded" if row["verified"] else "failed",
        }
        for row in local_results + failures
    )
    verified = all(row["verified"] for row in results) and (
        include_registered or bool(results)
    )
    admission = get_runtime_admission()
    if not _recover_uncertainty(admission, verified, include_registered):
        raise HTTPException(
            status_code=502,
            detail={"code": "runtime_release_failed", "runtimes": results},
        )
    return {"status": "success", "released": True, "runtimes": results}


def memory_snapshot() -> dict[str, Any]:
    """Observed process RAM and device VRAM, not a promise of zero GPU use."""
    result: dict[str, Any] = {
        "rss_mib": round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1),
        "gpu": [],
    }
    import subprocess

    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout
        result["gpu"] = [
            {
                "index": int(parts[0]),
                "used_mib": int(parts[1]),
                "total_mib": int(parts[2]),
            }
            for line in output.splitlines()
            if len(parts := line.split(",")) == 3
        ]
    except (OSError, ValueError, subprocess.SubprocessError):
        result["gpu_available"] = False
    return result


async def _settle_cleanup(
    controller, failures, runtime_ids, *, include_registered=True
):
    """Caller cancellation cannot reopen admission while native unload is running."""
    task = asyncio.create_task(
        _release_all_models(
            controller, failures, runtime_ids, include_registered=include_registered
        )
    )
    interrupted = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            interrupted = True
    if interrupted:
        raise asyncio.CancelledError
    return result


async def release_all_runtime_models(
    controller: Any,
    *,
    runtime_ids: set[str] | None = None,
    include_registered: bool = True,
) -> dict[str, Any]:
    """Pause consumers and drain work before verifying global RAM/VRAM release."""
    with release_barrier():
        gate = begin_runtime_switch(
            source="models-release",
            from_runtime="local",
            to_runtime="idle",
            reason="operator_release",
        )
        try:
            before = await asyncio.to_thread(memory_snapshot)
            if include_registered:
                await prepare_registered_models()
            if not await wait_for_runtime_requests_to_drain():
                raise HTTPException(
                    status_code=409, detail={"code": "runtime_release_work_not_drained"}
                )
            if include_registered:
                await asyncio.to_thread(wait_for_model_work)
            # Already admitted asynchronous work may have queued children while
            # the first preparation was stopping producers. Reconcile after drain.
            failures = await prepare_registered_models() if include_registered else []
            if include_registered:
                await asyncio.to_thread(wait_for_model_work)
            result = await _settle_cleanup(
                controller, failures, runtime_ids, include_registered=include_registered
            )
            result["memory_before"] = before
            result["memory_after"] = await asyncio.to_thread(memory_snapshot)
            return result
        finally:
            finish_runtime_switch(switch_id=gate.switch_id)
