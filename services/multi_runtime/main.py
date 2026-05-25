"""FastAPI application for Gemma 4 Audio Runtime Service."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlparse
from uuid import uuid4

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
from .engine import (
    InferenceError,
    ModelLoadError,
    MultiRuntimeDaemon,
    MultiRuntimeEngine,
    ReloadSignal,
)
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


_BOOTSTRAP_CONFIG_SNAPSHOT: dict[str, str] = {}


def _bootstrap_config_snapshot_value(name: str) -> str:
    raw = getattr(SETTINGS, name, None)
    if raw is None or str(raw).strip() == "":
        raw = os.environ.get(name)
    if raw is None:
        return ""
    return str(raw).strip()


def _refresh_bootstrap_config_snapshot() -> None:
    tracked_names = (
        "GEMMA4_AUDIO_PROBE_TIMEOUT_SECONDS",
        "GEMMA4_AUDIO_PROBE_MAX_PROMPT_TOKENS",
        "GEMMA4_AUDIO_PROBE_MAX_LAYERS",
        "GEMMA4_AUDIO_PROBE_MAX_TOP_K",
        "GEMMA4_AUDIO_PROBE_HIDDEN_SLICE",
        "GEMMA4_AUDIO_PROBE_ENABLED",
        "VENOM_INTROSPECTION_PROBE_MAX_CONCURRENCY",
        "GEMMA4_AUDIO_PROBE_MAX_CONCURRENCY",
        "VENOM_INTROSPECTION_PROBE_EXECUTOR_WORKERS",
        "GEMMA4_AUDIO_PROBE_EXECUTOR_WORKERS",
        "GEMMA4_AUDIO_PRECISION",
        "GEMMA4_AUDIO_QUANTIZATION_BACKEND",
        "GEMMA4_AUDIO_DEVICE_TARGET",
        "GEMMA4_AUDIO_CACHE_IMPLEMENTATION",
        "GEMMA4_AUDIO_STARTUP_PROFILE",
        "GEMMA4_AUDIO_MODEL_ID",
        "GEMMA4_AUDIO_CACHE_DIR",
        "GEMMA4_AUDIO_DEVICE",
        "GEMMA4_AUDIO_MAX_NEW_TOKENS",
        "GEMMA4_AUDIO_IMAGE_ALLOWED_HOSTS",
        "GEMMA4_AUDIO_IMAGE_INPUT_DIR",
        "GEMMA4_CORS_ORIGINS",
        "GEMMA4_AUDIO_HOST",
        "GEMMA4_AUDIO_PORT",
        "GEMMA4_AUDIO_LOG_PATH",
    )
    for name in tracked_names:
        _BOOTSTRAP_CONFIG_SNAPSHOT[name] = _bootstrap_config_snapshot_value(name)


_refresh_bootstrap_config_snapshot()


def _read_config_str(name: str, default: str = "") -> str:
    text = _BOOTSTRAP_CONFIG_SNAPSHOT.get(name, "")
    if not text:
        text = str(os.environ.get(name, "")).strip()
    return text or default


def _read_config_bool(name: str, default: bool = False) -> bool:
    raw = _read_config_str(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _read_positive_int_config(*names: str, default: int) -> int:
    for name in names:
        raw = _read_config_str(name, "")
        if not raw:
            continue
        try:
            parsed = int(raw)
        except ValueError:
            continue
        if parsed > 0:
            return parsed
    return default


def _read_positive_float_config(*names: str, default: float) -> float:
    for name in names:
        raw = _read_config_str(name, "")
        if not raw:
            continue
        try:
            parsed = float(raw)
        except ValueError:
            continue
        if parsed > 0:
            return parsed
    return default


_PROBE_TIMEOUT_SECONDS = _read_positive_float_config(
    "GEMMA4_AUDIO_PROBE_TIMEOUT_SECONDS",
    default=20.0,
)
_PROBE_MAX_PROMPT_TOKENS = _read_positive_int_config(
    "GEMMA4_AUDIO_PROBE_MAX_PROMPT_TOKENS",
    default=1024,
)
_PROBE_MAX_LAYERS = _read_positive_int_config(
    "GEMMA4_AUDIO_PROBE_MAX_LAYERS",
    default=8,
)
_PROBE_MAX_TOP_K = _read_positive_int_config(
    "GEMMA4_AUDIO_PROBE_MAX_TOP_K",
    default=32,
)
_PROBE_HIDDEN_SLICE = _read_positive_int_config(
    "GEMMA4_AUDIO_PROBE_HIDDEN_SLICE",
    default=16,
)
_PROBE_ENABLED = _read_config_bool("GEMMA4_AUDIO_PROBE_ENABLED", default=False)
_PROBE_MAX_CONCURRENCY = _read_positive_int_config(
    "VENOM_INTROSPECTION_PROBE_MAX_CONCURRENCY",
    "GEMMA4_AUDIO_PROBE_MAX_CONCURRENCY",
    default=2,
)
_PROBE_EXECUTOR_WORKERS = _read_positive_int_config(
    "VENOM_INTROSPECTION_PROBE_EXECUTOR_WORKERS",
    "GEMMA4_AUDIO_PROBE_EXECUTOR_WORKERS",
    default=_PROBE_MAX_CONCURRENCY,
)
_PROBE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_PROBE_EXECUTOR_WORKERS,
    thread_name_prefix="introspection-probe",
)
_PROBE_SEMAPHORE = asyncio.Semaphore(_PROBE_MAX_CONCURRENCY)
# Gradient-based saliency uses model-global grads; serialize that path.
_PROBE_SALIENCY_LOCK = threading.Lock()
_PROBE_SALIENCY_LOCK_WAIT_SECONDS = 0.05


def _estimate_payload_bytes(payload: Any) -> int:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return len(serialized.encode("utf-8"))
    except (TypeError, ValueError):
        return len(str(payload).encode("utf-8"))


# Global daemon instance
_daemon: Optional[MultiRuntimeDaemon] = None
_start_time: float = 0
_warming: bool = False
_startup_error: Optional[str] = None
_lifecycle_lock: asyncio.Lock = asyncio.Lock()
_respond_inflight_requests: int = 0
_INFLIGHT_DRAIN_TIMEOUT_SECONDS = 30.0
_INFLIGHT_DRAIN_POLL_SECONDS = 0.05


async def _increment_respond_inflight() -> None:
    global _respond_inflight_requests
    async with _lifecycle_lock:
        _respond_inflight_requests += 1


async def _decrement_respond_inflight() -> int:
    global _respond_inflight_requests
    async with _lifecycle_lock:
        _respond_inflight_requests = max(0, _respond_inflight_requests - 1)
        return _respond_inflight_requests


async def _drain_inflight_requests(timeout_seconds: float) -> None:
    """Wait until no request uses active engine to avoid unload/generate race."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        async with _lifecycle_lock:
            inflight = _respond_inflight_requests
        if inflight <= 0:
            return
        if time.monotonic() >= deadline:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Cannot apply lifecycle action while inference is in progress "
                    f"(inflight={inflight})"
                ),
            )
        await asyncio.sleep(_INFLIGHT_DRAIN_POLL_SECONDS)


