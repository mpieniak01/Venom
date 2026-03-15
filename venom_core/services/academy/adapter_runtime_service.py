"""Adapter runtime deploy/rollback service for Academy."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

from venom_core.services.config_manager import config_manager
from venom_core.services.system_llm_service import previous_model_key_for_server
from venom_core.utils.llm_runtime import compute_llm_config_hash, get_active_llm_runtime
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

from .adapter_metadata_service import (
    ADAPTER_NOT_FOUND_DETAIL,
    _load_adapter_metadata,
    _require_trusted_adapter_base_model,
)
from .trainable_catalog_service import (
    _canonical_runtime_model_id,
    _resolve_local_runtime_id,
)

logger = get_logger(__name__)
MODEL_CONFIG_FILENAME = "config.json"
ONNX_GENAI_CONFIG_FILENAME = "genai_config.json"
UNKNOWN_ERROR_DETAIL = "unknown error"
_MERGE_MEMORY_LIMIT_ENV = "VENOM_ADAPTER_MERGE_MAX_RSS_MB"
_MEMORY_MONITOR_INTERVAL_ENV = "VENOM_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC"
_DEFAULT_MERGE_MEMORY_LIMIT_MB = 14336
_DEFAULT_MEMORY_MONITOR_INTERVAL_SEC = 0.5
_RESOURCE_MONITOR_FILENAME = "resource_monitor.jsonl"

_OLLAMA_GGUF_ADAPTER_CANDIDATES = (
    "Adapter-F16-LoRA.gguf",
    "Adapter-F32-LoRA.gguf",
)
_RUNTIME_ADAPTER_MODEL_PREFIX = "venom-adapter-"
_CANONICAL_TO_OLLAMA_FROM_MODEL: Dict[str, str] = {
    "gemma-2-2b-it": "gemma2:2b",
    "gemma-3-4b-it": "gemma3:4b",
    "gemma-3-1b-it": "gemma3:1b",
    "phi-3-mini-4k-instruct": "phi3:mini",
    "phi-3.5-mini-instruct": "phi3:mini",
    "llama-3.2-1b-instruct": "llama3.2:1b",
    "llama-3.2-3b-instruct": "llama3.2:3b",
    "qwen/qwen2.5-coder-3b-instruct": "qwen2.5-coder:3b",
    "qwen/qwen2.5-coder-7b-instruct": "qwen2.5-coder:7b",
}


def _parse_positive_float(raw: Any, *, default: float) -> float:
    try:
        value = float(str(raw).strip())
        if value > 0:
            return value
    except Exception:
        pass
    return default


def _parse_positive_int(raw: Any, *, default: int) -> int:
    try:
        value = int(str(raw).strip())
        if value > 0:
            return value
    except Exception:
        pass
    return default


def _resolve_merge_memory_limit_mb(*, settings_obj: Any | None = None) -> int:
    settings = settings_obj or _get_settings()
    env_value = str(os.getenv(_MERGE_MEMORY_LIMIT_ENV, "")).strip()
    if env_value:
        return _parse_positive_int(env_value, default=_DEFAULT_MERGE_MEMORY_LIMIT_MB)
    settings_value = getattr(settings, "ACADEMY_ADAPTER_MERGE_MAX_RSS_MB", None)
    if settings_value:
        return _parse_positive_int(
            settings_value, default=_DEFAULT_MERGE_MEMORY_LIMIT_MB
        )
    return _DEFAULT_MERGE_MEMORY_LIMIT_MB


def _resolve_memory_monitor_interval_sec(*, settings_obj: Any | None = None) -> float:
    settings = settings_obj or _get_settings()
    env_value = str(os.getenv(_MEMORY_MONITOR_INTERVAL_ENV, "")).strip()
    if env_value:
        return _parse_positive_float(
            env_value, default=_DEFAULT_MEMORY_MONITOR_INTERVAL_SEC
        )
    settings_value = getattr(
        settings, "ACADEMY_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC", None
    )
    if settings_value:
        return _parse_positive_float(
            settings_value, default=_DEFAULT_MEMORY_MONITOR_INTERVAL_SEC
        )
    return _DEFAULT_MEMORY_MONITOR_INTERVAL_SEC


def _read_process_rss_mb(*, pid: int) -> float:
    try:
        status_file = Path("/proc") / str(pid) / "status"
        lines = status_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines:
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2:
                    kb = float(parts[1])
                    return kb / 1024.0
    except Exception:
        return 0.0
    return 0.0


def _append_resource_monitor_entry(
    *,
    adapter_dir: Path,
    stage: str,
    pid: int,
    peak_rss_mb: float,
    max_rss_mb: int,
    exceeded: bool,
) -> None:
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "stage": stage,
        "pid": pid,
        "peak_rss_mb": round(float(peak_rss_mb), 2),
        "max_rss_mb": int(max_rss_mb),
        "exceeded": bool(exceeded),
    }
    try:
        monitor_file = adapter_dir / _RESOURCE_MONITOR_FILENAME
        with monitor_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("Failed to append adapter resource monitor entry.")


def _run_subprocess_with_memory_guard(
    *,
    cmd: list[str],
    stage: str,
    adapter_dir: Path,
    timeout_sec: int,
    max_rss_mb: int,
    monitor_interval_sec: float,
    env: Dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    state: Dict[str, Any] = {"peak_rss_mb": 0.0, "exceeded": False}
    stop_event = threading.Event()

    def _monitor() -> None:
        while not stop_event.is_set():
            if process.poll() is not None:
                break
            rss_mb = _read_process_rss_mb(pid=process.pid)
            if rss_mb > float(state["peak_rss_mb"]):
                state["peak_rss_mb"] = rss_mb
            if max_rss_mb > 0 and rss_mb > float(max_rss_mb):
                state["exceeded"] = True
                try:
                    process.send_signal(signal.SIGTERM)
                except Exception:
                    pass
                break
            time.sleep(max(monitor_interval_sec, 0.1))

    monitor_thread = threading.Thread(target=_monitor, daemon=True)
    monitor_thread.start()
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except Exception:
            pass
        stdout, stderr = process.communicate()
        raise RuntimeError(f"{stage} timed out after {timeout_sec}s.") from None
    finally:
        stop_event.set()
        monitor_thread.join(timeout=2.0)

    peak_rss_mb = float(state.get("peak_rss_mb") or 0.0)
    _append_resource_monitor_entry(
        adapter_dir=adapter_dir,
        stage=stage,
        pid=process.pid,
        peak_rss_mb=peak_rss_mb,
        max_rss_mb=max_rss_mb,
        exceeded=bool(state.get("exceeded")),
    )
    if bool(state.get("exceeded")):
        raise RuntimeError(
            f"{stage} exceeded memory guard ({max_rss_mb} MiB). "
            f"Peak RSS: {peak_rss_mb:.1f} MiB."
        )
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=int(process.returncode or 0),
        stdout=stdout,
        stderr=stderr,
    )


def _get_settings() -> Any:
    from venom_core.config import SETTINGS

    return SETTINGS


def _resolve_runtime_for_adapter_deploy(
    runtime_id: str | None,
) -> str:
    return (runtime_id or "").strip().lower()


def _runtime_endpoint_for_hash(
    runtime_id: str, *, settings_obj: Any | None = None
) -> str | None:
    settings = settings_obj or _get_settings()
    if runtime_id == "vllm":
        return str(getattr(settings, "VLLM_ENDPOINT", "")).strip() or None
    if runtime_id == "onnx":
        return None
    return build_http_url("localhost", 11434, "/v1")


def _resolve_runtime_for_rollback(
    *,
    active_runtime: Any,
    settings_obj: Any | None = None,
) -> tuple[str, str]:
    settings = settings_obj or _get_settings()
    runtime_candidate = (
        str(getattr(settings, "ACTIVE_LLM_SERVER", "") or "").strip().lower()
        or str(getattr(active_runtime, "provider", "") or "").strip().lower()
    )
    runtime_local_id = _resolve_local_runtime_id(runtime_candidate)
    return runtime_local_id or "", runtime_candidate


def _resolve_fallback_model_for_rollback(
    *,
    config: Dict[str, Any],
    runtime_local_id: str,
) -> tuple[str, str, str]:
    previous_key = previous_model_key_for_server(runtime_local_id)
    fallback_model = str(config.get(previous_key) or "").strip()
    return runtime_local_id, previous_key, fallback_model


def _resolve_current_runtime_state(
    *,
    active_runtime: Any,
    settings_obj: Any | None = None,
) -> tuple[str, str]:
    settings = settings_obj or _get_settings()
    runtime_candidate = (
        str(getattr(settings, "ACTIVE_LLM_SERVER", "") or "").strip().lower()
        or str(getattr(active_runtime, "provider", "") or "").strip().lower()
    )
    runtime_local_id = _resolve_local_runtime_id(runtime_candidate) or ""
    active_model = (
        str(getattr(settings, "LLM_MODEL_NAME", "") or "").strip()
        or str(getattr(active_runtime, "model_name", "") or "").strip()
    )
    return runtime_local_id, active_model


def _build_runtime_rollback_updates(
    *,
    mgr: Any,
    runtime_local_id: str,
    previous_key: str,
    fallback_model: str,
    resolve_local_runtime_model_path_by_name_fn: Any | None = None,
    settings_obj: Any | None = None,
) -> Dict[str, Any]:
    resolver = (
        resolve_local_runtime_model_path_by_name_fn
        or _resolve_local_runtime_model_path_by_name
    )
    updates: Dict[str, Any] = {
        "ACTIVE_LLM_SERVER": runtime_local_id,
        "LLM_MODEL_NAME": fallback_model,
        "HYBRID_LOCAL_MODEL": fallback_model,
        previous_key: "",
    }
    if runtime_local_id == "ollama":
        updates["LAST_MODEL_OLLAMA"] = fallback_model
        return updates
    if runtime_local_id != "vllm":
        return updates
    updates["LAST_MODEL_VLLM"] = fallback_model
    fallback_path = resolver(
        mgr=mgr,
        model_name=fallback_model,
        settings_obj=settings_obj,
    )
    if not fallback_path:
        return updates
    updates["VLLM_MODEL_PATH"] = fallback_path
    updates["VLLM_SERVED_MODEL_NAME"] = fallback_model
    template_path = Path(fallback_path) / "chat_template.jinja"
    updates["VLLM_CHAT_TEMPLATE"] = str(template_path) if template_path.exists() else ""
    return updates


def _apply_runtime_rollback_settings(
    *,
    runtime_local_id: str,
    fallback_model: str,
    config_hash: str,
    updates: Dict[str, Any],
    settings_obj: Any | None = None,
    restart_vllm_runtime_fn: Any | None = None,
) -> None:
    restart_fn = restart_vllm_runtime_fn or _restart_vllm_runtime
    settings = settings_obj or _get_settings()
    settings.ACTIVE_LLM_SERVER = runtime_local_id
    settings.LLM_MODEL_NAME = fallback_model
    settings.HYBRID_LOCAL_MODEL = fallback_model
    settings.LLM_CONFIG_HASH = config_hash
    if runtime_local_id != "vllm":
        return
    if "VLLM_MODEL_PATH" in updates:
        settings.VLLM_MODEL_PATH = str(updates["VLLM_MODEL_PATH"])
    settings.VLLM_SERVED_MODEL_NAME = fallback_model
    settings.LAST_MODEL_VLLM = fallback_model
    restart_fn(settings_obj=settings)


def _is_runtime_model_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    if not (path / MODEL_CONFIG_FILENAME).exists():
        return False
    if any(path.glob("*.safetensors")):
        return True
    if any(path.glob("pytorch_model*.bin")):
        return True
    if any(path.glob("model*.bin")):
        return True
    return False


def _resolve_repo_root(*, settings_obj: Any | None = None) -> Path:
    settings = settings_obj or _get_settings()
    fallback_root = Path(__file__).resolve().parents[3]
    configured = Path(str(getattr(settings, "REPO_ROOT", "") or "")).expanduser()
    if not str(configured).strip():
        return fallback_root
    if configured.is_absolute():
        return configured.resolve()
    return (fallback_root / configured).resolve()


def _resolve_academy_models_dir(*, settings_obj: Any | None = None) -> Path:
    settings = settings_obj or _get_settings()
    configured = Path(str(getattr(settings, "ACADEMY_MODELS_DIR", "data/models")))
    if configured.is_absolute():
        return configured.resolve()
    return (_resolve_repo_root(settings_obj=settings_obj) / configured).resolve()


def _resolve_local_runtime_model_path_by_name(
    *,
    mgr: Any,
    model_name: str,
    settings_obj: Any | None = None,
    resolve_repo_root_fn: Any = _resolve_repo_root,
) -> str:
    candidate = model_name.strip()
    if not candidate:
        return ""
    search_dirs: list[Path] = []
    models_dir = getattr(mgr, "models_dir", None)
    if isinstance(models_dir, Path):
        search_dirs.append(models_dir.resolve())
    else:
        search_dirs.append(_resolve_academy_models_dir(settings_obj=settings_obj))
    repo_models = resolve_repo_root_fn(settings_obj=settings_obj) / "models"
    if repo_models not in search_dirs:
        search_dirs.append(repo_models)
    for base in search_dirs:
        base_resolved = base.resolve()
        candidate_path = (base_resolved / candidate).resolve()
        try:
            candidate_path.relative_to(base_resolved)
        except ValueError:
            continue
        if candidate_path.exists() and candidate_path.is_dir():
            return str(candidate_path)
    return ""


def _restart_vllm_runtime(
    *,
    resolve_repo_root_fn: Any = _resolve_repo_root,
    settings_obj: Any | None = None,
) -> None:
    service_script = (
        resolve_repo_root_fn(settings_obj=settings_obj)
        / "scripts"
        / "llm"
        / "vllm_service.sh"
    )
    if not service_script.exists():
        raise RuntimeError(f"vLLM service script not found: {service_script}")
    result = subprocess.run(
        ["bash", str(service_script), "restart"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or UNKNOWN_ERROR_DETAIL
        raise RuntimeError(f"Failed to restart vLLM runtime: {stderr}")


def _build_vllm_runtime_model_from_adapter(
    *,
    adapter_dir: Path,
    base_model: str,
) -> Path:
    adapter_path = adapter_dir / "adapter"
    if not adapter_path.exists():
        raise FileNotFoundError(f"Adapter path not found: {adapter_path}")

    runtime_dir = adapter_dir / "runtime_vllm"
    if _is_runtime_model_dir(runtime_dir):
        return runtime_dir

    tmp_dir = adapter_dir / "runtime_vllm_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        merge_payload = {
            "base_model": str(base_model),
            "adapter_path": str(adapter_path),
            "output_dir": str(tmp_dir),
        }
        merge_script = r"""
