"""Moduł: routes/system_llm - Endpointy zarządzania LLM."""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import time
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException

from venom_core.api.routes import system_deps
from venom_core.api.schemas.system_llm import (
    ActiveLlmServerRequest,
    LlmRuntimeActivateRequest,
)
from venom_core.config import SETTINGS
from venom_core.execution.onnx_llm_client import OnnxLlmClient
from venom_core.services.config_manager import config_manager
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
LLM_SERVER_ACTIVATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Nieznany serwer LLM lub brak konfiguracji"},
    403: {
        "description": "Wybrany serwer LLM jest niedostępny w aktualnym profilu runtime"
    },
    503: {"description": "LLMController lub ModelManager nie jest dostępny"},
    500: {"description": "Błąd wewnętrzny podczas przełączania aktywnego serwera"},
}


def _runtime_profile_name() -> str:
    profile = (
        str(getattr(SETTINGS, "VENOM_RUNTIME_PROFILE", "full") or "").strip().lower()
    )
    if profile in {"light", "llm_off", "full"}:
        return profile
    return "full"


def _allowed_local_servers() -> set[str]:
    profile = _runtime_profile_name()
    if profile == "light":
        return {"ollama"}
    if profile == "llm_off":
        return set()
    allowed = {"ollama", "vllm"}
    if bool(getattr(SETTINGS, "ONNX_LLM_ENABLED", False)):
        allowed.add("onnx")
    return allowed


def _is_ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def _is_vllm_installed() -> bool:
    if shutil.which("vllm") is not None:
        return True
    return importlib.util.find_spec("vllm") is not None


def _is_onnx_runtime_installed() -> bool:
    return importlib.util.find_spec("onnxruntime_genai") is not None


def _installed_local_servers() -> set[str]:
    installed: set[str] = set()
    if _is_ollama_installed():
        installed.add("ollama")
    if _is_vllm_installed():
        installed.add("vllm")
    if _is_onnx_runtime_installed():
        installed.add("onnx")
    return installed