def _resolve_startup_runtime_params() -> dict[str, object]:
    """Resolve startup runtime params with safe defaults for constrained VRAM.

    Priority:
    1. Explicit env overrides (GEMMA4_AUDIO_*).
    2. Optional startup profile override (safe_int4) when explicitly enabled.
    3. Defaults (auto/no quant/auto).
    """
    precision = _read_config_str("GEMMA4_AUDIO_PRECISION", "").lower()
    quantization_backend = _read_config_str(
        "GEMMA4_AUDIO_QUANTIZATION_BACKEND", ""
    ).lower()
    device_target = _read_config_str("GEMMA4_AUDIO_DEVICE_TARGET", "").lower()
    cache_impl = _read_config_str("GEMMA4_AUDIO_CACHE_IMPLEMENTATION", "").lower()

    if not precision:
        precision = "auto"
    if precision not in {"auto", "float16", "bfloat16", "int8", "int4"}:
        precision = "auto"

    if quantization_backend not in {"", "bitsandbytes"}:
        quantization_backend = ""
    if device_target not in {"", "auto", "cpu", "cuda"}:
        device_target = "auto"
    if cache_impl not in {"", "dynamic", "static", "offloaded", "quantized"}:
        cache_impl = ""

    # Optional startup profile: explicitly opt-in, does not redefine "auto".
    startup_profile = _read_config_str(
        "GEMMA4_AUDIO_STARTUP_PROFILE", "default"
    ).lower()
    if (
        startup_profile == "safe_int4"
        and precision == "auto"
        and not quantization_backend
    ):
        try:
            import torch

            cuda_ok = bool(torch.cuda.is_available())
        except Exception:
            cuda_ok = False
        if cuda_ok:
            try:
                import bitsandbytes as _  # noqa: F401

                precision = "int4"
                quantization_backend = "bitsandbytes"
                if device_target in {"", "auto"}:
                    device_target = "cuda"
                logger.info(
                    "Applying startup safe profile: precision=int4, quantization_backend=bitsandbytes, device_target=%s",
                    device_target or "auto",
                )
            except Exception:
                # Keep defaults when bitsandbytes is unavailable.
                pass

    return {
        "precision": precision,
        "quantization_backend": quantization_backend or None,
        "device_target": device_target or "auto",
        "cache_implementation": cache_impl or None,
    }


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
        startup_params = _resolve_startup_runtime_params()
        daemon.update_params(
            precision=str(startup_params["precision"]),
            quantization_backend=startup_params["quantization_backend"],  # type: ignore[arg-type]
            device_target=str(startup_params["device_target"]),
            cache_implementation=startup_params["cache_implementation"],  # type: ignore[arg-type]
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
    model_id = _read_config_str("GEMMA4_AUDIO_MODEL_ID", "google/gemma-4-E2B-it")
    cache_dir = _read_config_str("GEMMA4_AUDIO_CACHE_DIR", "models_cache/hf")
    device = _read_config_str("GEMMA4_AUDIO_DEVICE", "auto")
    max_tokens = _read_positive_int_config("GEMMA4_AUDIO_MAX_NEW_TOKENS", default=128)
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
    _PROBE_EXECUTOR.shutdown(wait=False, cancel_futures=True)


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

    raw_allowed_hosts = _read_config_str("GEMMA4_AUDIO_IMAGE_ALLOWED_HOSTS", "")
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
    raw_allowed_dir = _read_config_str("GEMMA4_AUDIO_IMAGE_INPUT_DIR", "")
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
    allow_origins=[
        origin.strip()
        for origin in _read_config_str(
            "GEMMA4_CORS_ORIGINS", "http://localhost:3000"
        ).split(",")
        if origin.strip()
    ],
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
        active_runtime_config=DaemonParamsInfo(
            **raw.get("active_runtime_config", raw["params"])
        ),
        staged_runtime_config=DaemonParamsInfo(
            **raw.get("staged_runtime_config", raw["params"])
        ),
        quantization_effective=bool(raw.get("quantization_effective", False)),
        quantization_effective_reason=raw.get("quantization_effective_reason"),
        effective_precision_mode=str(raw.get("effective_precision_mode", "unknown")),
        effective_config_reason=raw.get("effective_config_reason"),
        vram_interpretation_hint=raw.get("vram_interpretation_hint"),
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
        daemon_params=p,
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
        "precision",
        "quantization_backend",
        "device_target",
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
    required_mode = result.required_apply_mode
    applied = (
        bool(result.accepted)
        and required_mode == "live"
        and signal == ReloadSignal.NONE
        and not has_hard_restart
    )
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

    update_kwargs = body.model_dump(exclude_unset=True)
    signal = daemon.update_params(**update_kwargs)

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

    await _drain_inflight_requests(_INFLIGHT_DRAIN_TIMEOUT_SECONDS)
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
    await _drain_inflight_requests(_INFLIGHT_DRAIN_TIMEOUT_SECONDS)
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


@app.post("/v1/daemon/unload")
async def daemon_unload() -> dict[str, Any]:
    """Unload all currently loaded models without restarting the daemon process."""
    await _drain_inflight_requests(_INFLIGHT_DRAIN_TIMEOUT_SECONDS)
    async with _lifecycle_lock:
        try:
            daemon = get_daemon()
            await asyncio.to_thread(daemon.unload_all)
        except RuntimeError:
            raise HTTPException(status_code=503, detail="Daemon not initialized")
    return {"status": "ok", "message": "All models unloaded."}


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
    inflight_incremented = False
    try:
        daemon = get_daemon()
        engine = daemon.active_engine()
        await _increment_respond_inflight()
        inflight_incremented = True
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not engine.is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded")
    try:
        (
            request_payload,
            audio_bytes,
            uploaded_image_bytes,
        ) = await _parse_respond_request(request)

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
    finally:
        if inflight_incremented:
            await _decrement_respond_inflight()

    daemon_params = daemon_status["params"]
    generated_text = pipeline_result.generated_text
    duration = pipeline_result.audio_duration_sec
    active_precision = str(daemon_params.get("precision", "auto"))
    post_response_cleanup = "none"

    if request_payload.release_after_response:
        try:
            async with _lifecycle_lock:
                if _respond_inflight_requests > 0:
                    post_response_cleanup = "cleanup_skipped_inflight"
                    logger.info(
                        "Post-response cleanup skipped due to inflight requests",
                        extra={"inflight_requests": _respond_inflight_requests},
                    )
                else:
                    await asyncio.to_thread(daemon.unload_all)
                    post_response_cleanup = "unload_all"
                    logger.info("Post-response cleanup: unload_all completed")
        except Exception:
            post_response_cleanup = "cleanup_failed"
            logger.exception("Post-response cleanup failed")

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
        audio_output_bytes=pipeline_result.audio_bytes,
        audio_output_sample_rate=pipeline_result.audio_sample_rate,
        active_precision=active_precision,
        post_response_cleanup=post_response_cleanup,
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


class IntrospectionProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=1, max_length=50000)
    mode: Literal["hidden", "attention", "logits", "saliency"] = "hidden"
    layer_selection: list[int] = Field(default_factory=list, max_length=64)
    top_k: int = Field(default=8, ge=1, le=256)
    target_output_token_index: int | None = Field(
        default=0,
        ge=0,
        le=255,
        description=(
            "For saliency mode: rank index in next-token logits "
            "(0 = top-1, 1 = top-2, ...), not generated sequence position."
        ),
    )


