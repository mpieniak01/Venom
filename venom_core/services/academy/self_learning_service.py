"""Self-learning orchestration service for Academy."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Literal, Optional, cast

import psutil

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

SelfLearningMode = Literal["llm_finetune", "rag_index"]
SelfLearningSource = Literal["docs", "docs_en", "docs_pl", "docs_dev", "code"]
SelfLearningDatasetStrategy = Literal[
    "reconstruct",
    "qa_from_docs",
    "repo_tasks_basic",
]
SelfLearningTaskMixPreset = Literal["balanced", "qa-heavy", "repair-heavy"]
SelfLearningStatus = Literal[
    "pending",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
]
SelfLearningEmbeddingPolicy = Literal["strict", "allow_fallback"]
SelfLearningRagChunkingMode = Literal["plain", "code_aware"]
SelfLearningRagRetrievalMode = Literal["vector", "hybrid"]

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
_MIN_DATASET_RECORDS = 3
_MIN_RECORD_INPUT_CHARS = 20
_MIN_RECORD_OUTPUT_CHARS = 24
_TRAINING_STATUS_POLL_INTERVAL_SECONDS = 1.0
_TRAINING_TIMEOUT_MIN_SECONDS = 300
_TRAINING_TIMEOUT_MAX_SECONDS = 7200
_LOW_RAM_AVAILABLE_GB = 8.0
_CRITICAL_RAM_AVAILABLE_GB = 2.0
_CRITICAL_RAM_USAGE_PERCENT = 92.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


_SOURCE_PATHS: dict[SelfLearningSource, tuple[str, ...]] = {
    "docs": ("docs",),
    "docs_en": ("docs",),
    "docs_pl": ("docs/PL",),
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
_VALID_DATASET_STRATEGIES: tuple[SelfLearningDatasetStrategy, ...] = (
    "reconstruct",
    "qa_from_docs",
    "repo_tasks_basic",
)
_VALID_TASK_MIX_PRESETS: tuple[SelfLearningTaskMixPreset, ...] = (
    "balanced",
    "qa-heavy",
    "repair-heavy",
)
_VALID_RAG_CHUNKING_MODES: tuple[SelfLearningRagChunkingMode, ...] = (
    "plain",
    "code_aware",
)
_VALID_RAG_RETRIEVAL_MODES: tuple[SelfLearningRagRetrievalMode, ...] = (
    "vector",
    "hybrid",
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
_LOCAL_EMBEDDING_PROFILES: tuple[tuple[str, int], ...] = (
    ("sentence-transformers/all-MiniLM-L6-v2", 384),
    ("intfloat/multilingual-e5-base", 768),
)


class SelfLearningError(Exception):
    """Domain-level exception for self-learning runs."""


@dataclass
class RunLimits:
    max_file_size_kb: int = 128
    max_files: int = 300
    max_total_size_mb: int = 32

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_kb * 1024

    @property
    def max_total_size_bytes(self) -> int:
        return self.max_total_size_mb * 1024 * 1024


@dataclass
class LlmConfig:
    base_model: Optional[str] = None
    runtime_id: Optional[str] = None
    dataset_strategy: SelfLearningDatasetStrategy = "reconstruct"
    task_mix_preset: SelfLearningTaskMixPreset = "balanced"
    lora_rank: int = 8
    learning_rate: float = 2e-4
    num_epochs: int = 2
    batch_size: int = 1
    max_seq_length: int = 1024


@dataclass
class RagConfig:
    collection: str = "default"
    category: str = "academy_self_learning"
    chunk_text: bool = False
    chunking_mode: SelfLearningRagChunkingMode = "plain"
    retrieval_mode: SelfLearningRagRetrievalMode = "vector"
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
        self._runtime_log_cache: dict[str, list[str]] = {}
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
        self._apply_mode_defaults(
            mode=mode,
            llm_config=run_llm_config,
            rag_config=run_rag_config,
        )
        self._validate_mode_config(
            mode=mode,
            llm_config=run_llm_config,
            rag_config=run_rag_config,
        )
        if mode == "llm_finetune":
            self._validate_llm_finetune_runtime_preflight(dry_run=bool(dry_run))

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
        run.artifacts["repo_commit_sha"] = self._resolve_repo_commit_sha()
        run.artifacts["knowledge_snapshot_at"] = run.created_at
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
        self._refresh_live_run_state(run)
        return run.to_dict()

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            runs = list(self._runs.values())
        for run in runs:
            self._refresh_live_run_state(run)
        runs.sort(key=lambda item: item.created_at, reverse=True)
        return [run.to_dict() for run in runs[:limit]]

    def _refresh_live_run_state(self, run: SelfLearningRun) -> None:
        if run.status not in {"pending", "running"}:
            return
        with self._lock:
            task = self._pipeline_tasks.get(run.run_id)
            if task is not None and not task.done():
                return
        self._recover_orphaned_run(run)

    def _recover_orphaned_run(self, run: SelfLearningRun) -> None:
        if run.mode != "llm_finetune":
            if run.status != "failed":
                run.status = "failed"
                run.finished_at = _utc_now_iso()
                run.error_message = "Run monitor task was lost before completion. Restart self-learning run."
                self._add_log(run, "Run monitor task lost; marking run as failed.")
            return
        habitat = self.gpu_habitat
        if habitat is None:
            return
        training_job_id = str(
            run.artifacts.get("training_job_id") or f"self_learning_{run.run_id}"
        )
        try:
            payload = habitat.get_training_status(training_job_id)
        except Exception:
            payload = self._build_orphan_status_payload_from_files(run)
            if payload is None:
                return

        changed = False
        status = str(payload.get("status") or "").strip().lower()
        if status in {"running", "preparing", "queued", "finished", "failed", "error"}:
            if status == "finished":
                if run.status != "completed":
                    run.status = "completed"
                    run.finished_at = _utc_now_iso()
                    changed = True
            elif status in {"failed", "error"}:
                if run.status != "failed":
                    run.status = "failed"
                    run.finished_at = _utc_now_iso()
                    changed = True
                error_message = str(payload.get("logs") or "").strip() or (
                    "Training process reported failure"
                )
                if run.error_message != error_message:
                    run.error_message = error_message
                    changed = True
            else:
                if run.status != "running":
                    run.status = "running"
                    changed = True
                if run.started_at is None:
                    run.started_at = _utc_now_iso()
                    changed = True
            self._append_training_progress_logs(
                run=run,
                status=status or "unknown",
                status_payload=payload if isinstance(payload, dict) else {},
            )
            if changed:
                self._append_run_snapshot(run)

    def _build_orphan_status_payload_from_files(
        self, run: SelfLearningRun
    ) -> dict[str, str] | None:
        output_dir = Path(
            run.artifacts.get("training_output_dir")
            or (Path(SETTINGS.ACADEMY_MODELS_DIR) / f"self_learning_{run.run_id}")
        ).resolve()
        log_file = output_dir / "training.log"
        if not log_file.exists():
            return None
        logs = ""
        try:
            file_size = log_file.stat().st_size
            with log_file.open("r", encoding="utf-8", errors="ignore") as handle:
                if file_size > 4000:
                    handle.seek(file_size - 4000)
                logs = handle.read()
        except Exception:
            logs = ""

        adapter_config = output_dir / "adapter" / "adapter_config.json"
        alive = self._is_local_training_process_alive(run.run_id)
        if alive:
            status = "running"
        elif adapter_config.exists():
            status = "finished"
        else:
            status = "failed"
        return {"status": status, "logs": logs}

    def _is_local_training_process_alive(self, run_id: str) -> bool:
        run_marker = f"self_learning_{run_id}"
        for process in psutil.process_iter(attrs=["cmdline"]):
            try:
                cmdline = process.info.get("cmdline") or []
                joined = " ".join(str(part) for part in cmdline)
            except Exception:
                continue
            if "train_script.py" in joined and run_marker in joined:
                return True
        return False

    def delete_run(self, run_id: str) -> bool:
        if not _is_valid_uuid(run_id):
            return False
        task_to_cancel: asyncio.Task[None] | None = None
        with self._lock:
            run = self._runs.pop(run_id, None)
            task_to_cancel = self._pipeline_tasks.pop(run_id, None)
        if run is None:
            return False
        self._runtime_log_cache.pop(run_id, None)
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
        self._runtime_log_cache.clear()
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
                16, min(4096, _safe_int(data.get("max_file_size_kb"), 128))
            ),
            max_files=max(1, min(10000, _safe_int(data.get("max_files"), 300))),
            max_total_size_mb=max(
                1,
                min(4096, _safe_int(data.get("max_total_size_mb"), 32)),
            ),
        )

    def _parse_llm_config(self, payload: dict[str, Any] | None) -> LlmConfig:
        data = payload or {}
        dataset_strategy_raw = str(data.get("dataset_strategy") or "reconstruct")
        dataset_strategy = dataset_strategy_raw.strip().lower()
        if dataset_strategy not in _VALID_DATASET_STRATEGIES:
            dataset_strategy = "reconstruct"

        task_mix_raw = str(data.get("task_mix_preset") or "balanced")
        task_mix_preset = task_mix_raw.strip().lower()
        if task_mix_preset not in _VALID_TASK_MIX_PRESETS:
            task_mix_preset = "balanced"

        runtime_raw = str(data.get("runtime_id") or "").strip().lower()
        runtime_id = runtime_raw if runtime_raw in _LOCAL_RUNTIME_IDS else None

        return LlmConfig(
            base_model=(str(data.get("base_model")).strip() or None)
            if data.get("base_model")
            else None,
            runtime_id=runtime_id,
            dataset_strategy=cast(SelfLearningDatasetStrategy, dataset_strategy),
            task_mix_preset=cast(SelfLearningTaskMixPreset, task_mix_preset),
            lora_rank=max(4, min(64, _safe_int(data.get("lora_rank"), 8))),
            learning_rate=float(data.get("learning_rate", 2e-4)),
            num_epochs=max(1, min(20, _safe_int(data.get("num_epochs"), 2))),
            batch_size=max(1, min(32, _safe_int(data.get("batch_size"), 1))),
            max_seq_length=max(
                256,
                min(8192, _safe_int(data.get("max_seq_length"), 1024)),
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
        chunking_mode_raw = str(data.get("chunking_mode") or "plain").strip().lower()
        if chunking_mode_raw not in _VALID_RAG_CHUNKING_MODES:
            chunking_mode_raw = "plain"
        retrieval_mode_raw = str(data.get("retrieval_mode") or "vector").strip().lower()
        if retrieval_mode_raw not in _VALID_RAG_RETRIEVAL_MODES:
            retrieval_mode_raw = "vector"
        embedding_profile_id = data.get("embedding_profile_id")
        embedding_policy = str(data.get("embedding_policy") or "strict").strip().lower()
        if embedding_policy not in {"strict", "allow_fallback"}:
            embedding_policy = "strict"
        return RagConfig(
            collection=collection[:64],
            category=category[:64],
            chunk_text=chunk_text,
            chunking_mode=cast(SelfLearningRagChunkingMode, chunking_mode_raw),
            retrieval_mode=cast(SelfLearningRagRetrievalMode, retrieval_mode_raw),
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
            is_trainable = self._is_trainable_model(llm_config.base_model)
            if not is_trainable:
                raise ValueError(
                    f"Model '{llm_config.base_model}' is not trainable in Academy"
                )
            if llm_config.runtime_id:
                self._validate_runtime_compatibility_for_base_model(
                    base_model=llm_config.base_model,
                    runtime_id=llm_config.runtime_id,
                )
        if mode == "rag_index" and not rag_config.embedding_profile_id:
            raise ValueError(
                "rag_config.embedding_profile_id is required for rag_index mode"
            )

    def _validate_runtime_compatibility_for_base_model(
        self,
        *,
        base_model: str,
        runtime_id: str,
    ) -> None:
        provider = self._infer_training_provider(base_model)
        compatibility = self._resolve_runtime_compatibility(
            provider=provider,
            available_runtime_ids=[],
            model_metadata={"name": base_model},
        )
        if compatibility.get(runtime_id):
            return
        available = [
            runtime for runtime in _LOCAL_RUNTIME_IDS if compatibility.get(runtime)
        ]
        if available:
            supported = ", ".join(available)
            raise ValueError(
                f"Model '{base_model}' is incompatible with runtime '{runtime_id}'. "
                f"Supported runtimes: {supported}."
            )
        raise ValueError(
            f"Model '{base_model}' does not expose compatible local runtime targets."
        )

    @staticmethod
    def _infer_training_provider(model_id: str) -> str:
        normalized = model_id.strip().lower()
        if ":" in normalized:
            return "ollama"
        if normalized.startswith("unsloth/"):
            return "unsloth"
        if "/" in normalized:
            return "huggingface"
        return "unknown"

    def _validate_llm_finetune_runtime_preflight(self, *, dry_run: bool) -> None:
        if dry_run:
            return
        habitat = self.gpu_habitat
        if habitat is None:
            raise ValueError("GPUHabitat is not available for fine-tuning")
        if not bool(getattr(habitat, "use_local_runtime", False)):
            return
        check_dependencies = getattr(habitat, "_check_local_dependencies", None)
        if not callable(check_dependencies):
            return
        try:
            check_dependencies()
        except Exception as exc:
            raise ValueError(str(exc)) from exc

    def _apply_mode_defaults(
        self,
        *,
        mode: SelfLearningMode,
        llm_config: LlmConfig,
        rag_config: RagConfig,
    ) -> None:
        if mode == "llm_finetune":
            selected_model = (llm_config.base_model or "").strip()
            if not selected_model or not self._is_trainable_model(selected_model):
                fallback_model = self._resolve_fallback_base_model()
                if fallback_model:
                    llm_config.base_model = fallback_model
        if mode == "rag_index" and not rag_config.embedding_profile_id:
            fallback_profile_id = self._resolve_default_embedding_profile_id()
            if fallback_profile_id:
                rag_config.embedding_profile_id = fallback_profile_id

    def _is_trainable_model(self, model_id: str) -> bool:
        candidate = model_id.strip()
        if not candidate:
            return False
        if self.is_model_trainable_fn is not None:
            try:
                return bool(self.is_model_trainable_fn(candidate))
            except Exception as exc:
                logger.warning(
                    "is_model_trainable_fn failed for '%s': %s",
                    candidate,
                    exc,
                )
        return self._is_trainable_model_candidate(candidate)

    def _resolve_fallback_base_model(self) -> str | None:
        default_model = str(getattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "") or "")
        candidate = default_model.strip()
        if candidate and self._is_trainable_model(candidate):
            return candidate
        return None

    def _resolve_default_embedding_profile_id(self) -> str | None:
        profiles = self._embedding_profiles()
        for profile in profiles:
            profile_id = str(profile.get("profile_id") or "").strip()
            if profile_id and bool(profile.get("healthy")):
                return profile_id
        for profile in profiles:
            profile_id = str(profile.get("profile_id") or "").strip()
            if profile_id:
                return profile_id
        return None

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
        preferred_runtime = self._resolve_preferred_runtime_for_capabilities()
        default_base_model = next(
            (
                item["model_id"]
                for item in trainable_models
                if preferred_runtime
                and bool(item.get("runtime_compatibility", {}).get(preferred_runtime))
                and bool(item.get("recommended"))
            ),
            None,
        )
        if default_base_model is None:
            default_base_model = next(
                (
                    item["model_id"]
                    for item in trainable_models
                    if preferred_runtime
                    and bool(
                        item.get("runtime_compatibility", {}).get(preferred_runtime)
                    )
                ),
                None,
            )
        if default_base_model is None:
            default_base_model = next(
                (
                    item["model_id"]
                    for item in trainable_models
                    if bool(item.get("recommended"))
                ),
                trainable_models[0]["model_id"] if trainable_models else None,
            )
        default_embedding_profile_id = next(
            (item["profile_id"] for item in embedding_profiles if item.get("healthy")),
            embedding_profiles[0]["profile_id"] if embedding_profiles else None,
        )
        return {
            "trainable_models": trainable_models,
            "embedding_profiles": embedding_profiles,
            "default_base_model": default_base_model,
            "default_embedding_profile_id": default_embedding_profile_id,
        }

    def _resolve_preferred_runtime_for_capabilities(self) -> str | None:
        active_runtime = (
            str(getattr(SETTINGS, "ACTIVE_LLM_SERVER", "") or "").strip().lower()
        )
        if active_runtime in _LOCAL_RUNTIME_IDS:
            return active_runtime
        return None

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

    @staticmethod
    def _build_local_embedding_profile(
        *,
        model_name: str,
        dimension: int | None,
        is_active: bool,
        healthy: bool,
        fallback_active: bool,
    ) -> dict[str, Any]:
        if is_active:
            return {
                "profile_id": "local:default",
                "provider": "local",
                "model": model_name,
                "dimension": dimension,
                "healthy": healthy,
                "fallback_active": fallback_active,
                "details": {},
            }

        return {
            "profile_id": f"local/{model_name}",
            "provider": "local",
            "model": model_name,
            "dimension": dimension,
            "healthy": False,
            "fallback_active": False,
            "details": {"reason": "not_active_runtime_model"},
        }

    @staticmethod
    def _build_missing_active_embedding_profile(
        *,
        active_model: str,
        active_dimension: int | None,
        healthy: bool,
        fallback_active: bool,
    ) -> dict[str, Any]:
        return {
            "profile_id": "local:default",
            "provider": "local",
            "model": active_model or "unknown",
            "dimension": active_dimension,
            "healthy": healthy,
            "fallback_active": fallback_active,
            "details": {"reason": "active_model_not_in_catalog"},
        }

    def _embedding_profiles(self) -> list[dict[str, Any]]:
        state = self._embedding_runtime_state()
        if state["profile_id"] is None:
            return []

        provider = str(state.get("provider") or "unknown")
        if provider != "local":
            return [state]

        active_model = str(state.get("model") or "")
        healthy = bool(state.get("healthy"))
        fallback_active = bool(state.get("fallback_active"))
        active_dimension = state.get("dimension")
        result: list[dict[str, Any]] = []
        for model_name, dimension in _LOCAL_EMBEDDING_PROFILES:
            is_active = model_name == active_model
            result.append(
                self._build_local_embedding_profile(
                    model_name=model_name,
                    dimension=active_dimension if is_active else dimension,
                    is_active=is_active,
                    healthy=healthy,
                    fallback_active=fallback_active,
                )
            )

        if not any(item["model"] == active_model for item in result):
            result.insert(
                0,
                self._build_missing_active_embedding_profile(
                    active_model=active_model,
                    active_dimension=active_dimension,
                    healthy=healthy,
                    fallback_active=fallback_active,
                ),
            )
        return result

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

            chunks = self._chunk_extracted_files(
                extracted_files,
                rag_mode=(run.mode == "rag_index"),
                rag_config=run.rag_config,
            )
            run.progress.chunks_created = len(chunks)
            self._add_log(run, f"Chunks created: {len(chunks)}")

            if run.mode == "llm_finetune":
                if not run.dry_run:
                    await self._prepare_runtime_for_llm_training(run)
                else:
                    self._add_log(
                        run,
                        "Dry run enabled; runtime preparation checks skipped.",
                    )
                await self._run_llm_finetune(run, chunks)
            elif run.mode == "rag_index":
                self._run_rag_index(run, chunks, extracted_files)
            else:
                raise SelfLearningError(f"Unsupported mode: {run.mode}")
            self._run_eval_harness(run)

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

    async def _run_llm_finetune(
        self,
        run: SelfLearningRun,
        chunks: list[dict[str, Any]],
    ) -> None:
        run_dir = self._run_dir(run.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = run_dir / "dataset.jsonl"
        records = self._build_dataset_records(run, chunks)
        accepted_records, dataset_report = self._validate_and_report_dataset_quality(
            run, records
        )

        with dataset_path.open("w", encoding="utf-8") as handle:
            for record in accepted_records:
                record.pop("__task_type", None)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        dataset_report_path = run_dir / "dataset_report.json"
        dataset_report_path.write_text(
            json.dumps(dataset_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        run.progress.records_created = len(accepted_records)
        run.artifacts["dataset_path"] = str(dataset_path)
        run.artifacts["dataset_report_path"] = str(dataset_report_path)
        run.artifacts["dataset_strategy"] = run.llm_config.dataset_strategy
        run.artifacts["task_mix_preset"] = run.llm_config.task_mix_preset
        self._add_log(run, f"Dataset created: {dataset_path}")
        self._add_log(
            run,
            "Dataset quality accepted="
            f"{dataset_report['accepted_records']}/"
            f"{dataset_report['input_records']} "
            f"(duplicates_removed={dataset_report['duplicates_removed']}, "
            f"too_short_removed={dataset_report['too_short_removed']})",
        )

        if not dataset_report["quality_ok"]:
            raise SelfLearningError(
                "Dataset quality check failed: insufficient accepted records for selected strategy"
            )

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
        status_payload = await self._wait_for_training_completion(
            run=run,
            habitat=habitat,
            training_job_id=training_job_id,
            output_dir=output_dir,
        )
        run.artifacts["adapter_path"] = str(output_dir / "adapter")
        self._write_adapter_metadata(
            output_dir=output_dir,
            base_model=base_model,
            run=run,
        )
        self._add_log(
            run,
            f"Training job finished with status={status_payload.get('status', 'unknown')}",
        )

    def _write_adapter_metadata(
        self,
        *,
        output_dir: Path,
        base_model: str,
        run: SelfLearningRun,
    ) -> None:
        metadata_payload = {
            "base_model": base_model,
            "created_at": run.finished_at or _utc_now_iso(),
            "parameters": {
                "lora_rank": run.llm_config.lora_rank,
                "learning_rate": run.llm_config.learning_rate,
                "num_epochs": run.llm_config.num_epochs,
                "batch_size": run.llm_config.batch_size,
                "max_seq_length": run.llm_config.max_seq_length,
                "dataset_strategy": run.llm_config.dataset_strategy,
                "task_mix_preset": run.llm_config.task_mix_preset,
            },
        }
        metadata_file = output_dir / "metadata.json"
        metadata_file.write_text(
            json.dumps(metadata_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _prepare_runtime_for_llm_training(self, run: SelfLearningRun) -> None:
        habitat = self.gpu_habitat
        if habitat is None:
            return
        self._ensure_no_active_training_jobs(habitat=habitat)
        await self._release_runtime_models(run)
        self._apply_resource_optimizations(run)

    def _ensure_no_active_training_jobs(self, *, habitat: Any) -> None:
        training_jobs = getattr(habitat, "training_containers", {})
        if not isinstance(training_jobs, dict) or not training_jobs:
            return
        active_jobs: list[str] = []
        for job_name in list(training_jobs.keys()):
            try:
                payload = habitat.get_training_status(job_name)
            except Exception:
                continue
            status = str(payload.get("status") or "").strip().lower()
            if status in {"running", "preparing", "queued"}:
                active_jobs.append(job_name)
        if active_jobs:
            raise SelfLearningError(
                "Aktywny trening już trwa; zatrzymaj poprzedni run przed uruchomieniem nowego."
            )

    async def _release_runtime_models(self, run: SelfLearningRun) -> None:
        manager = self.model_manager
        if manager is None or not hasattr(manager, "unload_all"):
            return
        try:
            released = await manager.unload_all()
            if released:
                self._add_log(
                    run,
                    "Inference runtime unloaded before training to free RAM/VRAM.",
                )
            else:
                self._add_log(
                    run,
                    "Warning: runtime unload returned false; continuing with safeguards.",
                )
        except Exception as exc:
            logger.warning("Failed to unload runtime models before training: %s", exc)
            self._add_log(
                run,
                f"Warning: runtime unload failed ({exc}); continuing with safeguards.",
            )

    def _apply_resource_optimizations(self, run: SelfLearningRun) -> None:
        memory = psutil.virtual_memory()
        available_gb = float(memory.available) / float(1024**3)
        run.artifacts["resource_snapshot"] = {
            "ram_total_gb": round(float(memory.total) / float(1024**3), 2),
            "ram_available_gb": round(available_gb, 2),
            "ram_usage_percent": round(float(memory.percent), 2),
        }
        if (
            available_gb < _CRITICAL_RAM_AVAILABLE_GB
            and float(memory.percent) >= _CRITICAL_RAM_USAGE_PERCENT
        ):
            ultra_safe_changes: list[str] = []
            if run.llm_config.batch_size > 1:
                run.llm_config.batch_size = 1
                ultra_safe_changes.append("batch_size=1")
            if run.llm_config.max_seq_length > 512:
                run.llm_config.max_seq_length = 512
                ultra_safe_changes.append("max_seq_length=512")
            if run.llm_config.lora_rank > 4:
                run.llm_config.lora_rank = 4
                ultra_safe_changes.append("lora_rank=4")
            if run.llm_config.num_epochs > 1:
                run.llm_config.num_epochs = 1
                ultra_safe_changes.append("num_epochs=1")
            if ultra_safe_changes:
                run.artifacts["resource_optimizations_critical"] = ultra_safe_changes
            self._add_log(
                run,
                "Critical low-RAM mode enabled; applying ultra-safe training parameters "
                f"(available={available_gb:.2f} GB, usage={float(memory.percent):.1f}%).",
            )
        optimizations: list[str] = []
        if available_gb < _LOW_RAM_AVAILABLE_GB:
            if run.llm_config.batch_size > 1:
                run.llm_config.batch_size = 1
                optimizations.append("batch_size=1")
            if run.llm_config.max_seq_length > 1024:
                run.llm_config.max_seq_length = 1024
                optimizations.append("max_seq_length=1024")
            if run.llm_config.lora_rank > 8:
                run.llm_config.lora_rank = 8
                optimizations.append("lora_rank=8")
            if run.llm_config.num_epochs > 2:
                run.llm_config.num_epochs = 2
                optimizations.append("num_epochs=2")
        if optimizations:
            run.artifacts["resource_optimizations"] = optimizations
            self._add_log(
                run,
                "Applied low-resource training optimizations: "
                + ", ".join(optimizations),
            )

    async def _wait_for_training_completion(
        self,
        *,
        run: SelfLearningRun,
        habitat: Any,
        training_job_id: str,
        output_dir: Path,
    ) -> dict[str, Any]:
        timeout_seconds = max(
            _TRAINING_TIMEOUT_MIN_SECONDS,
            min(
                _TRAINING_TIMEOUT_MAX_SECONDS,
                run.llm_config.num_epochs * 1200,
            ),
        )
        deadline = asyncio.get_event_loop().time() + float(timeout_seconds)
        latest_payload: dict[str, Any] = {}
        previous_status = ""
        while asyncio.get_event_loop().time() < deadline:
            status_payload = habitat.get_training_status(training_job_id)
            latest_payload = status_payload if isinstance(status_payload, dict) else {}
            status = str(latest_payload.get("status") or "").strip().lower()
            if status and status != previous_status:
                self._add_log(run, f"Training status: {status}")
                previous_status = status
            self._append_training_progress_logs(
                run=run,
                status=status or "unknown",
                status_payload=latest_payload,
            )
            if status == "finished":
                break
            if status in {"failed", "error"}:
                logs = str(latest_payload.get("logs") or "").strip()
                raise SelfLearningError(
                    "Błąd podczas treningu modelu. "
                    + (logs[-800:] if logs else "Sprawdź training.log.")
                )
            await asyncio.sleep(_TRAINING_STATUS_POLL_INTERVAL_SECONDS)
        else:
            raise SelfLearningError(
                f"Trening przekroczył limit czasu ({timeout_seconds}s) i został przerwany."
            )

        adapter_dir = output_dir / "adapter"
        adapter_config = adapter_dir / "adapter_config.json"
        if not adapter_config.exists():
            logs = str(latest_payload.get("logs") or "").strip()
            raise SelfLearningError(
                "Trening zakończył się bez zapisu adaptera. "
                + (logs[-800:] if logs else "Brak adapter_config.json.")
            )
        return latest_payload

    def _append_training_progress_logs(
        self,
        *,
        run: SelfLearningRun,
        status: str,
        status_payload: dict[str, Any],
    ) -> None:
        raw_logs = str(status_payload.get("logs") or "").strip()
        if not raw_logs:
            return
        current_lines = [line.strip() for line in raw_logs.splitlines() if line.strip()]
        if not current_lines:
            return
        seen_lines = self._runtime_log_cache.get(run.run_id, [])

        new_lines: list[str]
        if (
            seen_lines
            and len(current_lines) >= len(seen_lines)
            and current_lines[: len(seen_lines)] == seen_lines
        ):
            new_lines = current_lines[len(seen_lines) :]
        else:
            # Fallback for rotated/truncated runtime logs: keep recent tail only.
            new_lines = current_lines[-5:]

        for line in new_lines[-5:]:
            self._add_log(run, f"[train:{status}] {line}")

        self._runtime_log_cache[run.run_id] = current_lines

    def _run_eval_harness(self, run: SelfLearningRun) -> None:
        """
        Lightweight run evaluation (phase 191B.3) based on observable run metrics.

        This is a proxy benchmark and does not replace full task-level evaluation.
        """
        if run.mode == "llm_finetune":
            evaluation = self._evaluate_llm_run(run)
        else:
            evaluation = self._evaluate_rag_run(run)

        run_dir = self._run_dir(run.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        evaluation_report_path = run_dir / "evaluation_report.json"
        evaluation_report_path.write_text(
            json.dumps(evaluation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        run.artifacts["evaluation"] = evaluation
        run.artifacts["evaluation_report_path"] = str(evaluation_report_path)
        run.artifacts["promotion_decision"] = evaluation["decision"]
        run.artifacts["promotion_score"] = evaluation["score"]
        self._add_log(
            run,
            "Evaluation completed: "
            f"decision={evaluation['decision']}, score={evaluation['score']}, "
            f"passed={evaluation['passed']}",
        )

    def _evaluate_llm_run(self, run: SelfLearningRun) -> dict[str, Any]:
        dataset_report = self._read_dataset_report(run)
        accepted_records = int(dataset_report.get("accepted_records") or 0)
        chunks_created = max(1, int(run.progress.chunks_created))
        qa_signal = 0.2 if run.llm_config.dataset_strategy == "reconstruct" else 0.55
        qa_accuracy = _clamp01((accepted_records / chunks_created) * 0.45 + qa_signal)

        task_distribution = dataset_report.get("task_distribution") or {}
        bugfix_ratio = 0.0
        total_tasks = 1
        if isinstance(task_distribution, dict):
            total_tasks = max(1, sum(int(v) for v in task_distribution.values()))
            bugfix_ratio = float(task_distribution.get("bugfix_hint", 0)) / float(
                total_tasks
            )
        code_localization_accuracy = _clamp01(0.35 + (qa_accuracy * 0.35))
        fix_success_rate = _clamp01(0.2 + (bugfix_ratio * 0.8))
        hallucination_rate = _clamp01(
            1.0 - ((qa_accuracy * 0.65) + (code_localization_accuracy * 0.35))
        )

        baseline = {
            "repo_qa_accuracy": 0.55,
            "code_localization_accuracy": 0.45,
            "fix_success_rate": 0.25,
            "hallucination_rate_max": 0.35,
        }
        return self._finalize_evaluation_payload(
            run=run,
            metrics={
                "repo_qa_accuracy": round(qa_accuracy, 4),
                "code_localization_accuracy": round(code_localization_accuracy, 4),
                "fix_success_rate": round(fix_success_rate, 4),
                "hallucination_rate": round(hallucination_rate, 4),
            },
            baseline=baseline,
        )

    def _evaluate_rag_run(self, run: SelfLearningRun) -> dict[str, Any]:
        indexed_vectors = max(1, int(run.progress.indexed_vectors))
        chunks_created = max(1, int(run.progress.chunks_created))
        symbol_chunks = int(run.artifacts.get("symbol_chunks") or 0)
        symbol_ratio = float(symbol_chunks) / float(chunks_created)

        qa_accuracy = _clamp01(
            0.45 + min(0.35, (indexed_vectors / chunks_created) * 0.35)
        )
        code_localization_accuracy = _clamp01(
            0.35
            + (0.25 if run.rag_config.chunking_mode == "code_aware" else 0.0)
            + (0.15 if run.rag_config.retrieval_mode == "hybrid" else 0.0)
            + (symbol_ratio * 0.15)
        )
        fix_success_rate = _clamp01(0.2 + (code_localization_accuracy * 0.6))
        hallucination_rate = _clamp01(
            1.0 - ((qa_accuracy * 0.6) + (code_localization_accuracy * 0.4))
        )

        baseline = {
            "repo_qa_accuracy": 0.6,
            "code_localization_accuracy": 0.55,
            "fix_success_rate": 0.3,
            "hallucination_rate_max": 0.3,
        }
        return self._finalize_evaluation_payload(
            run=run,
            metrics={
                "repo_qa_accuracy": round(qa_accuracy, 4),
                "code_localization_accuracy": round(code_localization_accuracy, 4),
                "fix_success_rate": round(fix_success_rate, 4),
                "hallucination_rate": round(hallucination_rate, 4),
            },
            baseline=baseline,
        )

    def _read_dataset_report(self, run: SelfLearningRun) -> dict[str, Any]:
        report_path = run.artifacts.get("dataset_report_path")
        if not report_path:
            return {}
        try:
            payload = json.loads(Path(str(report_path)).read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {}
        return {}

    @staticmethod
    def _finalize_evaluation_payload(
        *,
        run: SelfLearningRun,
        metrics: dict[str, float],
        baseline: dict[str, float],
    ) -> dict[str, Any]:
        passed = (
            metrics["repo_qa_accuracy"] >= baseline["repo_qa_accuracy"]
            and metrics["code_localization_accuracy"]
            >= baseline["code_localization_accuracy"]
            and metrics["fix_success_rate"] >= baseline["fix_success_rate"]
            and metrics["hallucination_rate"] <= baseline["hallucination_rate_max"]
        )
        weighted_score = _clamp01(
            (metrics["repo_qa_accuracy"] * 0.35)
            + (metrics["code_localization_accuracy"] * 0.3)
            + (metrics["fix_success_rate"] * 0.25)
            + ((1.0 - metrics["hallucination_rate"]) * 0.1)
        )
        return {
            "version": "191b.3-proxy-v1",
            "kind": "proxy_eval",
            "mode": run.mode,
            "evaluated_at": _utc_now_iso(),
            "metrics": metrics,
            "baseline": baseline,
            "score": round(weighted_score, 4),
            "decision": "promote" if passed else "reject",
            "passed": passed,
        }

    def _build_dataset_records(
        self,
        run: SelfLearningRun,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        strategy = run.llm_config.dataset_strategy
        if strategy == "reconstruct":
            return self._build_reconstruct_records(chunks)
        if strategy == "qa_from_docs":
            return self._build_qa_from_docs_records(chunks)
        return self._build_repo_tasks_basic_records(
            chunks,
            task_mix_preset=run.llm_config.task_mix_preset,
        )

    @staticmethod
    def _shorten_context(text: str, limit: int = 900) -> str:
        compact = " ".join(text.strip().split())
        if len(compact) <= limit:
            return compact
        return compact[:limit].rstrip() + "..."

    def _build_reconstruct_records(
        self,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "instruction": f"Learn repository knowledge from file: {chunk['path']}",
                "input": chunk["text"],
                "output": chunk["text"],
                "__task_type": "reconstruct",
            }
            for chunk in chunks
        ]

    def _build_qa_from_docs_records(
        self,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for chunk in chunks:
            snippet = self._shorten_context(str(chunk.get("text") or ""))
            path = str(chunk.get("path") or "unknown")
            source = str(chunk.get("source") or "unknown")
            records.append(
                {
                    "instruction": "Answer repository questions using provided context.",
                    "input": (
                        f"Question: What key information is documented in `{path}`?\n"
                        f"Source: {source}\n"
                        f"Context:\n{snippet}"
                    ),
                    "output": (
                        f"Primary reference file: `{path}`.\nKey context:\n{snippet}"
                    ),
                    "__task_type": "qa",
                }
            )
        return records

    def _build_repo_tasks_basic_records(
        self,
        chunks: list[dict[str, Any]],
        *,
        task_mix_preset: SelfLearningTaskMixPreset,
    ) -> list[dict[str, Any]]:
        sequence = self._task_sequence_for_preset(task_mix_preset)
        records: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            task_type = sequence[index % len(sequence)]
            if task_type == "qa":
                records.append(self._build_repo_task_qa_record(chunk))
                continue
            if task_type == "where_is":
                records.append(self._build_repo_task_where_is_record(chunk))
                continue
            records.append(self._build_repo_task_bugfix_record(chunk))
        return records

    @staticmethod
    def _task_sequence_for_preset(
        task_mix_preset: SelfLearningTaskMixPreset,
    ) -> tuple[str, ...]:
        if task_mix_preset == "qa-heavy":
            return (
                "qa",
                "qa",
                "qa",
                "qa",
                "qa",
                "qa",
                "qa",
                "where_is",
                "where_is",
                "bugfix_hint",
            )
        if task_mix_preset == "repair-heavy":
            return (
                "bugfix_hint",
                "bugfix_hint",
                "bugfix_hint",
                "bugfix_hint",
                "bugfix_hint",
                "qa",
                "qa",
                "qa",
                "where_is",
                "where_is",
            )
        return (
            "qa",
            "qa",
            "qa",
            "qa",
            "qa",
            "where_is",
            "where_is",
            "where_is",
            "bugfix_hint",
            "bugfix_hint",
        )

    def _build_repo_task_qa_record(self, chunk: dict[str, Any]) -> dict[str, Any]:
        path = str(chunk.get("path") or "unknown")
        snippet = self._shorten_context(str(chunk.get("text") or ""))
        return {
            "instruction": "Explain repository modules and responsibilities from context.",
            "input": (
                f"Task: Explain what this module/file is responsible for.\n"
                f"File: {path}\n"
                f"Context:\n{snippet}"
            ),
            "output": (
                f"Module reference: `{path}`.\nUse this context to answer:\n{snippet}"
            ),
            "__task_type": "qa",
        }

    def _build_repo_task_where_is_record(self, chunk: dict[str, Any]) -> dict[str, Any]:
        path = str(chunk.get("path") or "unknown")
        snippet = self._shorten_context(str(chunk.get("text") or ""))
        return {
            "instruction": "Locate implementation files based on repository hints.",
            "input": (
                "Task: Find where this behavior is implemented and provide the best "
                "starting file.\n"
                f"Hint excerpt:\n{snippet}"
            ),
            "output": (
                f"Start in `{path}`.\n"
                "If needed, inspect related references from this excerpt:\n"
                f"{snippet}"
            ),
            "__task_type": "where_is",
        }

    def _build_repo_task_bugfix_record(self, chunk: dict[str, Any]) -> dict[str, Any]:
        path = str(chunk.get("path") or "unknown")
        snippet = self._shorten_context(str(chunk.get("text") or ""))
        return {
            "instruction": "Propose first debugging and repair steps from repository evidence.",
            "input": (
                "Issue: Unexpected behavior reported by user.\n"
                f"Candidate file: {path}\n"
                f"Observed context:\n{snippet}"
            ),
            "output": (
                f"Investigate `{path}` first.\n"
                "Validate logic and tests around this context:\n"
                f"{snippet}"
            ),
            "__task_type": "bugfix_hint",
        }

    def _validate_and_report_dataset_quality(
        self,
        run: SelfLearningRun,
        records: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        seen: set[str] = set()
        duplicates_removed = 0
        too_short_removed = 0

        for record in records:
            instruction = str(record.get("instruction") or "").strip()
            input_text = str(record.get("input") or "").strip()
            output_text = str(record.get("output") or "").strip()
            if (
                len(input_text) < _MIN_RECORD_INPUT_CHARS
                or len(output_text) < _MIN_RECORD_OUTPUT_CHARS
            ):
                too_short_removed += 1
                continue
            dedup_key = _sha256_bytes(
                f"{instruction}\n{input_text}\n{output_text}".encode("utf-8")
            )
            if dedup_key in seen:
                duplicates_removed += 1
                continue
            seen.add(dedup_key)
            accepted.append(
                {
                    "instruction": instruction,
                    "input": input_text,
                    "output": output_text,
                    "__task_type": record.get("__task_type") or "unknown",
                }
            )

        task_distribution: dict[str, int] = {}
        for item in accepted:
            task_type = str(item.get("__task_type") or "unknown")
            task_distribution[task_type] = task_distribution.get(task_type, 0) + 1

        required_min_records = self._required_min_dataset_records(
            run.llm_config.dataset_strategy
        )
        report = {
            "strategy": run.llm_config.dataset_strategy,
            "task_mix_preset": run.llm_config.task_mix_preset,
            "input_records": len(records),
            "accepted_records": len(accepted),
            "duplicates_removed": duplicates_removed,
            "too_short_removed": too_short_removed,
            "required_min_records": required_min_records,
            "quality_ok": len(accepted) >= required_min_records,
            "task_distribution": task_distribution,
        }
        return accepted, report

    @staticmethod
    def _required_min_dataset_records(
        strategy: SelfLearningDatasetStrategy,
    ) -> int:
        if strategy == "reconstruct":
            return 1
        return _MIN_DATASET_RECORDS

    def _run_rag_index(
        self,
        run: SelfLearningRun,
        chunks: list[dict[str, Any]],
        extracted_files: list[tuple[Path, str, str, str, SelfLearningSource]],
    ) -> None:
        if run.dry_run:
            run.progress.indexed_vectors = len(chunks)
            run.artifacts["chunking_mode"] = run.rag_config.chunking_mode
            run.artifacts["retrieval_mode"] = run.rag_config.retrieval_mode
            run.artifacts["knowledge_freshness"] = {
                "indexed_at": _utc_now_iso(),
                "repo_commit_sha": run.artifacts.get("repo_commit_sha"),
                "mode": "dry_run",
            }
            self._add_log(run, "Dry run enabled; vector index upsert skipped.")
            return

        if self.vector_store is None:
            raise SelfLearningError("VectorStore is not available for RAG indexing")

        embedding_profiles = self._embedding_profiles()
        selected_profile = run.rag_config.embedding_profile_id or ""
        selected_profile_state = next(
            (
                item
                for item in embedding_profiles
                if item.get("profile_id") == selected_profile
            ),
            None,
        )
        if selected_profile_state is None:
            raise SelfLearningError(f"Unknown embedding profile: {selected_profile}")
        if not bool(selected_profile_state.get("healthy")):
            raise SelfLearningError("Embedding runtime is unhealthy")
        if run.rag_config.embedding_policy == "strict" and bool(
            selected_profile_state.get("fallback_active")
        ):
            raise SelfLearningError(
                "Embedding runtime uses fallback mode and strict policy is enabled"
            )

        run.artifacts["embedding_profile"] = {
            "profile_id": selected_profile,
            "provider": selected_profile_state.get("provider"),
            "model": selected_profile_state.get("model"),
            "dimension": selected_profile_state.get("dimension"),
            "fallback_active": selected_profile_state.get("fallback_active"),
            "policy": run.rag_config.embedding_policy,
        }
        run.artifacts["chunking_mode"] = run.rag_config.chunking_mode
        run.artifacts["retrieval_mode"] = run.rag_config.retrieval_mode

        indexed_vectors = 0
        newly_indexed_file_keys: set[str] = set()
        skipped_manifest_chunks = 0
        symbol_chunks = 0
        doc_chunks = 0
        eligible_keys = {
            f"{file_hash}:{rel_path}"
            for _, _, file_hash, rel_path, _ in extracted_files
        }

        for chunk in chunks:
            file_key = f"{chunk['sha256']}:{chunk['path']}"
            if file_key in self._index_manifest:
                skipped_manifest_chunks += 1
                continue
            chunk_symbol = chunk.get("symbol")
            if chunk_symbol:
                symbol_chunks += 1
            else:
                doc_chunks += 1

            metadata = {
                "source": chunk["source"],
                "path": chunk["path"],
                "sha256": chunk["sha256"],
                "run_id": run.run_id,
                "chunk_index": chunk["chunk_index"],
                "language": chunk.get("language"),
                "symbol": chunk_symbol,
                "last_modified": chunk.get("last_modified"),
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
        run.artifacts["symbol_chunks"] = symbol_chunks
        run.artifacts["doc_chunks"] = doc_chunks
        run.artifacts["skipped_manifest_chunks"] = skipped_manifest_chunks
        run.artifacts["knowledge_freshness"] = {
            "indexed_at": _utc_now_iso(),
            "repo_commit_sha": run.artifacts.get("repo_commit_sha"),
            "mode": "indexed",
        }
        self._add_log(run, f"Indexed vectors: {indexed_vectors}")
        self._add_log(
            run,
            "RAG stats: "
            f"chunking_mode={run.rag_config.chunking_mode}, "
            f"retrieval_mode={run.rag_config.retrieval_mode}, "
            f"symbol_chunks={symbol_chunks}, doc_chunks={doc_chunks}, "
            f"skipped_manifest_chunks={skipped_manifest_chunks}",
        )

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
        seen_paths: set[Path] = set()

        for source, root in allowed_roots:
            for path in self._iter_candidate_paths(root):
                resolved_path = path.resolve()
                if resolved_path in seen_paths:
                    continue
                if len(collected) >= max_files:
                    self._add_log(run, "Reached max_files limit.")
                    return collected
                decision, size = self._evaluate_candidate_path(
                    run=run,
                    source=source,
                    path=path,
                    max_file_size=max_file_size,
                    max_total_size=max_total_size,
                    current_total_size=total_size,
                )
                if decision == "collect":
                    total_size += size
                    seen_paths.add(resolved_path)
                    collected.append((resolved_path, source))
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
        source: SelfLearningSource,
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
        if not self._is_path_allowed_for_source(source=source, path=path):
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
        *,
        rag_mode: bool = False,
        rag_config: RagConfig | None = None,
    ) -> list[dict[str, Any]]:
        chunk_size = 1000
        overlap = 120
        chunks: list[dict[str, Any]] = []
        use_code_aware = bool(
            rag_mode
            and rag_config is not None
            and rag_config.chunking_mode == "code_aware"
        )

        for file_path, text, file_hash, rel_path, source in extracted_files:
            language = self._language_from_path(rel_path)
            last_modified = self._safe_last_modified_iso(file_path)
            if use_code_aware and self._is_code_file(rel_path):
                file_chunks = self._chunk_text_code_aware(
                    text,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
            else:
                file_chunks = [
                    (chunk, None)
                    for chunk in self._chunk_text(
                        text,
                        chunk_size=chunk_size,
                        overlap=overlap,
                    )
                ]
            for idx, (chunk, symbol) in enumerate(file_chunks):
                if not chunk.strip():
                    continue
                chunks.append(
                    self._build_chunk_entry(
                        text=chunk,
                        file_hash=file_hash,
                        rel_path=rel_path,
                        source=source,
                        chunk_index=idx,
                        language=language,
                        symbol=symbol,
                        last_modified=last_modified,
                    )
                )
        return chunks

    @staticmethod
    def _build_chunk_entry(
        *,
        text: str,
        file_hash: str,
        rel_path: str,
        source: SelfLearningSource,
        chunk_index: int,
        language: str,
        symbol: str | None,
        last_modified: str | None,
    ) -> dict[str, Any]:
        return {
            "text": text,
            "sha256": file_hash,
            "path": rel_path,
            "source": source,
            "chunk_index": chunk_index,
            "language": language,
            "symbol": symbol,
            "last_modified": last_modified,
        }

    @staticmethod
    def _safe_last_modified_iso(path: Path) -> str | None:
        try:
            return datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat()
        except OSError:
            return None

    @staticmethod
    def _language_from_path(rel_path: str) -> str:
        suffix = Path(rel_path).suffix.lower()
        mapping = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".js": "javascript",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".ini": "ini",
            ".md": "markdown",
            ".txt": "text",
            ".rst": "rst",
        }
        return mapping.get(suffix, "text")

    @staticmethod
    def _is_code_file(rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".py", ".ts", ".tsx", ".js"}

    def _chunk_text_code_aware(
        self,
        text: str,
        *,
        chunk_size: int,
        overlap: int,
    ) -> list[tuple[str, str | None]]:
        symbol_blocks = self._extract_symbol_blocks(text)
        if not symbol_blocks:
            return [
                (chunk, None)
                for chunk in self._chunk_text(
                    text, chunk_size=chunk_size, overlap=overlap
                )
            ]

        chunks: list[tuple[str, str | None]] = []
        for symbol, block in symbol_blocks:
            for piece in self._chunk_text(
                block, chunk_size=chunk_size, overlap=overlap
            ):
                clean_piece = piece.strip()
                if clean_piece:
                    chunks.append((clean_piece, symbol))
        return chunks

    @staticmethod
    def _extract_symbol_blocks(text: str) -> list[tuple[str | None, str]]:
        lines = text.splitlines()
        if not lines:
            return []

        symbol_markers = SelfLearningService._scan_symbol_markers(lines)

        if not symbol_markers:
            return []

        return SelfLearningService._build_symbol_blocks(lines, symbol_markers)

    @staticmethod
    def _symbol_patterns() -> tuple[re.Pattern[str], ...]:
        return (
            re.compile(r"^\s*async\s+def\s+([A-Za-z_]\w*)\s*\(", re.ASCII),
            re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", re.ASCII),
            re.compile(r"^\s*class\s+([A-Za-z_]\w*)\b", re.ASCII),
            re.compile(
                r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\(", re.ASCII
            ),
            re.compile(r"^\s*function\s+([A-Za-z_]\w*)\s*\(", re.ASCII),
            re.compile(r"^\s*export\s+class\s+([A-Za-z_]\w*)\b", re.ASCII),
            re.compile(
                r"^\s*(?:export\s+)?const\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\(",
                re.ASCII,
            ),
        )

    @staticmethod
    def _scan_symbol_markers(lines: list[str]) -> list[tuple[int, str]]:
        symbol_markers: list[tuple[int, str]] = []
        patterns = SelfLearningService._symbol_patterns()
        for idx, line in enumerate(lines):
            for pattern in patterns:
                matched = pattern.match(line)
                if matched:
                    symbol_markers.append((idx, matched.group(1)))
                    break
        return symbol_markers

    @staticmethod
    def _build_symbol_blocks(
        lines: list[str], symbol_markers: list[tuple[int, str]]
    ) -> list[tuple[str | None, str]]:
        blocks: list[tuple[str | None, str]] = []
        first_symbol_line = symbol_markers[0][0]
        if first_symbol_line > 0:
            preamble = "\n".join(lines[:first_symbol_line]).strip()
            if preamble:
                blocks.append(("module_preamble", preamble))

        for marker_index, (start_line, symbol_name) in enumerate(symbol_markers):
            end_line = (
                symbol_markers[marker_index + 1][0]
                if marker_index + 1 < len(symbol_markers)
                else len(lines)
            )
            block = "\n".join(lines[start_line:end_line]).strip()
            if block:
                blocks.append((symbol_name, block))
        return blocks

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

    def _resolve_repo_commit_sha(self) -> str | None:
        try:
            process = subprocess.run(
                ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if process.returncode != 0:
                return None
            sha = process.stdout.strip()
            if len(sha) >= 7:
                return sha
            return None
        except Exception:
            return None

    def _get_run(self, run_id: str) -> SelfLearningRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def _set_run_state(self, run: SelfLearningRun, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(run, key, value)
        self._append_run_snapshot(run)

    def _add_log(self, run: SelfLearningRun, message: str) -> None:
        if run.logs and run.logs[-1] == message:
            return
        run.logs.append(message)
        if len(run.logs) > _RUN_LOG_LIMIT:
            run.logs[:] = run.logs[-_RUN_LOG_LIMIT:]
        if isinstance(run, SelfLearningRun) and _is_valid_uuid(run.run_id):
            self._append_run_snapshot(run)

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
                max_file_size_kb=_safe_int(limits.get("max_file_size_kb"), 128),
                max_files=_safe_int(limits.get("max_files"), 300),
                max_total_size_mb=_safe_int(limits.get("max_total_size_mb"), 32),
            ),
            llm_config=self._llm_config_from_payload(llm_cfg),
            rag_config=self._rag_config_from_payload(rag_cfg),
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
    def _coerce_choice(value: Any, valid_values: set[str], default: str) -> str:
        candidate = str(value or default).strip()
        return candidate if candidate in valid_values else default

    def _llm_config_from_payload(self, llm_cfg: dict[str, Any]) -> LlmConfig:
        dataset_strategy = cast(
            SelfLearningDatasetStrategy,
            self._coerce_choice(
                llm_cfg.get("dataset_strategy"),
                _VALID_DATASET_STRATEGIES,
                "reconstruct",
            ),
        )
        task_mix_preset = cast(
            SelfLearningTaskMixPreset,
            self._coerce_choice(
                llm_cfg.get("task_mix_preset"),
                _VALID_TASK_MIX_PRESETS,
                "balanced",
            ),
        )
        return LlmConfig(
            base_model=llm_cfg.get("base_model"),
            runtime_id=(
                str(llm_cfg.get("runtime_id") or "").strip().lower()
                if str(llm_cfg.get("runtime_id") or "").strip().lower()
                in _LOCAL_RUNTIME_IDS
                else None
            ),
            dataset_strategy=dataset_strategy,
            task_mix_preset=task_mix_preset,
            lora_rank=_safe_int(llm_cfg.get("lora_rank"), 8),
            learning_rate=float(llm_cfg.get("learning_rate", 2e-4)),
            num_epochs=_safe_int(llm_cfg.get("num_epochs"), 2),
            batch_size=_safe_int(llm_cfg.get("batch_size"), 1),
            max_seq_length=_safe_int(llm_cfg.get("max_seq_length"), 1024),
        )

    def _rag_config_from_payload(self, rag_cfg: dict[str, Any]) -> RagConfig:
        chunking_mode = cast(
            SelfLearningRagChunkingMode,
            self._coerce_choice(
                rag_cfg.get("chunking_mode"),
                _VALID_RAG_CHUNKING_MODES,
                "plain",
            ),
        )
        retrieval_mode = cast(
            SelfLearningRagRetrievalMode,
            self._coerce_choice(
                rag_cfg.get("retrieval_mode"),
                _VALID_RAG_RETRIEVAL_MODES,
                "vector",
            ),
        )
        embedding_profile_id = rag_cfg.get("embedding_profile_id")
        embedding_policy = (
            "allow_fallback"
            if str(rag_cfg.get("embedding_policy") or "strict").strip().lower()
            == "allow_fallback"
            else "strict"
        )
        return RagConfig(
            collection=str(rag_cfg.get("collection") or "default"),
            category=str(rag_cfg.get("category") or "academy_self_learning"),
            chunk_text=bool(rag_cfg.get("chunk_text", False)),
            chunking_mode=chunking_mode,
            retrieval_mode=retrieval_mode,
            embedding_profile_id=(
                str(embedding_profile_id).strip()[:128]
                if embedding_profile_id
                else None
            ),
            embedding_policy=embedding_policy,
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

    def _is_path_allowed_for_source(
        self,
        *,
        source: SelfLearningSource,
        path: Path,
    ) -> bool:
        resolved = path.resolve()
        docs_root = (self.repo_root / "docs").resolve()
        docs_pl_root = (docs_root / "PL").resolve()

        if source == "docs_en":
            return self._is_path_relative_to(
                resolved, docs_root
            ) and not self._is_path_relative_to(resolved, docs_pl_root)
        if source == "docs_pl":
            return self._is_path_relative_to(resolved, docs_pl_root)
        return True

    @staticmethod
    def _is_path_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _contains_blocked_part(path: Path) -> bool:
        return any(part in _BLOCKED_PATH_PARTS for part in path.parts)
