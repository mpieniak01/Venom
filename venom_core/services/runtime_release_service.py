"""Operator-triggered release of local LLM workers, without deleting model files."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from venom_core.services.runtime_admission import (
    admitted_operation,
    get_runtime_admission,
)
from venom_core.services.runtime_switch_gate import (
    begin_runtime_switch,
    finish_runtime_switch,
    wait_for_runtime_requests_to_drain,
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
        response = await client.get(base + "/api/ps")
        response.raise_for_status()
        if response.json()["models"]:
            raise ValueError("runtime_release_models_remaining")
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


@admitted_operation("cleanup", mutation=True, cleanup=True)
async def release_all_runtime_models(controller: Any) -> dict[str, Any]:
    """Keep admission closed until every configured local worker is verified idle.

    Ollama stays available with an empty /api/ps so other screens can load their
    own model. Fixed-model workers stop; the existing activation flow restarts them.
    """
    gate = begin_runtime_switch(
        source="models-release",
        from_runtime="local",
        to_runtime="idle",
        reason="operator_release",
    )
    results = []
    try:
        await wait_for_runtime_requests_to_drain()
        servers = [s for s in controller.list_servers() if s["name"] in _LOCAL_RUNTIMES]
        if not servers:
            raise ValueError("runtime_release_no_local_workers")
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
            except Exception:
                result["state"] = "failed"
            results.append(result)
        verified = bool(results) and all(row["verified"] for row in results)
        if not verified or not get_runtime_admission().recover(
            confirm_quiescent=lambda: verified
        ):
            raise HTTPException(
                status_code=502,
                detail={"code": "runtime_release_failed", "runtimes": results},
            )
        return {"status": "success", "released": True, "runtimes": results}
    finally:
        finish_runtime_switch(switch_id=gate.switch_id)