def _sanitize_probe_layers(
    requested_layers: list[int],
    *,
    available_layers: int,
) -> tuple[list[int], list[str]]:
    limits_hit: list[str] = []
    valid_layers = sorted({layer for layer in requested_layers if layer >= 0})
    if len(valid_layers) > _PROBE_MAX_LAYERS:
        valid_layers = valid_layers[:_PROBE_MAX_LAYERS]
        limits_hit.append("max_layers")
    if available_layers <= 0:
        return [], limits_hit
    filtered_layers = [layer for layer in valid_layers if layer < available_layers]
    if not filtered_layers:
        filtered_layers = [available_layers - 1]
    return filtered_layers, limits_hit


def _tokenize_probe_prompt(
    *,
    tokenizer: Any,
    prompt: str,
) -> tuple[Any, list[str], bool]:
    tokenized = tokenizer(
        prompt,
        return_tensors="pt",
        add_special_tokens=True,
        truncation=True,
        max_length=_PROBE_MAX_PROMPT_TOKENS,
    )
    input_ids = tokenized.get("input_ids")
    if input_ids is None:
        raise RuntimeError("probe_tokenization_failed")
    token_ids = input_ids[0].tolist()
    try:
        token_strings = tokenizer.convert_ids_to_tokens(token_ids)
    except Exception:
        token_strings = [str(token_id) for token_id in token_ids]
    truncated = len(token_ids) >= _PROBE_MAX_PROMPT_TOKENS
    return tokenized, token_strings, truncated