def _ensure_server_allowed(server_name: str) -> None:
    allowed = _allowed_local_servers()
    if server_name not in allowed:
        profile = _runtime_profile_name()
        raise HTTPException(
            status_code=403,
            detail=(
                f"Serwer LLM '{server_name}' jest niedostępny w profilu '{profile}'. "
                f"Dozwolone: {', '.join(sorted(allowed)) or 'brak'}."
            ),
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


def _merge_monitor_status_into_servers(servers: list[dict], service_monitor) -> None:
    if not service_monitor:
        return
    status_lookup = {
        service.name.lower(): service for service in service_monitor.get_all_services()
    }
    for server in servers:
        status = None
        for key in (server["name"].lower(), server["display_name"].lower()):
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
        prev_model_key = (
            "PREVIOUS_MODEL_OLLAMA"
            if server_name == "ollama"
            else (
                "PREVIOUS_MODEL_VLLM"
                if server_name == "vllm"
                else "PREVIOUS_MODEL_ONNX"
            )
        )
        updates[prev_model_key] = previous_model
    return updates


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


def _dedupe_servers_by_name(
    servers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for server in servers:
        name = str(server.get("name") or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(server)
    return deduped


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
    config = config_manager.get_config(mask_secrets=False)
    return {
        "status": "success",
        "active_server": runtime.provider,
        "active_endpoint": runtime.endpoint,
        "active_model": runtime.model_name,
        "config_hash": runtime.config_hash,
        "runtime_id": runtime.runtime_id,
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


@router.post(
    "/system/llm-runtime/active",
    responses=LLM_RUNTIME_ACTIVATE_RESPONSES,
)
def set_active_llm_runtime(request: LlmRuntimeActivateRequest):
    """
    Przelacza runtime LLM na provider (openai/google/onnx).
    """
    provider_raw = (request.provider or "").lower()
    if provider_raw in ("google-gemini", "gem"):
        provider_raw = "google"
    if provider_raw not in ("openai", "google", "onnx"):
        raise HTTPException(status_code=400, detail="Nieznany provider runtime")

    if provider_raw == "onnx":
        onnx_client = OnnxLlmClient()
        try:
            onnx_client.ensure_ready()
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        model_name = request.model or onnx_client.config.model_path
        old_service_type = SETTINGS.LLM_SERVICE_TYPE
        old_model_name = SETTINGS.LLM_MODEL_NAME
        old_active_server = SETTINGS.ACTIVE_LLM_SERVER
        old_config_hash = SETTINGS.LLM_CONFIG_HASH

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
            SETTINGS.LLM_SERVICE_TYPE = old_service_type
            SETTINGS.LLM_MODEL_NAME = old_model_name
            SETTINGS.ACTIVE_LLM_SERVER = old_active_server
            SETTINGS.LLM_CONFIG_HASH = old_config_hash
            raise

        return {
            "status": "success",
            "active_server": runtime.provider,
            "active_endpoint": runtime.endpoint,
            "active_model": runtime.model_name,
            "config_hash": runtime.config_hash,
            "runtime_id": runtime.runtime_id,
        }

    _release_onnx_runtime_caches()

    if provider_raw == "openai" and not SETTINGS.OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="Brak OPENAI_API_KEY")
    if provider_raw == "google":
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

    default_model = (
        SETTINGS.OPENAI_GPT4O_MODEL
        if provider_raw == "openai"
        else SETTINGS.GOOGLE_GEMINI_PRO_MODEL
    )
    model_name = request.model or default_model

    old_service_type = SETTINGS.LLM_SERVICE_TYPE
    old_model_name = SETTINGS.LLM_MODEL_NAME
    old_active_server = SETTINGS.ACTIVE_LLM_SERVER
    old_config_hash = SETTINGS.LLM_CONFIG_HASH

    try:
        SETTINGS.LLM_SERVICE_TYPE = provider_raw
        SETTINGS.LLM_MODEL_NAME = model_name
        SETTINGS.ACTIVE_LLM_SERVER = provider_raw

        runtime = get_active_llm_runtime()
        config_hash = runtime.config_hash or ""
        SETTINGS.LLM_CONFIG_HASH = config_hash

        updates = {
            "LLM_SERVICE_TYPE": provider_raw,
            "LLM_MODEL_NAME": model_name,
            "ACTIVE_LLM_SERVER": provider_raw,
            "LLM_CONFIG_HASH": config_hash,
        }
        config_manager.update_config(updates)
    except Exception:
        SETTINGS.LLM_SERVICE_TYPE = old_service_type
        SETTINGS.LLM_MODEL_NAME = old_model_name
        SETTINGS.ACTIVE_LLM_SERVER = old_active_server
        SETTINGS.LLM_CONFIG_HASH = old_config_hash
        raise

    return {
        "status": "success",
        "active_server": runtime.provider,
        "active_endpoint": runtime.endpoint,
        "active_model": runtime.model_name,
        "config_hash": runtime.config_hash,
        "runtime_id": runtime.runtime_id,
    }


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
    llm_controller = _get_llm_controller_or_503()
    servers = llm_controller.list_servers()
    stop_results = await _stop_other_servers(llm_controller, servers, server_name)
    _assert_stop_results_clean(stop_results)
    if server_name != "onnx":
        _release_onnx_runtime_caches()
    if server_name == "onnx":
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
        return {
            "status": "success",
            "active_server": runtime.provider,
            "active_model": runtime.model_name,
            "config_hash": runtime.config_hash,
            "runtime_id": runtime.runtime_id,
            "start_result": {"ok": True, "mode": "in_process"},
            "stop_results": stop_results,
        }

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
    selected_model, last_model_key, _ = _select_model_for_server(
        server_name=server_name,
        config=config,
        models=models,
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
        "start_result": start_result,
        "stop_results": stop_results,
    }
