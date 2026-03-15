"""Moduł: routes/system_llm - Endpointy zarządzania LLM."""

from __future__ import annotations

import asyncio
import importlib.util
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from uuid import UUID

import httpx
import psutil
from fastapi import APIRouter, HTTPException

from venom_core.api.routes import system_deps
from venom_core.api.routes.models_utils import infer_model_provider
from venom_core.api.routes.permission_denied_contract import (
    raise_permission_denied_http,
)
from venom_core.api.schemas.system_llm import (
    ActiveLlmServerRequest,
    LlmRuntimeActivateRequest,
)
from venom_core.config import SETTINGS
from venom_core.execution.onnx_llm_client import OnnxLlmClient
from venom_core.services import remote_models_service, system_llm_service
from venom_core.services.config_manager import config_manager
from venom_core.services.feedback_loop_policy import (
    FEEDBACK_LOOP_REQUESTED_ALIAS,
    FeedbackLoopGuardResult,
    classify_feedback_loop_tier,
    evaluate_feedback_loop_guard,
    feedback_loop_policy,
    is_feedback_loop_alias,
    is_feedback_loop_ready,
    resolve_feedback_loop_model,
)
from venom_core.utils.llm_runtime import (
    compute_llm_config_hash,
    get_active_llm_runtime,
    infer_local_provider,
)
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

LLM_CONTROLLER_UNAVAILABLE = "LLMController nie jest dostępny"

LLM_SERVERS_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": LLM_CONTROLLER_UNAVAILABLE},
}
LLM_SERVER_CONTROL_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Nieprawidłowa akcja lub parametry sterowania serwerem"},
    503: {"description": LLM_CONTROLLER_UNAVAILABLE},
    500: {"description": "Błąd podczas wykonywania komendy serwera LLM"},
}
LLM_RUNTIME_ACTIVATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {
        "description": "Nieprawidłowy provider/model lub brak wymaganej konfiguracji"
    },
}
LLM_RUNTIME_OPTIONS_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": "LLMController lub ModelManager nie jest dostępny"},
}
LLM_SERVER_ACTIVATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Nieznany serwer LLM lub brak konfiguracji"},
    403: {
        "description": "Wybrany serwer LLM jest niedostępny w aktualnym profilu runtime"
    },
    503: {"description": "LLMController lub ModelManager nie jest dostępny"},
    500: {"description": "Błąd wewnętrzny podczas przełączania aktywnego serwera"},
}

_runtime_options_catalog_cache_lock = remote_models_service.Lock()
_runtime_options_catalog_cache: dict[str, dict[str, Any]] = {}
_runtime_options_probe_cache_lock = remote_models_service.Lock()
_runtime_options_probe_cache: dict[str, dict[str, Any]] = {}
_MODEL_ALIAS_TO_CANONICAL: dict[str, str] = {
    "gemma3:latest": "gemma-3-4b-it",
    "gemma3:4b": "gemma-3-4b-it",
    "gemma3:1b": "gemma-3-1b-it",
}
_CANONICAL_TO_ALIASES: dict[str, set[str]] = {
    "gemma-3-4b-it": {"gemma3:latest", "gemma3:4b"},
    "gemma-3-1b-it": {"gemma3:1b"},
}
_CODING_MODEL_MARKERS: tuple[str, ...] = (
    "coder",
    "codestral",
    "codegemma",
    "starcoder",
    "deepseek-coder",
    "codeqwen",
    "opencoder",
)


def _runtime_adapter_deploy_capability(runtime_id: str) -> tuple[bool, str]:
    runtime = runtime_id.strip().lower()
    if runtime == "ollama":
        return True, "ollama_modelfile"
    if runtime == "vllm":
        return True, "vllm_exported_runtime_model"
    if runtime == "onnx":
        return True, "onnx_merge_export_runtime_model"
    return False, "none"


def _runtime_profile_name() -> str:
    return system_llm_service.runtime_profile_name(
        str(getattr(SETTINGS, "VENOM_RUNTIME_PROFILE", "full") or "").strip().lower()
    )


def _feedback_loop_resolution_defaults(model_name: str | None) -> dict[str, Any]:
    tier = classify_feedback_loop_tier(model_name)
    if tier == "primary":
        reason = "exact"
    elif tier == "fallback":
        reason = "fallback"
    else:
        reason = None
    ready = is_feedback_loop_ready(model_name)
    return {
        "requested_model_alias": FEEDBACK_LOOP_REQUESTED_ALIAS if ready else None,
        "resolved_model_id": model_name if ready else None,
        "resolution_reason": reason,
        "feedback_loop_ready": ready,
        "feedback_loop_tier": tier,
    }


def _canonical_model_id(model_id: str | None) -> str:
    candidate = str(model_id or "").strip()
    if not candidate:
        return ""
    normalized = candidate.lower()
    return _MODEL_ALIAS_TO_CANONICAL.get(normalized, candidate)


def _model_aliases(model_id: str | None) -> list[str]:
    candidate = str(model_id or "").strip()
    if not candidate:
        return []
    canonical = _canonical_model_id(candidate)
    aliases = {candidate, canonical}
    canonical_lower = canonical.lower()
    aliases.update(_CANONICAL_TO_ALIASES.get(canonical_lower, set()))
    return sorted(alias for alias in aliases if alias)


def _is_coding_model(model_id: str | None) -> bool:
    normalized = _canonical_model_id(model_id).lower()
    return any(marker in normalized for marker in _CODING_MODEL_MARKERS)


def _allowed_local_servers() -> set[str]:
    return system_llm_service.allowed_local_servers(
        profile=_runtime_profile_name(),
        onnx_enabled=bool(getattr(SETTINGS, "ONNX_LLM_ENABLED", False)),
    )


def _is_ollama_installed() -> bool:
    return system_llm_service.is_ollama_installed()


def _is_vllm_installed() -> bool:
    return system_llm_service.is_vllm_installed()


def _is_onnx_runtime_installed() -> bool:
    return system_llm_service.is_onnx_runtime_installed()


def _installed_local_servers() -> set[str]:
    return system_llm_service.installed_local_servers(
        ollama_installed=_is_ollama_installed(),
        vllm_installed=_is_vllm_installed(),
        onnx_installed=_is_onnx_runtime_installed(),
    )


def _ensure_server_allowed(server_name: str) -> None:
    allowed = _allowed_local_servers()
    if server_name not in allowed:
        profile = _runtime_profile_name()
        raise_permission_denied_http(
            PermissionError(
                f"Serwer LLM '{server_name}' jest niedostępny w profilu '{profile}'. "
                f"Dozwolone: {', '.join(sorted(allowed)) or 'brak'}."
            ),
            operation="system.llm.server_allowed",
        )
    if server_name not in _installed_local_servers():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Serwer LLM '{server_name}' nie jest zainstalowany w tym środowisku."
            ),
        )


async def _stop_other_servers(
    llm_controller, servers: list[dict], server_name: str
) -> dict:
    stop_results: dict[str, dict[str, Any]] = {}
    for server in servers:
        if server["name"] == server_name:
            continue
        if not server.get("supports", {}).get("stop"):
            continue
        try:
            result = await llm_controller.run_action(server["name"], "stop")
            stop_results[server["name"]] = {
                "ok": result.ok,
                "exit_code": result.exit_code,
            }
        except Exception as exc:
            stop_results[server["name"]] = {"ok": False, "error": str(exc)}
    return stop_results


