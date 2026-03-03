"""Guard zapewniający single-runtime/single-model dla startu benchmarków."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from venom_core.config import SETTINGS
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_ACTIVE_RUN_STATES = frozenset({"pending", "running"})
_DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


class RuntimeExclusiveConflictError(RuntimeError):
    """Błąd konfliktu locka lub aktywnego run."""


class RuntimeExclusivePreflightError(RuntimeError):
    """Błąd preflight runtime/model."""


@dataclass(frozen=True)
class RuntimeExclusiveSnapshot:
    runtime: str
    loaded_models: list[str]
    lock_owner: Optional[str]
    lock_acquired_at: Optional[float]


class RuntimeExclusiveGuard:
    """Globalny guard benchmarków: lock + preflight runtime/model."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owner: Optional[str] = None
        self._acquired_at: Optional[float] = None

    def acquire_lock(self, owner: str) -> None:
        """Próbuje przejąć globalny lock benchmarku."""
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            holder = self._owner or "unknown"
            raise RuntimeExclusiveConflictError(
                f"Benchmark lock is already held by {holder}"
            )
        self._owner = owner
        self._acquired_at = time.time()

    def release_lock(self, owner: str) -> None:
        """Zwalnia lock benchmarku (jeśli należy do ownera)."""
        if not self._lock.locked():
            self._owner = None
            self._acquired_at = None
            return
        if self._owner is not None and self._owner != owner:
            logger.warning(
                "Próba zwolnienia locka przez obcego ownera: %s (owner=%s)",
                owner,
                self._owner,
            )
            return
        self._owner = None
        self._acquired_at = None
        self._lock.release()

    async def preflight_for_benchmark(
        self,
        *,
        source: str,
        benchmark_service: Any = None,
        coding_benchmark_service: Any = None,
        endpoint: Optional[str] = None,
    ) -> RuntimeExclusiveSnapshot:
        """
        Wspólny preflight benchmarków.

        Kolejność: runtime -> health -> aktywne runy -> unload modelu.
        """
        runtime = self._resolve_runtime(endpoint=endpoint)
        await self._healthcheck_runtime(runtime=runtime, endpoint=endpoint)
        self._ensure_no_other_runs(
            source=source,
            benchmark_service=benchmark_service,
            coding_benchmark_service=coding_benchmark_service,
        )
        loaded_models = await self._drain_loaded_model(
            runtime=runtime,
            endpoint=endpoint,
        )
        return RuntimeExclusiveSnapshot(
            runtime=runtime,
            loaded_models=loaded_models,
            lock_owner=self._owner,
            lock_acquired_at=self._acquired_at,
        )

    def status_snapshot(self) -> dict[str, Any]:
        """Techniczny snapshot locka (do diagnostyki/logów)."""
        return {
            "lock_owner": self._owner,
            "lock_acquired_at": self._acquired_at,
            "lock_held": self._lock.locked(),
        }

    def _resolve_runtime(self, *, endpoint: Optional[str]) -> str:
        if endpoint:
            parsed = (endpoint or "").lower()
            if "11434" in parsed or "ollama" in parsed:
                return "ollama"
            if "vllm" in parsed or ":800" in parsed:
                return "vllm"
            if "onnx" in parsed:
                return "onnx"
        runtime_info = get_active_llm_runtime(SETTINGS)
        provider = (runtime_info.provider or "local").lower()
        if provider in {"ollama", "vllm", "onnx"}:
            return provider
        return "ollama"

    async def _healthcheck_runtime(
        self, *, runtime: str, endpoint: Optional[str]
    ) -> None:
        if runtime == "onnx":
            return
        base = self._resolve_base_url(runtime=runtime, endpoint=endpoint)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                if runtime == "ollama":
                    tags = await client.get(f"{base}/api/tags")
                    ps = await client.get(f"{base}/api/ps")
                    if tags.status_code >= 400 or ps.status_code >= 400:
                        raise RuntimeExclusivePreflightError(
                            f"Ollama healthcheck failed (tags={tags.status_code}, ps={ps.status_code})"
                        )
                    return
                models = await client.get(f"{base}/v1/models")
                if models.status_code >= 400:
                    raise RuntimeExclusivePreflightError(
                        f"{runtime} healthcheck failed (models={models.status_code})"
                    )
        except RuntimeExclusivePreflightError:
            raise
        except Exception as exc:
            raise RuntimeExclusivePreflightError(
                f"Runtime healthcheck error for {runtime}: {exc}"
            ) from exc

    def _ensure_no_other_runs(
        self,
        *,
        source: str,
        benchmark_service: Any,
        coding_benchmark_service: Any,
    ) -> None:
        if source not in {"llm", "coding"}:
            logger.debug("Unknown benchmark source in guard: %s", source)
        if self._has_active_llm_runs(benchmark_service):
            raise RuntimeExclusiveConflictError("LLM benchmark already running")
        if self._has_active_coding_runs(coding_benchmark_service):
            raise RuntimeExclusiveConflictError("Coding benchmark already running")

    def _has_active_llm_runs(self, service: Any) -> bool:
        if service is None:
            return False
        try:
            runs = service.list_benchmarks(limit=100)
            for run in runs:
                status = str(run.get("status", "")).lower()
                if status in _ACTIVE_RUN_STATES:
                    return True
        except Exception as exc:
            logger.warning("Błąd sprawdzania aktywnych LLM benchmarków: %s", exc)
        return False

    def _has_active_coding_runs(self, service: Any) -> bool:
        if service is None:
            return False
        try:
            runs = service.list_runs(limit=100)
            for run in runs:
                status = str(run.get("status", "")).lower()
                if status in _ACTIVE_RUN_STATES:
                    return True
        except Exception as exc:
            logger.warning("Błąd sprawdzania aktywnych coding benchmarków: %s", exc)
        return False

    async def _drain_loaded_model(
        self, *, runtime: str, endpoint: Optional[str]
    ) -> list[str]:
        if runtime != "ollama":
            return []
        base = self._resolve_base_url(runtime="ollama", endpoint=endpoint)
        loaded_models = await self._ollama_loaded_models(base)
        if not loaded_models:
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for model_name in loaded_models:
                    # keep_alive=0 zwalnia model z RAM/VRAM w Ollama.
                    response = await client.post(
                        f"{base}/api/generate",
                        json={
                            "model": model_name,
                            "prompt": "",
                            "stream": False,
                            "keep_alive": 0,
                        },
                    )
                    if response.status_code >= 400:
                        raise RuntimeExclusivePreflightError(
                            f"Ollama /api/generate failed for model {model_name} "
                            f"with {response.status_code}"
                        )
        except RuntimeExclusivePreflightError:
            raise
        except Exception as exc:
            raise RuntimeExclusivePreflightError(
                f"Unable to unload Ollama models: {exc}"
            ) from exc
        remaining = await self._ollama_loaded_models(base)
        if remaining:
            raise RuntimeExclusivePreflightError(
                f"Could not unload all models from Ollama: {remaining}"
            )
        return loaded_models

    async def _ollama_loaded_models(self, base: str) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base}/api/ps")
            if response.status_code >= 400:
                raise RuntimeExclusivePreflightError(
                    f"Ollama /api/ps failed with {response.status_code}"
                )
            payload = response.json() if response.content else {}
            raw_models = payload.get("models", []) if isinstance(payload, dict) else []
            result: list[str] = []
            for item in raw_models:
                if isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                    if name:
                        result.append(name)
            return result
        except RuntimeExclusivePreflightError:
            raise
        except Exception as exc:
            raise RuntimeExclusivePreflightError(
                f"Unable to read Ollama loaded models: {exc}"
            ) from exc

    def _resolve_base_url(self, *, runtime: str, endpoint: Optional[str]) -> str:
        if runtime == "ollama":
            default_endpoint = SETTINGS.LLM_LOCAL_ENDPOINT or _DEFAULT_OLLAMA_BASE_URL
            raw = endpoint or default_endpoint
            parsed = urlparse(raw)
            base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
            if base.endswith("/v1"):
                base = base[:-3]
            return base.rstrip("/") or _DEFAULT_OLLAMA_BASE_URL
        if runtime == "vllm":
            base = endpoint or SETTINGS.VLLM_ENDPOINT or "http://127.0.0.1:8000"
            return str(base).rstrip("/")
        base = endpoint or SETTINGS.LLM_LOCAL_ENDPOINT or _DEFAULT_OLLAMA_BASE_URL
        return str(base).rstrip("/")