def _extract_attention_top(
    *,
    layer_attention: Any,
    top_k: int,
    token_strings: list[str],
) -> list[dict[str, object]]:
    import torch

    # [batch, heads, query, key] -> mean over heads for the last query token.
    scores = layer_attention[0, :, -1, :].mean(dim=0)
    score_count = int(scores.shape[0])
    k = max(1, min(top_k, score_count, _PROBE_MAX_TOP_K))
    values, indices = torch.topk(scores, k=k)
    entries: list[dict[str, object]] = []
    for value, index in zip(values.tolist(), indices.tolist()):
        token_index = int(index)
        token = token_strings[token_index] if token_index < len(token_strings) else "?"
        entries.append(
            {
                "token_index": token_index,
                "token": token,
                "score": round(float(value), 6),
            }
        )
    return entries


def _extract_hidden_slice(layer_hidden: Any) -> list[float]:
    vector = layer_hidden[0, -1, :].detach().float().cpu().tolist()
    return [round(float(value), 6) for value in vector[:_PROBE_HIDDEN_SLICE]]


def _extract_logits_top(
    *,
    logits_vector: Any,
    top_k: int,
    tokenizer: Any,
) -> list[dict[str, object]]:
    import torch

    score_count = int(logits_vector.shape[0])
    k = max(1, min(top_k, score_count, _PROBE_MAX_TOP_K))
    values, indices = torch.topk(logits_vector, k=k)
    entries: list[dict[str, object]] = []
    for value, index in zip(values.tolist(), indices.tolist()):
        token_index = int(index)
        token = str(token_index)
        try:
            decoded = tokenizer.convert_ids_to_tokens([token_index])
            if isinstance(decoded, list) and decoded:
                token = str(decoded[0])
        except (AttributeError, TypeError, ValueError, KeyError, IndexError):
            # Token decode is best-effort for diagnostics only.
            token = str(token_index)
        entries.append(
            {
                "token_index": token_index,
                "token": token,
                "score": round(float(value), 6),
            }
        )
    return entries