async def _start_server_if_supported(
    llm_controller, server_name: str, target: dict
) -> Optional[dict]:
    if not target.get("supports", {}).get("start"):
        return None
    try:
        result = await llm_controller.run_action(server_name, "start")
        return {"ok": result.ok, "exit_code": result.exit_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _assert_stop_results_clean(stop_results: dict[str, dict[str, Any]]) -> None:
    failures = [
        server
        for server, result in stop_results.items()
        if not bool(result.get("ok", False))
    ]
    if failures:
        raise HTTPException(
            status_code=500,
            detail=(
                "Nie udało się zatrzymać poprzednich serwerów LLM: "
                + ", ".join(sorted(failures))
            ),
        )


def _release_onnx_runtime_caches() -> None:
    """Release ONNX in-process caches when switching away from ONNX runtime."""
    try:
        from venom_core.api.routes import llm_simple as llm_simple_routes

        llm_simple_routes.release_onnx_simple_client()
    except Exception:
        logger.warning("Nie udało się zwolnić klienta ONNX simple-mode.")
    try:
        from venom_core.api.routes import tasks as tasks_routes

        tasks_routes.release_onnx_task_runtime(wait=False)
    except Exception:
        logger.warning("Nie udało się zwolnić runtime ONNX task-mode.")


async def _await_server_health(_server_name: str, health_url: str) -> bool:
    logger.info("Oczekiwanie na gotowość serwera LLM.")
    async with httpx.AsyncClient(timeout=2.0) as client:
        for attempt in range(60):
            try:
                resp = await client.get(health_url)
                if 200 <= resp.status_code < 300:
                    logger.info("Serwer LLM gotowy po %.1fs", attempt * 0.5)
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
    logger.error("Serwer LLM nie odpowiedział prawidłowo po 30s")
    return False


def _resolve_local_endpoint(server_name: str, target: dict) -> str | None:
    endpoint = target.get("endpoint")
    if server_name == "ollama":
        return build_http_url("localhost", 11434, "/v1")
    if server_name == "vllm":
        return SETTINGS.VLLM_ENDPOINT
    if server_name == "onnx":
        return None
    return endpoint


def _persist_local_runtime_endpoint(server_name: str, endpoint: str | None) -> None:
    if server_name == "onnx":
        try:
            SETTINGS.LLM_SERVICE_TYPE = "onnx"
            SETTINGS.ACTIVE_LLM_SERVER = "onnx"
        except Exception:
            logger.warning("Nie udało się zaktualizować SETTINGS dla runtime ONNX.")
        config_manager.update_config(
            {
                "LLM_SERVICE_TYPE": "onnx",
                "ACTIVE_LLM_SERVER": "onnx",
            }
        )
        return

    if not endpoint:
        return
    try:
        SETTINGS.LLM_SERVICE_TYPE = "local"
        SETTINGS.LLM_LOCAL_ENDPOINT = endpoint
    except Exception:
        logger.warning("Nie udało się zaktualizować SETTINGS dla endpointu LLM.")
    config_manager.update_config(
        {
            "LLM_SERVICE_TYPE": "local",
            "LLM_LOCAL_ENDPOINT": endpoint,
            "ACTIVE_LLM_SERVER": server_name,
        }
    )


def _select_model_for_server(
    *,
    server_name: str,
    config: dict,
    models: list[dict],
) -> tuple[str, str, str]:
    if server_name == "onnx":
        last_model_key = "LAST_MODEL_ONNX"
        prev_model_key = "PREVIOUS_MODEL_ONNX"
    else:
        last_model_key = (
            "LAST_MODEL_OLLAMA" if server_name == "ollama" else "LAST_MODEL_VLLM"
        )
        prev_model_key = (
            "PREVIOUS_MODEL_OLLAMA"
            if server_name == "ollama"
            else "PREVIOUS_MODEL_VLLM"
        )
    desired_model = config.get(last_model_key) or config.get("LLM_MODEL_NAME", "")
    previous_model = config.get(prev_model_key) or ""
    available = {
        m["name"] for m in models if m.get("provider") == server_name and m.get("name")
    }
    if desired_model in available:
        return desired_model, last_model_key, prev_model_key
    if previous_model and previous_model in available:
        config_manager.update_config({last_model_key: previous_model})
        return previous_model, last_model_key, prev_model_key
    raise HTTPException(
        status_code=400,
        detail="Brak modelu na wybranym serwerze (brak fallbacku).",
    )


def _available_models_for_server(*, models: list[dict], server_name: str) -> list[str]:
    return [
        str(model.get("name") or "").strip()
        for model in models
        if model.get("provider") == server_name and str(model.get("name") or "").strip()
    ]


def _host_ram_total_gb() -> float | None:
    try:
        return round(float(psutil.virtual_memory().total) / float(1024**3), 2)
    except Exception:
        return None


async def _host_vram_total_mb(model_manager: Any) -> float | None:
    usage_reader = getattr(model_manager, "get_usage_metrics", None)
    if not callable(usage_reader):
        return None
    try:
        usage = await usage_reader()
        raw_value = usage.get("vram_total_mb")
        if raw_value is None:
            return None
        return float(raw_value)
    except (TypeError, ValueError):
        return None
    except Exception:
        return None


async def _evaluate_feedback_loop_resource_guard(
    *,
    model_manager: Any,
    model_name: str,
) -> FeedbackLoopGuardResult:
    return evaluate_feedback_loop_guard(
        model_id=model_name,
        settings=SETTINGS,
        ram_total_gb=_host_ram_total_gb(),
        vram_total_mb=await _host_vram_total_mb(model_manager),
    )


def _validate_requested_model_available(
    *,
    requested_model: str | None,
    available_models: set[str],
    server_name: str,
) -> str | None:
    requested = str(requested_model or "").strip()
    if not requested:
        return None
    if requested in available_models:
        return requested
    raise HTTPException(
        status_code=400,
        detail=(
            f"Model '{requested}' nie jest dostępny na serwerze '{server_name}'. "
            "Użyj /system/llm-runtime/options aby sprawdzić listę modeli."
        ),
    )


def _merge_monitor_status_into_servers(servers: list[dict], service_monitor) -> None:
    if not service_monitor:
        return
    status_lookup = {
        service.name.lower(): service for service in service_monitor.get_all_services()
    }
    for server in servers:
        status = None
        name_key = str(server.get("name") or "").lower()
        display_key = str(server.get("display_name") or "").lower()
        for key in (name_key, display_key):
            if not key:
                continue
            status = status_lookup.get(key)
            if status:
                break
        if not status:
            continue
        server["status"] = status.status.value
        server["latency_ms"] = status.latency_ms
        server["last_check"] = status.last_check
        server["error_message"] = status.error_message


def _should_probe_server(candidate: dict) -> bool:
    url = candidate.get("health_url") or candidate.get("endpoint")
    if not url:
        return False
    status = candidate.get("status")
    return not status or status == "unknown"


async def _probe_server_status(candidate: dict) -> None:
    url = candidate.get("health_url") or candidate.get("endpoint")
    if not _should_probe_server(candidate) or not url:
        return
    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
        elapsed = (time.perf_counter() - start) * 1000
        candidate["latency_ms"] = elapsed
        if response.status_code < 400:
            candidate["status"] = "online"
            candidate["error_message"] = None
            return
        candidate["status"] = "degraded"
        candidate["error_message"] = f"HTTP {response.status_code}"
    except Exception as exc:  # pragma: no cover
        candidate["status"] = candidate.get("status") or "offline"
        candidate["error_message"] = str(exc)


async def _probe_servers(servers: list[dict]) -> None:
    probe_tasks = [_probe_server_status(server) for server in servers]
    if probe_tasks:
        await asyncio.gather(*probe_tasks)


def _validate_switch_dependencies():
    llm_controller = system_deps.get_llm_controller()
    model_manager = system_deps.get_model_manager()
    request_tracer = system_deps.get_request_tracer()
    if llm_controller is None:
        raise HTTPException(status_code=503, detail=LLM_CONTROLLER_UNAVAILABLE)
    if model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")
    return llm_controller, model_manager, request_tracer


def _get_llm_controller_or_503():
    llm_controller = system_deps.get_llm_controller()
    if llm_controller is None:
        raise HTTPException(status_code=503, detail=LLM_CONTROLLER_UNAVAILABLE)
    return llm_controller


def _find_target_server(server_name: str, servers: list[dict]) -> dict:
    target = next((s for s in servers if s["name"] == server_name), None)
    if not target:
        raise HTTPException(
            status_code=404, detail="Nie znaleziono konfiguracji serwera"
        )
    return target


def _trace_switch(
    request_tracer, trace_id: UUID | None, action: str, details: str
) -> None:
    if not request_tracer or not trace_id:
        return
    request_tracer.add_step(
        trace_id,
        "System",
        action,
        status="ok",
        details=details,
    )


def _build_model_updates(
    *,
    server_name: str,
    selected_model: str,
    models: list[dict],
    last_model_key: str,
    previous_model: str,
) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "LLM_MODEL_NAME": selected_model,
        "HYBRID_LOCAL_MODEL": selected_model,
        last_model_key: selected_model,
    }
    if server_name == "vllm":
        model_info = next((m for m in models if m["name"] == selected_model), None)
        if model_info and model_info.get("path"):
            updates["VLLM_MODEL_PATH"] = model_info["path"]
            logger.info("Persisting VLLM model path from registry metadata.")
    if server_name == "onnx":
        model_info = next((m for m in models if m["name"] == selected_model), None)
        if model_info and model_info.get("path"):
            updates["ONNX_LLM_MODEL_PATH"] = model_info["path"]
            updates["ONNX_LLM_ENABLED"] = "true"
            logger.info("Persisting ONNX model path from registry metadata.")

    if previous_model and previous_model != selected_model:
        prev_model_key = _previous_model_key_for_server(server_name)
        updates[prev_model_key] = previous_model
    return updates


def _previous_model_key_for_server(server_name: str) -> str:
    return system_llm_service.previous_model_key_for_server(server_name)


def _persist_selected_model_settings(
    server_name: str, selected_model: str, endpoint: str | None
) -> str:
    try:
        SETTINGS.LLM_MODEL_NAME = selected_model
        SETTINGS.HYBRID_LOCAL_MODEL = selected_model
    except Exception:
        logger.warning("Nie udało się zaktualizować SETTINGS dla modelu LLM.")

    config_hash = compute_llm_config_hash(server_name, endpoint, selected_model)
    config_manager.update_config({"LLM_CONFIG_HASH": config_hash})
    try:
        SETTINGS.LLM_CONFIG_HASH = config_hash
        SETTINGS.ACTIVE_LLM_SERVER = server_name
        if server_name == "onnx":
            SETTINGS.LLM_SERVICE_TYPE = "onnx"
    except Exception:
        logger.warning("Nie udało się zaktualizować SETTINGS dla hash LLM.")
    return config_hash


def _build_onnx_server_payload() -> dict[str, Any]:
    client = OnnxLlmClient()
    status = client.status_payload()
    return {
        "name": "onnx",
        "display_name": "ONNX Runtime",
        "description": "In-process ONNX Runtime GenAI backend.",
        "endpoint": None,
        "provider": "onnx",
        "health_url": None,
        "supports": {"start": False, "stop": False, "restart": False},
        "status": "online" if status.get("ready") else "degraded",
        "error_message": None
        if status.get("ready")
        else "ONNX runtime not ready (check model path and dependencies).",
        "onnx": status,
    }


