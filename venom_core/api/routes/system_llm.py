"""Moduł: routes/system_llm - Endpointy zarządzania LLM."""

from __future__ import annotations

import asyncio
import importlib.util
import time
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from venom_core.api.routes import system_deps
from venom_core.config import SETTINGS
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


class ActiveLlmServerRequest(BaseModel):
    server_name: str
    trace_id: Optional[UUID] = None


class LlmRuntimeActivateRequest(BaseModel):
    provider: str = Field(..., description="Docelowy provider runtime (openai/google)")
    model: str | None = Field(default=None, description="Opcjonalny model LLM")


@router.get("/system/llm-servers")
async def get_llm_servers():
    """
    Zwraca listę znanych serwerów LLM z informacją o dostępnych akcjach.
    """
    llm_controller = system_deps.get_llm_controller()
    service_monitor = system_deps.get_service_monitor()
    if llm_controller is None:
        raise HTTPException(status_code=503, detail="LLMController nie jest dostępny")

    servers = llm_controller.list_servers()

    if service_monitor:
        status_lookup = {
            service.name.lower(): service
            for service in service_monitor.get_all_services()
        }
        for server in servers:
            status = None
            for key in (server["name"].lower(), server["display_name"].lower()):
                status = status_lookup.get(key)
                if status:
                    break
            if status:
                server["status"] = status.status.value
                server["latency_ms"] = status.latency_ms
                server["last_check"] = status.last_check
                server["error_message"] = status.error_message

    async def probe_server(candidate: dict):
        url = candidate.get("health_url") or candidate.get("endpoint")
        if not url:
            return
        if candidate.get("status") and candidate.get("status") not in {"unknown", None}:
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
            else:
                candidate["status"] = "degraded"
                candidate["error_message"] = f"HTTP {response.status_code}"
        except Exception as exc:  # pragma: no cover
            candidate["status"] = candidate.get("status") or "offline"
            candidate["error_message"] = str(exc)

    probe_tasks = [probe_server(server) for server in servers]
    if probe_tasks:
        await asyncio.gather(*probe_tasks)

    return {"status": "success", "servers": servers, "count": len(servers)}


@router.post("/system/llm-servers/{server_name}/{action}")
async def control_llm_server(server_name: str, action: str):
    """
    Wykonuje akcję (start/stop/restart) na wskazanym serwerze LLM.
    """
    llm_controller = system_deps.get_llm_controller()
    if llm_controller is None:
        raise HTTPException(status_code=503, detail="LLMController nie jest dostępny")

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
async def get_active_llm_server():
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
            "previous_ollama": config.get("PREVIOUS_MODEL_OLLAMA", ""),
            "previous_vllm": config.get("PREVIOUS_MODEL_VLLM", ""),
        },
    }


@router.get("/system/llm-runtime/active")
async def get_active_llm_runtime_info():
    """Alias z pełnym payloadem aktywnego runtime LLM."""
    runtime = get_active_llm_runtime()
    return {"status": "success", "runtime": runtime.to_payload()}