import json
import os
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

payload = json.loads(os.environ["VENOM_ADAPTER_MERGE_PAYLOAD"])
base_model = str(payload["base_model"])
adapter_path = str(payload["adapter_path"])
output_dir = str(payload["output_dir"])
has_cuda = bool(torch.cuda.is_available())
if has_cuda:
    model_kwargs = {"torch_dtype": torch.float16, "device_map": "auto"}
else:
    model_kwargs = {
        "torch_dtype": "auto",
        "device_map": "cpu",
        "low_cpu_mem_usage": True,
    }

base_model_obj = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)
peft_model = PeftModel.from_pretrained(base_model_obj, adapter_path)
merged_model = peft_model.merge_and_unload()
merged_model.save_pretrained(output_dir, safe_serialization=True)

tokenizer_source = (
    adapter_path if os.path.exists(os.path.join(adapter_path, "tokenizer.json"))
    else base_model
)
tokenizer = AutoTokenizer.from_pretrained(tokenizer_source)
tokenizer.save_pretrained(output_dir)
"""
        merge_env = dict(os.environ)
        merge_env["VENOM_ADAPTER_MERGE_PAYLOAD"] = json.dumps(
            merge_payload, ensure_ascii=False
        )
        merge_limit_mb = _resolve_merge_memory_limit_mb()
        monitor_interval = _resolve_memory_monitor_interval_sec()
        merge_result = _run_subprocess_with_memory_guard(
            cmd=[sys.executable, "-c", merge_script],
            stage="adapter_merge",
            adapter_dir=adapter_dir,
            timeout_sec=3600,
            max_rss_mb=merge_limit_mb,
            monitor_interval_sec=monitor_interval,
            env=merge_env,
        )
        if merge_result.returncode != 0:
            stderr = (merge_result.stderr or "").strip()
            stdout = (merge_result.stdout or "").strip()
            raise RuntimeError(
                "Failed to merge adapter with base model: "
                + (stderr or stdout or UNKNOWN_ERROR_DETAIL)
            )
        (tmp_dir / "venom_runtime_vllm.json").write_text(
            json.dumps(
                {
                    "base_model": base_model,
                    "adapter_path": str(adapter_path),
                    "runtime": "vllm",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    tmp_dir.rename(runtime_dir)
    return runtime_dir


def _resolve_adapter_dir(*, models_dir: Path, adapter_id: str) -> Path:
    """Resolve adapter directory and reject path traversal."""
    adapter_dir = (models_dir / adapter_id).resolve()
    try:
        adapter_dir.relative_to(models_dir)
    except ValueError as exc:
        raise ValueError(
            f"Invalid adapter_id '{adapter_id}': outside of models directory."
        ) from exc
    return adapter_dir


def _require_existing_adapter_artifact(*, adapter_dir: Path) -> Path:
    adapter_path = (adapter_dir / "adapter").resolve()
    if not adapter_path.exists():
        raise FileNotFoundError(ADAPTER_NOT_FOUND_DETAIL)
    return adapter_path


def _resolve_requested_runtime_model(model_id: str | None) -> str:
    return str(model_id or "").strip()


def _resolve_ollama_from_model_alias(requested_model: str) -> str:
    candidate = requested_model.strip()
    if not candidate:
        return ""
    canonical = _canonical_runtime_model_id(candidate)
    mapped = _CANONICAL_TO_OLLAMA_FROM_MODEL.get(canonical)
    if mapped:
        return mapped
    return candidate


def _resolve_ollama_create_from_model(
    *,
    adapter_dir: Path,
    requested_model: str,
    is_runtime_model_dir_fn: Any = _is_runtime_model_dir,
) -> tuple[str, bool]:
    """Resolve FROM model for ollama create and whether --experimental is required."""
    metadata = _load_adapter_metadata(adapter_dir)
    parameters = metadata.get("parameters")
    training_base_model = ""
    if isinstance(parameters, dict):
        training_base_model = str(parameters.get("training_base_model") or "").strip()

    if training_base_model:
        candidate = Path(training_base_model).expanduser().resolve()
        if is_runtime_model_dir_fn(candidate):
            return str(candidate), True
    return _resolve_ollama_from_model_alias(requested_model), False


def _resolve_hf_cache_snapshot_for_repo_id(
    *,
    repo_id: str,
    settings_obj: Any | None = None,
) -> str:
    settings = settings_obj or _get_settings()
    repo_root = _resolve_repo_root(settings_obj=settings)
    normalized = repo_id.strip().strip("/")
    if not normalized or "/" not in normalized:
        return ""
    owner, name = normalized.split("/", 1)
    model_store_id = f"models--{owner}--{name}".replace("/", "--")
    hub_base = repo_root / "models" / "cache" / "huggingface" / "hub" / model_store_id
    snapshots_dir = hub_base / "snapshots"
    if not snapshots_dir.exists() or not snapshots_dir.is_dir():
        return ""
    snapshots = sorted(
        [p for p in snapshots_dir.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for snapshot in snapshots:
        if (snapshot / MODEL_CONFIG_FILENAME).exists():
            return str(snapshot.resolve())
    return ""


def _resolve_adapter_training_base_for_ollama_gguf(
    *,
    adapter_dir: Path,
    requested_from_model: str,
    settings_obj: Any | None = None,
) -> str:
    metadata = _load_adapter_metadata(adapter_dir)
    parameters = metadata.get("parameters")
    training_base_model = ""
    if isinstance(parameters, dict):
        training_base_model = str(parameters.get("training_base_model") or "").strip()
    candidate_values = [
        training_base_model,
        str(metadata.get("effective_base_model") or "").strip(),
        str(metadata.get("base_model") or "").strip(),
        requested_from_model.strip(),
    ]
    for candidate_raw in candidate_values:
        candidate = candidate_raw.strip()
        if not candidate:
            continue
        candidate_path = Path(candidate).expanduser()
        if candidate_path.exists() and candidate_path.is_dir():
            if (candidate_path / MODEL_CONFIG_FILENAME).exists():
                return str(candidate_path.resolve())
        resolved_snapshot = _resolve_hf_cache_snapshot_for_repo_id(
            repo_id=candidate,
            settings_obj=settings_obj,
        )
        if resolved_snapshot:
            return resolved_snapshot
    raise RuntimeError(
        "Cannot resolve local HF base model snapshot for Ollama GGUF adapter export. "
        "Expected training_base_model path or cached repo snapshot."
    )


def _resolve_local_training_base_model_for_merge(*, adapter_dir: Path) -> str:
    """Resolve local training base model path for merge/export when available."""
    metadata = _load_adapter_metadata(adapter_dir)
    parameters = metadata.get("parameters")
    if not isinstance(parameters, dict):
        return ""
    training_base_model = str(parameters.get("training_base_model") or "").strip()
    if not training_base_model:
        return ""
    candidate = Path(training_base_model).expanduser()
    if not candidate.exists() or not candidate.is_dir():
        return ""
    if not (candidate / MODEL_CONFIG_FILENAME).exists():
        return ""
    return str(candidate.resolve())


def _resolve_llama_cpp_convert_script(*, settings_obj: Any | None = None) -> Path:
    settings = settings_obj or _get_settings()
    explicit_script = str(os.getenv("VENOM_LLAMA_CPP_CONVERT_SCRIPT", "")).strip()
    if explicit_script:
        path = Path(explicit_script).expanduser().resolve()
        if path.exists() and path.is_file():
            return path

    explicit_dir = str(os.getenv("VENOM_LLAMA_CPP_DIR", "")).strip()
    if not explicit_dir:
        explicit_dir = str(getattr(settings, "ACADEMY_LLAMA_CPP_DIR", "") or "").strip()
    if explicit_dir:
        candidate = (
            Path(explicit_dir).expanduser().resolve() / "convert_lora_to_gguf.py"
        )
        if candidate.exists() and candidate.is_file():
            return candidate

    repo_root = _resolve_repo_root(settings_obj=settings)
    default_candidates = [
        repo_root / "tools" / "llama.cpp" / "convert_lora_to_gguf.py",
    ]
    for candidate in default_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "llama.cpp convert_lora_to_gguf.py not found. "
        "Set VENOM_LLAMA_CPP_DIR or VENOM_LLAMA_CPP_CONVERT_SCRIPT."
    )


def _resolve_existing_ollama_adapter_gguf(*, adapter_dir: Path) -> Path | None:
    adapter_path = adapter_dir / "adapter"
    if not adapter_path.exists() or not adapter_path.is_dir():
        return None
    for filename in _OLLAMA_GGUF_ADAPTER_CANDIDATES:
        candidate = adapter_path / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    for candidate in sorted(adapter_path.glob("*.gguf")):
        if candidate.is_file():
            return candidate
    return None


def _ensure_ollama_adapter_gguf(
    *,
    adapter_dir: Path,
    from_model: str,
    settings_obj: Any | None = None,
) -> Path:
    existing = _resolve_existing_ollama_adapter_gguf(adapter_dir=adapter_dir)
    if existing is not None:
        return existing.resolve()

    adapter_path = adapter_dir / "adapter"
    if not adapter_path.exists() or not adapter_path.is_dir():
        raise FileNotFoundError(f"Adapter path not found: {adapter_path}")

    base_model_path = _resolve_adapter_training_base_for_ollama_gguf(
        adapter_dir=adapter_dir,
        requested_from_model=from_model,
        settings_obj=settings_obj,
    )
    convert_script = _resolve_llama_cpp_convert_script(settings_obj=settings_obj)
    cmd = [
        sys.executable,
        str(convert_script),
        "--outtype",
        "f16",
        "--base",
        base_model_path,
        str(adapter_path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or UNKNOWN_ERROR_DETAIL
        raise RuntimeError(
            f"Failed to convert LoRA adapter to GGUF for Ollama deployment: {details}"
        )
    resolved = _resolve_existing_ollama_adapter_gguf(adapter_dir=adapter_dir)
    if resolved is None:
        raise RuntimeError(
            "LoRA->GGUF conversion finished but no *.gguf file found in adapter dir."
        )
    return resolved.resolve()


def _deploy_adapter_to_vllm_runtime(
    *,
    adapter_id: str,
    settings_obj: Any | None = None,
    config_manager_obj: Any = config_manager,
    compute_llm_config_hash_fn: Any = compute_llm_config_hash,
    runtime_endpoint_for_hash_fn: Any = _runtime_endpoint_for_hash,
    build_vllm_runtime_model_from_adapter_fn: Any = _build_vllm_runtime_model_from_adapter,
    is_runtime_model_dir_fn: Any = _is_runtime_model_dir,
    restart_vllm_runtime_fn: Any = _restart_vllm_runtime,
    get_active_llm_runtime_fn: Any = get_active_llm_runtime,
) -> Dict[str, Any]:
    settings = settings_obj or _get_settings()
    models_dir = _resolve_academy_models_dir(settings_obj=settings)
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    adapter_path = adapter_dir / "adapter"
    if not adapter_path.exists():
        raise FileNotFoundError(ADAPTER_NOT_FOUND_DETAIL)
    trusted_base_model = _require_trusted_adapter_base_model(
        adapter_dir=adapter_dir,
    ).strip()
    if not trusted_base_model:
        raise RuntimeError("Adapter base model is empty; cannot deploy to vLLM")
    base_model = (
        _resolve_local_training_base_model_for_merge(adapter_dir=adapter_dir)
        or trusted_base_model
    )

    runtime_model_dir = build_vllm_runtime_model_from_adapter_fn(
        adapter_dir=adapter_dir,
        base_model=base_model,
    )
    if not is_runtime_model_dir_fn(runtime_model_dir):
        raise RuntimeError(
            f"Failed to prepare runtime-usable vLLM model from adapter: {runtime_model_dir}"
        )

    last_model_key = "LAST_MODEL_VLLM"
    previous_model_key = previous_model_key_for_server("vllm")
    active_runtime = get_active_llm_runtime_fn()
    active_runtime_id, active_model = _resolve_current_runtime_state(
        active_runtime=active_runtime,
        settings_obj=settings,
    )
    selected_model = f"venom-adapter-{adapter_id}"
    template_path = runtime_model_dir / "chat_template.jinja"
    updates: Dict[str, Any] = {
        "LLM_SERVICE_TYPE": "local",
        "ACTIVE_LLM_SERVER": "vllm",
        "LLM_MODEL_NAME": selected_model,
        "HYBRID_LOCAL_MODEL": selected_model,
        "VLLM_MODEL_PATH": str(runtime_model_dir),
        "VLLM_SERVED_MODEL_NAME": selected_model,
        "VLLM_CHAT_TEMPLATE": str(template_path) if template_path.exists() else "",
        last_model_key: selected_model,
    }
    if active_runtime_id == "vllm" and active_model and active_model != selected_model:
        updates[previous_model_key] = active_model
    endpoint = runtime_endpoint_for_hash_fn("vllm", settings_obj=settings)
    config_hash = compute_llm_config_hash_fn("vllm", endpoint, selected_model)
    updates["LLM_CONFIG_HASH"] = config_hash
    config_manager_obj.update_config(updates)
    try:
        settings.LLM_SERVICE_TYPE = "local"
        settings.ACTIVE_LLM_SERVER = "vllm"
        settings.LLM_MODEL_NAME = selected_model
        settings.HYBRID_LOCAL_MODEL = selected_model
        settings.VLLM_MODEL_PATH = str(runtime_model_dir)
        settings.VLLM_SERVED_MODEL_NAME = selected_model
        settings.VLLM_CHAT_TEMPLATE = (
            str(template_path) if template_path.exists() else ""
        )
        settings.LAST_MODEL_VLLM = selected_model
        settings.LLM_CONFIG_HASH = config_hash
    except Exception:
        logger.warning("Failed to update SETTINGS for vLLM adapter deploy.")

    restart_vllm_runtime_fn(settings_obj=settings)
    return {
        "deployed": True,
        "runtime_id": "vllm",
        "chat_model": selected_model,
        "config_hash": config_hash,
        "runtime_model_path": str(runtime_model_dir),
    }


def _resolve_onnx_builder_script(*, settings_obj: Any | None = None) -> Path:
    """Resolve path to onnxruntime-genai builder.py script."""
    import os as _os

    settings = settings_obj or _get_settings()
    default_rel = "third_party/onnxruntime-genai/src/python/py/models/builder.py"
    env_script = _os.getenv("ONNX_GENAI_BUILDER_SCRIPT", "").strip()
    candidates = [
        env_script,
        str(getattr(settings, "ONNX_BUILDER_SCRIPT", "") or ""),
    ]
    repo_root = _resolve_repo_root(settings_obj=settings)
    for raw in candidates:
        if not raw:
            continue
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        if p.exists() and p.is_file():
            return p
    default_path = (repo_root / default_rel).resolve()
    if default_path.exists() and default_path.is_file():
        return default_path
    tools_path = (repo_root / "tools" / "onnx_builder" / "builder.py").resolve()
    if tools_path.exists() and tools_path.is_file():
        return tools_path
    try:
        installed_builder = importlib.import_module("onnxruntime_genai.models.builder")
        installed_builder_file = Path(str(getattr(installed_builder, "__file__", "")))
        if installed_builder_file.exists() and installed_builder_file.is_file():
            return installed_builder_file.resolve()
    except Exception:
        pass
    raise FileNotFoundError(
        "ONNX genai builder.py not found. Searched ONNX_GENAI_BUILDER_SCRIPT env var, "
        "ONNX_BUILDER_SCRIPT setting, and default paths "
        f"('{default_rel}', 'tools/onnx_builder/builder.py', installed onnxruntime_genai package)."
    )


def _build_onnx_runtime_model_from_adapter(
    *,
    adapter_dir: Path,
    base_model: str,
    execution_provider: str = "cpu",
    precision: str = "int4",
    settings_obj: Any | None = None,
    build_vllm_runtime_model_from_adapter_fn: Any = _build_vllm_runtime_model_from_adapter,
) -> Path:
    """Merge LoRA adapter with base model and export to ONNX genai format.

    Pipeline: adapter + base_model → HF merged model → onnxruntime-genai builder → runtime_onnx/
    """
    adapter_path = adapter_dir / "adapter"
    if not adapter_path.exists():
        raise FileNotFoundError(f"Adapter path not found: {adapter_path}")

    runtime_dir = adapter_dir / "runtime_onnx"
    if runtime_dir.exists() and (runtime_dir / ONNX_GENAI_CONFIG_FILENAME).exists():
        return runtime_dir

    # Step 1: merge LoRA into base model (reuse vLLM merge — produces HF merged dir)
    merged_dir = build_vllm_runtime_model_from_adapter_fn(
        adapter_dir=adapter_dir,
        base_model=base_model,
    )
    export_input_dir = _prepare_gemma3_text_export_input_dir(
        adapter_dir=adapter_dir,
        merged_dir=merged_dir,
    )
    export_input = export_input_dir or merged_dir

    # Step 2: export merged HF model to onnxruntime-genai format via builder.py
    builder_script = _resolve_onnx_builder_script(settings_obj=settings_obj)
    tmp_dir = adapter_dir / "runtime_onnx_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        export_cmd = [
            sys.executable,
            str(builder_script),
            "-i",
            str(export_input),
            "-e",
            execution_provider,
            "-p",
            precision,
            "-o",
            str(tmp_dir),
        ]
        result = _run_subprocess_with_memory_guard(
            cmd=export_cmd,
            stage="onnx_export",
            adapter_dir=adapter_dir,
            timeout_sec=1800,
            max_rss_mb=_resolve_merge_memory_limit_mb(settings_obj=settings_obj),
            monitor_interval_sec=_resolve_memory_monitor_interval_sec(
                settings_obj=settings_obj
            ),
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            raise RuntimeError(
                "ONNX genai export failed: "
                + (stderr or stdout or UNKNOWN_ERROR_DETAIL)
            )
        genai_config_path = tmp_dir / ONNX_GENAI_CONFIG_FILENAME
        if not genai_config_path.exists():
            raise RuntimeError(
                f"ONNX genai export finished but {ONNX_GENAI_CONFIG_FILENAME} not found in output."
            )
        # onnxruntime-genai builder may emit `model.type=gemma3` for text-only Gemma-3.
        # Runtime loaders in our stack expect `gemma3_text` for this path.
        try:
            payload = json.loads(genai_config_path.read_text(encoding="utf-8"))
            model_obj = payload.get("model")
            model_type = (
                str(model_obj.get("type") or "").strip().lower()
                if isinstance(model_obj, dict)
                else ""
            )
            if model_type == "gemma3":
                model_obj["type"] = "gemma3_text"
                genai_config_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info(
                    "Normalized ONNX GenAI config model.type from gemma3 to gemma3_text"
                )
        except Exception as exc:
            logger.warning(
                "Failed to normalize ONNX GenAI config model.type (%s)",
                exc,
            )
        (tmp_dir / "venom_runtime_onnx.json").write_text(
            json.dumps(
                {
                    "base_model": base_model,
                    "adapter_path": str(adapter_path),
                    "runtime": "onnx",
                    "execution_provider": execution_provider,
                    "precision": precision,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if export_input_dir is not None:
            shutil.rmtree(export_input_dir, ignore_errors=True)
        raise

    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    try:
        tmp_dir.rename(runtime_dir)
    except Exception:
        # Keep workspace clean if final move fails after successful export.
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if export_input_dir is not None:
            shutil.rmtree(export_input_dir, ignore_errors=True)
        raise
    if export_input_dir is not None:
        shutil.rmtree(export_input_dir, ignore_errors=True)
    return runtime_dir


def _prepare_gemma3_text_export_input_dir(
    *,
    adapter_dir: Path,
    merged_dir: Path,
) -> Path | None:
    """Prepare temporary text-only HF layout for Gemma-3 ONNX export.

    Builder may emit decoder contract with `inputs_embeds` for multimodal Gemma-3
    (`model_type=gemma3`). For runtime generation we need token-based contract.
    We generate a temporary input directory with a text-only config while reusing
    merged weights/tokenizer files via symlinks.
    """
    config_path = merged_dir / "config.json"
    if not config_path.exists():
        return None
    try:
        merged_cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(merged_cfg, dict):
        return None
    if str(merged_cfg.get("model_type") or "").strip().lower() != "gemma3":
        return None
    text_cfg = merged_cfg.get("text_config")
    if not isinstance(text_cfg, dict):
        return None

    export_cfg = dict(text_cfg)
    export_cfg["model_type"] = "gemma3_text"
    export_cfg["architectures"] = ["Gemma3ForCausalLM"]
    for key in (
        "bos_token_id",
        "eos_token_id",
        "pad_token_id",
        "torch_dtype",
        "transformers_version",
    ):
        if key in merged_cfg and key not in export_cfg:
            export_cfg[key] = merged_cfg[key]

    tmp_input_dir = adapter_dir / "runtime_onnx_export_input_tmp"
    if tmp_input_dir.exists():
        shutil.rmtree(tmp_input_dir, ignore_errors=True)
    tmp_input_dir.mkdir(parents=True, exist_ok=True)

    for item in merged_dir.iterdir():
        target = tmp_input_dir / item.name
        if item.name == "config.json":
            continue
        if item.is_symlink() or item.is_file():
            try:
                target.symlink_to(item.resolve())
            except Exception:
                shutil.copy2(item, target)
        elif item.is_dir():
            try:
                target.symlink_to(item.resolve(), target_is_directory=True)
            except Exception:
                shutil.copytree(item, target, dirs_exist_ok=True)

    (tmp_input_dir / "config.json").write_text(
        json.dumps(export_cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Prepared Gemma-3 text-only ONNX export input dir: %s", tmp_input_dir)
    return tmp_input_dir


def _deploy_adapter_to_onnx_runtime(
    *,
    adapter_id: str,
    settings_obj: Any | None = None,
    config_manager_obj: Any = config_manager,
    compute_llm_config_hash_fn: Any = compute_llm_config_hash,
    runtime_endpoint_for_hash_fn: Any = _runtime_endpoint_for_hash,
    build_vllm_runtime_model_from_adapter_fn: Any = _build_vllm_runtime_model_from_adapter,
    build_onnx_runtime_model_from_adapter_fn: Any | None = None,
    get_active_llm_runtime_fn: Any = get_active_llm_runtime,
) -> Dict[str, Any]:
    """Deploy LoRA adapter to ONNX runtime via merge → ONNX export pipeline."""
    settings = settings_obj or _get_settings()
    models_dir = _resolve_academy_models_dir(settings_obj=settings)
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    adapter_path = adapter_dir / "adapter"
    if not adapter_path.exists():
        raise FileNotFoundError(ADAPTER_NOT_FOUND_DETAIL)
    trusted_base_model = _require_trusted_adapter_base_model(
        adapter_dir=adapter_dir,
    ).strip()
    if not trusted_base_model:
        raise RuntimeError("Adapter base model is empty; cannot deploy to ONNX")
    base_model = (
        _resolve_local_training_base_model_for_merge(adapter_dir=adapter_dir)
        or trusted_base_model
    )

    build_fn = (
        build_onnx_runtime_model_from_adapter_fn
        or _build_onnx_runtime_model_from_adapter
    )
    execution_provider = (
        str(getattr(settings, "ONNX_LLM_EXECUTION_PROVIDER", "cpu") or "cpu").strip()
        or "cpu"
    )
    precision = (
        str(getattr(settings, "ONNX_LLM_PRECISION", "int4") or "int4").strip() or "int4"
    )
    runtime_onnx_dir = build_fn(
        adapter_dir=adapter_dir,
        base_model=base_model,
        execution_provider=execution_provider,
        precision=precision,
        build_vllm_runtime_model_from_adapter_fn=build_vllm_runtime_model_from_adapter_fn,
    )
    if not (runtime_onnx_dir / ONNX_GENAI_CONFIG_FILENAME).exists():
        raise RuntimeError(
            f"ONNX export succeeded but {ONNX_GENAI_CONFIG_FILENAME} missing: {runtime_onnx_dir}"
        )

    previous_model_key = "PREVIOUS_MODEL_ONNX"
    active_runtime = get_active_llm_runtime_fn()
    active_runtime_id, active_model = _resolve_current_runtime_state(
        active_runtime=active_runtime,
        settings_obj=settings,
    )
    selected_model = f"venom-adapter-{adapter_id}"
    previous_onnx_model_path = str(
        getattr(settings, "ONNX_LLM_MODEL_PATH", "") or ""
    ).strip()
    updates: Dict[str, Any] = {
        "ACTIVE_LLM_SERVER": "onnx",
        "LLM_SERVICE_TYPE": "onnx",
        "LLM_LOCAL_ENDPOINT": "",
        "LLM_MODEL_NAME": selected_model,
        "HYBRID_LOCAL_MODEL": selected_model,
        "ONNX_LLM_MODEL_PATH": str(runtime_onnx_dir),
        "ONNX_LLM_ENABLED": True,
        "LAST_MODEL_ONNX": selected_model,
        "PREVIOUS_ONNX_LLM_MODEL_PATH": previous_onnx_model_path,
    }
    if active_runtime_id == "onnx" and active_model and active_model != selected_model:
        updates[previous_model_key] = active_model
    endpoint = runtime_endpoint_for_hash_fn("onnx", settings_obj=settings)
    config_hash = compute_llm_config_hash_fn("onnx", endpoint or "", selected_model)
    updates["LLM_CONFIG_HASH"] = config_hash
    update_result = config_manager_obj.update_config(updates)
    if isinstance(update_result, dict) and not bool(update_result.get("success", True)):
        raise RuntimeError(
            "Failed to persist ONNX adapter deploy config: "
            f"{update_result.get('message', 'unknown error')}"
        )
    try:
        settings.ACTIVE_LLM_SERVER = "onnx"
        settings.LLM_SERVICE_TYPE = "onnx"
        settings.LLM_LOCAL_ENDPOINT = ""
        settings.LLM_MODEL_NAME = selected_model
        settings.HYBRID_LOCAL_MODEL = selected_model
        settings.ONNX_LLM_MODEL_PATH = str(runtime_onnx_dir)
        settings.ONNX_LLM_ENABLED = True
        settings.LAST_MODEL_ONNX = selected_model
        settings.LLM_CONFIG_HASH = config_hash
    except Exception:
        logger.warning("Failed to update SETTINGS for ONNX adapter deploy.")
    return {
        "deployed": True,
        "runtime_id": "onnx",
        "chat_model": selected_model,
        "config_hash": config_hash,
        "runtime_model_path": str(runtime_onnx_dir),
    }


def _handle_non_ollama_runtime_deploy(
    *,
    runtime_local_id: str,
    adapter_id: str,
    settings_obj: Any | None = None,
    config_manager_obj: Any = config_manager,
    compute_llm_config_hash_fn: Any = compute_llm_config_hash,
    runtime_endpoint_for_hash_fn: Any = _runtime_endpoint_for_hash,
    build_vllm_runtime_model_from_adapter_fn: Any = _build_vllm_runtime_model_from_adapter,
    is_runtime_model_dir_fn: Any = _is_runtime_model_dir,
    restart_vllm_runtime_fn: Any = _restart_vllm_runtime,
    deploy_adapter_to_vllm_runtime_fn: Any | None = None,
    deploy_adapter_to_onnx_runtime_fn: Any | None = None,
    get_active_llm_runtime_fn: Any = get_active_llm_runtime,
) -> Dict[str, Any]:
    if runtime_local_id == "onnx":
        if deploy_adapter_to_onnx_runtime_fn is not None:
            return deploy_adapter_to_onnx_runtime_fn(adapter_id=adapter_id)
        return _deploy_adapter_to_onnx_runtime(
            adapter_id=adapter_id,
            settings_obj=settings_obj,
            config_manager_obj=config_manager_obj,
            compute_llm_config_hash_fn=compute_llm_config_hash_fn,
            runtime_endpoint_for_hash_fn=runtime_endpoint_for_hash_fn,
            build_vllm_runtime_model_from_adapter_fn=build_vllm_runtime_model_from_adapter_fn,
            get_active_llm_runtime_fn=get_active_llm_runtime_fn,
        )
    if runtime_local_id == "vllm":
        if deploy_adapter_to_vllm_runtime_fn is not None:
            return deploy_adapter_to_vllm_runtime_fn(adapter_id=adapter_id)
        return _deploy_adapter_to_vllm_runtime(
            adapter_id=adapter_id,
            settings_obj=settings_obj,
            config_manager_obj=config_manager_obj,
            compute_llm_config_hash_fn=compute_llm_config_hash_fn,
            runtime_endpoint_for_hash_fn=runtime_endpoint_for_hash_fn,
            build_vllm_runtime_model_from_adapter_fn=build_vllm_runtime_model_from_adapter_fn,
            is_runtime_model_dir_fn=is_runtime_model_dir_fn,
            restart_vllm_runtime_fn=restart_vllm_runtime_fn,
            get_active_llm_runtime_fn=get_active_llm_runtime_fn,
        )
    return {}


def _resolve_chat_runtime_deploy_deps(
    *,
    deploy_deps: Dict[str, Any] | None,
    legacy_deps: Dict[str, Any],
) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "canonical_runtime_model_id_fn": _canonical_runtime_model_id,
        "require_trusted_adapter_base_model_fn": _require_trusted_adapter_base_model,
        "config_manager_obj": config_manager,
        "compute_llm_config_hash_fn": compute_llm_config_hash,
        "resolve_runtime_for_adapter_deploy_fn": _resolve_runtime_for_adapter_deploy,
        "runtime_endpoint_for_hash_fn": _runtime_endpoint_for_hash,
        "build_vllm_runtime_model_from_adapter_fn": _build_vllm_runtime_model_from_adapter,
        "is_runtime_model_dir_fn": _is_runtime_model_dir,
        "restart_vllm_runtime_fn": _restart_vllm_runtime,
        "get_active_llm_runtime_fn": get_active_llm_runtime,
        "deploy_adapter_to_vllm_runtime_fn": None,
        "deploy_adapter_to_onnx_runtime_fn": None,
    }
    resolved = dict(defaults)
    if deploy_deps:
        resolved.update(deploy_deps)
    if legacy_deps:
        resolved.update(legacy_deps)
    return resolved


def _deploy_adapter_to_chat_runtime(
    *,
    mgr: Any,
    adapter_id: str,
    runtime_id: str | None,
    model_id: str | None,
    settings_obj: Any | None = None,
    deploy_deps: Dict[str, Any] | None = None,
    **legacy_deps: Any,
) -> Dict[str, Any]:
    settings = settings_obj or _get_settings()
    deps = _resolve_chat_runtime_deploy_deps(
        deploy_deps=deploy_deps,
        legacy_deps=legacy_deps,
    )

    runtime_candidate = deps["resolve_runtime_for_adapter_deploy_fn"](runtime_id)
    if not runtime_candidate:
        raise ValueError(
            "ADAPTER_RUNTIME_REQUIRED: Select target runtime before adapter activation."
        )
    requested_model = _resolve_requested_runtime_model(model_id)
    if not requested_model:
        raise ValueError(
            "ADAPTER_RUNTIME_MODEL_REQUIRED: Select runtime model before adapter activation."
        )
    runtime_local_id = _resolve_local_runtime_id(runtime_candidate)
    if runtime_local_id is None:
        return {
            "deployed": False,
            "reason": f"runtime_not_local:{runtime_candidate}",
            "runtime_id": runtime_candidate,
        }

    non_ollama_payload = _handle_non_ollama_runtime_deploy(
        runtime_local_id=runtime_local_id,
        adapter_id=adapter_id,
        settings_obj=settings,
        config_manager_obj=deps["config_manager_obj"],
        compute_llm_config_hash_fn=deps["compute_llm_config_hash_fn"],
        runtime_endpoint_for_hash_fn=deps["runtime_endpoint_for_hash_fn"],
        build_vllm_runtime_model_from_adapter_fn=deps[
            "build_vllm_runtime_model_from_adapter_fn"
        ],
        is_runtime_model_dir_fn=deps["is_runtime_model_dir_fn"],
        restart_vllm_runtime_fn=deps["restart_vllm_runtime_fn"],
        deploy_adapter_to_vllm_runtime_fn=deps["deploy_adapter_to_vllm_runtime_fn"],
        get_active_llm_runtime_fn=deps["get_active_llm_runtime_fn"],
        deploy_adapter_to_onnx_runtime_fn=deps["deploy_adapter_to_onnx_runtime_fn"],
    )
    if non_ollama_payload:
        return non_ollama_payload

    models_dir = _resolve_academy_models_dir(settings_obj=settings)
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    adapter_base_model = deps["require_trusted_adapter_base_model_fn"](
        adapter_dir=adapter_dir,
    ).strip()
    requested_model_is_runtime_adapter = requested_model.lower().startswith(
        _RUNTIME_ADAPTER_MODEL_PREFIX
    )
    if (
        adapter_base_model
        and requested_model
        and not requested_model_is_runtime_adapter
    ):
        adapter_canonical = deps["canonical_runtime_model_id_fn"](adapter_base_model)
        requested_canonical = deps["canonical_runtime_model_id_fn"](requested_model)
        if requested_canonical and requested_canonical != adapter_canonical:
            message = (
                "Adapter base model does not match selected Ollama runtime FROM model. "
                f"runtime_model='{requested_model}', adapter_base_model='{adapter_base_model}'."
            )
            logger.warning(
                "Blocking Ollama adapter deploy due to ADAPTER_BASE_MODEL_MISMATCH "
                "(adapter_id=%s, runtime_model=%s, adapter_base_model=%s)",
                adapter_id,
                requested_model,
                adapter_base_model,
            )
            raise ValueError(f"ADAPTER_BASE_MODEL_MISMATCH: {message}")

    ollama_model_name = f"venom-adapter-{adapter_id}"
    requested_from_model = (
        adapter_base_model if requested_model_is_runtime_adapter else requested_model
    )
    from_model, use_experimental = _resolve_ollama_create_from_model(
        adapter_dir=adapter_dir,
        requested_model=requested_from_model,
        is_runtime_model_dir_fn=deps["is_runtime_model_dir_fn"],
    )
    _ensure_ollama_adapter_gguf(
        adapter_dir=adapter_dir,
        from_model=from_model,
        settings_obj=settings,
    )

    deployed_model = mgr.create_ollama_modelfile(
        version_id=adapter_id,
        output_name=ollama_model_name,
        from_model=from_model,
        use_experimental=use_experimental,
    )
    if not deployed_model:
        raise RuntimeError("Failed to create Ollama model for adapter deployment")

    last_model_key = "LAST_MODEL_OLLAMA"
    previous_model_key = previous_model_key_for_server(runtime_local_id)
    active_runtime = deps["get_active_llm_runtime_fn"]()
    active_runtime_id, active_model = _resolve_current_runtime_state(
        active_runtime=active_runtime,
        settings_obj=settings,
    )
    selected_model = str(deployed_model)
    updates: Dict[str, Any] = {
        "ACTIVE_LLM_SERVER": runtime_local_id,
        "LLM_MODEL_NAME": selected_model,
        "HYBRID_LOCAL_MODEL": selected_model,
        last_model_key: selected_model,
    }
    if (
        active_runtime_id == runtime_local_id
        and active_model
        and active_model != selected_model
    ):
        updates[previous_model_key] = active_model
    endpoint = deps["runtime_endpoint_for_hash_fn"](
        runtime_local_id,
        settings_obj=settings,
    )
    config_hash = deps["compute_llm_config_hash_fn"](
        runtime_local_id, endpoint, selected_model
    )
    updates["LLM_CONFIG_HASH"] = config_hash
    deps["config_manager_obj"].update_config(updates)
    try:
        settings.ACTIVE_LLM_SERVER = runtime_local_id
        settings.LLM_MODEL_NAME = selected_model
        settings.HYBRID_LOCAL_MODEL = selected_model
        settings.LLM_CONFIG_HASH = config_hash
    except Exception:
        logger.warning("Failed to update SETTINGS for adapter chat deployment.")

    return {
        "deployed": True,
        "runtime_id": runtime_local_id,
        "chat_model": selected_model,
        "config_hash": config_hash,
    }


def _rollback_onnx_adapter_deploy(
    *,
    config: Dict[str, Any],
    settings_obj: Any | None = None,
    config_manager_obj: Any = config_manager,
    compute_llm_config_hash_fn: Any = compute_llm_config_hash,
    runtime_endpoint_for_hash_fn: Any = _runtime_endpoint_for_hash,
) -> Dict[str, Any]:
    """Roll back ONNX adapter deploy: restore previous ONNX model path and settings."""
    settings = settings_obj or _get_settings()
    previous_onnx_path = str(config.get("PREVIOUS_ONNX_LLM_MODEL_PATH") or "").strip()
    previous_model = str(config.get("PREVIOUS_MODEL_ONNX") or "").strip()
    fallback_model = (
        previous_model or str(getattr(settings, "LAST_MODEL_ONNX", "") or "").strip()
    )

    if not fallback_model and not previous_onnx_path:
        return {
            "rolled_back": False,
            "reason": "previous_model_missing",
            "runtime_id": "onnx",
        }
    if fallback_model and not previous_onnx_path:
        logger.warning(
            "ONNX adapter rollback requested but no previous ONNX_LLM_MODEL_PATH was recorded; "
            "leaving configuration unchanged."
        )
        return {
            "rolled_back": False,
            "reason": "previous_path_missing",
            "runtime_id": "onnx",
            "chat_model": fallback_model,
        }

    updates: Dict[str, Any] = {
        "ACTIVE_LLM_SERVER": "onnx",
        "LLM_SERVICE_TYPE": "onnx",
        "LLM_LOCAL_ENDPOINT": "",
        "LLM_MODEL_NAME": fallback_model,
        "HYBRID_LOCAL_MODEL": fallback_model,
        "LAST_MODEL_ONNX": fallback_model,
        "PREVIOUS_MODEL_ONNX": "",
        "PREVIOUS_ONNX_LLM_MODEL_PATH": "",
    }
    updates["ONNX_LLM_MODEL_PATH"] = previous_onnx_path
    updates["ONNX_LLM_ENABLED"] = True
    endpoint = runtime_endpoint_for_hash_fn("onnx", settings_obj=settings)
    config_hash = compute_llm_config_hash_fn("onnx", endpoint or "", fallback_model)
    updates["LLM_CONFIG_HASH"] = config_hash
    update_result = config_manager_obj.update_config(updates)
    if isinstance(update_result, dict) and not bool(update_result.get("success", True)):
        raise RuntimeError(
            "Failed to persist ONNX adapter rollback config: "
            f"{update_result.get('message', 'unknown error')}"
        )
    try:
        settings.ACTIVE_LLM_SERVER = "onnx"
        settings.LLM_SERVICE_TYPE = "onnx"
        settings.LLM_LOCAL_ENDPOINT = ""
        settings.LLM_MODEL_NAME = fallback_model
        settings.HYBRID_LOCAL_MODEL = fallback_model
        settings.LAST_MODEL_ONNX = fallback_model
        settings.LLM_CONFIG_HASH = config_hash
        settings.ONNX_LLM_MODEL_PATH = previous_onnx_path
        settings.ONNX_LLM_ENABLED = True
    except Exception:
        logger.warning("Failed to update SETTINGS during ONNX adapter rollback.")
    return {
        "rolled_back": True,
        "runtime_id": "onnx",
        "chat_model": fallback_model,
        "config_hash": config_hash,
    }


def _rollback_chat_runtime_after_adapter_deactivation(
    *,
    mgr: Any,
    settings_obj: Any | None = None,
    get_active_llm_runtime_fn: Any = get_active_llm_runtime,
    config_manager_obj: Any = config_manager,
    compute_llm_config_hash_fn: Any = compute_llm_config_hash,
    runtime_endpoint_for_hash_fn: Any = _runtime_endpoint_for_hash,
    resolve_local_runtime_model_path_by_name_fn: Any = _resolve_local_runtime_model_path_by_name,
    restart_vllm_runtime_fn: Any = _restart_vllm_runtime,
) -> Dict[str, Any]:
    settings = settings_obj or _get_settings()
    active_runtime = get_active_llm_runtime_fn()
    config = config_manager_obj.get_config(mask_secrets=False)
    runtime_local_id, _ = _resolve_runtime_for_rollback(
        active_runtime=active_runtime,
        settings_obj=settings,
    )

    if not runtime_local_id:
        return {
            "rolled_back": False,
            "reason": "runtime_not_local",
            "runtime_id": "",
        }

    if runtime_local_id == "onnx":
        return _rollback_onnx_adapter_deploy(
            config=config,
            settings_obj=settings,
            config_manager_obj=config_manager_obj,
            compute_llm_config_hash_fn=compute_llm_config_hash_fn,
            runtime_endpoint_for_hash_fn=runtime_endpoint_for_hash_fn,
        )

    runtime_local_id, previous_key, fallback_model = (
        _resolve_fallback_model_for_rollback(
            config=config,
            runtime_local_id=runtime_local_id,
        )
    )
    if not fallback_model:
        return {
            "rolled_back": False,
            "reason": "previous_model_missing",
            "runtime_id": runtime_local_id,
        }

    updates = _build_runtime_rollback_updates(
        mgr=mgr,
        runtime_local_id=runtime_local_id,
        previous_key=previous_key,
        fallback_model=fallback_model,
        resolve_local_runtime_model_path_by_name_fn=resolve_local_runtime_model_path_by_name_fn,
        settings_obj=settings,
    )
    endpoint = runtime_endpoint_for_hash_fn(runtime_local_id, settings_obj=settings)
    config_hash = compute_llm_config_hash_fn(runtime_local_id, endpoint, fallback_model)
    updates["LLM_CONFIG_HASH"] = config_hash
    config_manager_obj.update_config(updates)
    try:
        _apply_runtime_rollback_settings(
            runtime_local_id=runtime_local_id,
            fallback_model=fallback_model,
            config_hash=config_hash,
            updates=updates,
            settings_obj=settings,
            restart_vllm_runtime_fn=restart_vllm_runtime_fn,
        )
    except Exception:
        logger.warning("Failed to update SETTINGS during adapter chat rollback.")

    return {
        "rolled_back": True,
        "runtime_id": runtime_local_id,
        "chat_model": fallback_model,
        "config_hash": config_hash,
    }