def _normalize_runtime_provider(provider_raw: str | None) -> str:
    return system_llm_service.normalize_runtime_provider(provider_raw)


def _assert_runtime_provider_supported(provider_raw: str) -> None:
    if provider_raw not in ("openai", "google", "onnx"):
        raise HTTPException(status_code=400, detail="Nieznany provider runtime")


def _capture_runtime_settings_snapshot() -> tuple[str, str, str, str]:
    return (
        SETTINGS.LLM_SERVICE_TYPE,
        SETTINGS.LLM_MODEL_NAME,
        SETTINGS.ACTIVE_LLM_SERVER,
        SETTINGS.LLM_CONFIG_HASH,
    )


def _restore_runtime_settings_snapshot(snapshot: tuple[str, str, str, str]) -> None:
    (
        SETTINGS.LLM_SERVICE_TYPE,
        SETTINGS.LLM_MODEL_NAME,
        SETTINGS.ACTIVE_LLM_SERVER,
        SETTINGS.LLM_CONFIG_HASH,
    ) = snapshot


def _runtime_activate_payload(runtime) -> dict[str, Any]:
    feedback_resolution = _feedback_loop_resolution_defaults(runtime.model_name)
    return {
        "status": "success",
        "active_server": runtime.provider,
        "active_endpoint": runtime.endpoint,
        "active_model": runtime.model_name,
        "config_hash": runtime.config_hash,
        "runtime_id": runtime.runtime_id,
        "source_type": _runtime_source_type(runtime.provider),
        "requested_model_alias": feedback_resolution["requested_model_alias"],
        "resolved_model_id": feedback_resolution["resolved_model_id"],
        "resolution_reason": feedback_resolution["resolution_reason"],
    }


def _assert_cloud_provider_requirements(provider_raw: str) -> None:
    if provider_raw == "openai" and not SETTINGS.OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="Brak OPENAI_API_KEY")
    if provider_raw != "google":
        return
    if not SETTINGS.GOOGLE_API_KEY:
        raise HTTPException(status_code=400, detail="Brak GOOGLE_API_KEY")
    if (
        importlib.util.find_spec("google.genai") is None
        and importlib.util.find_spec("google.generativeai") is None
    ):
        raise HTTPException(
            status_code=400,
            detail="Brak SDK Gemini (google-genai / google-generativeai)",
        )


def _activate_onnx_runtime(model: str | None) -> dict[str, Any]:
    onnx_client = OnnxLlmClient()
    try:
        onnx_client.ensure_ready()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    model_name = model or onnx_client.config.model_path
    snapshot = _capture_runtime_settings_snapshot()
    try:
        SETTINGS.LLM_SERVICE_TYPE = "onnx"
        SETTINGS.LLM_MODEL_NAME = model_name
        SETTINGS.ACTIVE_LLM_SERVER = "onnx"
        runtime = get_active_llm_runtime()
        config_hash = runtime.config_hash or ""
        SETTINGS.LLM_CONFIG_HASH = config_hash
        config_manager.update_config(
            {
                "LLM_SERVICE_TYPE": "onnx",
                "LLM_MODEL_NAME": model_name,
                "ACTIVE_LLM_SERVER": "onnx",
                "LAST_MODEL_ONNX": model_name,
                "LLM_CONFIG_HASH": config_hash,
            }
        )
    except Exception:
        _restore_runtime_settings_snapshot(snapshot)
        raise
    return _runtime_activate_payload(runtime)


def _default_cloud_model(provider_raw: str) -> str:
    if provider_raw == "openai":
        return SETTINGS.OPENAI_GPT4O_MODEL
    return SETTINGS.GOOGLE_GEMINI_PRO_MODEL


def _runtime_source_type(provider: str) -> str:
    if provider in {"openai", "google"}:
        return "cloud-api"
    return "local-runtime"


def _remote_timeout_seconds() -> float:
    return remote_models_service.remote_timeout_seconds(
        openai_api_timeout=getattr(SETTINGS, "OPENAI_API_TIMEOUT", 6.0)
    )


def _check_openai_configured() -> bool:
    return remote_models_service.is_api_key_configured(SETTINGS.OPENAI_API_KEY)


def _check_google_configured() -> bool:
    return remote_models_service.is_api_key_configured(SETTINGS.GOOGLE_API_KEY)


def _now_iso() -> str:
    return datetime.now().isoformat()


async def _fetch_openai_models_catalog_live_payload() -> list[dict[str, Any]]:
    return await remote_models_service.fetch_openai_models_catalog_live(
        api_key=(SETTINGS.OPENAI_API_KEY or "").strip(),
        timeout_seconds=_remote_timeout_seconds(),
        models_url=remote_models_service.openai_models_url(
            chat_completions_endpoint=(
                getattr(SETTINGS, "OPENAI_CHAT_COMPLETIONS_ENDPOINT", "") or ""
            )
        ),
        traffic_client_factory=remote_models_service.traffic_controlled_http_client_cls(),
        map_openai_capabilities_fn=remote_models_service.map_openai_capabilities,
    )


async def _fetch_google_models_catalog_live_payload() -> list[dict[str, Any]]:
    return await remote_models_service.fetch_google_models_catalog_live(
        api_key=(SETTINGS.GOOGLE_API_KEY or "").strip(),
        timeout_seconds=_remote_timeout_seconds(),
        models_url=remote_models_service.google_models_url(),
        traffic_client_factory=remote_models_service.traffic_controlled_http_client_cls(),
        map_google_capabilities_fn=remote_models_service.map_google_capabilities,
    )


async def _catalog_for_cloud_provider(
    provider: str,
) -> tuple[list[dict[str, Any]], str, str | None]:
    return await remote_models_service.catalog_for_provider(
        provider=provider,
        cache=_runtime_options_catalog_cache,
        lock=_runtime_options_catalog_cache_lock,
        catalog_ttl_seconds=remote_models_service.catalog_ttl_seconds(),
        deps=remote_models_service.CatalogProviderDeps(
            cache_get_fn=remote_models_service.cache_get,
            cache_put_fn=remote_models_service.cache_put,
            fetch_openai_models_catalog_live_fn=(
                _fetch_openai_models_catalog_live_payload
            ),
            fetch_google_models_catalog_live_fn=(
                _fetch_google_models_catalog_live_payload
            ),
            openai_static_catalog_payload_fn=(
                remote_models_service.openai_static_catalog_payload
            ),
            google_static_catalog_payload_fn=(
                remote_models_service.google_static_catalog_payload
            ),
            check_openai_configured_fn=_check_openai_configured,
            check_google_configured_fn=_check_google_configured,
            now_iso_fn=_now_iso,
            logger=logger,
        ),
    )


async def _validate_openai_connection() -> tuple[bool, str, float | None]:
    return await remote_models_service.validate_openai_connection(
        api_key=(SETTINGS.OPENAI_API_KEY or "").strip(),
        model=None,
        timeout_seconds=_remote_timeout_seconds(),
        openai_models_url=remote_models_service.openai_models_url(
            chat_completions_endpoint=(
                getattr(SETTINGS, "OPENAI_CHAT_COMPLETIONS_ENDPOINT", "") or ""
            )
        ),
        openai_model_url_fn=lambda model_id: remote_models_service.openai_model_url(
            models_url=remote_models_service.openai_models_url(
                chat_completions_endpoint=(
                    getattr(SETTINGS, "OPENAI_CHAT_COMPLETIONS_ENDPOINT", "") or ""
                )
            ),
            model_id=model_id,
        ),
        traffic_client_factory=remote_models_service.traffic_controlled_http_client_cls(),
        http_error_type=httpx.HTTPError,
    )


async def _validate_google_connection() -> tuple[bool, str, float | None]:
    return await remote_models_service.validate_google_connection(
        api_key=(SETTINGS.GOOGLE_API_KEY or "").strip(),
        model=None,
        timeout_seconds=_remote_timeout_seconds(),
        google_models_url=remote_models_service.google_models_url(),
        google_model_url_fn=remote_models_service.google_model_url,
        traffic_client_factory=remote_models_service.traffic_controlled_http_client_cls(),
        http_error_type=httpx.HTTPError,
    )


async def _probe_cloud_provider(provider: str) -> tuple[str, str | None, float | None]:
    return await remote_models_service.probe_provider_cached(
        provider=provider,
        cache=_runtime_options_probe_cache,
        lock=_runtime_options_probe_cache_lock,
        provider_probe_ttl_seconds=remote_models_service.provider_probe_ttl_seconds(),
        cache_get_fn=remote_models_service.cache_get,
        cache_put_fn=remote_models_service.cache_put,
        validate_openai_connection_fn=_validate_openai_connection,
        validate_google_connection_fn=_validate_google_connection,
    )


