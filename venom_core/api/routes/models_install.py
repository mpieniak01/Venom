"""Endpointy instalacji i wyboru modeli (local models)."""

import asyncio
import json
from pathlib import Path
from typing import Dict, List

import psutil
from fastapi import APIRouter, BackgroundTasks, HTTPException

from venom_core.api.model_schemas.model_requests import (
    ModelInstallRequest,
    ModelSwitchRequest,
)
from venom_core.api.model_schemas.model_validators import validate_model_name_basic
from venom_core.api.routes.models_dependencies import get_model_manager
from venom_core.api.routes.models_utils import (
    infer_model_provider,
    resolve_model_provider,
    update_last_model,
)
from venom_core.config import SETTINGS
from venom_core.core.model_manager import DEFAULT_MODEL_SIZE_GB
from venom_core.services.config_manager import config_manager
from venom_core.services.feedback_loop_policy import (
    FEEDBACK_LOOP_REQUESTED_ALIAS,
    classify_feedback_loop_tier,
    evaluate_feedback_loop_guard,
    feedback_loop_policy,
    is_feedback_loop_alias,
    resolve_feedback_loop_model,
)
from venom_core.utils.llm_runtime import (
    compute_llm_config_hash,
    get_active_llm_runtime,
    probe_runtime_status,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])
MODEL_MANAGER_UNAVAILABLE_DETAIL = "ModelManager nie jest dostępny"
GENAI_CONFIG_FILENAME = "genai_config.json"


def _parse_duration_to_seconds(raw: str | None, default_seconds: float) -> float:
    value = str(raw or "").strip().lower()
    if not value:
        return default_seconds
    multiplier = 1.0
    if value.endswith("ms"):
        multiplier = 0.001
        value = value[:-2]
    elif value.endswith("s"):
        multiplier = 1.0
        value = value[:-1]
    elif value.endswith("m"):
        multiplier = 60.0
        value = value[:-1]
    elif value.endswith("h"):
        multiplier = 3600.0
        value = value[:-1]
    try:
        parsed = float(value)
    except ValueError:
        return default_seconds
    if parsed <= 0:
        return default_seconds
    return parsed * multiplier


async def _installed_model_names(model_manager) -> set[str]:
    try:
        models = await model_manager.list_local_models()
    except Exception:
        return set()
    names: set[str] = set()
    for model in models:
        name = str(model.get("name") or "").strip()
        if name:
            names.add(name)
    return names


async def _feedback_loop_primary_allowed(model_manager) -> bool:
    usage_reader = getattr(model_manager, "get_usage_metrics", None)
    vram_total_mb: float | None = None
    if callable(usage_reader):
        try:
            usage = await usage_reader()
            raw_vram = usage.get("vram_total_mb")
            if raw_vram is not None:
                vram_total_mb = float(raw_vram)
        except Exception:
            vram_total_mb = None
    try:
        ram_total_gb = round(float(psutil.virtual_memory().total) / float(1024**3), 2)
    except Exception:
        ram_total_gb = None
    guard = evaluate_feedback_loop_guard(
        model_id=feedback_loop_policy().primary,
        settings=SETTINGS,
        ram_total_gb=ram_total_gb,
        vram_total_mb=vram_total_mb,
    )
    return bool(guard.allowed)


async def _pull_with_retry(
    *,
    model_manager,
    model_name: str,
    max_attempts: int,
    timeout_seconds: float,
    backoff_seconds: float,
) -> bool:
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(
                "Install attempt %s/%s for model '%s'",
                attempt,
                max_attempts,
                model_name,
            )
            pull_result = await asyncio.wait_for(
                model_manager.pull_model(model_name),
                timeout=timeout_seconds,
            )
            if pull_result:
                logger.info("Install completed for model '%s'", model_name)
                return True
            logger.warning(
                "Install failed for model '%s' on attempt %s/%s",
                model_name,
                attempt,
                max_attempts,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Install timeout for model '%s' on attempt %s/%s",
                model_name,
                attempt,
                max_attempts,
            )
        except asyncio.CancelledError:
            logger.warning("Install task cancelled for model '%s'", model_name)
            raise
        except Exception as exc:
            logger.warning(
                "Install exception for model '%s' on attempt %s/%s: %s",
                model_name,
                attempt,
                max_attempts,
                exc,
            )
        if attempt < max_attempts and backoff_seconds > 0:
            await asyncio.sleep(backoff_seconds * attempt)
    return False


