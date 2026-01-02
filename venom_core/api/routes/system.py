"""Moduł: routes/system - Endpointy API dla systemu (metrics, scheduler, services)."""

import asyncio
import importlib.util
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from venom_core.config import SETTINGS
from venom_core.core import metrics as metrics_module
from venom_core.core.permission_guard import permission_guard
from venom_core.services.config_manager import config_manager
from venom_core.services.runtime_controller import ServiceType, runtime_controller
from venom_core.utils.boot_id import BOOT_ID
from venom_core.utils.llm_runtime import (
    compute_llm_config_hash,
    get_active_llm_runtime,
    infer_local_provider,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

# Dependencies - będą ustawione w main.py
_background_scheduler = None
_service_monitor = None
_state_manager = None  # Nowa zależność dla Cost Guard
_llm_controller = None
_model_manager = None
_request_tracer = None
_hardware_bridge = None


class CostModeRequest(BaseModel):
    """Request do zmiany trybu kosztowego."""

    enable: bool


class CostModeResponse(BaseModel):
    """Response z informacją o trybie kosztowym."""

    enabled: bool
    provider: str


class ActiveLlmServerRequest(BaseModel):
    server_name: str
    trace_id: Optional[UUID] = None


class IoTStatusResponse(BaseModel):
    connected: bool
    cpu_temp: Optional[str] = None
    memory: Optional[str] = None
    disk: Optional[str] = None
    message: Optional[str] = None


def set_dependencies(
    background_scheduler,
    service_monitor,
    state_manager=None,
    llm_controller=None,
    model_manager=None,
    request_tracer=None,
    hardware_bridge=None,
):
    """Ustaw zależności dla routera."""
    global \
        _background_scheduler, \
        _service_monitor, \
        _state_manager, \
        _llm_controller, \
        _model_manager, \
        _request_tracer, \
        _hardware_bridge
    _background_scheduler = background_scheduler
    _service_monitor = service_monitor
    _state_manager = state_manager
    _llm_controller = llm_controller
    _model_manager = model_manager
    _request_tracer = request_tracer
    _hardware_bridge = hardware_bridge


@router.get("/metrics")
async def get_metrics():
    """
    Zwraca metryki systemowe.

    Returns:
        Słownik z metrykami wydajności i użycia

    Raises:
        HTTPException: 503 jeśli MetricsCollector nie jest dostępny
    """
    collector = metrics_module.metrics_collector
    if collector is None:
        raise HTTPException(status_code=503, detail="Metrics collector not initialized")
    return collector.get_metrics()


@router.get("/scheduler/status")
async def get_scheduler_status():
    """
    Zwraca status schedulera zadań w tle.

    Returns:
        Status schedulera

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if _background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        status = _background_scheduler.get_status()
        return {"status": "success", "scheduler": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu schedulera")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/scheduler/jobs")
async def get_scheduler_jobs():
    """
    Zwraca listę zadań w tle.

    Returns:
        Lista zadań

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if _background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        jobs = _background_scheduler.get_jobs()
        return {"status": "success", "jobs": jobs, "count": len(jobs)}
    except Exception as e:
        logger.exception("Błąd podczas pobierania listy zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/scheduler/pause")
async def pause_scheduler():
    """
    Wstrzymuje wszystkie zadania w tle.

    Returns:
        Potwierdzenie wstrzymania

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if _background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        await _background_scheduler.pause_all_jobs()
        return {"status": "success", "message": "All background jobs paused"}
    except Exception as e:
        logger.exception("Błąd podczas wstrzymywania zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/scheduler/resume")
async def resume_scheduler():
    """
    Wznawia wszystkie zadania w tle.

    Returns:
        Potwierdzenie wznowienia

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if _background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        await _background_scheduler.resume_all_jobs()
        return {"status": "success", "message": "All background jobs resumed"}
    except Exception as e:
        logger.exception("Błąd podczas wznawiania zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/system/services")
async def get_all_services():
    """
    Zwraca listę wszystkich monitorowanych usług.

    Returns:
        Lista usług z ich statusami

    Raises:
        HTTPException: 503 jeśli ServiceMonitor nie jest dostępny
    """
    if _service_monitor is None:
        raise HTTPException(status_code=503, detail="ServiceMonitor nie jest dostępny")

    try:
        # Odśwież statusy przed zwróceniem – inaczej pozostają w stanie "unknown".
        await _service_monitor.check_health()
        services = _service_monitor.get_all_services()

        services_data = [
            {
                "name": service.name,
                "type": service.service_type,
                "status": service.status.value,
                "latency_ms": service.latency_ms,
                "last_check": service.last_check,
                "is_critical": service.is_critical,
            }
            for service in services
        ]

        return {"status": "success", "services": services_data, "count": len(services)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy usług")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/system/services/{service_name}")
async def get_service_status(service_name: str):
    """
    Zwraca szczegółowy status konkretnej usługi.

    Args:
        service_name: Nazwa usługi

    Returns:
        Szczegółowy status usługi

    Raises:
        HTTPException: 404 jeśli usługa nie istnieje, 503 jeśli ServiceMonitor nie jest dostępny
    """
    if _service_monitor is None:
        raise HTTPException(status_code=503, detail="ServiceMonitor nie jest dostępny")

    try:
        services = _service_monitor.get_all_services()
        services = [s for s in services if s.name == service_name]

        if not services:
            raise HTTPException(
                status_code=404, detail=f"Usługa '{service_name}' nie znaleziona"
            )

        service = services[0]

        return {
            "status": "success",
            "service": {
                "name": service.name,
                "type": service.service_type,
                "status": service.status.value,
                "latency_ms": service.latency_ms,
                "last_check": service.last_check,
                "is_critical": service.is_critical,
                "error_message": service.error_message,
                "description": service.description,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas sprawdzania statusu usługi {service_name}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/iot/status", response_model=IoTStatusResponse)
async def get_iot_status():
    """
    Zwraca podstawowy status Rider-Pi (IoT bridge).
    """
    if not SETTINGS.ENABLE_IOT_BRIDGE:
        return IoTStatusResponse(
            connected=False,
            message="IoT bridge jest wyłączony w konfiguracji.",
        )

    if _hardware_bridge is None or not getattr(_hardware_bridge, "connected", False):
        return IoTStatusResponse(
            connected=False,
            message="Brak połączenia z Rider-Pi.",
        )

    if getattr(_hardware_bridge, "protocol", None) != "ssh":
        return IoTStatusResponse(
            connected=True,
            message="Połączono z Rider-Pi, telemetria tylko w trybie SSH.",
        )

    cpu_temp = None
    memory = None
    disk = None

    try:
        temp_value = await _hardware_bridge.read_sensor("cpu_temp")
        if temp_value is not None:
            cpu_temp = f"{temp_value:.1f}°C"
    except Exception as exc:
        logger.warning("Nie udało się pobrać temperatury CPU Rider-Pi: %s", exc)

    try:
        mem_result = await _hardware_bridge.execute_command(
            "free -m | awk 'NR==2{printf \"%s/%sMB\", $3, $2}'"
        )
        if mem_result.get("return_code") == 0:
            memory = mem_result.get("stdout", "").strip() or None
    except Exception as exc:
        logger.warning("Nie udało się pobrać pamięci Rider-Pi: %s", exc)

    try:
        disk_result = await _hardware_bridge.execute_command(
            "df -h / | awk 'NR==2{print $3\"/\"$2}'"
        )
        if disk_result.get("return_code") == 0:
            disk = disk_result.get("stdout", "").strip() or None
    except Exception as exc:
        logger.warning("Nie udało się pobrać dysku Rider-Pi: %s", exc)

    message = None
    if not any([cpu_temp, memory, disk]):
        message = "Brak danych telemetrycznych z Rider-Pi."

    return IoTStatusResponse(
        connected=True,
        cpu_temp=cpu_temp,
        memory=memory,
        disk=disk,
        message=message,
    )


@router.get("/system/status")
async def get_system_status():
    """
    Zwraca status systemu wraz z metrykami użycia pamięci RAM i VRAM.

    Returns:
        Status systemu z metrykami pamięci:
        - memory_usage_mb: Użycie pamięci RAM w MB
        - memory_total_mb: Całkowita pamięć RAM w MB
        - memory_usage_percent: Procent użycia RAM
        - vram_usage_mb: Użycie pamięci VRAM w MB (jeśli dostępne GPU)
        - vram_total_mb: Całkowita pamięć VRAM w MB (jeśli dostępne)
        - vram_usage_percent: Procent użycia VRAM (jeśli dostępne)

    Raises:
        HTTPException: 503 jeśli ServiceMonitor nie jest dostępny
    """
    if _service_monitor is None:
        raise HTTPException(status_code=503, detail="ServiceMonitor nie jest dostępny")

    try:
        memory_metrics = _service_monitor.get_memory_metrics()
        system_summary = _service_monitor.get_summary()

        return {
            "status": "success",
            "boot_id": BOOT_ID,
            "system_healthy": system_summary["system_healthy"],
            "memory_usage_mb": memory_metrics["memory_usage_mb"],
            "memory_total_mb": memory_metrics["memory_total_mb"],
            "memory_usage_percent": memory_metrics["memory_usage_percent"],
            "vram_usage_mb": memory_metrics["vram_usage_mb"],
            "vram_total_mb": memory_metrics["vram_total_mb"],
            "vram_usage_percent": memory_metrics["vram_usage_percent"],
        }

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu systemu")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/system/llm-servers")
async def get_llm_servers():
    """
    Zwraca listę znanych serwerów LLM z informacją o dostępnych akcjach.
    """
    if _llm_controller is None:
        raise HTTPException(status_code=503, detail="LLMController nie jest dostępny")

    servers = _llm_controller.list_servers()

    if _service_monitor:
        status_lookup = {
            service.name.lower(): service
            for service in _service_monitor.get_all_services()
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
        # Skip if status already znany
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
        except Exception as exc:  # pragma: no cover - zależne od środowiska
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

    if _llm_controller is None:
        raise HTTPException(status_code=503, detail="LLMController nie jest dostępny")

    try:
        result = await _llm_controller.run_action(server_name, action)
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
    active_provider = runtime.provider
    active_endpoint = runtime.endpoint
    config = config_manager.get_config(mask_secrets=False)
    return {
        "status": "success",
        "active_server": active_provider,
        "active_endpoint": active_endpoint,
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


class LlmRuntimeActivateRequest(BaseModel):
    provider: str = Field(..., description="Docelowy provider runtime (openai/google)")
    model: str | None = Field(default=None, description="Opcjonalny model LLM")


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

    # Zachowanie transakcyjne: zapisz poprzednie wartości dla rollbacku
    old_service_type = SETTINGS.LLM_SERVICE_TYPE
    old_model_name = SETTINGS.LLM_MODEL_NAME
    old_active_server = SETTINGS.ACTIVE_LLM_SERVER
    old_config_hash = SETTINGS.LLM_CONFIG_HASH

    try:
        SETTINGS.LLM_SERVICE_TYPE = provider_raw
        SETTINGS.LLM_MODEL_NAME = model_name
        SETTINGS.ACTIVE_LLM_SERVER = provider_raw

        runtime = get_active_llm_runtime()
        config_hash = runtime.config_hash
        SETTINGS.LLM_CONFIG_HASH = config_hash

        updates = {
            "LLM_SERVICE_TYPE": provider_raw,
            "LLM_MODEL_NAME": model_name,
            "ACTIVE_LLM_SERVER": provider_raw,
            "LLM_CONFIG_HASH": config_hash,
        }
        config_manager.update_config(updates)
    except Exception:
        # Wycofaj zmiany w SETTINGS jeśli aktualizacja konfiguracji się nie powiedzie
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
    if _llm_controller is None:
        raise HTTPException(status_code=503, detail="LLMController nie jest dostępny")
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    server_name = request.server_name
    if not _llm_controller.has_server(server_name):
        raise HTTPException(status_code=404, detail="Nieznany serwer LLM")

    if _request_tracer and request.trace_id:
        _request_tracer.add_step(
            request.trace_id,
            "System",
            "llm_switch_requested",
            status="ok",
            details=f"server={server_name}",
        )

    servers = _llm_controller.list_servers()
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
                result = await _llm_controller.run_action(server["name"], "stop")
                stop_results[server["name"]] = {
                    "ok": result.ok,
                    "exit_code": result.exit_code,
                }
            except Exception as exc:
                stop_results[server["name"]] = {"ok": False, "error": str(exc)}

    start_result = None
    if target.get("supports", {}).get("start"):
        try:
            result = await _llm_controller.run_action(server_name, "start")
            start_result = {"ok": result.ok, "exit_code": result.exit_code}
        except Exception as exc:
            start_result = {"ok": False, "error": str(exc)}

    # Aktualizuj endpoint i tryb lokalny
    endpoint = target.get("endpoint")
    if server_name == "ollama":
        endpoint = "http://localhost:11434/v1"
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

    # Wybierz model dla runtime
    config = config_manager.get_config(mask_secrets=False)
    last_model_key = (
        "LAST_MODEL_OLLAMA" if server_name == "ollama" else "LAST_MODEL_VLLM"
    )
    prev_model_key = (
        "PREVIOUS_MODEL_OLLAMA" if server_name == "ollama" else "PREVIOUS_MODEL_VLLM"
    )
    desired_model = config.get(last_model_key) or config.get("LLM_MODEL_NAME", "")
    previous_model = config.get(prev_model_key) or ""

    models = await _model_manager.list_local_models()
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
    if _request_tracer and request.trace_id:
        _request_tracer.add_step(
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


# ========================================
# Global Cost Guard Endpoints
# ========================================


@router.get("/system/cost-mode", response_model=CostModeResponse)
async def get_cost_mode():
    """
    Zwraca aktualny stan Global Cost Guard.

    Returns:
        Informacja czy tryb płatny jest włączony i jaki provider jest używany

    Raises:
        HTTPException: 503 jeśli StateManager nie jest dostępny
    """
    if _state_manager is None:
        raise HTTPException(
            status_code=503, detail="StateManager nie jest dostępny (Cost Guard)"
        )

    try:
        from venom_core.config import SETTINGS

        enabled = _state_manager.is_paid_mode_enabled()
        provider = (
            "hybrid" if SETTINGS.AI_MODE == "HYBRID" else SETTINGS.AI_MODE.lower()
        )

        return CostModeResponse(enabled=enabled, provider=provider)

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Cost Guard")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/system/cost-mode")
async def set_cost_mode(request: CostModeRequest):
    """
    Ustawia tryb kosztowy (Eco/Pro).

    Args:
        request: Żądanie z flagą enable (True = Pro Mode, False = Eco Mode)

    Returns:
        Potwierdzenie zmiany trybu

    Raises:
        HTTPException: 503 jeśli StateManager nie jest dostępny
    """
    if _state_manager is None:
        raise HTTPException(
            status_code=503, detail="StateManager nie jest dostępny (Cost Guard)"
        )

    try:
        if request.enable:
            _state_manager.enable_paid_mode()
            logger.warning(
                "🔓 Paid Mode ENABLED przez API - użytkownik zaakceptował koszty"
            )
            return {
                "status": "success",
                "message": "Paid Mode (Pro) włączony - dostęp do Cloud API otwarty",
                "enabled": True,
            }
        else:
            _state_manager.disable_paid_mode()
            logger.info("🔒 Paid Mode DISABLED przez API - tryb Eco aktywny")
            return {
                "status": "success",
                "message": "Paid Mode (Pro) wyłączony - tylko lokalne modele",
                "enabled": False,
            }

    except Exception as e:
        logger.exception("Błąd podczas zmiany trybu kosztowego")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# ========================================
# AutonomyGate Endpoints
# ========================================


class AutonomyLevelRequest(BaseModel):
    """Request do zmiany poziomu autonomii."""

    level: int


class AutonomyLevelResponse(BaseModel):
    """Response z informacją o poziomie autonomii."""

    current_level: int
    current_level_name: str
    color: str
    color_name: str
    description: str
    permissions: dict
    risk_level: str


@router.get("/system/autonomy", response_model=AutonomyLevelResponse)
async def get_autonomy_level():
    """
    Zwraca aktualny poziom autonomii AutonomyGate.

    Returns:
        Informacje o aktualnym poziomie autonomii

    Raises:
        HTTPException: 500 jeśli wystąpi błąd
    """
    try:
        current_level = permission_guard.get_current_level()
        level_info = permission_guard.get_level_info(current_level)

        if not level_info:
            raise HTTPException(
                status_code=500, detail="Nie można pobrać informacji o poziomie"
            )

        return AutonomyLevelResponse(
            current_level=current_level,
            current_level_name=level_info.name,
            color=level_info.color,
            color_name=level_info.color_name,
            description=level_info.description,
            permissions=level_info.permissions,
            risk_level=level_info.risk_level,
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania poziomu autonomii")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/system/autonomy")
async def set_autonomy_level(request: AutonomyLevelRequest):
    """
    Ustawia nowy poziom autonomii.

    Args:
        request: Żądanie z nowym poziomem (0, 10, 20, 30, 40)

    Returns:
        Potwierdzenie zmiany poziomu

    Raises:
        HTTPException: 400 jeśli poziom nieprawidłowy, 500 jeśli wystąpi błąd
    """
    try:
        success = permission_guard.set_level(request.level)

        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Nieprawidłowy poziom: {request.level}. Dostępne: 0, 10, 20, 30, 40",
            )

        level_info = permission_guard.get_level_info(request.level)

        if not level_info:
            raise HTTPException(
                status_code=500,
                detail="Nie można pobrać informacji o poziomie po zmianie",
            )

        return {
            "status": "success",
            "message": f"Poziom autonomii zmieniony na {level_info.name}",
            "level": request.level,
            "level_name": level_info.name,
            "color": level_info.color,
            "permissions": level_info.permissions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Błąd podczas zmiany poziomu autonomii")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/system/autonomy/levels")
async def get_all_autonomy_levels():
    """
    Zwraca listę wszystkich dostępnych poziomów autonomii.

    Returns:
        Lista poziomów z ich konfiguracją
    """
    try:
        levels = permission_guard.get_all_levels()

        levels_data = [
            {
                "id": level.id,
                "name": level.name,
                "description": level.description,
                "color": level.color,
                "color_name": level.color_name,
                "permissions": level.permissions,
                "risk_level": level.risk_level,
                "examples": level.examples,
            }
            for level in levels.values()
        ]

        return {"status": "success", "levels": levels_data, "count": len(levels_data)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy poziomów")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# ========================================
# Runtime Controller Endpoints
# ========================================


@router.get("/runtime/status")
async def get_runtime_status():
    """
    Zwraca status wszystkich usług Venom (backend, UI, LLM, Hive, Nexus, background tasks).

    Returns:
        Lista usług z ich statusem, PID, portem, CPU/RAM, actionable
    """
    try:
        services = runtime_controller.get_all_services_status()

        services_data = [
            {
                "name": s.name,
                "service_type": s.service_type.value,
                "status": s.status.value,
                "pid": s.pid,
                "port": s.port,
                "cpu_percent": s.cpu_percent,
                "memory_mb": s.memory_mb,
                "uptime_seconds": s.uptime_seconds,
                "last_log": s.last_log,
                "error_message": s.error_message,
                "actionable": s.actionable,
            }
            for s in services
        ]

        # Dorzuć statusy z ServiceMonitor (bazy/LLM lokalny/Docker/GitHub).
        if _service_monitor:
            try:
                monitor_services = await _service_monitor.check_health()
            except Exception as exc:  # pragma: no cover - fallback
                logger.warning(f"Nie udało się sprawdzić ServiceMonitor: {exc}")
                monitor_services = _service_monitor.get_all_services()

            status_map = {
                "online": "running",
                "offline": "stopped",
                "degraded": "degraded",
                "unknown": "unknown",
            }
            for svc in monitor_services:
                # Pomijamy zewnętrzne API (OpenAI/GitHub) i duplikaty LLM z runtime.
                if svc.service_type == "api":
                    continue
                if svc.name.lower() in {"local llm", "vllm", "ollama"}:
                    continue
                if any(s["name"].lower() == svc.name.lower() for s in services_data):
                    continue
                services_data.append(
                    {
                        "name": svc.name,
                        "service_type": svc.service_type,
                        "status": status_map.get(svc.status.value, "unknown"),
                        "pid": None,
                        "port": None,
                        "cpu_percent": 0.0,
                        "memory_mb": 0.0,
                        "uptime_seconds": None,
                        "last_log": None,
                        "error_message": svc.error_message,
                        "latency_ms": getattr(svc, "latency_ms", 0.0),
                        "endpoint": svc.endpoint,
                        "actionable": False,  # Usługi z ServiceMonitor są tylko monitorowane
                    }
                )

        return {
            "status": "success",
            "services": services_data,
            "count": len(services_data),
        }

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu runtime")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/runtime/profile/{profile_name}")
async def apply_runtime_profile(profile_name: str):
    """
    Aplikuje profil konfiguracji (full, light, llm_off).

    Args:
        profile_name: Nazwa profilu (full, light, llm_off)

    Returns:
        Rezultat aplikacji profilu
    """
    try:
        result = runtime_controller.apply_profile(profile_name)

        return result

    except Exception as e:
        logger.exception(f"Błąd podczas aplikowania profilu {profile_name}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/runtime/{service}/{action}")
async def runtime_service_action(service: str, action: str):
    """
    Wykonuje akcję (start/stop/restart) na wskazanej usłudze.

    Args:
        service: Nazwa usługi (backend, ui, llm_ollama, llm_vllm, hive, nexus, background_tasks)
        action: Akcja (start, stop, restart)

    Returns:
        Rezultat akcji
    """
    try:
        # Walidacja service
        try:
            service_type = ServiceType(service)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Nieznana usługa: {service}. Dostępne: backend, ui, llm_ollama, llm_vllm, hive, nexus, background_tasks",
            )

        # Walidacja action
        if action not in ["start", "stop", "restart"]:
            raise HTTPException(
                status_code=400,
                detail=f"Nieznana akcja: {action}. Dostępne: start, stop, restart",
            )

        # Wykonaj akcję
        if action == "start":
            result = runtime_controller.start_service(service_type)
        elif action == "stop":
            result = runtime_controller.stop_service(service_type)
        elif action == "restart":
            result = runtime_controller.restart_service(service_type)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas wykonywania akcji {action} na {service}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/system/storage")
async def get_storage_snapshot():
    """
    Zwraca snapshot użycia dysku oraz największe katalogi (whitelist).
    """
    try:
        total, used, free = shutil.disk_usage(PROJECT_ROOT)
        entries = [
            {"name": "Modele LLM", "path": "models", "kind": "models"},
            {"name": "Modele cache", "path": "models_cache", "kind": "cache"},
            {"name": "Logi", "path": "logs", "kind": "logs"},
            {"name": "Dane: timelines", "path": "data/timelines", "kind": "data"},
            {"name": "Dane: memory", "path": "data/memory", "kind": "data"},
            {"name": "Dane: audio", "path": "data/audio", "kind": "data"},
            {"name": "Dane: learning", "path": "data/learning", "kind": "data"},
            {
                "name": "Build: web-next/.next",
                "path": "web-next/.next",
                "kind": "build",
            },
            {
                "name": "Deps: web-next/node_modules",
                "path": "web-next/node_modules",
                "kind": "deps",
            },
        ]
        # Zrównoleglenie operacji I/O aby uniknąć blokowania event loop
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(None, _dir_size_bytes, PROJECT_ROOT / entry["path"])
            for entry in entries
        ]
        sizes = await asyncio.gather(*tasks)

        items = [
            {
                "name": entry["name"],
                "path": str(PROJECT_ROOT / entry["path"]),
                "size_bytes": size,
                "kind": entry["kind"],
            }
            for entry, size in zip(entries, sizes)
        ]
        items.sort(key=lambda item: item["size_bytes"], reverse=True)
        return {
            "status": "success",
            "refreshed_at": datetime.now().isoformat(),
            "disk": {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
            },
            "items": items,
        }
    except Exception as e:
        logger.exception("Błąd podczas pobierania snapshotu storage")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/runtime/history")
async def get_runtime_history(limit: int = 50):
    """
    Zwraca historię akcji runtime (start/stop/restart).

    Args:
        limit: Maksymalna liczba wpisów (domyślnie 50)

    Returns:
        Lista akcji z historii
    """
    try:
        history = runtime_controller.get_history(limit=limit)

        return {"status": "success", "history": history, "count": len(history)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania historii runtime")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# ========================================
# Configuration Manager Endpoints
# ========================================


@router.get("/config/runtime")
async def get_runtime_config(mask_secrets: bool = True):
    """
    Zwraca aktualną konfigurację runtime (whitelist parametrów z .env).

    Args:
        mask_secrets: Czy maskować sekrety (domyślnie True)

    Returns:
        Słownik z parametrami konfiguracji
    """
    try:
        config = config_manager.get_config(mask_secrets=mask_secrets)

        return {"status": "success", "config": config}

    except Exception as e:
        logger.exception("Błąd podczas pobierania konfiguracji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


class ConfigUpdateRequest(BaseModel):
    """Request do aktualizacji konfiguracji."""

    updates: dict


@router.post("/config/runtime")
async def update_runtime_config(request: ConfigUpdateRequest):
    """
    Aktualizuje konfigurację runtime (zapis do .env z backupem).

    Args:
        request: Słownik zmian (klucz->wartość)

    Returns:
        Rezultat aktualizacji + lista usług wymagających restartu
    """
    try:
        result = config_manager.update_config(request.updates)

        return result

    except Exception as e:
        logger.exception("Błąd podczas aktualizacji konfiguracji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/config/backups")
async def get_config_backups(limit: int = 20):
    """
    Zwraca listę backupów .env.

    Args:
        limit: Maksymalna liczba backupów (domyślnie 20)

    Returns:
        Lista backupów
    """
    try:
        backups = config_manager.get_backup_list(limit=limit)

        return {"status": "success", "backups": backups, "count": len(backups)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy backupów")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


class RestoreBackupRequest(BaseModel):
    """Request do przywrócenia backupu."""

    backup_filename: str


@router.post("/config/restore")
async def restore_config_backup(request: RestoreBackupRequest):
    """
    Przywraca .env z backupu.

    Args:
        request: Nazwa pliku backupu

    Returns:
        Rezultat przywrócenia
    """
    try:
        result = config_manager.restore_backup(request.backup_filename)

        return result

    except Exception as e:
        logger.exception("Błąd podczas przywracania backupu")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# ----------------------------------------
# Storage monitoring helpers
# ----------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _dir_size_bytes(path: Path) -> int:
    """Suma rozmiarów plików w katalogu (bez podążania za symlinkami)."""
    if not path.exists():
        return 0
    total = 0
    for root, _, files in os.walk(path, followlinks=False):
        for name in files:
            file_path = os.path.join(root, name)
            try:
                if os.path.islink(file_path):
                    continue
                total += os.path.getsize(file_path)
            except OSError:
                continue
    return total