def _runtime_model_payload(
    *,
    runtime_id: str,
    model_id: str,
    name: str,
    provider: str,
    active: bool,
    source_type: str,
    capabilities: list[str] | None = None,
    chat_compatible: bool = True,
    feedback_loop_ready: bool | None = None,
    feedback_loop_tier: str | None = None,
    owned_by_runtime: str | None = None,
    ownership_status: str | None = None,
    compatible_runtimes: list[str] | None = None,
) -> dict[str, Any]:
    model_feedback_tier = feedback_loop_tier or classify_feedback_loop_tier(model_id)
    model_feedback_ready = (
        bool(feedback_loop_ready)
        if feedback_loop_ready is not None
        else is_feedback_loop_ready(model_id)
    )
    canonical_model_id = _canonical_model_id(model_id)
    is_adapter_artifact = str(name or "").strip().lower().startswith("venom-adapter-")
    payload: dict[str, Any] = {
        "id": model_id,
        "name": name,
        "provider": provider,
        "runtime_id": runtime_id,
        "source_type": source_type,
        "active": active,
        "chat_compatible": chat_compatible,
        "feedback_loop_ready": model_feedback_ready,
        "feedback_loop_tier": model_feedback_tier,
        "canonical_model_id": canonical_model_id,
        "aliases": _model_aliases(model_id),
        "coding_eligible": (
            _is_coding_model(canonical_model_id)
            or model_feedback_tier in {"primary", "fallback"}
        ),
        "owned_by_runtime": owned_by_runtime,
        "ownership_status": ownership_status or "unknown",
        "compatible_runtimes": compatible_runtimes or [],
        "model_kind": "adapter_artifact" if is_adapter_artifact else "base_model",
        "is_adapter_artifact": is_adapter_artifact,
    }
    if capabilities:
        payload["capabilities"] = capabilities
    return payload


