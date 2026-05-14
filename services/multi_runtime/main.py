"""FastAPI application for Gemma 4 Audio Runtime Service."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import numpy as np
import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from venom_core.api.schemas.multi_runtime_profile import (
    MultiRuntimeProfileResponse,
    MultiRuntimeProfileUpdateRequest,
    MultiRuntimeProfileUpdateResponse,
)
from venom_core.config import SETTINGS
from venom_core.services.multi_runtime_profile_service import (
    build_profile_from_daemon_params,
    build_profile_response,
    validate_profile_update,
)
from venom_core.utils.voice_metadata import build_voice_session_insights

from .audio import audio_from_bytes, audio_from_file, get_audio_duration
from .components import build_component_snapshot
from .engine import InferenceError, ModelLoadError, MultiRuntimeDaemon, ReloadSignal
from .pipeline import MultiRuntimePipeline, PipelineRequestData
from .schemas import (
    AssistantAttachRequest,
    AssistantAttachResponse,
    AudioMetadata,
    Capabilities,
    ComponentListResponse,
    DaemonConfigRequest,
    DaemonConfigResponse,
    DaemonParamsInfo,
    DaemonStatusResponse,
    FallbackResponse,
    GenerationConfig,
    HealthResponse,
    ModelInfo,
    RespondRequest,
    RespondResponse,
    RestartResponse,
    SoftReloadResponse,
    StatusResponse,
    TranscribeResponse,
    VRAMStatus,
)

logger = logging.getLogger(__name__)


# Global daemon instance
_daemon: Optional[MultiRuntimeDaemon] = None
_start_time: float = 0
_warming: bool = False
_startup_error: Optional[str] = None
_lifecycle_lock: asyncio.Lock = asyncio.Lock()


def get_daemon() -> MultiRuntimeDaemon:
    global _daemon
    if _daemon is None:
        raise RuntimeError("Daemon not initialized")
    return _daemon


def get_engine():
    """Return the active inference engine from the daemon (backward compat)."""
    return get_daemon().active_engine()


async def initialize_daemon(
    model_id: str, cache_dir: str, device: str = "auto", max_new_tokens: int = 128
) -> None:
    global _daemon, _warming, _startup_error

    _warming = True
    _startup_error = None
    try:
        logger.info("Initializing Gemma 4 Daemon with target model %s", model_id)
        daemon = MultiRuntimeDaemon(
            cache_dir=cache_dir,
            device=device,
            model_id=model_id,
            max_new_tokens=max_new_tokens,
        )
        daemon.update_params(
            reasoning_summary_enabled=bool(
                getattr(SETTINGS, "GEMMA4_AUDIO_REASONING_SUMMARY_ENABLED", False)
            ),
            emotion_detection_enabled=bool(
                getattr(SETTINGS, "GEMMA4_AUDIO_EMOTION_DETECTION_ENABLED", False)
            ),
            emotion_response_style_enabled=bool(
                getattr(
                    SETTINGS,
                    "GEMMA4_AUDIO_EMOTION_RESPONSE_STYLE_ENABLED",
                    False,
                )
            ),
        )
        # Expose daemon immediately so control endpoints work during warmup.
        _daemon = daemon
        logger.info("Loading target model...")
        await asyncio.to_thread(daemon.load_target)
        logger.info("Daemon ready. Target: %s", daemon._target_id)  # noqa: SLF001
        _warming = False
    except Exception as e:
        logger.error("Failed to initialize daemon: %s", e)
        _startup_error = str(e)
        _warming = False


async def _startup_model_loader() -> None:
    model_id = os.getenv("GEMMA4_AUDIO_MODEL_ID", "google/gemma-4-E2B-it")
    cache_dir = os.getenv("GEMMA4_AUDIO_CACHE_DIR", "models_cache/hf")
    device = os.getenv("GEMMA4_AUDIO_DEVICE", "auto")
    max_tokens = int(os.getenv("GEMMA4_AUDIO_MAX_NEW_TOKENS", "128"))
    await initialize_daemon(model_id, cache_dir, device, max_tokens)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time
    _start_time = time.time()
    asyncio.create_task(_startup_model_loader())
    yield
    if _daemon is not None:
        _daemon.unload_all()
        logger.info("Daemon unloaded")


async def _parse_respond_request(
    request: Request,
) -> tuple[RespondRequest, bytes | None, list[bytes]]:
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_request = form.get("request")
        if not raw_request:
            raise HTTPException(status_code=400, detail="Missing request form field")
        request_payload = RespondRequest.model_validate_json(str(raw_request))
        audio_file = form.get("audio")
        audio_bytes = None
        if isinstance(audio_file, UploadFile):
            audio_bytes = await audio_file.read()
        image_bytes_list: list[bytes] = []
        image_field = form.get("image")
        if isinstance(image_field, UploadFile):
            image_bytes_list.append(await image_field.read())
        for image_item in form.getlist("images"):
            if isinstance(image_item, UploadFile):
                image_bytes_list.append(await image_item.read())
        return request_payload, audio_bytes, image_bytes_list

    payload = await request.json()
    return RespondRequest.model_validate(payload), None, []


def _image_from_data_field(data: str) -> Image.Image:
    raw = data.strip()
    if not raw:
        raise ValueError("Empty image data")
    if raw.startswith("data:"):
        _, encoded = raw.split(",", 1)
        decoded = base64.b64decode(encoded)
    else:
        decoded = base64.b64decode(raw)
    with Image.open(BytesIO(decoded)) as image:
        return image.convert("RGB")


def _is_private_or_local_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "0.0.0.0", "::1"}:
        return True
    if host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _validate_image_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https image URLs are supported")
    if not parsed.hostname:
        raise ValueError("Image URL hostname is required")
    if _is_private_or_local_host(parsed.hostname):
        raise ValueError("Local/private hosts are not allowed for image URLs")

    raw_allowed_hosts = os.getenv("GEMMA4_AUDIO_IMAGE_ALLOWED_HOSTS", "").strip()
    if not raw_allowed_hosts:
        return

    allowed_hosts = {
        item.strip().lower() for item in raw_allowed_hosts.split(",") if item.strip()
    }
    host = parsed.hostname.lower()
    if host not in allowed_hosts:
        raise ValueError("Image URL host is not allowed by policy")


async def _image_from_url(url: str) -> Image.Image:
    _validate_image_url(url)
    timeout = httpx.Timeout(20.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise ValueError(f"Failed to fetch image URL: HTTP {resp.status_code}")
    with Image.open(BytesIO(resp.content)) as image:
        return image.convert("RGB")


def _image_from_path(path: str) -> Image.Image:
    raw_allowed_dir = os.getenv("GEMMA4_AUDIO_IMAGE_INPUT_DIR", "").strip()
    if not raw_allowed_dir:
        raise ValueError("Local image path loading is disabled by policy")
    allowed_root = Path(raw_allowed_dir).resolve()

    file_path = Path(path)
    if not file_path.exists():
        raise ValueError(f"Image path not found: {path}")
    resolved = file_path.resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError("Image path is outside allowed input directory") from exc
    payload = file_path.read_bytes()
    with Image.open(BytesIO(payload)) as image:
        return image.convert("RGB")


app = FastAPI(
    title="Gemma 4 Audio Runtime Service",
    description="Local native audio inference daemon for Gemma 4 models",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("GEMMA4_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health / status
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        daemon = get_daemon()
        if _warming:
            return HealthResponse(
                status="warming", message="Model is warming up, please wait..."
            )
        if not daemon.is_ready():
            return HealthResponse(status="error", message="Model is not loaded")
        return HealthResponse(status="ok", message="Service is healthy and ready")
    except RuntimeError:
        if _startup_error:
            return HealthResponse(
                status="error", message=f"Startup failed: {_startup_error}"
            )
        if _warming:
            return HealthResponse(
                status="warming", message="Service is initializing..."
            )
        return HealthResponse(status="error", message="Service not initialized")


@app.get("/v1/health", response_model=HealthResponse)
async def v1_health() -> HealthResponse:
    return await health()


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    try:
        daemon = get_daemon()
        is_loaded = daemon.is_ready()

        model_info = None
        if is_loaded:
            model_info = ModelInfo(
                model_id=daemon._target_id,  # noqa: SLF001
                instruction_tuned=True,
                supports_text_input=True,
                supports_audio_input=True,
                supports_image_input=True,
                supports_text_output=True,
                runtime_mode="processor_model",
                status="loaded",
            )

        status_val = "warming" if _warming else ("running" if is_loaded else "error")
        component_snapshot = build_component_snapshot(daemon.status())
        return StatusResponse(
            service="multi_runtime",
            status=status_val,
            model_loaded=is_loaded,
            model_info=model_info,
            timestamp_ms=int(time.time() * 1000),
            component_snapshot=component_snapshot,
        )
    except RuntimeError:
        return StatusResponse(
            service="multi_runtime",
            status="warming" if _warming else "error",
            model_loaded=False,
            timestamp_ms=int(time.time() * 1000),
        )


@app.get("/v1/models")
async def list_models():
    try:
        daemon = get_daemon()
        models = [
            {
                "id": daemon._target_id,  # noqa: SLF001
                "object": "model",
                "owned_by": "google",
                "role": "target",
                "instruction_tuned": True,
                "supports_text_input": True,
                "supports_audio_input": True,
                "supports_image_input": True,
                "supports_text_output": True,
                "runtime_mode": "processor_model",
                "status": "loaded" if daemon.is_ready() else "warming",
            }
        ]
        if daemon._assistant_id:  # noqa: SLF001
            models.append(
                {
                    "id": daemon._assistant_id,  # noqa: SLF001
                    "object": "model",
                    "owned_by": "google",
                    "role": "assistant",
                    "status": "loaded"
                    if daemon._assistant_engine and daemon._assistant_engine.is_loaded()
                    else "error",  # noqa: SLF001
                }
            )
        return {"object": "list", "data": models}
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Service not initialized")


# ---------------------------------------------------------------------------
# Daemon control API
# ---------------------------------------------------------------------------


@app.get("/v1/daemon/status", response_model=DaemonStatusResponse)
async def daemon_status() -> DaemonStatusResponse:
    """Full daemon state: active models, params, VRAM, reload requirements."""
    try:
        daemon = get_daemon()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Daemon not initialized")

    raw = daemon.status()
    component_snapshot = build_component_snapshot(raw)
    return DaemonStatusResponse(
        target_model=raw["target_model"],
        assistant_model=raw["assistant_model"],
        mode=raw["mode"],
        target_loaded=raw["target_loaded"],
        assistant_loaded=raw["assistant_loaded"],
        params=DaemonParamsInfo(**raw["params"]),
        vram=VRAMStatus(**raw["vram"]),
        raw_thinking_available=bool(raw.get("raw_thinking_available", False)),
        reasoning_summary_status=str(raw.get("reasoning_summary_status", "disabled")),
        reasoning_summary=raw.get("reasoning_summary"),
        emotion_label=raw.get("emotion_label"),
        emotion_confidence=raw.get("emotion_confidence"),
        emotion_source=raw.get("emotion_source"),
        pending_reload=raw["pending_reload"],
        reload_reason=raw["reload_reason"],
        supports_image_input=bool(raw.get("supports_image_input", True)),
        component_snapshot=component_snapshot,
    )


@app.get("/v1/components", response_model=ComponentListResponse)
async def components() -> ComponentListResponse:
    try:
        daemon = get_daemon()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Daemon not initialized")

    raw = daemon.status()
    return ComponentListResponse(
        runtime_id="multi_runtime",
        timestamp_ms=int(time.time() * 1000),
        components=build_component_snapshot(raw),
    )


@app.get("/v1/daemon/profile", response_model=MultiRuntimeProfileResponse)
async def daemon_get_profile() -> MultiRuntimeProfileResponse:
    """Return the active multi_runtime execution profile."""
    try:
        daemon = get_daemon()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Daemon not initialized")

    raw = daemon.status()
    p = raw["params"]
    profile = build_profile_from_daemon_params(
        target_model=raw["target_model"],
        assistant_model=raw["assistant_model"],
        max_new_tokens=p["max_new_tokens"],
        enable_thinking=p["enable_thinking"],
        image_token_budget=p["image_token_budget"],
        reasoning_summary_enabled=p["reasoning_summary_enabled"],
        emotion_detection_enabled=p["emotion_detection_enabled"],
        emotion_response_style_enabled=p["emotion_response_style_enabled"],
        cache_implementation=p["cache_implementation"],
        execution_mode=p.get("execution_mode", "balanced"),
        image_strategy=p.get("image_strategy", "vlm_only"),
        retrieval_mode=p.get("retrieval_mode", "off"),
        audio_output_mode=p.get("audio_output_mode", "off"),
        assistant_mode=p.get("assistant_mode", "off"),
        economy_mode=p.get("economy_mode", "off"),
    )
    return build_profile_response(profile, daemon_reachable=True)


# Fields accepted by daemon.update_params() (excludes hard-restart-only model fields)
_UPDATE_PARAMS_FIELDS = frozenset(
    {
        "max_new_tokens",
        "enable_thinking",
        "image_token_budget",
        "reasoning_summary_enabled",
        "emotion_detection_enabled",
        "emotion_response_style_enabled",
        "cache_implementation",
        "execution_mode",
        "image_strategy",
        "retrieval_mode",
        "audio_output_mode",
        "assistant_mode",
        "economy_mode",
    }
)

_RELOAD_TO_APPLY_MODE = {
    ReloadSignal.NONE: "live",
    ReloadSignal.SOFT_RELOAD: "soft_reload",
    ReloadSignal.HARD_RESTART: "hard_restart",
}


@app.post("/v1/daemon/profile", response_model=MultiRuntimeProfileUpdateResponse)
async def daemon_update_profile(
    body: MultiRuntimeProfileUpdateRequest,
) -> MultiRuntimeProfileUpdateResponse:
    """Partial update of the multi_runtime execution profile.

    Each accepted field is applied according to its apply_mode:
    - live: applied immediately, no reload needed.
    - soft_reload: staged — call POST /v1/daemon/reload to apply.
    - hard_restart: acknowledged but not applied — process restart required.
    - unsupported: rejected with an explicit reason.
    """
    try:
        daemon = get_daemon()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Daemon not initialized")

    result = validate_profile_update(body)

    updatable = {k: v for k, v in result.accepted.items() if k in _UPDATE_PARAMS_FIELDS}
    signal = ReloadSignal.NONE
    if updatable:
        signal = daemon.update_params(**updatable)

    has_hard_restart = any(
        k in result.accepted for k in ("model_id", "assistant_model_id")
    )
    applied = (
        signal == ReloadSignal.NONE and not has_hard_restart and bool(result.accepted)
    )

    required_mode = result.required_apply_mode
    if has_hard_restart and required_mode != "hard_restart":
        required_mode = "hard_restart"

    return MultiRuntimeProfileUpdateResponse(
        accepted=result.accepted,
        rejected=result.rejected,
        required_apply_mode=required_mode,
        applied=applied,
        message=result.message,
    )


@app.post("/v1/daemon/config", response_model=DaemonConfigResponse)
async def daemon_config(body: DaemonConfigRequest) -> DaemonConfigResponse:
    """Update daemon parameters. Returns the minimum reload action required.

    Transitional endpoint — prefer POST /v1/daemon/profile for new integrations.

    - `none` — change applied live, no reload needed.
    - `soft_reload` — call POST /v1/daemon/reload to apply.
    - `hard_restart` — full process restart required.
    """
    try:
        daemon = get_daemon()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Daemon not initialized")

    signal = daemon.update_params(
        max_new_tokens=body.max_new_tokens,
        enable_thinking=body.enable_thinking,
        image_token_budget=body.image_token_budget,
        reasoning_summary_enabled=body.reasoning_summary_enabled,
        emotion_detection_enabled=body.emotion_detection_enabled,
        emotion_response_style_enabled=body.emotion_response_style_enabled,
        cache_implementation=body.cache_implementation,
        execution_mode=body.execution_mode,
        image_strategy=body.image_strategy,
        retrieval_mode=body.retrieval_mode,
        audio_output_mode=body.audio_output_mode,
        assistant_mode=body.assistant_mode,
        economy_mode=body.economy_mode,
    )

    raw = daemon.status()
    msg_map = {
        ReloadSignal.NONE: "Parameters applied live — no reload required.",
        ReloadSignal.SOFT_RELOAD: "Parameters staged — run POST /v1/daemon/reload to apply.",
        ReloadSignal.HARD_RESTART: "Parameters staged — hard restart required to apply.",
    }
    return DaemonConfigResponse(
        reload_signal=signal.value,
        applied=DaemonParamsInfo(**raw["params"]),
        message=msg_map[signal],
    )


@app.post("/v1/daemon/reload", response_model=SoftReloadResponse)
async def daemon_reload() -> SoftReloadResponse:
    """Soft reload: free VRAM and reload the target model.

    The assistant model is dropped and must be re-attached explicitly.
    """
    try:
        daemon = get_daemon()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Daemon not initialized")

    if _warming:
        raise HTTPException(status_code=409, detail="Cannot reload while warming up")

    if not daemon.is_ready():
        raise HTTPException(status_code=503, detail="Target model is not loaded")

    async with _lifecycle_lock:
        try:
            reason = await asyncio.to_thread(daemon.soft_reload)
        except ModelLoadError as e:
            raise HTTPException(status_code=500, detail=f"Soft reload failed: {e}")

    return SoftReloadResponse(
        reason=reason,
        target_model=daemon._target_id,  # noqa: SLF001
        message="Soft reload complete. VRAM freed and target model reloaded.",
    )


@app.post("/v1/daemon/restart", response_model=RestartResponse)
async def daemon_restart() -> RestartResponse:
    """Hard restart: unload everything and restart the process.

    The OS process manager (Docker, systemd) is expected to restart the service.
    """
    async with _lifecycle_lock:
        try:
            daemon = get_daemon()
            daemon.unload_all()
        except RuntimeError:
            pass  # Not initialized — still proceed with restart

    async def _do_restart():
        await asyncio.sleep(0.2)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    asyncio.create_task(_do_restart())
    return RestartResponse(
        status="restarting",
        message="All models unloaded. Process will restart in ~200ms.",
    )


@app.post("/v1/daemon/assistant/attach", response_model=AssistantAttachResponse)
async def daemon_assistant_attach(
    body: AssistantAttachRequest,
) -> AssistantAttachResponse:
    """Attach an assistant/drafter model alongside the target.

    The assistant is loaded into VRAM in addition to the target.
    Only one assistant at a time — attaching a new one replaces the current.
    """
    try:
        daemon = get_daemon()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Daemon not initialized")

    if not daemon.is_ready():
        raise HTTPException(status_code=503, detail="Target model must be loaded first")

    async with _lifecycle_lock:
        try:
            await asyncio.to_thread(daemon.attach_assistant, body.model_id)
        except ModelLoadError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot attach assistant: {e}",
            )

    return AssistantAttachResponse(
        assistant_model=body.model_id,
        mode=daemon.status()["mode"],
        message=f"Assistant '{body.model_id}' attached successfully.",
    )


@app.post("/v1/daemon/assistant/detach")
async def daemon_assistant_detach() -> dict:
    """Detach and unload the assistant model. VRAM freed immediately."""
    try:
        daemon = get_daemon()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Daemon not initialized")

    async with _lifecycle_lock:
        daemon.detach_assistant()
    return {"mode": "target_only", "message": "Assistant model detached. VRAM freed."}


@app.post("/v1/daemon/fallback", response_model=FallbackResponse)
async def daemon_fallback() -> FallbackResponse:
    """Reset daemon to safe defaults (target-only, default params).

    Returns a reload signal indicating what action is needed to complete the fallback.
    If reload_signal is 'soft_reload', call POST /v1/daemon/reload.
    If reload_signal is 'hard_restart', call POST /v1/daemon/restart.
    """
    try:
        daemon = get_daemon()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Daemon not initialized")

    signal = daemon.fallback()

    msg_map = {
        ReloadSignal.NONE: "Fallback complete — no reload needed.",
        ReloadSignal.SOFT_RELOAD: "Fallback staged — run POST /v1/daemon/reload to complete.",
        ReloadSignal.HARD_RESTART: "Target model changed — run POST /v1/daemon/restart to complete.",
    }
    return FallbackResponse(
        reload_signal=signal.value,
        target_model=daemon._target_id,  # noqa: SLF001
        message=msg_map[signal],
    )


# ---------------------------------------------------------------------------
# Inference endpoints
# ---------------------------------------------------------------------------


@app.post("/v1/respond", response_model=RespondResponse)
async def respond(request: Request) -> RespondResponse:
    try:
        daemon = get_daemon()
        engine = daemon.active_engine()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not engine.is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded")

    request_payload, audio_bytes, uploaded_image_bytes = await _parse_respond_request(
        request
    )

    audio_array = None
    sample_rate = 16000
    text_content = None
    images: list[Image.Image] = []

    if audio_bytes is not None:
        try:
            audio_array, sample_rate = await asyncio.to_thread(
                audio_from_bytes, audio_bytes
            )
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to process uploaded audio: {e}"
            )
    else:
        for message in request_payload.messages:
            for content in message.content:
                if content.type == "audio" and content.path:
                    audio_path = Path(content.path)
                    try:
                        audio_array, sample_rate = await asyncio.to_thread(
                            audio_from_file, audio_path
                        )
                    except Exception as e:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Failed to load audio from {content.path}: {e}",
                        )
                elif content.type == "text" and content.text:
                    text_content = content.text
                elif content.type == "image":
                    try:
                        if content.data:
                            images.append(_image_from_data_field(content.data))
                        elif content.path:
                            images.append(_image_from_path(content.path))
                        elif content.url:
                            images.append(await _image_from_url(content.url))
                    except Exception as e:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Failed to load image input: {e}",
                        )

    for image_bytes in uploaded_image_bytes:
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                images.append(image.convert("RGB"))
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to process uploaded image: {e}"
            )

    if audio_array is None and not text_content and not images:
        raise HTTPException(
            status_code=400, detail="No audio, text, or image content provided"
        )

    daemon_status = daemon.status()

    try:
        pipeline_result = await asyncio.to_thread(
            MultiRuntimePipeline(engine, daemon).execute,
            daemon_status=daemon_status,
            request=PipelineRequestData(
                request_payload=request_payload,
                text_content=text_content,
                audio_array=audio_array,
                sample_rate=sample_rate,
                images=images,
            ),
        )
    except InferenceError as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

    daemon_params = daemon_status["params"]
    generated_text = pipeline_result.generated_text
    duration = pipeline_result.audio_duration_sec

    total_duration_ms = pipeline_result.total_duration_ms
    voice_insights = build_voice_session_insights(
        transcript=text_content or "",
        response=generated_text,
        voice_mode="multi_runtime",
        pipeline_id="multi_runtime_native",
        reasoning_summary_enabled=bool(daemon_params["reasoning_summary_enabled"]),
        emotion_detection_enabled=bool(daemon_params["emotion_detection_enabled"]),
        emotion_response_style_enabled=bool(
            daemon_params["emotion_response_style_enabled"]
        ),
        raw_thinking_available=bool(daemon_status["raw_thinking_available"]),
    )

    return RespondResponse(
        model=engine.model_id,
        task=request_payload.task,
        text=generated_text,
        duration_ms=total_duration_ms,
        audio=(
            AudioMetadata(sample_rate=sample_rate, duration_sec=duration)
            if audio_array is not None
            else None
        ),
        input_modalities=pipeline_result.input_modalities,
        output_modalities=["text"],
        runtime_mode="processor_model",
        capabilities=Capabilities(
            audio_input="verified" if audio_array is not None else "unknown",
            audio_reasoning="verified" if audio_array is not None else "unknown",
            audio_transcription="verified" if audio_array is not None else "unknown",
            image_input="verified" if images else "unknown",
            image_ocr="verified" if images else "unknown",
        ),
        generation_config=GenerationConfig(
            max_new_tokens=request_payload.max_new_tokens,
            temperature=request_payload.temperature,
            top_p=request_payload.top_p,
            do_sample=request_payload.do_sample,
        ),
        raw_thinking_available=bool(voice_insights["raw_thinking_available"]),
        reasoning_summary_status=str(voice_insights["reasoning_summary_status"]),
        reasoning_summary=voice_insights.get("reasoning_summary"),
        emotion_label=voice_insights.get("emotion_label"),
        emotion_confidence=voice_insights.get("emotion_confidence"),
        emotion_source=voice_insights.get("emotion_source"),
        execution_trace=pipeline_result.diagnostics.trace_names(),
        selected_policy=pipeline_result.diagnostics.selected_policy,
        selected_image_strategy=pipeline_result.diagnostics.selected_image_strategy,
        retrieval_used=pipeline_result.diagnostics.retrieval_used,
        retrieval_context_items=pipeline_result.diagnostics.retrieval_context_items,
        retrieval_route=pipeline_result.diagnostics.retrieval_route,
        assistant_used=pipeline_result.diagnostics.assistant_used,
        economy_mode_activated=pipeline_result.diagnostics.economy_mode_activated,
        degradation_reasons=pipeline_result.diagnostics.degradation_reasons,
        component_snapshot=pipeline_result.diagnostics.component_snapshot,
    )


def _extract_text_prompt_from_openai_messages(messages: list[dict]) -> str:
    for message in reversed(messages):
        if str(message.get("role", "")).strip().lower() != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text = str(item.get("text", "")).strip()
                    if text:
                        return text
    return "Hello"


def _extract_image_urls_from_openai_messages(messages: list[dict]) -> list[str]:
    image_urls: list[str] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).strip().lower()
            if item_type != "image_url":
                continue
            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                candidate = str(image_url.get("url", "")).strip()
            else:
                candidate = str(image_url or "").strip()
            if candidate:
                image_urls.append(candidate)
    return image_urls


class ChatCompletionContentPart(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str
    text: str | None = None
    image_url: str | dict[str, str] | None = None


class ChatCompletionMessage(BaseModel):
    role: str
    content: str | list[ChatCompletionContentPart]


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str | None = None
    messages: list[ChatCompletionMessage] = Field(default_factory=list)
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stream: bool = False


@app.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionRequest) -> dict:
    """OpenAI-compatible text chat endpoint for Semantic Kernel connectors."""
    try:
        daemon = get_daemon()
        engine = daemon.active_engine()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not engine.is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded")

    model = str(payload.model or engine.model_id)
    messages = [message.model_dump(mode="python") for message in payload.messages]

    prompt = _extract_text_prompt_from_openai_messages(messages)
    image_urls = _extract_image_urls_from_openai_messages(messages)
    images: list[Image.Image] = []
    for image_url in image_urls:
        try:
            if image_url.startswith("data:"):
                images.append(_image_from_data_field(image_url))
            else:
                images.append(await _image_from_url(image_url))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image_url: {e}")
    max_tokens = int(payload.max_tokens or payload.max_completion_tokens or 128)
    temperature_raw = payload.temperature
    top_p_raw = payload.top_p

    if payload.stream:
        raise HTTPException(
            status_code=400,
            detail="Streaming is not supported by multi_runtime",
        )

    daemon_status = daemon.status()
    daemon_params = daemon_status["params"]
    text, _ = await asyncio.to_thread(
        engine.respond,
        None,
        sample_rate=16000,
        prompt=prompt,
        images=images or None,
        max_new_tokens=max_tokens,
        temperature=float(temperature_raw) if temperature_raw is not None else None,
        top_p=float(top_p_raw) if top_p_raw is not None else None,
        do_sample=bool(temperature_raw is not None or top_p_raw is not None),
        enable_thinking=bool(daemon_params["enable_thinking"]),
        cache_implementation=daemon_params["cache_implementation"],
    )

    now = int(time.time())
    completion_tokens = max(1, len(text) // 4)
    prompt_tokens = max(1, len(prompt) // 4)
    return {
        "id": f"chatcmpl-gemma4-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@app.post("/audio/transcribe", response_model=TranscribeResponse)
async def transcribe(audio: UploadFile = File(...)) -> TranscribeResponse:
    try:
        daemon = get_daemon()
        engine = daemon.active_engine()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not engine.is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded")

    start_time = time.time()

    try:
        file_bytes = await audio.read()
        audio_array, sample_rate = await asyncio.to_thread(audio_from_bytes, file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to process audio file: {e}"
        )

    try:
        text = await asyncio.to_thread(engine.transcribe, audio_array, sample_rate)
    except InferenceError as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    duration_sec = get_audio_duration(audio_array, sample_rate)
    duration_ms = int((time.time() - start_time) * 1000)

    return TranscribeResponse(
        text=text,
        duration_ms=duration_ms,
        audio=AudioMetadata(sample_rate=sample_rate, duration_sec=duration_sec),
    )


@app.post("/warmup")
async def warmup():
    try:
        daemon = get_daemon()
        engine = daemon.active_engine()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not engine.is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded")

    dummy_audio = np.zeros(16000, dtype=np.float32)
    try:
        text, _ = await asyncio.to_thread(
            engine.respond,
            dummy_audio,
            sample_rate=16000,
            prompt="Say hello",
            max_new_tokens=10,
        )
        return {"status": "warmed", "sample_output": text}
    except InferenceError as e:
        raise HTTPException(status_code=500, detail=f"Warmup failed: {e}")


@app.get("/")
async def root():
    return {"service": "Gemma 4 Audio Runtime", "version": "0.2.0", "status": "running"}


# ---------------------------------------------------------------------------
# Server helpers
# ---------------------------------------------------------------------------


def configure_logging(log_file: Optional[str] = None, level: int = logging.INFO):
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def run_server(
    host: str = "127.0.0.1", port: int = 8014, log_file: Optional[str] = None
):
    configure_logging(log_file)
    logger.info("Starting Multi-Runtime Service on %s:%d", host, port)
    uvicorn.run(
        "services.multi_runtime.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    host = os.getenv("GEMMA4_AUDIO_HOST", "127.0.0.1")
    port = int(os.getenv("GEMMA4_AUDIO_PORT", "8014"))
    log_file = os.getenv("GEMMA4_AUDIO_LOG_PATH", "logs/gemma4_audio_service.log")
    run_server(host, port, log_file)