def _resolve_onnx_runtime_path(model_path: str | None) -> str | None:
    if not model_path:
        return None
    path = Path(model_path)
    if path.is_file() and path.name == GENAI_CONFIG_FILENAME:
        return str(path.parent)
    if path.is_dir():
        direct = path / GENAI_CONFIG_FILENAME
        if direct.exists():
            return str(path)
        matches = sorted(
            path.rglob(GENAI_CONFIG_FILENAME),
            key=lambda p: (len(p.parts), str(p)),
        )
        if matches:
            return str(matches[0].parent)
    return model_path


def _ensure_model_exists(models: list[dict], model_name: str) -> None:
    if any(m["name"] == model_name for m in models):
        return
    raise HTTPException(status_code=404, detail=f"Model {model_name} nie znaleziony")


def _resolve_onnx_runtime_dir(model: dict) -> Path | None:
    raw_path = model.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    resolved = _resolve_onnx_runtime_path(raw_path)
    if not isinstance(resolved, str) or not resolved.strip():
        return None
    path = Path(resolved)
    return path if path.exists() else None


def _read_decoder_filename(config_path: Path) -> tuple[str, str | None]:
    decoder_filename = "model.onnx"
    try:
        payload = json.loads(config_path.read_text("utf-8"))
    except Exception as exc:
        return decoder_filename, f"Nieprawidłowy genai_config.json: {exc}"

    if not isinstance(payload, dict):
        return decoder_filename, None

    model_cfg = payload.get("model")
    if not isinstance(model_cfg, dict):
        return decoder_filename, None

    decoder_cfg = model_cfg.get("decoder")
    if not isinstance(decoder_cfg, dict):
        return decoder_filename, None

    raw_name = decoder_cfg.get("filename")
    if isinstance(raw_name, str) and raw_name.strip():
        decoder_filename = raw_name.strip()
    return decoder_filename, None


def _validate_onnx_chat_compatibility(model: dict) -> tuple[bool, str | None]:
    runtime_dir = _resolve_onnx_runtime_dir(model)
    if runtime_dir is None:
        return False, "Brak ścieżki runtime ONNX lub katalog modelu nie istnieje."
    if not runtime_dir.is_dir():
        return False, "Ścieżka runtime ONNX nie wskazuje katalogu modelu."

    config_path = runtime_dir / GENAI_CONFIG_FILENAME
    if not config_path.exists():
        return False, "Brak genai_config.json w katalogu modelu ONNX."

    decoder_filename, decoder_err = _read_decoder_filename(config_path)
    if decoder_err:
        return False, decoder_err

    decoder_path = runtime_dir / decoder_filename
    if not decoder_path.exists():
        return False, f"Brak pliku dekodera ONNX: {decoder_filename}"
    if not decoder_path.is_file():
        return False, f"Plik dekodera ONNX ma nieprawidłowy typ: {decoder_filename}"
    return True, None


def _annotate_chat_compatibility(models: list[dict]) -> None:
    for model in models:
        provider = str(
            infer_model_provider(model) or model.get("provider") or ""
        ).lower()
        model["provider"] = provider or model.get("provider")

        compatible = True
        reason: str | None = None
        if provider == "onnx":
            compatible, reason = _validate_onnx_chat_compatibility(model)
        elif provider == "vllm":
            raw_path = model.get("path")
            if (
                isinstance(raw_path, str)
                and raw_path
                and raw_path.startswith("ollama://")
            ):
                compatible = False
                reason = "Model vLLM wskazuje nieprawidłową ścieżkę typu ollama://."

        model["chat_compatible"] = compatible
        model["chat_block_reason"] = reason


def _ensure_model_chat_compatible(model: dict) -> None:
    compatible = model.get("chat_compatible")
    if compatible is False:
        detail = model.get("chat_block_reason") or "Model niezgodny z profilem czatu."
        raise HTTPException(status_code=400, detail=str(detail))


def _ensure_runtime_provider_match(
    *,
    model_name: str,
    models: list[dict],
    active_provider: str,
) -> str | None:
    model_provider = resolve_model_provider(models, model_name)
    if active_provider in {"ollama", "vllm"} and model_provider:
        if model_provider != active_provider:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Model {model_name} należy do {model_provider}, "
                    f"ale aktywny runtime to {active_provider}"
                ),
            )
    return model_provider