@router.post("/system/llm-runtime/active")
async def set_active_llm_runtime(request: LlmRuntimeActivateRequest):
    """
    Przelacza runtime LLM na cloud provider (openai/google).
    """
    provider_raw = (request.provider or "").lower()
    if provider_raw in ("google-gemini", "gem"):
        provider_raw = "google"
    if provider_raw not in ("openai", "google"):
        raise HTTPException(status_code=400, detail="Nieznany provider runtime")

    if provider_raw == "openai" and not SETTINGS.OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="Brak OPENAI_API_KEY")
    if provider_raw == "google":
        if not SETTINGS.GOOGLE_API_KEY:
            raise HTTPException(status_code=400, detail="Brak GOOGLE_API_KEY")
        if importlib.util.find_spec("google.generativeai") is None:
            raise HTTPException(
                status_code=400,
                detail="Brak biblioteki google-generativeai",
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


@router.post("/system/llm-servers/active")
async def set_active_llm_server(request: ActiveLlmServerRequest):
    """
    Ustawia aktywny runtime LLM, zatrzymuje inne serwery i aktywuje model.
    """
    llm_controller = system_deps.get_llm_controller()
    model_manager = system_deps.get_model_manager()
    request_tracer = system_deps.get_request_tracer()
    if llm_controller is None:
        raise HTTPException(status_code=503, detail="LLMController nie jest dostępny")
    if model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    server_name = request.server_name
    if not llm_controller.has_server(server_name):
        raise HTTPException(status_code=404, detail="Nieznany serwer LLM")

    if request_tracer and request.trace_id:
        request_tracer.add_step(
            request.trace_id,
            "System",
            "llm_switch_requested",
            status="ok",
            details=f"server={server_name}",
        )

    servers = llm_controller.list_servers()
    target = next((s for s in servers if s["name"] == server_name), None)
    if not target:
        raise HTTPException(
            status_code=404, detail="Nie znaleziono konfiguracji serwera"
        )

    stop_results = {}
    for server in servers:
        if server["name"] == server_name:
            continue
        if server.get("supports", {}).get("stop"):
            try:
                result = await llm_controller.run_action(server["name"], "stop")
                stop_results[server["name"]] = {
                    "ok": result.ok,
                    "exit_code": result.exit_code,
                }
            except Exception as exc:
                stop_results[server["name"]] = {"ok": False, "error": str(exc)}

    start_result = None
    if target.get("supports", {}).get("start"):
        try:
            result = await llm_controller.run_action(server_name, "start")
            start_result = {"ok": result.ok, "exit_code": result.exit_code}
        except Exception as exc:
            start_result = {"ok": False, "error": str(exc)}

    if start_result and start_result.get("ok"):
        health_url = target.get("health_url")
        if health_url:
            logger.info(f"Oczekiwanie na start serwera {server_name} ({health_url})...")
            health_ok = False
            async with httpx.AsyncClient(timeout=2.0) as client:
                for attempt in range(60):
                    try:
                        resp = await client.get(health_url)
                        if 200 <= resp.status_code < 300:
                            logger.info(
                                f"Serwer {server_name} gotowy po {attempt * 0.5}s"
                            )
                            health_ok = True
                            break
                    except Exception:
                        # Ignorujemy błędy health check - próbujemy ponownie
                        pass
                    await asyncio.sleep(0.5)

            if not health_ok:
                logger.error(f"Serwer {server_name} nie odpowiedział prawidłowo po 30s")
                start_result = {
                    "ok": False,
                    "error": "Health check timeout - serwer nie odpowiada",
                }

    endpoint = target.get("endpoint")
    if server_name == "ollama":
        endpoint = build_http_url("localhost", 11434, "/v1")
    elif server_name == "vllm":
        endpoint = SETTINGS.VLLM_ENDPOINT
    if endpoint:
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

    config = config_manager.get_config(mask_secrets=False)
    last_model_key = (
        "LAST_MODEL_OLLAMA" if server_name == "ollama" else "LAST_MODEL_VLLM"
    )
    prev_model_key = (
        "PREVIOUS_MODEL_OLLAMA" if server_name == "ollama" else "PREVIOUS_MODEL_VLLM"
    )
    desired_model = config.get(last_model_key) or config.get("LLM_MODEL_NAME", "")
    previous_model = config.get(prev_model_key) or ""

    models = await model_manager.list_local_models()
    available = {
        m["name"] for m in models if m.get("provider") == server_name and m.get("name")
    }

    selected_model = None
    if desired_model in available:
        selected_model = desired_model
    elif previous_model and previous_model in available:
        selected_model = previous_model
        config_manager.update_config({last_model_key: selected_model})
    else:
        raise HTTPException(
            status_code=400,
            detail="Brak modelu na wybranym serwerze (brak fallbacku).",
        )

    old_last_model = config.get(last_model_key) or ""
    updates = {
        "LLM_MODEL_NAME": selected_model,
        "HYBRID_LOCAL_MODEL": selected_model,
        last_model_key: selected_model,
    }
    if server_name == "vllm":
        # Znajdź fizyczną ścieżkę do modelu dla skryptów startu vLLM
        model_info = next((m for m in models if m["name"] == selected_model), None)
        if model_info and model_info.get("path"):
            updates["VLLM_MODEL_PATH"] = model_info["path"]
            logger.info(f"Persisting VLLM_MODEL_PATH: {model_info['path']}")

    if old_last_model and old_last_model != selected_model:
        updates[prev_model_key] = old_last_model
    config_manager.update_config(updates)
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
    except Exception:
        logger.warning("Nie udało się zaktualizować SETTINGS dla hash LLM.")

    runtime = get_active_llm_runtime()
    if request_tracer and request.trace_id:
        request_tracer.add_step(
            request.trace_id,
            "System",
            "llm_switch_applied",
            status="ok",
            details=f"server={server_name}, model={selected_model}, hash={config_hash}",
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
