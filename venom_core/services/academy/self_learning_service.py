"""Self-learning orchestration service for Academy."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Literal, Optional, cast

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

SelfLearningMode = Literal["llm_finetune", "rag_index"]
SelfLearningSource = Literal["docs", "docs_dev", "code"]
SelfLearningStatus = Literal[
    "pending",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
]
SelfLearningEmbeddingPolicy = Literal["strict", "allow_fallback"]

_ALLOWED_EXTENSIONS = {
    ".md",
    ".txt",
    ".rst",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
}
_BLOCKED_PATH_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "data",
    "test-results",
    "dist",
    "build",
    "__pycache__",
    ".next",
}
_RUN_LOG_LIMIT = 500
_CHUNK_SPLIT_THRESHOLD_RATIO = 0.6


_SOURCE_PATHS: dict[SelfLearningSource, tuple[str, ...]] = {
    "docs": ("docs",),
    "docs_dev": ("docs_dev",),
    "code": ("venom_core", "web-next", "scripts"),
}
_VALID_MODES: tuple[SelfLearningMode, ...] = ("llm_finetune", "rag_index")
_VALID_STATUSES: tuple[SelfLearningStatus, ...] = (
    "pending",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
)

_LOCAL_RUNTIME_IDS = ("vllm", "ollama", "onnx")
_BLOCKED_TRAINING_PROVIDERS = {
    "openai",
    "azure-openai",
    "anthropic",
    "google",
    "google-gemini",
    "ollama",
    "onnx",
}
_BLOCKED_TRAINING_NAME_MARKERS = ("gpt-", "claude", "gemini")
_VLLM_COMPATIBLE_PROVIDERS = {"huggingface", "unsloth", "hf", "config", "unknown"}
_DEFAULT_TRAINABLE_MODELS: tuple[tuple[str, str, str], ...] = (
    ("unsloth/Phi-3-mini-4k-instruct", "Phi-3 Mini 4K (Unsloth)", "unsloth"),
    ("unsloth/Phi-3.5-mini-instruct", "Phi-3.5 Mini (Unsloth)", "unsloth"),
    ("unsloth/Llama-3.2-1B-Instruct", "Llama 3.2 1B (Unsloth)", "unsloth"),
    ("unsloth/Llama-3.2-3B-Instruct", "Llama 3.2 3B (Unsloth)", "unsloth"),
    ("Qwen/Qwen2.5-Coder-3B-Instruct", "Qwen2.5 Coder 3B (HuggingFace)", "huggingface"),
    ("Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen2.5 Coder 7B (HuggingFace)", "huggingface"),
    ("google/gemma-3-4b-it", "Gemma 3 4B Instruct (HuggingFace)", "huggingface"),
)


class SelfLearningError(Exception):
    """Domain-level exception for self-learning runs."""


@dataclass
class RunLimits:
    max_file_size_kb: int = 256
    max_files: int = 1500
    max_total_size_mb: int = 200

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_kb * 1024

    @property
    def max_total_size_bytes(self) -> int:
        return self.max_total_size_mb * 1024 * 1024


@dataclass
class LlmConfig:
    base_model: Optional[str] = None
    lora_rank: int = 16
    learning_rate: float = 2e-4
    num_epochs: int = 3
    batch_size: int = 4
    max_seq_length: int = 2048


@dataclass
class RagConfig:
    collection: str = "default"
    category: str = "academy_self_learning"
    chunk_text: bool = False
    embedding_profile_id: str | None = None
    embedding_policy: SelfLearningEmbeddingPolicy = "strict"


@dataclass
class RunProgress:
    files_discovered: int = 0
    files_processed: int = 0
    chunks_created: int = 0
    records_created: int = 0
    indexed_vectors: int = 0


@dataclass
class SelfLearningRun:
    run_id: str
    mode: SelfLearningMode
    sources: list[SelfLearningSource]
    limits: RunLimits
    llm_config: LlmConfig
    rag_config: RagConfig
    dry_run: bool = False
    status: SelfLearningStatus = "pending"
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    progress: RunProgress = field(default_factory=RunProgress)
    artifacts: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["progress"] = asdict(self.progress)
        data["limits"] = asdict(self.limits)
        data["llm_config"] = asdict(self.llm_config)
        data["rag_config"] = asdict(self.rag_config)
        return data


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_valid_uuid(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return str(parsed) == value


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class SelfLearningService:
    """Orchestrates self-learning jobs for Academy."""

    def __init__(
        self,
        *,
        storage_dir: str,
        repo_root: str | None = None,
        vector_store: Any | None = None,
        gpu_habitat: Any | None = None,
        model_manager: Any | None = None,
        trainable_models_loader: Callable[[Any], Awaitable[list[Any]]] | None = None,
        is_model_trainable_fn: Callable[[str], bool] | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.repo_root = (
            Path(repo_root).resolve()
            if repo_root
            else Path(__file__).resolve().parents[3]
        )
        self.vector_store = vector_store
        self.gpu_habitat = gpu_habitat
        self.model_manager = model_manager
        self.trainable_models_loader = trainable_models_loader
        self.is_model_trainable_fn = is_model_trainable_fn
        self._runs: dict[str, SelfLearningRun] = {}
        self._pipeline_tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = threading.Lock()
        self._snapshot_lock = threading.Lock()
        self._manifest_lock = threading.Lock()
        self._runs_log_file = self.storage_dir / "runs.jsonl"
        self._index_manifest_file = self.storage_dir / "index_manifest.json"
        self._index_manifest = self._load_index_manifest()
        self._load_persisted_runs()

    def set_runtime_dependencies(
        self,
        *,
        vector_store: Any | None,
        gpu_habitat: Any | None,
        model_manager: Any | None = None,
        trainable_models_loader: Callable[[Any], Awaitable[list[Any]]] | None = None,
        is_model_trainable_fn: Callable[[str], bool] | None = None,
    ) -> None:
        """Refresh runtime-scoped dependencies after app startup wiring."""
        self.vector_store = vector_store
        self.gpu_habitat = gpu_habitat
        self.model_manager = model_manager
        if trainable_models_loader is not None:
            self.trainable_models_loader = trainable_models_loader
        if is_model_trainable_fn is not None:
            self.is_model_trainable_fn = is_model_trainable_fn

    def start_run(
        self,
        *,
        mode: SelfLearningMode,
        sources: list[SelfLearningSource],
        limits: dict[str, Any] | None = None,
        llm_config: dict[str, Any] | None = None,
        rag_config: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> str:
        self._validate_sources(sources)
        run_limits = self._parse_limits(limits)
        run_llm_config = self._parse_llm_config(llm_config)
        run_rag_config = self._parse_rag_config(rag_config)
        self._validate_mode_config(
            mode=mode,
            llm_config=run_llm_config,
            rag_config=run_rag_config,
        )

        run_id = str(uuid.uuid4())
        run = SelfLearningRun(
            run_id=run_id,
            mode=mode,
            sources=list(dict.fromkeys(sources)),
            limits=run_limits,
            llm_config=run_llm_config,
            rag_config=run_rag_config,
            dry_run=bool(dry_run),
            status="pending",
            created_at=_utc_now_iso(),
        )
        with self._lock:
            self._runs[run_id] = run
        self._append_run_snapshot(run)
        pipeline_task = asyncio.create_task(self._run_pipeline(run_id))
        with self._lock:
            self._pipeline_tasks[run_id] = pipeline_task
        pipeline_task.add_done_callback(
            lambda _: self._clear_pipeline_task_reference(run_id)
        )
        return run_id

    def get_status(self, run_id: str) -> dict[str, Any] | None:
        if not _is_valid_uuid(run_id):
            return None
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            return run.to_dict()

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            runs = list(self._runs.values())
        runs.sort(key=lambda item: item.created_at, reverse=True)
        return [run.to_dict() for run in runs[:limit]]

    def delete_run(self, run_id: str) -> bool:
        if not _is_valid_uuid(run_id):
            return False
        task_to_cancel: asyncio.Task[None] | None = None
        with self._lock:
            run = self._runs.pop(run_id, None)
            task_to_cancel = self._pipeline_tasks.pop(run_id, None)
        if run is None:
            return False
        if task_to_cancel is not None and not task_to_cancel.done():
            task_to_cancel.cancel()
        run_dir = self._run_dir(run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        return True

    def clear_all_runs(self) -> int:
        tasks_to_cancel: list[asyncio.Task[None]] = []
        with self._lock:
            run_ids = list(self._runs.keys())
            self._runs.clear()
            tasks_to_cancel = list(self._pipeline_tasks.values())
            self._pipeline_tasks.clear()
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
        for run_id in run_ids:
            run_dir = self._run_dir(run_id)
            if run_dir.exists():
                shutil.rmtree(run_dir, ignore_errors=True)
        return len(run_ids)

    def _clear_pipeline_task_reference(self, run_id: str) -> None:
        with self._lock:
            self._pipeline_tasks.pop(run_id, None)

    def _validate_sources(self, sources: Iterable[str]) -> None:
        if not sources:
            raise ValueError("At least one source must be selected")
        invalid = [s for s in sources if s not in _SOURCE_PATHS]
        if invalid:
            raise ValueError(f"Unsupported sources: {invalid}")

    def _parse_limits(self, payload: dict[str, Any] | None) -> RunLimits:
        data = payload or {}
        return RunLimits(
            max_file_size_kb=max(
                16, min(4096, _safe_int(data.get("max_file_size_kb"), 256))
            ),
            max_files=max(1, min(10000, _safe_int(data.get("max_files"), 1500))),
            max_total_size_mb=max(
                1,
                min(4096, _safe_int(data.get("max_total_size_mb"), 200)),
            ),
        )

    def _parse_llm_config(self, payload: dict[str, Any] | None) -> LlmConfig:
        data = payload or {}
        return LlmConfig(
            base_model=(str(data.get("base_model")).strip() or None)
            if data.get("base_model")
            else None,
            lora_rank=max(4, min(64, _safe_int(data.get("lora_rank"), 16))),
            learning_rate=float(data.get("learning_rate", 2e-4)),
            num_epochs=max(1, min(20, _safe_int(data.get("num_epochs"), 3))),
            batch_size=max(1, min(32, _safe_int(data.get("batch_size"), 4))),
            max_seq_length=max(
                256,
                min(8192, _safe_int(data.get("max_seq_length"), 2048)),
            ),
        )

    def _parse_rag_config(self, payload: dict[str, Any] | None) -> RagConfig:
        data = payload or {}
        collection = str(data.get("collection") or "default").strip() or "default"
        category = (
            str(data.get("category") or "academy_self_learning").strip()
            or "academy_self_learning"
        )
        chunk_text = bool(data.get("chunk_text", False))
        embedding_profile_id = data.get("embedding_profile_id")
        embedding_policy = str(data.get("embedding_policy") or "strict").strip().lower()
        if embedding_policy not in {"strict", "allow_fallback"}:
            embedding_policy = "strict"
        return RagConfig(
            collection=collection[:64],
            category=category[:64],
            chunk_text=chunk_text,
            embedding_profile_id=(
                str(embedding_profile_id).strip()[:128]
                if embedding_profile_id
                else None
            ),
            embedding_policy=embedding_policy,  # type: ignore[arg-type]
        )

    def _validate_mode_config(
        self,
        *,
        mode: SelfLearningMode,
        llm_config: LlmConfig,
        rag_config: RagConfig,
    ) -> None:
        if mode == "llm_finetune":
            if not llm_config.base_model:
                raise ValueError(
                    "llm_config.base_model is required for llm_finetune mode"
                )
            is_trainable: bool
            if self.is_model_trainable_fn is not None:
                try:
                    is_trainable = bool(
                        self.is_model_trainable_fn(llm_config.base_model)
                    )
                except Exception as exc:
                    logger.warning(
                        "is_model_trainable_fn failed for '%s': %s",
                        llm_config.base_model,
                        exc,
                    )
                    is_trainable = self._is_trainable_model_candidate(
                        llm_config.base_model
                    )
            else:
                is_trainable = self._is_trainable_model_candidate(llm_config.base_model)
            if not is_trainable:
                raise ValueError(
                    f"Model '{llm_config.base_model}' is not trainable in Academy"
                )
        if mode == "rag_index" and not rag_config.embedding_profile_id:
            raise ValueError(
                "rag_config.embedding_profile_id is required for rag_index mode"
            )

    @staticmethod
    def _is_trainable_model_candidate(
        model_id: str,
        provider: str | None = None,
    ) -> bool:
        candidate = model_id.strip()
        if not candidate:
            return False
        normalized = candidate.lower()
        provider_lc = (provider or "").strip().lower()
        if provider_lc in _BLOCKED_TRAINING_PROVIDERS:
            return False
        if any(marker in normalized for marker in _BLOCKED_TRAINING_NAME_MARKERS):
            return False
        if normalized.endswith(".onnx") or normalized.endswith(".gguf"):
            return False
        return "/" in candidate

    async def get_capabilities(self) -> dict[str, Any]:
        trainable_models = await self._load_trainable_models()
        embedding_profiles = self._embedding_profiles()
        default_base_model = next(
            (
                item["model_id"]
                for item in trainable_models
                if bool(item.get("recommended"))
            ),
            trainable_models[0]["model_id"] if trainable_models else None,
        )
        default_embedding_profile_id = (
            embedding_profiles[0]["profile_id"] if embedding_profiles else None
        )
        return {
            "trainable_models": trainable_models,
            "embedding_profiles": embedding_profiles,
            "default_base_model": default_base_model,
            "default_embedding_profile_id": default_embedding_profile_id,
        }

    async def _load_trainable_models(self) -> list[dict[str, Any]]:
        from_loader = await self._load_trainable_models_from_loader()
        if from_loader:
            return from_loader

        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        local_models = await self._fetch_local_models()
        default_model = str(
            getattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "") or ""
        ).strip()

        available_runtime_ids = self._resolve_available_runtime_ids(local_models)
        default_runtime_compatibility = self._resolve_runtime_compatibility(
            provider="huggingface",
            available_runtime_ids=available_runtime_ids,
        )
        default_recommended_runtime = self._resolve_recommended_runtime(
            default_runtime_compatibility
        )

        self._append_local_trainable_models(
            result=result,
            seen=seen,
            local_models=local_models,
            default_model=default_model,
            available_runtime_ids=available_runtime_ids,
        )
        self._append_default_trainable_models(
            result=result,
            seen=seen,
            default_model=default_model,
            default_runtime_compatibility=default_runtime_compatibility,
            default_recommended_runtime=default_recommended_runtime,
        )
        self._append_config_default_trainable_model(
            result=result,
            seen=seen,
            default_model=default_model,
            default_runtime_compatibility=default_runtime_compatibility,
            default_recommended_runtime=default_recommended_runtime,
        )

        result.sort(
            key=lambda item: (
                not bool(item.get("recommended")),
                str(item.get("label") or item.get("model_id") or "").lower(),
            )
        )
        return result

    async def _load_trainable_models_from_loader(self) -> list[dict[str, Any]]:
        if self.trainable_models_loader is None:
            return []
        try:
            loaded = await self.trainable_models_loader(self.model_manager)
            return self._normalize_trainable_models_payload(loaded)
        except Exception as exc:
            logger.warning(
                "trainable_models_loader failed in self-learning: %s",
                exc,
            )
            return []

    async def _fetch_local_models(self) -> list[dict[str, Any]]:
        if self.model_manager is None or not hasattr(
            self.model_manager, "list_local_models"
        ):
            return []
        try:
            fetched = await self.model_manager.list_local_models()
            if isinstance(fetched, list):
                return [item for item in fetched if isinstance(item, dict)]
        except Exception as exc:
            logger.warning("Failed to load local models for self-learning: %s", exc)
        return []

    def _append_local_trainable_models(
        self,
        *,
        result: list[dict[str, Any]],
        seen: set[str],
        local_models: list[dict[str, Any]],
        default_model: str,
        available_runtime_ids: list[str],
    ) -> None:
        for model in local_models:
            model_id = str(model.get("name") or "").strip()
            provider = str(model.get("provider") or model.get("source") or "unknown")
            if not model_id or model_id in seen:
                continue
            if not self._is_trainable_model_candidate(model_id, provider):
                continue
            runtime_compatibility = self._resolve_runtime_compatibility(
                provider=provider,
                available_runtime_ids=available_runtime_ids,
                model_metadata=model,
            )
            result.append(
                {
                    "model_id": model_id,
                    "label": f"{model_id} ({provider})",
                    "provider": provider,
                    "recommended": model_id == default_model,
                    "runtime_compatibility": runtime_compatibility,
                    "recommended_runtime": self._resolve_recommended_runtime(
                        runtime_compatibility
                    ),
                }
            )
            seen.add(model_id)

    @staticmethod
    def _append_default_trainable_models(
        *,
        result: list[dict[str, Any]],
        seen: set[str],
        default_model: str,
        default_runtime_compatibility: dict[str, bool],
        default_recommended_runtime: str | None,
    ) -> None:
        for model_id, label, provider in _DEFAULT_TRAINABLE_MODELS:
            if model_id in seen:
                continue
            result.append(
                {
                    "model_id": model_id,
                    "label": label,
                    "provider": provider,
                    "recommended": model_id == default_model,
                    "runtime_compatibility": dict(default_runtime_compatibility),
                    "recommended_runtime": default_recommended_runtime,
                }
            )
            seen.add(model_id)

    def _append_config_default_trainable_model(
        self,
        *,
        result: list[dict[str, Any]],
        seen: set[str],
        default_model: str,
        default_runtime_compatibility: dict[str, bool],
        default_recommended_runtime: str | None,
    ) -> None:
        if (
            not default_model
            or default_model in seen
            or not self._is_trainable_model_candidate(default_model)
        ):
            return
        result.append(
            {
                "model_id": default_model,
                "label": f"{default_model} (default)",
                "provider": "config",
                "recommended": True,
                "runtime_compatibility": dict(default_runtime_compatibility),
                "recommended_runtime": default_recommended_runtime,
            }
        )

    @staticmethod
    def _normalize_trainable_models_payload(payload: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in payload:
            if hasattr(item, "model_dump"):
                dumped = item.model_dump()
            elif isinstance(item, dict):
                dumped = dict(item)
            else:
                continue
            model_id = str(dumped.get("model_id") or "").strip()
            if not model_id:
                continue
            if dumped.get("trainable") is False:
                continue
            normalized.append(
                {
                    "model_id": model_id,
                    "label": str(dumped.get("label") or model_id),
                    "provider": str(dumped.get("provider") or "unknown"),
                    "recommended": bool(dumped.get("recommended", False)),
                    "runtime_compatibility": dict(
                        dumped.get("runtime_compatibility") or {}
                    ),
                    "recommended_runtime": dumped.get("recommended_runtime"),
                }
            )
        return normalized

    @staticmethod
    def _resolve_available_runtime_ids(local_models: list[dict[str, Any]]) -> list[str]:
        discovered: set[str] = set()
        for model in local_models:
            for candidate in (
                str(model.get("runtime") or ""),
                str(model.get("provider") or ""),
                str(model.get("source") or ""),
            ):
                normalized = candidate.strip().lower()
                if normalized in _LOCAL_RUNTIME_IDS:
                    discovered.add(normalized)
        return sorted(discovered)

    @staticmethod
    def _resolve_runtime_compatibility(
        *,
        provider: str,
        available_runtime_ids: list[str],
        model_metadata: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        compatibility = dict.fromkeys(_LOCAL_RUNTIME_IDS, False)
        preferred = SelfLearningService._preferred_runtime_ids(
            provider=provider,
            model_metadata=model_metadata,
        )
        for runtime in preferred:
            if runtime in compatibility:
                compatibility[runtime] = True
        SelfLearningService._apply_runtime_availability_filter(
            compatibility=compatibility,
            available_runtime_ids=available_runtime_ids,
        )
        return compatibility

    @staticmethod
    def _preferred_runtime_ids(
        *,
        provider: str,
        model_metadata: dict[str, Any] | None = None,
    ) -> set[str]:
        runtime_hint = (
            str(model_metadata.get("runtime") or "").strip().lower()
            if model_metadata
            else ""
        )
        provider_lc = provider.strip().lower()
        source_hint = (
            str(model_metadata.get("source") or "").strip().lower()
            if model_metadata
            else ""
        )
        model_type = (
            str(model_metadata.get("type") or "").strip().lower()
            if model_metadata
            else ""
        )
        preferred: set[str] = set()
        if provider_lc == "onnx" or runtime_hint == "onnx" or model_type == "onnx":
            preferred.add("onnx")
        if provider_lc == "ollama" or source_hint == "ollama":
            preferred.add("ollama")
        if provider_lc in _VLLM_COMPATIBLE_PROVIDERS:
            preferred.add("vllm")
        if runtime_hint in _LOCAL_RUNTIME_IDS:
            preferred.add(runtime_hint)
        if not preferred:
            preferred.add("vllm")
        return preferred

    @staticmethod
    def _apply_runtime_availability_filter(
        *,
        compatibility: dict[str, bool],
        available_runtime_ids: list[str],
    ) -> None:
        if available_runtime_ids:
            for runtime in list(compatibility.keys()):
                if runtime not in available_runtime_ids and compatibility[runtime]:
                    compatibility[runtime] = runtime == "vllm"

    @staticmethod
    def _resolve_recommended_runtime(
        runtime_compatibility: dict[str, bool],
    ) -> str | None:
        for runtime in _LOCAL_RUNTIME_IDS:
            if runtime_compatibility.get(runtime):
                return runtime
        return None

    def _embedding_profiles(self) -> list[dict[str, Any]]:
        state = self._embedding_runtime_state()
        if state["profile_id"] is None:
            return []
        return [state]

    def _embedding_runtime_state(self) -> dict[str, Any]:
        if self.vector_store is None:
            return {
                "profile_id": None,
                "provider": "none",
                "model": "unavailable",
                "dimension": None,
                "healthy": False,
                "fallback_active": False,
                "details": {"reason": "vector_store_unavailable"},
            }

        embedding_service = getattr(self.vector_store, "embedding_service", None)
        if embedding_service is None:
            return {
                "profile_id": None,
                "provider": "none",
                "model": "unavailable",
                "dimension": None,
                "healthy": False,
                "fallback_active": False,
                "details": {"reason": "embedding_service_unavailable"},
            }

        service_type = str(
            getattr(embedding_service, "service_type", "unknown") or "unknown"
        )
        fallback_active = bool(
            getattr(embedding_service, "_local_fallback_mode", False)
        )
        model_name_map = {
            "openai": "text-embedding-3-small",
        }
        if service_type == "local":
            model_name = str(
                getattr(
                    embedding_service,
                    "local_model_name",
                    "sentence-transformers/all-MiniLM-L6-v2",
                )
            )
        else:
            model_name = model_name_map.get(service_type, f"{service_type}:default")
        profile_id = f"{service_type}:default"
        try:
            dimension = int(getattr(embedding_service, "embedding_dimension"))
        except Exception as exc:
            return {
                "profile_id": profile_id,
                "provider": service_type,
                "model": model_name,
                "dimension": None,
                "healthy": False,
                "fallback_active": fallback_active,
                "details": {"reason": "embedding_dimension_error", "error": str(exc)},
            }

        return {
            "profile_id": profile_id,
            "provider": service_type,
            "model": model_name,
            "dimension": dimension,
            "healthy": True,
            "fallback_active": fallback_active,
            "details": {},
        }

    async def _run_pipeline(self, run_id: str) -> None:
        await asyncio.sleep(0)
        run = self._get_run(run_id)
        if run is None:
            return

        self._set_run_state(run, status="running", started_at=_utc_now_iso())
        warnings_count = 0
        try:
            discovered_files = self._discover_files(run)
            run.progress.files_discovered = len(discovered_files)
            self._add_log(run, f"Discovered files: {len(discovered_files)}")

            extracted_files: list[tuple[Path, str, str, str, SelfLearningSource]] = []
            for file_path, source in discovered_files:
                extract_result = self._extract_file_text(run, file_path)
                if extract_result is None:
                    warnings_count += 1
                    continue
                text, file_hash, rel_path = extract_result
                extracted_files.append((file_path, text, file_hash, rel_path, source))

            if not extracted_files:
                run.status = "completed_with_warnings"
                run.finished_at = _utc_now_iso()
                run.error_message = "No files processed after filtering"
                self._add_log(run, "No eligible files after filtering.")
                self._append_run_snapshot(run)
                return

            chunks = self._chunk_extracted_files(extracted_files)
            run.progress.chunks_created = len(chunks)
            self._add_log(run, f"Chunks created: {len(chunks)}")

            if run.mode == "llm_finetune":
                self._run_llm_finetune(run, chunks)
            elif run.mode == "rag_index":
                self._run_rag_index(run, chunks, extracted_files)
            else:
                raise SelfLearningError(f"Unsupported mode: {run.mode}")

            run.finished_at = _utc_now_iso()
            if warnings_count > 0 and run.status != "failed":
                run.status = "completed_with_warnings"
            elif run.status != "failed":
                run.status = "completed"
            self._append_run_snapshot(run)
        except Exception as exc:
            logger.exception("Self-learning run failed: %s", run_id)
            run.status = "failed"
            run.finished_at = _utc_now_iso()
            run.error_message = str(exc)
            self._add_log(run, f"Run failed: {exc}")
            self._append_run_snapshot(run)

    def _run_llm_finetune(
        self,
        run: SelfLearningRun,
        chunks: list[dict[str, Any]],
    ) -> None:
        run_dir = self._run_dir(run.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = run_dir / "dataset.jsonl"

        records = [
            {
                "instruction": f"Learn repository knowledge from file: {chunk['path']}",
                "input": chunk["text"],
                "output": chunk["text"],
            }
            for chunk in chunks
        ]

        with dataset_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        run.progress.records_created = len(records)
        run.artifacts["dataset_path"] = str(dataset_path)
        self._add_log(run, f"Dataset created: {dataset_path}")

        if run.dry_run:
            self._add_log(run, "Dry run enabled; training startup skipped.")
            return

        habitat = self.gpu_habitat
        if habitat is None:
            raise SelfLearningError("GPUHabitat is not available for fine-tuning")

        base_model = run.llm_config.base_model or SETTINGS.ACADEMY_DEFAULT_BASE_MODEL
        run.artifacts["selected_base_model"] = base_model
        output_dir = Path(SETTINGS.ACADEMY_MODELS_DIR) / f"self_learning_{run.run_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        job_info = habitat.run_training_job(
            dataset_path=str(dataset_path),
            base_model=base_model,
            output_dir=str(output_dir),
            lora_rank=run.llm_config.lora_rank,
            learning_rate=run.llm_config.learning_rate,
            num_epochs=run.llm_config.num_epochs,
            max_seq_length=run.llm_config.max_seq_length,
            batch_size=run.llm_config.batch_size,
            job_name=f"self_learning_{run.run_id}",
        )
        training_job_id = str(job_info.get("job_name") or f"self_learning_{run.run_id}")
        run.artifacts["training_job_id"] = training_job_id
        run.artifacts["training_output_dir"] = str(output_dir)
        self._add_log(run, f"Training job started: {training_job_id}")

    def _run_rag_index(
        self,
        run: SelfLearningRun,
        chunks: list[dict[str, Any]],
        extracted_files: list[tuple[Path, str, str, str, SelfLearningSource]],
    ) -> None:
        if run.dry_run:
            run.progress.indexed_vectors = len(chunks)
            self._add_log(run, "Dry run enabled; vector index upsert skipped.")
            return

        if self.vector_store is None:
            raise SelfLearningError("VectorStore is not available for RAG indexing")

        embedding_state = self._embedding_runtime_state()
        selected_profile = run.rag_config.embedding_profile_id or ""
        if selected_profile != embedding_state.get("profile_id"):
            raise SelfLearningError(f"Unknown embedding profile: {selected_profile}")
        if not bool(embedding_state.get("healthy")):
            raise SelfLearningError("Embedding runtime is unhealthy")
        if run.rag_config.embedding_policy == "strict" and bool(
            embedding_state.get("fallback_active")
        ):
            raise SelfLearningError(
                "Embedding runtime uses fallback mode and strict policy is enabled"
            )

        run.artifacts["embedding_profile"] = {
            "profile_id": selected_profile,
            "provider": embedding_state.get("provider"),
            "model": embedding_state.get("model"),
            "dimension": embedding_state.get("dimension"),
            "fallback_active": embedding_state.get("fallback_active"),
            "policy": run.rag_config.embedding_policy,
        }

        indexed_vectors = 0
        newly_indexed_file_keys: set[str] = set()
        eligible_keys = {
            f"{file_hash}:{rel_path}"
            for _, _, file_hash, rel_path, _ in extracted_files
        }

        for chunk in chunks:
            file_key = f"{chunk['sha256']}:{chunk['path']}"
            if file_key in self._index_manifest:
                continue

            metadata = {
                "source": chunk["source"],
                "path": chunk["path"],
                "sha256": chunk["sha256"],
                "run_id": run.run_id,
                "chunk_index": chunk["chunk_index"],
                "mode": run.mode,
                "category": run.rag_config.category,
            }
            upsert_result = self.vector_store.upsert(
                text=chunk["text"],
                metadata=metadata,
                collection_name=run.rag_config.collection,
                chunk_text=run.rag_config.chunk_text,
            )
            indexed_vectors += int(upsert_result.get("chunks_count", 0))
            newly_indexed_file_keys.add(file_key)

        # Mark file keys that were successfully indexed in this run.
        with self._manifest_lock:
            self._index_manifest.update(newly_indexed_file_keys & eligible_keys)
            self._save_index_manifest_unlocked()

        run.progress.indexed_vectors = indexed_vectors
        run.artifacts["collection"] = run.rag_config.collection
        run.artifacts["indexed_file_keys"] = len(newly_indexed_file_keys)
        self._add_log(run, f"Indexed vectors: {indexed_vectors}")

    def _discover_files(
        self,
        run: SelfLearningRun,
    ) -> list[tuple[Path, SelfLearningSource]]:
        allowed_roots = self._resolve_source_roots(run.sources)
        if not allowed_roots:
            raise SelfLearningError("No valid source roots available")

        max_files = run.limits.max_files
        max_file_size = run.limits.max_file_size_bytes
        max_total_size = run.limits.max_total_size_bytes
        total_size = 0
        collected: list[tuple[Path, SelfLearningSource]] = []

        for source, root in allowed_roots:
            for path in self._iter_candidate_paths(root):
                if len(collected) >= max_files:
                    self._add_log(run, "Reached max_files limit.")
                    return collected
                decision, size = self._evaluate_candidate_path(
                    run=run,
                    path=path,
                    max_file_size=max_file_size,
                    max_total_size=max_total_size,
                    current_total_size=total_size,
                )
                if decision == "collect":
                    total_size += size
                    collected.append((path.resolve(), source))
                if decision == "limit_total":
                    return collected
        return collected

    def _iter_candidate_paths(self, root: Path) -> Iterable[Path]:
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _BLOCKED_PATH_PARTS]
            if self._contains_blocked_part(Path(current_root)):
                continue
            for file_name in files:
                yield Path(current_root) / file_name

    def _evaluate_candidate_path(
        self,
        *,
        run: SelfLearningRun,
        path: Path,
        max_file_size: int,
        max_total_size: int,
        current_total_size: int,
    ) -> tuple[Literal["collect", "skip", "limit_total"], int]:
        if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
            return "skip", 0
        if not self._is_path_within_repo(path):
            self._add_log(run, f"Skipped outside repo path: {path}")
            return "skip", 0
        if self._contains_blocked_part(path):
            return "skip", 0
        try:
            size = path.stat().st_size
        except OSError:
            return "skip", 0
        if size <= 0:
            return "skip", 0
        if size > max_file_size:
            self._add_log(run, f"Skipped oversize file: {path}")
            return "skip", 0
        if current_total_size + size > max_total_size:
            self._add_log(run, "Reached max_total_size limit.")
            return "limit_total", 0
        return "collect", size

    def _extract_file_text(
        self,
        run: SelfLearningRun,
        file_path: Path,
    ) -> tuple[str, str, str] | None:
        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            self._add_log(run, f"Failed to read file {file_path}: {exc}")
            return None

        if b"\x00" in raw:
            self._add_log(run, f"Skipped binary file: {file_path}")
            return None

        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None

        run.progress.files_processed += 1
        file_hash = _sha256_bytes(raw)
        rel_path = str(file_path.resolve().relative_to(self.repo_root))
        return text, file_hash, rel_path

    def _chunk_extracted_files(
        self,
        extracted_files: list[tuple[Path, str, str, str, SelfLearningSource]],
    ) -> list[dict[str, Any]]:
        chunk_size = 1000
        overlap = 120
        chunks: list[dict[str, Any]] = []

        for _path, text, file_hash, rel_path, source in extracted_files:
            file_chunks = self._chunk_text(text, chunk_size=chunk_size, overlap=overlap)
            for idx, chunk in enumerate(file_chunks):
                if not chunk.strip():
                    continue
                chunks.append(
                    {
                        "text": chunk,
                        "sha256": file_hash,
                        "path": rel_path,
                        "source": source,
                        "chunk_index": idx,
                    }
                )
        return chunks

    @staticmethod
    def _chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
        if len(text) <= chunk_size:
            return [text]
        items: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end]
            if end < len(text):
                split_at = max(chunk.rfind("\n\n"), chunk.rfind("\n"), chunk.rfind(" "))
                if split_at > int(chunk_size * _CHUNK_SPLIT_THRESHOLD_RATIO):
                    chunk = chunk[:split_at]
                    end = start + len(chunk)
            items.append(chunk.strip())
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return [item for item in items if item]

    def _resolve_source_roots(
        self,
        sources: Iterable[SelfLearningSource],
    ) -> list[tuple[SelfLearningSource, Path]]:
        roots: list[tuple[SelfLearningSource, Path]] = []
        for source in sources:
            for rel_path in _SOURCE_PATHS[source]:
                candidate = (self.repo_root / rel_path).resolve()
                if (
                    candidate.exists()
                    and candidate.is_dir()
                    and self._is_path_within_repo(candidate)
                ):
                    roots.append((source, candidate))
        return roots

    def _run_dir(self, run_id: str) -> Path:
        if not _is_valid_uuid(run_id):
            raise ValueError("Invalid run_id")
        run_dir = (self.storage_dir / run_id).resolve()
        try:
            run_dir.relative_to(self.storage_dir)
        except ValueError as exc:
            raise ValueError("Run path escapes storage_dir") from exc
        return run_dir

    def _get_run(self, run_id: str) -> SelfLearningRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def _set_run_state(self, run: SelfLearningRun, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(run, key, value)
        self._append_run_snapshot(run)

    def _add_log(self, run: SelfLearningRun, message: str) -> None:
        run.logs.append(message)
        if len(run.logs) > _RUN_LOG_LIMIT:
            run.logs[:] = run.logs[-_RUN_LOG_LIMIT:]

    def _append_run_snapshot(self, run: SelfLearningRun) -> None:
        snapshot = run.to_dict()
        with self._snapshot_lock:
            with self._runs_log_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    def _load_persisted_runs(self) -> None:
        if not self._runs_log_file.exists():
            return
        loaded: dict[str, SelfLearningRun] = {}
        with self._runs_log_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                run_id = str(payload.get("run_id") or "")
                if not _is_valid_uuid(run_id):
                    continue
                loaded[run_id] = self._run_from_payload(payload)
        with self._lock:
            self._runs.update(loaded)

    def _run_from_payload(self, payload: dict[str, Any]) -> SelfLearningRun:
        progress = payload.get("progress") or {}
        limits = payload.get("limits") or {}
        llm_cfg = payload.get("llm_config") or {}
        rag_cfg = payload.get("rag_config") or {}
        return SelfLearningRun(
            run_id=str(payload.get("run_id", "")),
            mode=self._coerce_mode(payload.get("mode")),
            sources=self._coerce_sources(payload.get("sources")),
            limits=RunLimits(
                max_file_size_kb=_safe_int(limits.get("max_file_size_kb"), 256),
                max_files=_safe_int(limits.get("max_files"), 1500),
                max_total_size_mb=_safe_int(limits.get("max_total_size_mb"), 200),
            ),
            llm_config=LlmConfig(
                base_model=llm_cfg.get("base_model"),
                lora_rank=_safe_int(llm_cfg.get("lora_rank"), 16),
                learning_rate=float(llm_cfg.get("learning_rate", 2e-4)),
                num_epochs=_safe_int(llm_cfg.get("num_epochs"), 3),
                batch_size=_safe_int(llm_cfg.get("batch_size"), 4),
                max_seq_length=_safe_int(llm_cfg.get("max_seq_length"), 2048),
            ),
            rag_config=RagConfig(
                collection=str(rag_cfg.get("collection") or "default"),
                category=str(rag_cfg.get("category") or "academy_self_learning"),
                chunk_text=bool(rag_cfg.get("chunk_text", False)),
                embedding_profile_id=(
                    str(rag_cfg.get("embedding_profile_id")).strip()[:128]
                    if rag_cfg.get("embedding_profile_id")
                    else None
                ),
                embedding_policy=(
                    "allow_fallback"
                    if str(rag_cfg.get("embedding_policy") or "strict").strip().lower()
                    == "allow_fallback"
                    else "strict"
                ),
            ),
            dry_run=bool(payload.get("dry_run", False)),
            status=self._coerce_status(payload.get("status")),
            created_at=str(payload.get("created_at", "")),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            progress=RunProgress(
                files_discovered=_safe_int(progress.get("files_discovered"), 0),
                files_processed=_safe_int(progress.get("files_processed"), 0),
                chunks_created=_safe_int(progress.get("chunks_created"), 0),
                records_created=_safe_int(progress.get("records_created"), 0),
                indexed_vectors=_safe_int(progress.get("indexed_vectors"), 0),
            ),
            artifacts=dict(payload.get("artifacts") or {}),
            logs=list(payload.get("logs") or []),
            error_message=payload.get("error_message"),
        )

    @staticmethod
    def _coerce_mode(value: Any) -> SelfLearningMode:
        candidate = str(value or "rag_index")
        if candidate in _VALID_MODES:
            return cast(SelfLearningMode, candidate)
        return "rag_index"

    @staticmethod
    def _coerce_status(value: Any) -> SelfLearningStatus:
        candidate = str(value or "failed")
        if candidate in _VALID_STATUSES:
            return cast(SelfLearningStatus, candidate)
        return "failed"

    @staticmethod
    def _coerce_sources(value: Any) -> list[SelfLearningSource]:
        if not isinstance(value, list):
            return []
        return [
            cast(SelfLearningSource, item) for item in value if item in _SOURCE_PATHS
        ]

    def _load_index_manifest(self) -> set[str]:
        if not self._index_manifest_file.exists():
            return set()
        try:
            payload = json.loads(self._index_manifest_file.read_text(encoding="utf-8"))
        except Exception:
            return set()
        if not isinstance(payload, list):
            return set()
        return {str(item) for item in payload}

    def _save_index_manifest(self) -> None:
        with self._manifest_lock:
            self._save_index_manifest_unlocked()

    def _save_index_manifest_unlocked(self) -> None:
        tmp_file = self._index_manifest_file.with_suffix(".tmp")
        payload = json.dumps(sorted(self._index_manifest), ensure_ascii=False, indent=2)
        tmp_file.write_text(payload, encoding="utf-8")
        tmp_file.replace(self._index_manifest_file)

    def _is_path_within_repo(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.repo_root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _contains_blocked_part(path: Path) -> bool:
        return any(part in _BLOCKED_PATH_PARTS for part in path.parts)