def _ensure_registered_version(model_manager, model_name: str) -> None:
    if model_name in model_manager.versions:
        return
    model_manager.register_version(version_id=model_name, base_model=model_name)


def _update_runtime_settings(
    *,
    active_provider: str,
    model_name: str,
    model_path: str | None = None,
) -> None:
    try:
        SETTINGS.LLM_MODEL_NAME = model_name
        SETTINGS.HYBRID_LOCAL_MODEL = model_name
        SETTINGS.ACTIVE_LLM_SERVER = active_provider
        if active_provider == "onnx":
            SETTINGS.LLM_SERVICE_TYPE = "onnx"
            if model_path:
                SETTINGS.ONNX_LLM_MODEL_PATH = model_path
        else:
            SETTINGS.LLM_SERVICE_TYPE = "local"
    except Exception:
        logger.warning("Nie udało się zaktualizować SETTINGS w pamięci.")


def _update_config_for_active_model(
    *,
    active_provider: str,
    model_name: str,
    model_path: str | None = None,
) -> None:
    updates = {
        "LLM_MODEL_NAME": model_name,
        "HYBRID_LOCAL_MODEL": model_name,
        "ACTIVE_LLM_SERVER": active_provider,
    }
    if active_provider == "onnx":
        updates["LLM_SERVICE_TYPE"] = "onnx"
        updates["LAST_MODEL_ONNX"] = model_name
        if model_path:
            updates["ONNX_LLM_MODEL_PATH"] = model_path
    else:
        updates["LLM_SERVICE_TYPE"] = "local"
    config_manager.update_config(updates)
    endpoint_for_hash = (
        None if active_provider == "onnx" else SETTINGS.LLM_LOCAL_ENDPOINT
    )
    config_hash = compute_llm_config_hash(
        active_provider, endpoint_for_hash, model_name
    )
    config_manager.update_config({"LLM_CONFIG_HASH": config_hash})
    try:
        SETTINGS.LLM_CONFIG_HASH = config_hash
    except Exception:
        logger.warning("Nie udało się zaktualizować LLM_CONFIG_HASH w SETTINGS.")


def _resolve_provider_bucket(models: List[dict]) -> Dict[str, List[dict]]:
    provider_buckets: Dict[str, List[dict]] = {}

    for model in models:
        provider = infer_model_provider(model) or "vllm"
        model.setdefault("provider", provider)
        provider_buckets.setdefault(provider, []).append(model)

    return provider_buckets