def _flatten_runtime_models(runtimes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for key, candidate, canonical in _iter_runtime_model_candidates(runtimes):
        existing = deduped.get(key)
        if existing is None or _prefer_runtime_model_candidate(
            candidate=candidate,
            existing=existing,
            canonical=canonical,
        ):
            deduped[key] = candidate
    return list(deduped.values())


def _iter_runtime_model_candidates(
    runtimes: list[dict[str, Any]],
) -> Iterable[tuple[tuple[str, str], dict[str, Any], str]]:
    for runtime in runtimes:
        runtime_id = str(runtime.get("runtime_id") or "").strip().lower()
        for model in runtime.get("models") or []:
            candidate = _runtime_model_candidate(model)
            if candidate is None:
                continue
            model_name, dumped = candidate
            canonical = _canonical_runtime_model_name(model_name)
            yield (runtime_id, canonical), dumped, canonical


def _runtime_model_candidate(model: Any) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(model, dict):
        return None
    model_name = str(model.get("name") or "").strip()
    if not model_name:
        return None
    return model_name, dict(model)


def _canonical_runtime_model_name(model_name: str) -> str:
    canonical = _canonical_model_id(model_name).strip().lower()
    if canonical:
        return canonical
    return model_name.lower()


def _prefer_runtime_model_candidate(
    *,
    candidate: dict[str, Any],
    existing: dict[str, Any],
    canonical: str,
) -> bool:
    candidate_active = bool(candidate.get("active"))
    existing_active = bool(existing.get("active"))
    if candidate_active and not existing_active:
        return True
    candidate_is_canonical = (
        str(candidate.get("name") or "").strip().lower() == canonical
    )
    existing_is_canonical = str(existing.get("name") or "").strip().lower() == canonical
    return candidate_is_canonical and not existing_is_canonical


async def _load_trainable_model_catalog(
    model_manager: Any,
    *,
    local_models: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    from venom_core.api.routes import academy_models

    try:
        models = await academy_models.list_trainable_models(
            mgr=model_manager,
            local_models=local_models,
        )
    except Exception as exc:
        logger.warning("Failed to load trainable model catalog: %s", exc)
        return []

    normalized: list[dict[str, Any]] = []
    for item in models:
        dumped = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        model_id = str(dumped.get("model_id") or "").strip()
        if not model_id:
            continue
        canonical = _canonical_model_id(model_id)
        dumped["canonical_model_id"] = canonical
        dumped["aliases"] = _model_aliases(model_id)
        dumped["coding_eligible"] = _is_coding_model(canonical)
        normalized.append(dumped)
    return normalized


def _build_model_catalog(
    *,
    runtime_targets: list[dict[str, Any]],
    trainable_models: list[dict[str, Any]],
) -> dict[str, Any]:
    compatibility_by_canonical: dict[str, list[str]] = {}
    for model in trainable_models:
        canonical = _canonical_model_id(
            str(model.get("canonical_model_id") or model.get("model_id") or "").strip()
        ).lower()
        if not canonical:
            continue
        compatibility = model.get("runtime_compatibility")
        if not isinstance(compatibility, dict):
            continue
        compatibility_by_canonical[canonical] = sorted(
            runtime_id for runtime_id, allowed in compatibility.items() if bool(allowed)
        )

    all_models = _flatten_runtime_models(runtime_targets)
    for model in all_models:
        canonical = _canonical_model_id(str(model.get("name") or "").strip()).lower()
        if canonical and canonical in compatibility_by_canonical:
            model["compatible_runtimes"] = compatibility_by_canonical[canonical]

    chat_models = [
        model for model in all_models if bool(model.get("chat_compatible", True))
    ]
    coding_models = [
        model for model in chat_models if bool(model.get("coding_eligible"))
    ]
    inference_only_artifacts = [
        model for model in all_models if bool(model.get("is_adapter_artifact"))
    ]
    return {
        "all_models": all_models,
        "chat_models": chat_models,
        "coding_models": coding_models,
        "runtime_servable_models": chat_models,
        "trainable_base_models": trainable_models,
        "inference_only_artifacts": inference_only_artifacts,
        # Backward-compatible aliases (kept intentionally during 191E rollout).
        "trainable_models": trainable_models,
    }


def _runtime_model_index(
    runtime_targets: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    index: dict[str, dict[str, list[str]]] = {}
    for target in runtime_targets:
        runtime_id = str(target.get("runtime_id") or "").strip().lower()
        if not runtime_id:
            continue
        runtime_entry = index.setdefault(runtime_id, {})
        for model in target.get("models") or []:
            model_name = str(model.get("name") or "").strip()
            if not model_name:
                continue
            canonical = (
                _canonical_model_id(model_name).strip().lower() or model_name.lower()
            )
            names = runtime_entry.setdefault(canonical, [])
            if model_name not in names:
                names.append(model_name)
    return index


def _build_adapter_catalog(
    *,
    model_manager: Any,
    trainable_models: list[dict[str, Any]],
    runtime_targets: list[dict[str, Any]],
) -> dict[str, Any]:
    from venom_core.api.routes import academy_models

    try:
        adapters_raw = academy_models.list_adapters(model_manager)
    except Exception as exc:
        logger.warning("Failed to load adapter catalog for runtime options: %s", exc)
        return {
            "all_adapters": [],
            "by_runtime": {},
            "by_runtime_model": {},
        }

    compatibility_by_canonical = _trainable_runtime_compatibility_by_canonical(
        trainable_models
    )

    runtime_index = _runtime_model_index(runtime_targets)
    all_adapters: list[dict[str, Any]] = []
    by_runtime: dict[str, list[dict[str, Any]]] = {}
    by_runtime_model: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for adapter in adapters_raw:
        entry = _adapter_catalog_entry(
            adapter=adapter,
            compatibility_by_canonical=compatibility_by_canonical,
        )
        if entry is None:
            continue
        all_adapters.append(entry)
        _index_adapter_catalog_entry(
            entry=entry,
            by_runtime=by_runtime,
            by_runtime_model=by_runtime_model,
            runtime_index=runtime_index,
        )

    return {
        "all_adapters": all_adapters,
        "by_runtime": by_runtime,
        "by_runtime_model": by_runtime_model,
    }


def _trainable_runtime_compatibility_by_canonical(
    trainable_models: list[dict[str, Any]],
) -> dict[str, dict[str, bool]]:
    by_canonical: dict[str, dict[str, bool]] = {}
    for model in trainable_models:
        canonical = _canonical_model_id(
            str(model.get("canonical_model_id") or model.get("model_id") or "").strip()
        ).lower()
        if not canonical:
            continue
        compatibility = model.get("runtime_compatibility")
        by_canonical[canonical] = (
            dict(compatibility) if isinstance(compatibility, dict) else {}
        )
    return by_canonical


def _adapter_catalog_entry(
    *,
    adapter: Any,
    compatibility_by_canonical: dict[str, dict[str, bool]],
) -> dict[str, Any] | None:
    payload = adapter.model_dump() if hasattr(adapter, "model_dump") else dict(adapter)
    adapter_id = str(payload.get("adapter_id") or "").strip()
    base_model = str(payload.get("base_model") or "").strip()
    if not adapter_id or not base_model:
        return None
    canonical_base = (
        _canonical_model_id(base_model).strip().lower() or base_model.lower()
    )
    runtime_compatibility = compatibility_by_canonical.get(canonical_base, {})
    compatible_runtimes = sorted(
        runtime for runtime, allowed in runtime_compatibility.items() if bool(allowed)
    )
    return {
        "adapter_id": adapter_id,
        "adapter_path": str(payload.get("adapter_path") or ""),
        "base_model": base_model,
        "canonical_base_model_id": canonical_base,
        "is_active": bool(payload.get("is_active")),
        "created_at": payload.get("created_at"),
        "compatible_runtimes": compatible_runtimes,
    }


def _index_adapter_catalog_entry(
    *,
    entry: dict[str, Any],
    by_runtime: dict[str, list[dict[str, Any]]],
    by_runtime_model: dict[str, dict[str, list[dict[str, Any]]]],
    runtime_index: dict[str, dict[str, list[str]]],
) -> None:
    canonical_base = str(entry.get("canonical_base_model_id") or "").strip().lower()
    for runtime_id in entry.get("compatible_runtimes", []):
        by_runtime.setdefault(runtime_id, []).append(entry)
        runtime_models = runtime_index.get(runtime_id, {})
        if canonical_base not in runtime_models:
            continue
        by_runtime_model.setdefault(runtime_id, {}).setdefault(
            canonical_base, []
        ).append(entry)


async def _local_models_by_runtime(
    model_manager: Any,
    *,
    local_models: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {"ollama": [], "vllm": [], "onnx": []}
    audit_issues: list[dict[str, Any]] = []
    if local_models is None:
        try:
            local_models = await model_manager.list_local_models()
        except Exception:
            logger.warning("Nie udało się pobrać listy modeli lokalnych.")
            return grouped, audit_issues

    active_runtime = get_active_llm_runtime()
    active_provider = (active_runtime.provider or "").lower()
    active_model = (active_runtime.model_name or "").strip()
    for model in local_models:
        payload, issue = _runtime_payload_or_audit_issue(
            model=model,
            grouped=grouped,
            active_provider=active_provider,
            active_model=active_model,
        )
        if issue is not None:
            audit_issues.append(issue)
        if payload is not None:
            runtime_id = str(payload.get("runtime_id") or "").strip().lower()
            if runtime_id in grouped:
                grouped[runtime_id].append(payload)
    return grouped, audit_issues


def _runtime_payload_or_audit_issue(
    *,
    model: dict[str, Any],
    grouped: dict[str, list[dict[str, Any]]],
    active_provider: str,
    active_model: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    inferred = infer_model_provider(model) or "vllm"
    runtime_id = inferred if inferred in grouped else ""
    name = str(model.get("name") or "").strip()
    source = str(model.get("source") or "").strip().lower()
    model_path = str(model.get("path") or "").strip()
    if not name:
        return None, None
    if not runtime_id:
        return None, _runtime_model_audit_issue(
            name=name,
            path=model_path,
            source=source,
            reason="provider_unknown",
        )
    if runtime_id == "vllm" and not _looks_like_vllm_runtime_model_path(model_path):
        return None, _runtime_model_audit_issue(
            name=name,
            path=model_path,
            source=source,
            reason="not_runtime_loadable_for_vllm",
        )
    owner = _resolve_runtime_model_owner(
        source=source,
        inferred=inferred,
        grouped=grouped,
    )
    ownership_status = _resolve_runtime_model_ownership_status(
        owner=owner,
        runtime_id=runtime_id,
        grouped=grouped,
    )
    return (
        _runtime_model_payload(
            runtime_id=runtime_id,
            model_id=name,
            name=name,
            provider=runtime_id,
            source_type="local-runtime",
            active=(runtime_id == active_provider and name == active_model),
            chat_compatible=bool(model.get("chat_compatible", True)),
            owned_by_runtime=owner,
            ownership_status=ownership_status,
            compatible_runtimes=[runtime_id],
        ),
        None,
    )


def _runtime_model_audit_issue(
    *,
    name: str,
    path: str,
    source: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "path": path,
        "source": source or None,
        "reason": reason,
    }


def _resolve_runtime_model_owner(
    *,
    source: str,
    inferred: str,
    grouped: dict[str, list[dict[str, Any]]],
) -> str | None:
    if source in grouped:
        return source
    if inferred in grouped:
        return inferred
    return None


def _resolve_runtime_model_ownership_status(
    *,
    owner: str | None,
    runtime_id: str,
    grouped: dict[str, list[dict[str, Any]]],
) -> str:
    if owner == runtime_id:
        return "native"
    if owner in grouped:
        return "foreign"
    return "unknown"


def _runtime_target_payload(
    *,
    runtime_id: str,
    source_type: str,
    configured: bool,
    available: bool,
    status: str,
    reason: str | None,
    models: list[dict[str, Any]],
    active_runtime: Any,
) -> dict[str, Any]:
    adapter_deploy_supported, adapter_deploy_mode = _runtime_adapter_deploy_capability(
        runtime_id
    )
    runtime_capabilities = _runtime_capabilities(
        runtime_id=runtime_id,
        source_type=source_type,
    )
    return {
        "runtime_id": runtime_id,
        "source_type": source_type,
        "configured": configured,
        "available": available,
        "status": status,
        "reason": reason,
        "active": (active_runtime.provider or "").lower() == runtime_id,
        "models": models,
        "adapter_deploy_supported": adapter_deploy_supported,
        "adapter_deploy_mode": adapter_deploy_mode,
        "supports_native_training": runtime_capabilities["supports_native_training"],
        "supports_adapter_import_safetensors": runtime_capabilities[
            "supports_adapter_import_safetensors"
        ],
        "supports_adapter_import_gguf": runtime_capabilities[
            "supports_adapter_import_gguf"
        ],
        "supports_adapter_runtime_apply": runtime_capabilities[
            "supports_adapter_runtime_apply"
        ],
    }


def _runtime_capabilities(*, runtime_id: str, source_type: str) -> dict[str, bool]:
    runtime = runtime_id.strip().lower()
    source = source_type.strip().lower()
    if source != "local-runtime":
        return {
            "supports_native_training": False,
            "supports_adapter_import_safetensors": False,
            "supports_adapter_import_gguf": False,
            "supports_adapter_runtime_apply": False,
        }
    if runtime == "ollama":
        return {
            "supports_native_training": False,
            "supports_adapter_import_safetensors": True,
            "supports_adapter_import_gguf": True,
            "supports_adapter_runtime_apply": True,
        }
    if runtime in {"vllm", "onnx"}:
        return {
            "supports_native_training": False,
            "supports_adapter_import_safetensors": False,
            "supports_adapter_import_gguf": False,
            "supports_adapter_runtime_apply": True,
        }
    return {
        "supports_native_training": False,
        "supports_adapter_import_safetensors": False,
        "supports_adapter_import_gguf": False,
        "supports_adapter_runtime_apply": False,
    }


def _looks_like_vllm_runtime_model_path(path_raw: str | None) -> bool:
    candidate = str(path_raw or "").strip()
    if not candidate:
        return False
    path_obj = Path(candidate).expanduser()
    if not path_obj.is_absolute():
        path_obj = Path(getattr(SETTINGS, "REPO_ROOT", ".")) / path_obj
    try:
        path_obj = path_obj.resolve()
    except Exception:
        return False
    if not path_obj.exists() or not path_obj.is_dir():
        return False
    if not (path_obj / "config.json").exists():
        return False
    if any(path_obj.glob("*.safetensors")):
        return True
    if any(path_obj.glob("pytorch_model*.bin")):
        return True
    if any(path_obj.glob("model*.bin")):
        return True
    return False


def _is_vllm_runtime_model_entry(model: dict[str, Any]) -> bool:
    inferred = infer_model_provider(model) or "vllm"
    if inferred != "vllm":
        return False
    if model.get("chat_compatible", True) is False:
        return False
    name = str(model.get("name") or "").strip()
    if not name:
        return False
    return True


def _apply_vllm_runtime_autofix(
    *, local_models: list[dict[str, Any]]
) -> dict[str, Any] | None:
    context = _build_vllm_runtime_autofix_context(local_models=local_models)
    if context is None:
        return None

    fallback_name, fallback_path = _resolve_vllm_runtime_autofix_fallback(
        context=context
    )
    if not fallback_name or not fallback_path:
        return None

    updates = _vllm_autofix_updates(
        fallback_name=fallback_name,
        fallback_path=fallback_path,
        endpoint=str(getattr(SETTINGS, "VLLM_ENDPOINT", "") or "").strip() or None,
    )
    config_manager.update_config(updates)
    try:
        _apply_vllm_autofix_settings(
            fallback_name=fallback_name,
            fallback_path=fallback_path,
            config_hash=str(updates["LLM_CONFIG_HASH"]),
        )
    except Exception:
        logger.warning("Failed to update SETTINGS during vLLM auto-heal.")

    logger.warning(
        "vLLM runtime auto-heal applied: model='%s' path='%s' (previous model='%s', previous path='%s')",
        fallback_name,
        fallback_path,
        context["active_model"],
        context["configured_model_path"],
    )
    return {
        "healed": True,
        "runtime_id": "vllm",
        "selected_model": fallback_name,
        "selected_path": fallback_path,
        "reason": "invalid_active_model_or_path",
    }


def _build_vllm_runtime_autofix_context(
    *, local_models: list[dict[str, Any]]
) -> dict[str, Any] | None:
    config = config_manager.get_config(mask_secrets=False)
    active_runtime = get_active_llm_runtime()
    active_provider = str(getattr(active_runtime, "provider", "") or "").strip().lower()
    configured_runtime = str(config.get("ACTIVE_LLM_SERVER") or "").strip().lower()
    if active_provider != "vllm" and configured_runtime != "vllm":
        return None

    valid_models = [
        model for model in local_models if _is_vllm_runtime_model_entry(model)
    ]
    if not valid_models:
        return None

    valid_by_name = {
        str(model.get("name") or "").strip().lower(): model for model in valid_models
    }
    active_model = str(
        getattr(active_runtime, "model_name", "") or config.get("LLM_MODEL_NAME") or ""
    ).strip()
    configured_model_path = str(config.get("VLLM_MODEL_PATH") or "").strip()
    active_valid = active_model.lower() in valid_by_name
    path_valid = _looks_like_vllm_runtime_model_path(configured_model_path)
    if active_valid and path_valid:
        return None

    return {
        "config": config,
        "valid_models": valid_models,
        "valid_by_name": valid_by_name,
        "active_model": active_model,
        "configured_model_path": configured_model_path,
    }


def _resolve_vllm_runtime_autofix_fallback(
    *, context: dict[str, Any]
) -> tuple[str, str]:
    fallback_entry = _pick_vllm_fallback_entry(
        valid_models=context["valid_models"],
        valid_by_name=context["valid_by_name"],
        active_model=context["active_model"],
        preferred_model=str(context["config"].get("LAST_MODEL_VLLM") or "").strip(),
    )
    fallback_name = str(fallback_entry.get("name") or "").strip()
    fallback_path = str(fallback_entry.get("path") or "").strip()
    return fallback_name, fallback_path


def _pick_vllm_fallback_entry(
    *,
    valid_models: list[dict[str, Any]],
    valid_by_name: dict[str, dict[str, Any]],
    active_model: str,
    preferred_model: str,
) -> dict[str, Any]:
    preferred = preferred_model.strip().lower()
    fallback_entry = valid_by_name.get(preferred)
    if fallback_entry is not None:
        return fallback_entry
    fallback_entry = valid_by_name.get(active_model.lower())
    if fallback_entry is not None:
        return fallback_entry
    return valid_models[0]


def _vllm_autofix_updates(
    *,
    fallback_name: str,
    fallback_path: str,
    endpoint: str | None,
) -> dict[str, Any]:
    config_hash = compute_llm_config_hash("vllm", endpoint, fallback_name)
    return {
        "LLM_SERVICE_TYPE": "local",
        "ACTIVE_LLM_SERVER": "vllm",
        "LLM_MODEL_NAME": fallback_name,
        "HYBRID_LOCAL_MODEL": fallback_name,
        "LAST_MODEL_VLLM": fallback_name,
        "VLLM_MODEL_PATH": fallback_path,
        "VLLM_SERVED_MODEL_NAME": fallback_name,
        "LLM_CONFIG_HASH": config_hash,
    }


def _apply_vllm_autofix_settings(
    *,
    fallback_name: str,
    fallback_path: str,
    config_hash: str,
) -> None:
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.ACTIVE_LLM_SERVER = "vllm"
    SETTINGS.LLM_MODEL_NAME = fallback_name
    SETTINGS.HYBRID_LOCAL_MODEL = fallback_name
    SETTINGS.LAST_MODEL_VLLM = fallback_name
    SETTINGS.VLLM_MODEL_PATH = fallback_path
    SETTINGS.VLLM_SERVED_MODEL_NAME = fallback_name
    SETTINGS.LLM_CONFIG_HASH = config_hash


def _local_runtime_targets(
    *,
    local_models: dict[str, list[dict[str, Any]]],
    server_status: dict[str, dict[str, Any]],
    active_runtime: Any,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    allowed = _allowed_local_servers()
    installed = _installed_local_servers()
    for runtime_id in ("ollama", "vllm", "onnx"):
        info = server_status.get(runtime_id, {})
        status = str(info.get("status") or "unknown")
        reason = None
        if runtime_id not in allowed:
            status = "disabled"
            reason = "runtime_disabled_by_profile"
        elif runtime_id not in installed:
            status = "offline"
            reason = "runtime_not_installed"
        elif str(info.get("error_message") or "").strip():
            reason = str(info.get("error_message")).strip()
        targets.append(
            _runtime_target_payload(
                runtime_id=runtime_id,
                source_type="local-runtime",
                configured=runtime_id in allowed,
                available=runtime_id in installed and runtime_id in allowed,
                status=status,
                reason=reason,
                models=local_models.get(runtime_id, []),
                active_runtime=active_runtime,
            )
        )
    return targets


async def _cloud_runtime_target(
    *,
    provider: str,
    active_runtime: Any,
) -> dict[str, Any]:
    configured = (
        _check_openai_configured()
        if provider == "openai"
        else _check_google_configured()
    )
    status = "disabled"
    reason: str | None = None
    latency: float | None = None
    if not configured:
        reason = f"{provider.upper()}_API_KEY not configured"
    else:
        probe_status, probe_error, probe_latency = await _probe_cloud_provider(provider)
        status = probe_status
        reason = probe_error
        latency = probe_latency

    models_payload, _source, _live_error = await _catalog_for_cloud_provider(provider)
    active_provider = (active_runtime.provider or "").lower()
    active_model = (active_runtime.model_name or "").strip()
    models = [
        _runtime_model_payload(
            runtime_id=provider,
            model_id=str(item.get("id") or item.get("name") or "").strip(),
            name=str(item.get("id") or item.get("name") or "").strip(),
            provider=provider,
            source_type="cloud-api",
            active=(
                active_provider == provider
                and _normalize_cloud_model_key(active_model)
                in _catalog_model_variants(item)
            ),
            capabilities=list(item.get("capabilities") or []),
        )
        for item in models_payload
        if str(item.get("id") or item.get("name") or "").strip()
    ]
    target = _runtime_target_payload(
        runtime_id=provider,
        source_type="cloud-api",
        configured=configured,
        available=configured and status in {"configured", "reachable", "online"},
        status=status,
        reason=reason,
        models=models,
        active_runtime=active_runtime,
    )
    if latency is not None:
        target["latency_ms"] = latency
    return target


async def _resolve_runtime_options_payload() -> dict[str, Any]:
    active_runtime = get_active_llm_runtime()
    _get_llm_controller_or_503()
    model_manager = system_deps.get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")
    server_status = await _runtime_server_status_snapshot()

    try:
        local_models = await model_manager.list_local_models()
    except Exception:
        logger.warning("Nie udało się pobrać listy modeli lokalnych.")
        local_models = []
    auto_heal = _apply_vllm_runtime_autofix(local_models=local_models)
    if auto_heal:
        active_runtime = get_active_llm_runtime()

    runtime_local_models, local_model_audit_issues = await _local_models_by_runtime(
        model_manager,
        local_models=local_models,
    )
    local_targets = _local_runtime_targets(
        local_models=runtime_local_models,
        server_status=server_status,
        active_runtime=active_runtime,
    )
    cloud_targets = await asyncio.gather(
        _cloud_runtime_target(provider="openai", active_runtime=active_runtime),
        _cloud_runtime_target(provider="google", active_runtime=active_runtime),
    )
    runtime_targets = [*local_targets, *cloud_targets]
    trainable_models = await _load_trainable_model_catalog(
        model_manager,
        local_models=local_models,
    )
    model_catalog = _build_model_catalog(
        runtime_targets=runtime_targets,
        trainable_models=trainable_models,
    )
    adapter_catalog = _build_adapter_catalog(
        model_manager=model_manager,
        trainable_models=trainable_models,
        runtime_targets=runtime_targets,
    )

    active_feedback_resolution = _feedback_loop_resolution_defaults(
        active_runtime.model_name
    )
    feedback_policy = feedback_loop_policy()
    return {
        "status": "success",
        "active": {
            "runtime_id": active_runtime.provider,
            "active_server": active_runtime.provider,
            "active_model": active_runtime.model_name,
            "active_endpoint": active_runtime.endpoint,
            "config_hash": active_runtime.config_hash,
            "source_type": _runtime_source_type(active_runtime.provider),
            "requested_model_alias": active_feedback_resolution[
                "requested_model_alias"
            ],
            "resolved_model_id": active_feedback_resolution["resolved_model_id"],
            "resolution_reason": active_feedback_resolution["resolution_reason"],
        },
        "runtimes": runtime_targets,
        "model_catalog": model_catalog,
        "adapter_catalog": adapter_catalog,
        "selector_flow": ["server", "model", "adapter"],
        "model_audit": {
            "issues": local_model_audit_issues,
            "issues_count": len(local_model_audit_issues),
        },
        "feedback_loop": {
            "requested_alias": FEEDBACK_LOOP_REQUESTED_ALIAS,
            "primary": feedback_policy.primary,
            "fallbacks": list(feedback_policy.fallbacks),
            "active_tier": active_feedback_resolution["feedback_loop_tier"],
            "active_ready": active_feedback_resolution["feedback_loop_ready"],
            "active_resolved_model_id": active_feedback_resolution["resolved_model_id"],
        },
        "auto_heal": auto_heal,
    }


def _normalize_cloud_model_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def _catalog_model_variants(item: dict[str, Any]) -> set[str]:
    variants = {
        _normalize_cloud_model_key(item.get("id")),
        _normalize_cloud_model_key(item.get("name")),
        _normalize_cloud_model_key(item.get("model_alias")),
    }
    return {variant for variant in variants if variant}


async def _resolve_validated_cloud_model(
    *,
    provider_raw: str,
    requested_model: str | None,
) -> str:
    desired_model = (
        requested_model or _default_cloud_model(provider_raw) or ""
    ).strip()
    models_payload, _source, _error = await _catalog_for_cloud_provider(provider_raw)
    desired_key = _normalize_cloud_model_key(desired_model)
    if not desired_key:
        raise HTTPException(status_code=400, detail="Brak modelu dla runtime cloud")
    for item in models_payload:
        variants = _catalog_model_variants(item)
        if desired_key in variants:
            model_id = str(item.get("id") or "").strip()
            return model_id or desired_model
    raise HTTPException(
        status_code=400,
        detail=(
            f"Model '{desired_model}' nie należy do katalogu providera '{provider_raw}'."
        ),
    )


def _activate_cloud_runtime(provider_raw: str, model: str | None) -> dict[str, Any]:
    model_name = model or _default_cloud_model(provider_raw)
    snapshot = _capture_runtime_settings_snapshot()
    try:
        SETTINGS.LLM_SERVICE_TYPE = provider_raw
        SETTINGS.LLM_MODEL_NAME = model_name
        SETTINGS.ACTIVE_LLM_SERVER = provider_raw

        runtime = get_active_llm_runtime()
        config_hash = runtime.config_hash or ""
        SETTINGS.LLM_CONFIG_HASH = config_hash

        config_manager.update_config(
            {
                "LLM_SERVICE_TYPE": provider_raw,
                "LLM_MODEL_NAME": model_name,
                "ACTIVE_LLM_SERVER": provider_raw,
                "LLM_CONFIG_HASH": config_hash,
            }
        )
    except Exception:
        _restore_runtime_settings_snapshot(snapshot)
        raise
    return _runtime_activate_payload(runtime)


def _dedupe_servers_by_name(
    servers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return system_llm_service.dedupe_servers_by_name(servers)


async def _runtime_server_status_snapshot() -> dict[str, dict[str, Any]]:
    llm_controller = _get_llm_controller_or_503()
    service_monitor = system_deps.get_service_monitor()
    allowed_servers = _allowed_local_servers()
    installed_servers = _installed_local_servers()
    visible_servers = allowed_servers & installed_servers

    servers = [
        server
        for server in llm_controller.list_servers()
        if server.get("name") in visible_servers
    ]
    if "onnx" in visible_servers:
        servers = [server for server in servers if server.get("name") != "onnx"]
        servers.append(_build_onnx_server_payload())
    servers = _dedupe_servers_by_name(servers)
    _merge_monitor_status_into_servers(servers, service_monitor)
    await _probe_servers(servers)

    status_map: dict[str, dict[str, Any]] = {}
    for server in servers:
        name = str(server.get("name") or "").strip().lower()
        if not name:
            continue
        status_map[name] = {
            "status": server.get("status"),
            "endpoint": server.get("endpoint"),
            "error_message": server.get("error_message"),
        }
    return status_map


@router.get("/system/llm-servers", responses=LLM_SERVERS_RESPONSES)
async def get_llm_servers():
    """
    Zwraca listę znanych serwerów LLM z informacją o dostępnych akcjach.
    """
    llm_controller = system_deps.get_llm_controller()
    service_monitor = system_deps.get_service_monitor()
    if llm_controller is None:
        raise HTTPException(status_code=503, detail=LLM_CONTROLLER_UNAVAILABLE)

    allowed_servers = _allowed_local_servers()
    installed_servers = _installed_local_servers()
    visible_servers = allowed_servers & installed_servers

    servers = [
        server
        for server in llm_controller.list_servers()
        if server.get("name") in visible_servers
    ]
    if "onnx" in visible_servers:
        # ONNX is in-process; prefer canonical ONNX payload to avoid duplicates
        # when controller list already includes an "onnx" entry.
        servers = [server for server in servers if server.get("name") != "onnx"]
        servers.append(_build_onnx_server_payload())
    servers = _dedupe_servers_by_name(servers)
    _merge_monitor_status_into_servers(servers, service_monitor)
    await _probe_servers(servers)

    return {"status": "success", "servers": servers, "count": len(servers)}


@router.post(
    "/system/llm-servers/{server_name}/{action}",
    responses=LLM_SERVER_CONTROL_RESPONSES,
)
async def control_llm_server(server_name: str, action: str):
    """
    Wykonuje akcję (start/stop/restart) na wskazanym serwerze LLM.
    """
    _ensure_server_allowed(server_name)
    llm_controller = system_deps.get_llm_controller()
    if llm_controller is None:
        raise HTTPException(status_code=503, detail=LLM_CONTROLLER_UNAVAILABLE)

    try:
        result = await llm_controller.run_action(server_name, action)
        response = {
            "status": "success" if result.ok else "error",
            "action": result.action,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
        }
        if result.ok:
            response["message"] = (
                f"Akcja {action} dla {server_name} zakończona sukcesem."
            )
        else:
            response["message"] = (
                f"Akcja {action} dla {server_name} zwróciła kod {result.exit_code}."
            )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("Błąd akcji serwera LLM")
        raise HTTPException(
            status_code=500, detail="Błąd podczas wykonywania komendy"
        ) from exc


@router.get("/system/llm-servers/active")
def get_active_llm_server():
    """Zwraca aktywny runtime LLM oraz zapamiętane modele."""
    runtime = get_active_llm_runtime()
    feedback_resolution = _feedback_loop_resolution_defaults(runtime.model_name)
    config = config_manager.get_config(mask_secrets=False)
    return {
        "status": "success",
        "active_server": runtime.provider,
        "active_endpoint": runtime.endpoint,
        "active_model": runtime.model_name,
        "config_hash": runtime.config_hash,
        "runtime_id": runtime.runtime_id,
        "requested_model_alias": feedback_resolution["requested_model_alias"],
        "resolved_model_id": feedback_resolution["resolved_model_id"],
        "resolution_reason": feedback_resolution["resolution_reason"],
        "last_models": {
            "ollama": config.get("LAST_MODEL_OLLAMA", ""),
            "vllm": config.get("LAST_MODEL_VLLM", ""),
            "onnx": config.get("LAST_MODEL_ONNX", ""),
            "previous_ollama": config.get("PREVIOUS_MODEL_OLLAMA", ""),
            "previous_vllm": config.get("PREVIOUS_MODEL_VLLM", ""),
            "previous_onnx": config.get("PREVIOUS_MODEL_ONNX", ""),
        },
    }


@router.get("/system/llm-runtime/active")
def get_active_llm_runtime_info():
    """Alias z pełnym payloadem aktywnego runtime LLM."""
    runtime = get_active_llm_runtime()
    return {"status": "success", "runtime": runtime.to_payload()}


@router.get(
    "/system/llm-runtime/options",
    responses=LLM_RUNTIME_OPTIONS_RESPONSES,
)
async def get_llm_runtime_options():
    """Spójny kontrakt opcji runtime/model dla paneli Chat i Models."""
    return await _resolve_runtime_options_payload()


@router.post(
    "/system/llm-runtime/active",
    responses=LLM_RUNTIME_ACTIVATE_RESPONSES,
)
async def set_active_llm_runtime(request: LlmRuntimeActivateRequest):
    """
    Przelacza runtime LLM na provider (openai/google/onnx).
    """
    provider_raw = _normalize_runtime_provider(request.provider)
    _assert_runtime_provider_supported(provider_raw)
    if provider_raw == "onnx":
        return _activate_onnx_runtime(request.model)

    _release_onnx_runtime_caches()
    _assert_cloud_provider_requirements(provider_raw)
    validated_model = await _resolve_validated_cloud_model(
        provider_raw=provider_raw,
        requested_model=request.model,
    )
    return _activate_cloud_runtime(provider_raw, validated_model)


def _validate_feedback_alias_request(*, server_name: str, requested_alias: str) -> None:
    if not requested_alias:
        return
    if not is_feedback_loop_alias(requested_alias):
        raise HTTPException(
            status_code=400,
            detail=(
                "Nieobsługiwany model_alias. Dozwolony alias: "
                f"{FEEDBACK_LOOP_REQUESTED_ALIAS}."
            ),
        )
    if server_name != "ollama":
        raise HTTPException(
            status_code=400,
            detail="Alias feedback-loop jest dostępny tylko dla serwera 'ollama'.",
        )


def _activate_onnx_server_switch(*, stop_results: dict[str, Any]) -> dict[str, Any]:
    onnx_client = OnnxLlmClient()
    try:
        onnx_client.ensure_ready()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    config = config_manager.get_config(mask_secrets=False)
    selected_model = config.get("LAST_MODEL_ONNX") or onnx_client.config.model_path
    config_manager.update_config(
        {
            "LLM_SERVICE_TYPE": "onnx",
            "ACTIVE_LLM_SERVER": "onnx",
            "LLM_MODEL_NAME": selected_model,
            "LAST_MODEL_ONNX": selected_model,
        }
    )
    try:
        SETTINGS.LLM_SERVICE_TYPE = "onnx"
        SETTINGS.ACTIVE_LLM_SERVER = "onnx"
        SETTINGS.LLM_MODEL_NAME = selected_model
    except Exception:
        logger.warning("Nie udało się zaktualizować SETTINGS dla ONNX runtime.")
    runtime = get_active_llm_runtime()
    feedback_resolution = _feedback_loop_resolution_defaults(runtime.model_name)
    return {
        "status": "success",
        "active_server": runtime.provider,
        "active_model": runtime.model_name,
        "config_hash": runtime.config_hash,
        "runtime_id": runtime.runtime_id,
        "requested_model_alias": feedback_resolution["requested_model_alias"],
        "resolved_model_id": feedback_resolution["resolved_model_id"],
        "resolution_reason": feedback_resolution["resolution_reason"],
        "start_result": {"ok": True, "mode": "in_process"},
        "stop_results": stop_results,
    }


def _resolve_selected_model_for_switch(
    *,
    request: ActiveLlmServerRequest,
    server_name: str,
    config: dict[str, Any],
    models: list[dict[str, Any]],
) -> tuple[str, str]:
    available_models = set(
        _available_models_for_server(models=models, server_name=server_name)
    )
    requested_model = str(request.model or "").strip()
    requested_last_model_key = _last_model_key_for_server(server_name)
    if requested_model:
        resolved = _validate_requested_model_available(
            requested_model=requested_model,
            available_models=available_models,
            server_name=server_name,
        )
        if resolved:
            return resolved, requested_last_model_key

    try:
        selected_model, last_model_key, _ = _select_model_for_server(
            server_name=server_name,
            config=config,
            models=models,
        )
        return selected_model, last_model_key
    except HTTPException:
        fallback = _fallback_ollama_model_selection(
            request=request,
            server_name=server_name,
            models=models,
        )
        if fallback is None:
            raise
        return fallback


def _last_model_key_for_server(server_name: str) -> str:
    if server_name == "ollama":
        return "LAST_MODEL_OLLAMA"
    if server_name == "onnx":
        return "LAST_MODEL_ONNX"
    return "LAST_MODEL_VLLM"


def _fallback_ollama_model_selection(
    *,
    request: ActiveLlmServerRequest,
    server_name: str,
    models: list[dict[str, Any]],
) -> tuple[str, str] | None:
    explicit_model_request = bool(
        str(request.model or "").strip() or str(request.model_alias or "").strip()
    )
    if server_name != "ollama" or not explicit_model_request:
        return None
    available_ollama = _available_models_for_server(
        models=models, server_name=server_name
    )
    if not available_ollama:
        return None
    return available_ollama[0], "LAST_MODEL_OLLAMA"


def _feedback_alias_resolution_payload(resolution) -> dict[str, Any]:
    return {
        "requested_model_alias": resolution.requested_model_alias,
        "resolved_model_id": resolution.resolved_model_id,
        "resolution_reason": resolution.resolution_reason,
    }


def _resolve_non_alias_requested_model(
    *, requested_model: str, available_models: set[str], selected_model: str
) -> str:
    if not requested_model or is_feedback_loop_alias(requested_model):
        return selected_model
    return (
        _validate_requested_model_available(
            requested_model=requested_model,
            available_models=available_models,
            server_name="ollama",
        )
        or selected_model
    )


async def _resolve_feedback_alias_model(
    *,
    request: ActiveLlmServerRequest,
    requested_alias: str,
    requested_model: str,
    available_models: set[str],
    model_manager: Any,
) -> tuple[str, dict[str, Any]]:
    guard = await _evaluate_feedback_loop_resource_guard(
        model_manager=model_manager,
        model_name=feedback_loop_policy().primary,
    )
    alias_resolution = resolve_feedback_loop_model(
        requested_model=requested_alias or requested_model,
        available_models=available_models,
        prefer_feedback_loop_default=False,
        exact_only=bool(request.exact_only),
        primary_allowed=guard.allowed,
    )
    if not alias_resolution.resolved_model_id:
        status_code = 409 if request.exact_only else 400
        recommendation = f" {guard.recommendation}" if guard.recommendation else ""
        raise HTTPException(
            status_code=status_code,
            detail=(
                "Nie udało się rozwiązać aliasu "
                f"'{FEEDBACK_LOOP_REQUESTED_ALIAS}' do dostępnego modelu."
                f"{recommendation}"
            ),
        )
    logger.info(
        "Feedback-loop alias resolved: requested=%s resolved=%s reason=%s",
        alias_resolution.requested_model_alias,
        alias_resolution.resolved_model_id,
        alias_resolution.resolution_reason,
    )
    return alias_resolution.resolved_model_id, _feedback_alias_resolution_payload(
        alias_resolution
    )


async def _resolve_feedback_guarded_selection(
    *,
    request: ActiveLlmServerRequest,
    model_manager: Any,
    selected_model: str,
    available_models: set[str],
) -> tuple[str, dict[str, Any]]:
    selected_guard = await _evaluate_feedback_loop_resource_guard(
        model_manager=model_manager,
        model_name=selected_model,
    )
    if (
        selected_guard.allowed
        or classify_feedback_loop_tier(selected_model) != "primary"
    ):
        return selected_model, _feedback_loop_resolution_defaults(selected_model)
    if request.exact_only:
        raise HTTPException(
            status_code=409,
            detail=selected_guard.recommendation
            or "Model 7B zablokowany przez guard zasobowy.",
        )
    fallback_resolution = resolve_feedback_loop_model(
        requested_model=FEEDBACK_LOOP_REQUESTED_ALIAS,
        available_models=available_models,
        prefer_feedback_loop_default=True,
        exact_only=False,
        primary_allowed=False,
    )
    if not fallback_resolution.resolved_model_id:
        raise HTTPException(
            status_code=400,
            detail=selected_guard.recommendation
            or "Model 7B zablokowany przez guard zasobowy.",
        )
    logger.warning(
        "Feedback-loop resource guard fallback: primary=%s fallback=%s",
        selected_model,
        fallback_resolution.resolved_model_id,
    )
    return fallback_resolution.resolved_model_id, _feedback_alias_resolution_payload(
        fallback_resolution
    )


async def _resolve_ollama_selected_model(
    *,
    request: ActiveLlmServerRequest,
    requested_alias: str,
    model_manager: Any,
    models: list[dict[str, Any]],
    selected_model: str,
) -> tuple[str, dict[str, Any]]:
    available_models = set(
        _available_models_for_server(models=models, server_name="ollama")
    )
    requested_model = str(request.model or "").strip()
    explicit_alias_request = bool(requested_alias) or is_feedback_loop_alias(
        requested_model
    )

    selected_model = _resolve_non_alias_requested_model(
        requested_model=requested_model,
        available_models=available_models,
        selected_model=selected_model,
    )
    if explicit_alias_request:
        return await _resolve_feedback_alias_model(
            request=request,
            requested_alias=requested_alias,
            requested_model=requested_model,
            available_models=available_models,
            model_manager=model_manager,
        )

    return await _resolve_feedback_guarded_selection(
        request=request,
        model_manager=model_manager,
        selected_model=selected_model,
        available_models=available_models,
    )


@router.post(
    "/system/llm-servers/active",
    responses=LLM_SERVER_ACTIVATE_RESPONSES,
)
async def set_active_llm_server(request: ActiveLlmServerRequest):
    """
    Ustawia aktywny runtime LLM, zatrzymuje inne serwery i aktywuje model.
    """
    _ensure_server_allowed(request.server_name)
    server_name = request.server_name
    requested_alias = str(request.model_alias or "").strip()
    _validate_feedback_alias_request(
        server_name=server_name, requested_alias=requested_alias
    )
    llm_controller = _get_llm_controller_or_503()
    servers = llm_controller.list_servers()
    stop_results = await _stop_other_servers(llm_controller, servers, server_name)
    _assert_stop_results_clean(stop_results)
    if server_name != "onnx":
        _release_onnx_runtime_caches()
    if server_name == "onnx":
        return _activate_onnx_server_switch(stop_results=stop_results)

    _, model_manager, request_tracer = _validate_switch_dependencies()

    if not llm_controller.has_server(server_name):
        raise HTTPException(status_code=404, detail="Nieznany serwer LLM")

    _trace_switch(
        request_tracer,
        request.trace_id,
        "llm_switch_requested",
        f"server={server_name}",
    )

    target = _find_target_server(server_name, servers)

    start_result = await _start_server_if_supported(llm_controller, server_name, target)

    if start_result and start_result.get("ok"):
        health_url = target.get("health_url")
        if health_url and not await _await_server_health(server_name, health_url):
            start_result = {
                "ok": False,
                "error": "Health check timeout - serwer nie odpowiada",
            }

    endpoint = _resolve_local_endpoint(server_name, target)
    _persist_local_runtime_endpoint(server_name, endpoint)

    config = config_manager.get_config(mask_secrets=False)
    models = await model_manager.list_local_models()
    selected_model, last_model_key = _resolve_selected_model_for_switch(
        request=request,
        server_name=server_name,
        config=config,
        models=models,
    )
    feedback_resolution = _feedback_loop_resolution_defaults(selected_model)

    if server_name == "ollama":
        selected_model, feedback_resolution = await _resolve_ollama_selected_model(
            request=request,
            requested_alias=requested_alias,
            model_manager=model_manager,
            models=models,
            selected_model=selected_model,
        )

    old_last_model = config.get(last_model_key) or ""
    updates = _build_model_updates(
        server_name=server_name,
        selected_model=selected_model,
        models=models,
        last_model_key=last_model_key,
        previous_model=old_last_model,
    )
    config_manager.update_config(updates)
    config_hash = _persist_selected_model_settings(
        server_name, selected_model, endpoint
    )

    runtime = get_active_llm_runtime()
    _trace_switch(
        request_tracer,
        request.trace_id,
        "llm_switch_applied",
        f"server={server_name}, model={selected_model}, hash={config_hash}",
    )
    return {
        "status": "success",
        "active_server": infer_local_provider(runtime.endpoint),
        "active_model": selected_model,
        "config_hash": runtime.config_hash,
        "runtime_id": runtime.runtime_id,
        "requested_model_alias": feedback_resolution["requested_model_alias"],
        "resolved_model_id": feedback_resolution["resolved_model_id"],
        "resolution_reason": feedback_resolution["resolution_reason"],
        "start_result": start_result,
        "stop_results": stop_results,
    }