def _resolve_saliency_target_token(
    *,
    logits_vector: Any,
    tokenizer: Any,
    target_output_token_index: int | None,
) -> tuple[int, str, int]:
    import torch

    vocab_size = int(logits_vector.shape[0])
    rank_index = (
        target_output_token_index if isinstance(target_output_token_index, int) else 0
    )
    rank_index = max(0, rank_index)
    top_k = min(vocab_size, max(1, rank_index + 1))
    _values, indices = torch.topk(logits_vector, k=top_k)
    selected_rank_index = rank_index if rank_index < top_k else 0
    token_id = int(indices[selected_rank_index])
    token = str(token_id)
    try:
        decoded = tokenizer.convert_ids_to_tokens([token_id])
        if isinstance(decoded, list) and decoded:
            token = str(decoded[0])
    except (AttributeError, TypeError, ValueError, KeyError, IndexError):
        token = str(token_id)
    return token_id, token, int(selected_rank_index)


def _extract_saliency_token_weights(
    *,
    grad_matrix: Any,
    token_strings: list[str],
    top_k: int,
) -> list[dict[str, object]]:
    import torch

    if grad_matrix is None:
        return []
    scores = torch.linalg.vector_norm(grad_matrix, dim=-1)
    score_count = int(scores.shape[0])
    k = max(1, min(top_k, score_count, _PROBE_MAX_TOP_K))
    values, indices = torch.topk(scores, k=k)
    entries: list[dict[str, object]] = []
    for value, index in zip(values.tolist(), indices.tolist()):
        token_index = int(index)
        token = token_strings[token_index] if token_index < len(token_strings) else "?"
        entries.append(
            {
                "token_index": token_index,
                "token": token,
                "weight": round(float(value), 6),
            }
        )
    return entries


def _acquire_saliency_lock_with_cancel(cancel_event: threading.Event | None) -> bool:
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return False
        if _PROBE_SALIENCY_LOCK.acquire(timeout=_PROBE_SALIENCY_LOCK_WAIT_SECONDS):
            return True


