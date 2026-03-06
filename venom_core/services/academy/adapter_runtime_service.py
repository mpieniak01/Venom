"""Adapter runtime deploy/rollback service for Academy."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

from venom_core.services.config_manager import config_manager
from venom_core.services.system_llm_service import previous_model_key_for_server
from venom_core.utils.llm_runtime import compute_llm_config_hash, get_active_llm_runtime
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

from .adapter_metadata_service import (
    ADAPTER_NOT_FOUND_DETAIL,
    _require_trusted_adapter_base_model,
)
from .trainable_catalog_service import (
    _canonical_runtime_model_id,
    _resolve_local_runtime_id,
)

logger = get_logger(__name__)


def _get_settings() -> Any:
    from venom_core.config import SETTINGS

    return SETTINGS


def _resolve_runtime_for_adapter_deploy(
    runtime_id: str | None,
    *,
    get_active_llm_runtime_fn: Any = get_active_llm_runtime,
    settings_obj: Any | None = None,
) -> str:
    requested = (runtime_id or "").strip().lower()
    if requested:
        return requested
    active_runtime = get_active_llm_runtime_fn()
    active_provider = str(getattr(active_runtime, "provider", "") or "").strip().lower()
    if active_provider:
        return active_provider
    settings = settings_obj or _get_settings()
    fallback = str(getattr(settings, "ACTIVE_LLM_SERVER", "") or "").strip().lower()
    return fallback or "ollama"


def _runtime_endpoint_for_hash(
    runtime_id: str, *, settings_obj: Any | None = None
) -> str | None:
    settings = settings_obj or _get_settings()
    if runtime_id == "vllm":
        return str(getattr(settings, "VLLM_ENDPOINT", "")).strip() or None
    if runtime_id == "onnx":
        return None
    return build_http_url("localhost", 11434, "/v1")


def _first_runtime_with_previous_model(
    *, config: Dict[str, Any], candidates: tuple[str, ...]
) -> tuple[str | None, str]:
    for candidate_runtime in candidates:
        prev_value = str(
            config.get(previous_model_key_for_server(candidate_runtime)) or ""
        ).strip()
        if prev_value:
            return candidate_runtime, prev_value
    return None, ""


def _resolve_runtime_for_rollback(
    *,
    active_runtime: Any,
    config: Dict[str, Any],
) -> tuple[str, str]:
    runtime_candidate = (
        str(getattr(active_runtime, "provider", "") or "").strip().lower()
    )
    settings = _get_settings()
    runtime_candidate = (
        runtime_candidate
        or str(getattr(settings, "ACTIVE_LLM_SERVER", "") or "").strip().lower()
    )
    runtime_local_id = _resolve_local_runtime_id(runtime_candidate)
    if runtime_local_id is None:
        inferred_runtime, _ = _first_runtime_with_previous_model(
            config=config,
            candidates=("ollama", "vllm"),
        )
        runtime_local_id = inferred_runtime
    return runtime_local_id or "ollama", runtime_candidate


def _resolve_fallback_model_for_rollback(
    *,
    config: Dict[str, Any],
    runtime_local_id: str,
) -> tuple[str, str, str]:
    previous_key = previous_model_key_for_server(runtime_local_id)
    fallback_model = str(config.get(previous_key) or "").strip()
    if fallback_model:
        return runtime_local_id, previous_key, fallback_model
    inferred_runtime, inferred_model = _first_runtime_with_previous_model(
        config=config,
        candidates=("ollama", "vllm"),
    )
    if not inferred_runtime:
        return runtime_local_id, previous_key, ""
    return (
        inferred_runtime,
        previous_model_key_for_server(inferred_runtime),
        inferred_model,
    )


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
    if not (path / "config.json").exists():
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
    root = Path(getattr(settings, "REPO_ROOT", ".")).resolve()
    return root


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
        settings = settings_obj or _get_settings()
        academy_dir = Path(getattr(settings, "ACADEMY_MODELS_DIR", "")).resolve()
        search_dirs.append(academy_dir)
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
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
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
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "Missing dependencies required for vLLM adapter deploy. "
            "Install: pip install transformers peft torch"
        ) from exc

    has_cuda = bool(torch.cuda.is_available())
    model_kwargs: Dict[str, Any] = {
        "torch_dtype": torch.float16 if has_cuda else torch.float32,
    }
    if has_cuda:
        model_kwargs["device_map"] = "auto"
    else:
        model_kwargs["low_cpu_mem_usage"] = True

    try:
        base_model_obj = AutoModelForCausalLM.from_pretrained(
            base_model, **model_kwargs
        )
        peft_model = PeftModel.from_pretrained(base_model_obj, str(adapter_path))
        merged_model = peft_model.merge_and_unload()
        merged_model.save_pretrained(str(tmp_dir), safe_serialization=True)

        tokenizer_source = (
            str(adapter_path)
            if (adapter_path / "tokenizer.json").exists()
            else base_model
        )
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_source)
        tokenizer.save_pretrained(str(tmp_dir))
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
    requested_model = str(model_id or "").strip()
    if requested_model:
        return requested_model
    config_snapshot = config_manager.get_config(mask_secrets=False)
    return str(
        config_snapshot.get("LAST_MODEL_OLLAMA")
        or config_snapshot.get("LLM_MODEL_NAME")
        or ""
    ).strip()


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
) -> Dict[str, Any]:
    settings = settings_obj or _get_settings()
    models_dir = Path(settings.ACADEMY_MODELS_DIR).resolve()
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    adapter_path = adapter_dir / "adapter"
    if not adapter_path.exists():
        raise FileNotFoundError(ADAPTER_NOT_FOUND_DETAIL)
    base_model = _require_trusted_adapter_base_model(
        adapter_dir=adapter_dir,
        default_model=str(getattr(settings, "ACADEMY_DEFAULT_BASE_MODEL", "")).strip(),
    ).strip()
    if not base_model:
        raise RuntimeError("Adapter base model is empty; cannot deploy to vLLM")

    runtime_model_dir = build_vllm_runtime_model_from_adapter_fn(
        adapter_dir=adapter_dir,
        base_model=base_model,
    )
    if not is_runtime_model_dir_fn(runtime_model_dir):
        raise RuntimeError(
            f"Failed to prepare runtime-usable vLLM model from adapter: {runtime_model_dir}"
        )

    config = config_manager_obj.get_config(mask_secrets=False)
    last_model_key = "LAST_MODEL_VLLM"
    previous_model_key = previous_model_key_for_server("vllm")
    previous_model = str(
        config.get(last_model_key) or config.get("LLM_MODEL_NAME") or ""
    ).strip()
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
    if previous_model and previous_model != selected_model:
        updates[previous_model_key] = previous_model
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
) -> Dict[str, Any]:
    if runtime_local_id == "onnx":
        return {
            "deployed": False,
            "reason": f"runtime_not_supported:{runtime_local_id}",
            "runtime_id": runtime_local_id,
        }
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

    runtime_candidate = deps["resolve_runtime_for_adapter_deploy_fn"](
        runtime_id,
        get_active_llm_runtime_fn=deps["get_active_llm_runtime_fn"],
        settings_obj=settings,
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
    )
    if non_ollama_payload:
        return non_ollama_payload

    requested_model = _resolve_requested_runtime_model(model_id)

    models_dir = Path(settings.ACADEMY_MODELS_DIR).resolve()
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    adapter_base_model = deps["require_trusted_adapter_base_model_fn"](
        adapter_dir=adapter_dir,
        default_model=str(getattr(settings, "ACADEMY_DEFAULT_BASE_MODEL", "")).strip(),
    ).strip()
    if adapter_base_model and requested_model:
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
    deployed_model = mgr.create_ollama_modelfile(
        version_id=adapter_id,
        output_name=ollama_model_name,
    )
    if not deployed_model:
        raise RuntimeError("Failed to create Ollama model for adapter deployment")

    config = deps["config_manager_obj"].get_config(mask_secrets=False)
    last_model_key = "LAST_MODEL_OLLAMA"
    previous_model_key = previous_model_key_for_server(runtime_local_id)
    previous_model = str(
        config.get(last_model_key) or config.get("LLM_MODEL_NAME") or ""
    ).strip()
    selected_model = str(deployed_model)
    updates: Dict[str, Any] = {
        "ACTIVE_LLM_SERVER": runtime_local_id,
        "LLM_MODEL_NAME": selected_model,
        "HYBRID_LOCAL_MODEL": selected_model,
        last_model_key: selected_model,
    }
    if previous_model and previous_model != selected_model:
        updates[previous_model_key] = previous_model
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
        config=config,
    )

    if runtime_local_id == "onnx":
        return {
            "rolled_back": False,
            "reason": f"runtime_not_supported:{runtime_local_id}",
            "runtime_id": runtime_local_id,
        }

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