@router.get(
    "/models",
    responses={
        503: {"description": MODEL_MANAGER_UNAVAILABLE_DETAIL},
        500: {"description": "Błąd serwera podczas listowania modeli"},
    },
)
async def list_models():
    """
    Zwraca liste modeli wraz z ich statusem.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail=MODEL_MANAGER_UNAVAILABLE_DETAIL)

    try:
        models = await model_manager.list_local_models()
        runtime_info = get_active_llm_runtime()
        runtime_status, runtime_error = await probe_runtime_status(runtime_info)
        runtime_payload = runtime_info.to_payload()
        runtime_payload["status"] = runtime_status
        if runtime_error:
            runtime_payload["error"] = runtime_error
        runtime_payload["configured_models"] = {
            "local": SETTINGS.LLM_MODEL_NAME,
            "hybrid_local": getattr(SETTINGS, "HYBRID_LOCAL_MODEL", None),
            "cloud": getattr(SETTINGS, "HYBRID_CLOUD_MODEL", None),
        }

        active_names = {
            SETTINGS.LLM_MODEL_NAME,
            getattr(SETTINGS, "HYBRID_LOCAL_MODEL", None),
        }
        active_names = {name for name in active_names if name}
        active_names.update({Path(name).name for name in active_names})

        for model in models:
            candidate_names = {model.get("name")}
            path_value = model.get("path")
            if path_value:
                candidate_names.add(Path(path_value).name)
            if any(name in active_names for name in candidate_names if name):
                model["active"] = True
                model.setdefault("source", runtime_info.provider)
            model_name = str(model.get("name") or "").strip()
            tier = classify_feedback_loop_tier(model_name)
            model["feedback_loop_ready"] = tier in {"primary", "fallback"}
            model["feedback_loop_tier"] = tier

        _annotate_chat_compatibility(models)
        provider_buckets = _resolve_provider_bucket(models)

        return {
            "success": True,
            "models": models,
            "count": len(models),
            "active": runtime_payload,
            "providers": provider_buckets,
        }
    except Exception as exc:
        logger.error(f"Błąd podczas listowania modeli: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.post(
    "/models/install",
    responses={
        503: {"description": MODEL_MANAGER_UNAVAILABLE_DETAIL},
        400: {"description": "Brak miejsca na dysku lub nieprawidłowe dane"},
        500: {"description": "Błąd serwera podczas inicjalizacji instalacji"},
    },
)
async def install_model(
    request: ModelInstallRequest, background_tasks: BackgroundTasks
):
    """
    Uruchamia pobieranie modelu w tle.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail=MODEL_MANAGER_UNAVAILABLE_DETAIL)

    if not model_manager.check_storage_quota(additional_size_gb=DEFAULT_MODEL_SIZE_GB):
        raise HTTPException(
            status_code=400,
            detail=("Brak miejsca na dysku. Usuń nieużywane modele lub zwiększ limit."),
        )

    try:
        requested_name = str(request.name or "").strip()
        installed_names = await _installed_model_names(model_manager)
        requested_alias: str | None = None
        resolution_reason = "exact"
        resolved_model_id = requested_name
        install_candidates: list[str] = []

        if is_feedback_loop_alias(requested_name):
            requested_alias = FEEDBACK_LOOP_REQUESTED_ALIAS
            policy = feedback_loop_policy()
            primary_allowed = await _feedback_loop_primary_allowed(model_manager)
            resolved = resolve_feedback_loop_model(
                requested_model=requested_name,
                available_models=installed_names,
                prefer_feedback_loop_default=False,
                exact_only=False,
                primary_allowed=primary_allowed,
            )
            if (
                resolved.resolved_model_id
                and resolved.resolved_model_id in installed_names
            ):
                logger.info(
                    "Feedback-loop install skipped (already installed): alias=%s resolved=%s reason=%s",
                    resolved.requested_model_alias,
                    resolved.resolved_model_id,
                    resolved.resolution_reason,
                )
                return {
                    "success": True,
                    "already_installed": True,
                    "model_name": resolved.resolved_model_id,
                    "requested_model_alias": resolved.requested_model_alias,
                    "resolved_model_id": resolved.resolved_model_id,
                    "resolution_reason": resolved.resolution_reason,
                    "feedback_loop_ready": True,
                    "feedback_loop_tier": classify_feedback_loop_tier(
                        resolved.resolved_model_id
                    ),
                    "message": (
                        "Model feedback-loop jest już zainstalowany: "
                        f"{resolved.resolved_model_id}"
                    ),
                }

            if primary_allowed:
                install_candidates = list(policy.candidates)
                resolved_model_id = policy.primary
                resolution_reason = "exact"
            else:
                install_candidates = list(policy.fallbacks)
                if not install_candidates:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Brak dostępnych modeli fallback dla feedback-loop przy "
                            "aktywnym ograniczeniu zasobów."
                        ),
                    )
                resolved_model_id = install_candidates[0]
                resolution_reason = "resource_guard"
            logger.info(
                "Feedback-loop install plan: alias=%s candidates=%s reason=%s",
                requested_alias,
                install_candidates,
                resolution_reason,
            )
        else:
            if requested_name in installed_names:
                return {
                    "success": True,
                    "already_installed": True,
                    "model_name": requested_name,
                    "requested_model_alias": None,
                    "resolved_model_id": requested_name,
                    "resolution_reason": "exact",
                    "feedback_loop_ready": classify_feedback_loop_tier(requested_name)
                    in {"primary", "fallback"},
                    "feedback_loop_tier": classify_feedback_loop_tier(requested_name),
                    "message": f"Model {requested_name} jest już zainstalowany",
                }
            install_candidates = [requested_name]
            resolved_model_id = requested_name

        timeout_seconds = _parse_duration_to_seconds(
            getattr(SETTINGS, "OLLAMA_LOAD_TIMEOUT", "10m"),
            default_seconds=600.0,
        )
        max_attempts = max(1, int(getattr(SETTINGS, "OLLAMA_RETRY_MAX_ATTEMPTS", 2)))
        backoff_seconds = max(
            0.0, float(getattr(SETTINGS, "OLLAMA_RETRY_BACKOFF_SECONDS", 0.35))
        )

        async def pull_task():
            logger.info(
                "Install attempt started: requested=%s alias=%s candidates=%s",
                requested_name,
                requested_alias,
                install_candidates,
            )
            for candidate in install_candidates:
                installed_now = await _installed_model_names(model_manager)
                if candidate in installed_now:
                    logger.info(
                        "Install skipped for already installed model: %s", candidate
                    )
                    return
                success = await _pull_with_retry(
                    model_manager=model_manager,
                    model_name=candidate,
                    max_attempts=max_attempts,
                    timeout_seconds=timeout_seconds,
                    backoff_seconds=backoff_seconds,
                )
                if success:
                    logger.info(
                        "Install result success: requested=%s resolved=%s",
                        requested_name,
                        candidate,
                    )
                    return
            logger.error(
                "Install result failure: requested=%s candidates=%s",
                requested_name,
                install_candidates,
            )

        background_tasks.add_task(pull_task)

        return {
            "success": True,
            "message": f"Pobieranie modelu {resolved_model_id} rozpoczęte w tle",
            "model_name": resolved_model_id,
            "requested_model_alias": requested_alias,
            "resolved_model_id": resolved_model_id,
            "resolution_reason": resolution_reason,
            "feedback_loop_ready": classify_feedback_loop_tier(resolved_model_id)
            in {"primary", "fallback"},
            "feedback_loop_tier": classify_feedback_loop_tier(resolved_model_id),
            "install_candidates": install_candidates,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas inicjalizacji pobierania modelu: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.post(
    "/models/switch",
    responses={
        503: {"description": MODEL_MANAGER_UNAVAILABLE_DETAIL},
        404: {"description": "Model nie został znaleziony"},
        400: {"description": "Model niezgodny z aktywnym runtime"},
        500: {"description": "Błąd serwera podczas zmiany modelu"},
    },
)
async def switch_model(request: ModelSwitchRequest):
    """
    Zmienia aktywny model dla okreslonej roli.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail=MODEL_MANAGER_UNAVAILABLE_DETAIL)

    try:
        models = await model_manager.list_local_models()
        _ensure_model_exists(models, request.name)

        runtime_info = get_active_llm_runtime()
        active_provider = runtime_info.provider
        model_provider = _ensure_runtime_provider_match(
            model_name=request.name,
            models=models,
            active_provider=active_provider,
        )
        selected_model = next(
            (m for m in models if m.get("name") == request.name), None
        )
        if selected_model is None:
            raise HTTPException(
                status_code=404, detail=f"Model {request.name} nie znaleziony"
            )
        _annotate_chat_compatibility(models)
        _ensure_model_chat_compatible(selected_model)
        selected_model_path = (
            str(selected_model.get("path"))
            if selected_model and selected_model.get("path")
            else None
        )
        if active_provider == "onnx":
            selected_model_path = _resolve_onnx_runtime_path(selected_model_path)
        _ensure_registered_version(model_manager, request.name)

        success = model_manager.activate_version(request.name)

        if success:
            _update_runtime_settings(
                active_provider=active_provider,
                model_name=request.name,
                model_path=selected_model_path,
            )
            _update_config_for_active_model(
                active_provider=active_provider,
                model_name=request.name,
                model_path=selected_model_path,
            )
            if model_provider:
                update_last_model(model_provider, request.name)
            return {
                "success": True,
                "message": f"Model {request.name} został aktywowany",
                "active_model": request.name,
            }

        raise HTTPException(status_code=500, detail="Nie udało się aktywować modelu")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas zmiany modelu: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.delete(
    "/models/{model_name}",
    responses={
        503: {"description": MODEL_MANAGER_UNAVAILABLE_DETAIL},
        400: {"description": "Nieprawidłowa nazwa modelu lub aktywny model"},
        404: {"description": "Model nie został znaleziony"},
        500: {"description": "Błąd serwera podczas usuwania modelu"},
    },
)
async def delete_model(model_name: str):
    """
    Usuwa model z dysku.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail=MODEL_MANAGER_UNAVAILABLE_DETAIL)

    try:
        validate_model_name_basic(model_name, max_length=100)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        success = await model_manager.delete_model(model_name)
        if success:
            return {"success": True, "message": f"Model {model_name} został usunięty"}

        if model_manager.active_version and model_name == model_manager.active_version:
            raise HTTPException(
                status_code=400,
                detail="Nie można usunąć aktywnego modelu. Najpierw zmień model.",
            )
        raise HTTPException(
            status_code=404,
            detail=f"Model {model_name} nie znaleziony lub nie można usunąć",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas usuwania modelu: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")