def _run_probe_sync(
    *,
    engine: MultiRuntimeEngine,
    prompt: str,
    mode: Literal["hidden", "attention", "logits", "saliency"],
    layer_selection: list[int],
    top_k: int,
    target_output_token_index: int | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[dict[str, object], list[str], bool]:
    import torch

    model = engine.model
    processor = engine.processor
    if model is None or processor is None:
        raise RuntimeError("model_not_loaded")
    tokenizer = getattr(processor, "tokenizer", None)
    if tokenizer is None:
        raise RuntimeError("tokenizer_unavailable")
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("probe_cancelled")

    tokenized, token_strings, truncated = _tokenize_probe_prompt(
        tokenizer=tokenizer,
        prompt=prompt,
    )
    input_ids = tokenized.get("input_ids")
    attention_mask = tokenized.get("attention_mask")
    if input_ids is None:
        raise RuntimeError("probe_tokenization_failed")
    input_ids = input_ids.to(model.device)
    if attention_mask is not None:
        attention_mask = attention_mask.to(model.device)

    if mode == "saliency":
        if not _acquire_saliency_lock_with_cancel(cancel_event):
            raise RuntimeError("probe_cancelled")
        try:
            embedding_layer = getattr(model, "get_input_embeddings", None)
            if not callable(embedding_layer):
                raise RuntimeError("input_embeddings_unavailable")
            input_embeddings = embedding_layer()(input_ids).detach()
            input_embeddings.requires_grad_(True)
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("probe_cancelled")
            outputs = model(
                inputs_embeds=input_embeddings,
                attention_mask=attention_mask,
                output_hidden_states=False,
                output_attentions=False,
                use_cache=False,
                return_dict=True,
            )
            logits = getattr(outputs, "logits", None)
            if logits is None:
                raise RuntimeError("logits_unavailable")
            next_token_logits = logits[0, -1, :]
            target_token_id, target_token, selected_rank_index = (
                _resolve_saliency_target_token(
                    logits_vector=next_token_logits,
                    tokenizer=tokenizer,
                    target_output_token_index=target_output_token_index,
                )
            )
            target_logit = next_token_logits[target_token_id]
            gradients = torch.autograd.grad(
                target_logit,
                input_embeddings,
                retain_graph=False,
                create_graph=False,
                allow_unused=False,
            )[0]
            if gradients is None:
                raise RuntimeError("saliency_gradients_unavailable")
            token_weights = _extract_saliency_token_weights(
                grad_matrix=gradients[0],
                token_strings=token_strings,
                top_k=top_k,
            )
        finally:
            _PROBE_SALIENCY_LOCK.release()
        probe_payload = {
            "query": prompt,
            "mode": mode,
            "layers": [],
            "target_output_token_index": int(target_output_token_index or 0),
            "target_output_token_rank_index": int(selected_rank_index),
            "target_output_token": target_token,
            "target_selection_mode": "next_token_rank",
            "method": "gradient_norm",
            "token_weights": token_weights,
            "tokenization": {
                "token_count": int(input_ids.shape[-1]),
                "tokens_preview": token_strings[:64],
                "truncated": truncated,
            },
        }
        return probe_payload, [], truncated

    with torch.no_grad():
        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            output_attentions=(mode == "attention"),
            use_cache=False,
            return_dict=True,
        )
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("probe_cancelled")

    hidden_states = getattr(outputs, "hidden_states", None)
    attentions = getattr(outputs, "attentions", None)
    limits_hit: list[str] = []
    layer_count = len(hidden_states) if hidden_states is not None else 0
    selected_layers, layer_limits = _sanitize_probe_layers(
        layer_selection,
        available_layers=layer_count,
    )
    limits_hit.extend(layer_limits)

    layers_payload: list[dict[str, object]] = []
    if mode == "hidden":
        if hidden_states is None:
            raise RuntimeError("hidden_states_unavailable")
        for layer_idx in selected_layers:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("probe_cancelled")
            layers_payload.append(
                {
                    "layer": layer_idx,
                    "hidden_slice": _extract_hidden_slice(hidden_states[layer_idx]),
                }
            )
    elif mode == "attention":
        if attentions is None:
            raise RuntimeError("attentions_unavailable")
        attention_layers, attention_limits = _sanitize_probe_layers(
            layer_selection,
            available_layers=len(attentions),
        )
        limits_hit.extend(attention_limits)
        for layer_idx in attention_layers:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("probe_cancelled")
            layers_payload.append(
                {
                    "layer": layer_idx,
                    "attention_top": _extract_attention_top(
                        layer_attention=attentions[layer_idx],
                        top_k=top_k,
                        token_strings=token_strings,
                    ),
                }
            )
    else:
        if hidden_states is None:
            raise RuntimeError("hidden_states_unavailable")
        lm_head = getattr(model, "lm_head", None)
        if not callable(lm_head):
            raise RuntimeError("lm_head_unavailable")
        for layer_idx in selected_layers:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("probe_cancelled")
            hidden_last = hidden_states[layer_idx][0, -1, :]
            logits_vec = lm_head(hidden_last)
            layers_payload.append(
                {
                    "layer": layer_idx,
                    "logits_top": _extract_logits_top(
                        logits_vector=logits_vec,
                        top_k=top_k,
                        tokenizer=tokenizer,
                    ),
                }
            )

    token_metadata = {
        "token_count": int(input_ids.shape[-1]),
        "tokens_preview": token_strings[:64],
        "truncated": truncated,
    }
    return (
        {
            "query": prompt,
            "mode": mode,
            "layers": layers_payload,
            "tokenization": token_metadata,
        },
        limits_hit,
        truncated,
    )


