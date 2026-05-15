"""Centralny orkiestrator przełączania runtime LLM.

Faza 2 PR 220A: wydziela logikę lifecycle switch z routera do serwisu.
Sekwencja: stop → release_wait → cache_flush → start → health_check.
Config/endpoint zapisywane są przez wywołującego TYLKO po pomyślnym return.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from venom_core.services.onnx_runtime_cleanup import release_onnx_runtime_best_effort
from venom_core.utils.llm_runtime import LifecycleStep, LifecycleSwitchState
from venom_core.utils.logger import get_logger
from venom_core.utils.runtime_names import is_multi_runtime

logger = get_logger(__name__)

_HEALTH_POLL_INTERVAL = 0.5
_HEALTH_MAX_ATTEMPTS = 60
_CLEANUP_TIMEOUT = 5.0


async def _release_ollama_model(endpoint: str, model_name: str) -> bool:
    """Ask Ollama to evict the model from VRAM before stopping the daemon.

    Uses keep_alive=0 so Ollama releases GPU/RAM immediately. Best-effort.
    """
    if not model_name or not endpoint:
        return False
    base = endpoint.rstrip("/").removesuffix("/v1")
    unload_url = f"{base}/api/generate"
    try:
        async with httpx.AsyncClient(timeout=_CLEANUP_TIMEOUT) as client:
            await client.post(
                unload_url,
                json={"model": model_name, "keep_alive": 0},
            )
        logger.info("Ollama model {} evicted from VRAM (keep_alive=0)", model_name)
        return True
    except Exception as exc:
        logger.warning("Nie udało się zwolnić modelu Ollama z VRAM: {}", exc)
        return False


async def release_runtime_resources(
    server_name: str,
    *,
    server: dict[str, Any],
    active_model: str = "",
) -> bool:
    """Best-effort pre-stop cleanup for a specific runtime stack.

    Called before stopping the server process to release GPU/RAM early.
    Never raises — failures are logged and ignored.

    Returns True if any cleanup hook ran successfully.
    """
    caps = server.get("capabilities", {})
    released = False

    if server_name == "ollama" and caps.get("supports_model_unload"):
        endpoint = str(server.get("endpoint") or "http://localhost:11434")
        if active_model:
            released = await _release_ollama_model(endpoint, active_model)

    if caps.get("is_in_process") and caps.get("supports_cache_flush"):
        try:
            released = release_onnx_runtime_best_effort(wait=False) or released
        except Exception as exc:
            logger.warning("Nie udało się zwolnić runtime ONNX: {}", exc)

    return released


def _extract_health_status(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    raw = payload.get("status")
    if raw is None:
        return None
    return str(raw).strip().lower() or None


def _is_health_response_ready(*, server_name: str, response: httpx.Response) -> bool:
    if not (200 <= response.status_code < 300):
        return False
    if not is_multi_runtime(server_name):
        return True
    status = _extract_health_status(response)
    return status in {"ok", "ready", "running"}


def _health_probe_attempts(server_name: str) -> int:
    """Return number of health probe attempts for a runtime.

    multi_runtime can need more than 30s while loading Gemma weights.
    """
    if is_multi_runtime(server_name):
        return 240  # 120s at 0.5s interval
    return _HEALTH_MAX_ATTEMPTS


async def probe_health_ready(server_name: str, health_url: str) -> bool:
    """Return True when server reports healthy within runtime-specific timeout."""
    logger.info("Oczekiwanie na gotowość serwera LLM: {}", server_name)
    max_attempts = _health_probe_attempts(server_name)
    timeout_seconds = max_attempts * _HEALTH_POLL_INTERVAL
    async with httpx.AsyncClient(timeout=2.0) as client:
        for attempt in range(max_attempts):
            try:
                resp = await client.get(health_url)
                if _is_health_response_ready(server_name=server_name, response=resp):
                    logger.info(
                        "Serwer LLM {} gotowy po {:.1f}s",
                        server_name,
                        attempt * _HEALTH_POLL_INTERVAL,
                    )
                    return True
            except Exception:
                pass
            await asyncio.sleep(_HEALTH_POLL_INTERVAL)
    logger.error(
        "Serwer LLM {} nie odpowiedział prawidłowo po {:.0f}s",
        server_name,
        timeout_seconds,
    )
    return False


async def probe_until_shutdown(server_name: str, health_url: str) -> bool:
    """Return True when server stops responding within 30 seconds."""
    logger.info("Oczekiwanie na zwolnienie serwera LLM: {}", server_name)
    async with httpx.AsyncClient(timeout=2.0) as client:
        for attempt in range(_HEALTH_MAX_ATTEMPTS):
            try:
                resp = await client.get(health_url)
                if not _is_health_response_ready(
                    server_name=server_name, response=resp
                ):
                    logger.info(
                        "Serwer LLM {} zwolnił zasoby po {:.1f}s",
                        server_name,
                        attempt * _HEALTH_POLL_INTERVAL,
                    )
                    return True
            except Exception:
                logger.info(
                    "Serwer LLM {} jest niedostępny po {:.1f}s",
                    server_name,
                    attempt * _HEALTH_POLL_INTERVAL,
                )
                return True
            await asyncio.sleep(_HEALTH_POLL_INTERVAL)
    logger.error("Serwer LLM {} nadal odpowiada po 30s", server_name)
    return False


class RuntimeSwitchOrchestrator:
    """Orchestrates the full lifecycle switch between LLM runtimes.

    Sequence: stop_others → await_release → flush_caches → start_target → verify_health.

    Tracks progress via LifecycleSwitchState.
    Raises HTTPException on critical failures.
    Config/endpoint MUST be saved by the caller only after this returns successfully.
    """

    def __init__(self, llm_controller: Any) -> None:
        self._controller = llm_controller

    async def execute_lifecycle_switch(
        self,
        *,
        servers: list[dict[str, Any]],
        target_server_name: str,
        from_server_name: str = "unknown",
        active_model: str = "",
        onnx_flush_fn: Optional[Any] = None,
    ) -> tuple[
        LifecycleSwitchState,
        dict[str, Any],
        dict[str, Any],
        Optional[dict[str, Any]],
        dict[str, Any],
    ]:
        """Execute the lifecycle switch.

        Returns (state, stop_results, shutdown_results, start_result, target_server_dict).
        Raises HTTPException if a critical lifecycle step fails.
        Config/endpoint MUST be saved by the caller only after this returns successfully.

        active_model: current model name, used for pre-stop unload hooks (e.g. Ollama).
        onnx_flush_fn: optional callable invoked to release ONNX in-process caches when
        switching away from ONNX. Injected by the caller so it can be patched in tests.
        """
        state = LifecycleSwitchState(
            from_server=from_server_name,
            to_server=target_server_name,
        )

        stop_results = await self._stop_other_servers(
            servers, target_server_name, state, active_model=active_model
        )
        shutdown_results = await self._await_release(servers, target_server_name, state)
        self._flush_caches_if_leaving_onnx(target_server_name, state, onnx_flush_fn)

        target = self._find_target(target_server_name, servers)
        start_result = await self._start_and_verify_health(
            target_server_name, target, state
        )

        return state, stop_results, shutdown_results, start_result, target

    async def _stop_other_servers(
        self,
        servers: list[dict[str, Any]],
        target_name: str,
        state: LifecycleSwitchState,
        *,
        active_model: str = "",
    ) -> dict[str, Any]:
        stop_results: dict[str, Any] = {}
        for server in servers:
            name = str(server.get("name") or "").strip()
            if not name or name == target_name:
                continue
            if not server.get("supports", {}).get("stop"):
                continue

            # Pre-stop cleanup: release model from VRAM/RAM before sending stop command.
            await release_runtime_resources(
                name, server=server, active_model=active_model
            )

            try:
                result = await self._controller.run_action(name, "stop")
                stop_results[name] = {"ok": result.ok, "exit_code": result.exit_code}
            except Exception as exc:
                stop_results[name] = {"ok": False, "error": str(exc)}

        failures = [n for n, r in stop_results.items() if not r.get("ok")]
        if failures:
            logger.warning(
                "Nie udało się zatrzymać poprzednich serwerów LLM: {}",
                ", ".join(sorted(failures)),
            )

        state.mark_done(LifecycleStep.PROCESS_STOPPED)
        return stop_results

    async def _await_release(
        self,
        servers: list[dict[str, Any]],
        target_name: str,
        state: LifecycleSwitchState,
    ) -> dict[str, Any]:
        """Await shutdown probes + per-capabilities release_wait.

        Returns shutdown_results dict mapping server_name → {"ok": bool, "health_url": str}.
        """
        shutdown_results: dict[str, Any] = {}
        for server in servers:
            name = str(server.get("name") or "").strip()
            if not name or name == target_name:
                continue
            if not server.get("supports", {}).get("stop"):
                continue

            health_url = str(server.get("health_url") or "").strip()
            if health_url:
                shutdown_ok = await probe_until_shutdown(name, health_url)
                shutdown_results[name] = {"ok": shutdown_ok, "health_url": health_url}
                if not shutdown_ok:
                    state.mark_failed(
                        LifecycleStep.RELEASE_DONE,
                        f"{name} nie zwolnił zasobów po zatrzymaniu",
                    )
                    raise HTTPException(
                        status_code=503,
                        detail=f"Serwer LLM '{name}' nie zwolnił zasobów po zatrzymaniu.",
                    )

            caps_dict = server.get("capabilities", {})
            release_wait = int(caps_dict.get("release_wait_seconds", 0))
            if release_wait > 0:
                logger.info(
                    "Oczekiwanie {}s na zwolnienie zasobów przez {}",
                    release_wait,
                    name,
                )
                await asyncio.sleep(release_wait)

        state.mark_done(LifecycleStep.RELEASE_DONE)
        return shutdown_results

    def _flush_caches_if_leaving_onnx(
        self,
        target_name: str,
        state: LifecycleSwitchState,
        onnx_flush_fn: Optional[Any] = None,
    ) -> None:
        if target_name == "onnx":
            return
        if onnx_flush_fn is not None:
            try:
                onnx_flush_fn()
            except Exception:
                logger.warning("Nie udało się zwolnić cache ONNX runtime.")
        else:
            try:
                release_onnx_runtime_best_effort(wait=False)
            except Exception:
                logger.warning("Nie udało się zwolnić runtime ONNX.")
        state.mark_done(LifecycleStep.CACHE_INVALIDATED)

    def _find_target(
        self,
        target_name: str,
        servers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        for server in servers:
            if server.get("name") == target_name:
                return server
        raise HTTPException(
            status_code=404,
            detail=f"Serwer LLM '{target_name}' nie znaleziony w konfiguracji.",
        )

    async def _start_and_verify_health(
        self,
        target_name: str,
        target: dict[str, Any],
        state: LifecycleSwitchState,
    ) -> Optional[dict[str, Any]]:
        start_result: Optional[dict[str, Any]] = None

        if target.get("supports", {}).get("start"):
            try:
                result = await self._controller.run_action(target_name, "start")
                start_result = {"ok": result.ok, "exit_code": result.exit_code}
            except Exception as exc:
                start_result = {"ok": False, "error": str(exc)}

        state.mark_done(LifecycleStep.START_DONE)

        caps_dict = target.get("capabilities", {})
        if caps_dict.get("supports_health_wait"):
            health_url = str(target.get("health_url") or "").strip()
            if health_url:
                is_ready = await probe_health_ready(target_name, health_url)
                if not is_ready:
                    state.mark_failed(
                        LifecycleStep.HEALTH_READY,
                        "Health check timeout - serwer nie odpowiada",
                    )
                    raise HTTPException(
                        status_code=503,
                        detail="Health check timeout — serwer LLM nie osiągnął gotowości.",
                    )

        state.mark_done(LifecycleStep.HEALTH_READY)
        return start_result