@app.post("/v1/introspection/probe")
async def introspection_probe(payload: IntrospectionProbeRequest) -> dict[str, object]:
    request_id = str(uuid4())
    started_at = time.perf_counter()

    if not _PROBE_ENABLED:
        return {
            "status": "probe_unavailable",
            "code": "probe_disabled",
            "message": "Probe mode is disabled on this runtime",
            "runtime_label": "multi_runtime",
            "probe": None,
            "diagnostics": {
                "request_id": request_id,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
                "limits_hit": [],
            },
        }

    try:
        daemon = get_daemon()
        engine = daemon.active_engine()
    except RuntimeError as exc:
        return {
            "status": "probe_unavailable",
            "code": "runtime_unavailable",
            "message": str(exc),
            "runtime_label": "multi_runtime",
            "probe": None,
            "diagnostics": {
                "request_id": request_id,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
                "limits_hit": [],
            },
        }

    if not engine.is_loaded():
        return {
            "status": "probe_unavailable",
            "code": "model_not_loaded",
            "message": "Model not loaded",
            "runtime_label": "multi_runtime",
            "probe": None,
            "diagnostics": {
                "request_id": request_id,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
                "limits_hit": [],
            },
        }

    if payload.top_k > _PROBE_MAX_TOP_K:
        raise HTTPException(
            status_code=400,
            detail=f"top_k exceeds runtime limit ({_PROBE_MAX_TOP_K})",
        )

    if len(payload.layer_selection) > _PROBE_MAX_LAYERS:
        raise HTTPException(
            status_code=400,
            detail=f"layer_selection exceeds runtime limit ({_PROBE_MAX_LAYERS})",
        )

    cancel_event = threading.Event()
    probe_task = None
    try:
        async with _PROBE_SEMAPHORE:
            loop = asyncio.get_running_loop()
            probe_task = loop.run_in_executor(
                _PROBE_EXECUTOR,
                partial(
                    _run_probe_sync,
                    engine=engine,
                    prompt=payload.prompt,
                    mode=payload.mode,
                    layer_selection=payload.layer_selection,
                    top_k=payload.top_k,
                    target_output_token_index=payload.target_output_token_index,
                    cancel_event=cancel_event,
                ),
            )
            probe_result, limits_hit, truncated = await asyncio.wait_for(
                probe_task,
                timeout=_PROBE_TIMEOUT_SECONDS,
            )
    except asyncio.TimeoutError:
        cancel_event.set()
        if probe_task is not None:
            probe_task.cancel()
        return {
            "status": "error",
            "code": "probe_timeout",
            "message": "Probe execution timed out",
            "runtime_label": daemon.status().get("target_model", "multi_runtime"),
            "probe": None,
            "diagnostics": {
                "request_id": request_id,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
                "limits_hit": ["timeout"],
            },
        }
    except RuntimeError as exc:
        return {
            "status": "error",
            "code": "probe_failed",
            "message": str(exc),
            "runtime_label": daemon.status().get("target_model", "multi_runtime"),
            "probe": None,
            "diagnostics": {
                "request_id": request_id,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
                "limits_hit": ["runtime_error"],
            },
        }
    except Exception:
        logger.exception("multi_runtime probe failed")
        return {
            "status": "error",
            "code": "probe_failed",
            "message": "Probe execution failed",
            "runtime_label": daemon.status().get("target_model", "multi_runtime"),
            "probe": None,
            "diagnostics": {
                "request_id": request_id,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
                "limits_hit": ["runtime_error"],
            },
        }

    if truncated:
        limits_hit.append("prompt_tokens")

    elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    diagnostics = {
        "request_id": request_id,
        "elapsed_ms": elapsed_ms,
        "limits_hit": sorted(set(limits_hit)),
        "payload_bytes": _estimate_payload_bytes(probe_result),
    }
    return {
        "status": "ok",
        "code": None,
        "message": "Probe completed",
        "runtime_label": daemon.status().get("target_model", "multi_runtime"),
        "probe": probe_result,
        "diagnostics": diagnostics,
    }


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
    await _increment_respond_inflight()
    try:
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
    finally:
        await _decrement_respond_inflight()

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
    host = _read_config_str("GEMMA4_AUDIO_HOST", "127.0.0.1")
    port = _read_positive_int_config("GEMMA4_AUDIO_PORT", default=8014)
    log_file = _read_config_str(
        "GEMMA4_AUDIO_LOG_PATH", "logs/gemma4_audio_service.log"
    )
    run_server(host, port, log_file)
