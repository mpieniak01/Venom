"""ONNX LLM runtime adapter for in-process generation/streaming."""

from __future__ import annotations

import importlib.util
import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def is_onnx_genai_available() -> bool:
    """Return True when onnxruntime-genai Python package is installed."""
    return importlib.util.find_spec("onnxruntime_genai") is not None


@dataclass(frozen=True)
class OnnxLlmRuntimeConfig:
    enabled: bool
    model_path: str
    execution_provider: str
    precision: str
    max_new_tokens: int
    temperature: float

    @classmethod
    def from_settings(cls, settings=None) -> "OnnxLlmRuntimeConfig":
        settings = settings or SETTINGS
        return cls(
            enabled=bool(getattr(settings, "ONNX_LLM_ENABLED", False)),
            model_path=str(getattr(settings, "ONNX_LLM_MODEL_PATH", "")),
            execution_provider=str(
                getattr(settings, "ONNX_LLM_EXECUTION_PROVIDER", "cuda")
            ).lower(),
            precision=str(getattr(settings, "ONNX_LLM_PRECISION", "int4")).lower(),
            max_new_tokens=int(getattr(settings, "ONNX_LLM_MAX_NEW_TOKENS", 512)),
            temperature=float(getattr(settings, "ONNX_LLM_TEMPERATURE", 0.2)),
        )


class OnnxLlmClient:
    """ONNX Runtime GenAI adapter exposing readiness + text generation."""

    def __init__(self, settings=None) -> None:
        self._config = OnnxLlmRuntimeConfig.from_settings(settings=settings)
        self._resolved_model_path: str | None = None
        self._model = None
        self._tokenizer = None
        self._tokenizer_stream = None
        self._active_execution_provider: str | None = None
        self._runtime_device_type: str | None = None
        self._lock = threading.Lock()

    @property
    def config(self) -> OnnxLlmRuntimeConfig:
        return self._config

    def is_enabled(self) -> bool:
        return self._config.enabled

    def has_model_path(self) -> bool:
        raw_path = self._config.model_path.strip()
        if not raw_path:
            return False
        return Path(raw_path).exists()

    def _resolve_runtime_model_path(self) -> Path | None:
        raw_path = self._config.model_path.strip()
        if not raw_path:
            return None

        configured = Path(raw_path)
        if configured.is_file() and configured.name == "genai_config.json":
            return configured.parent

        if configured.is_dir():
            direct_genai = configured / "genai_config.json"
            if direct_genai.exists():
                return configured

            candidates = sorted(
                configured.rglob("genai_config.json"),
                key=lambda p: (len(p.parts), str(p)),
            )
            if candidates:
                return candidates[0].parent

        return None

    def can_serve(self) -> bool:
        return self.is_enabled() and is_onnx_genai_available() and self.has_model_path()

    def status_payload(self) -> dict[str, Any]:
        resolved_path = self._resolve_runtime_model_path()
        return {
            **asdict(self._config),
            "genai_installed": is_onnx_genai_available(),
            "model_path_exists": self.has_model_path(),
            "resolved_model_path": str(resolved_path) if resolved_path else None,
            "active_execution_provider": self._active_execution_provider,
            "runtime_device_type": self._runtime_device_type,
            "ready": self.can_serve(),
        }

    @staticmethod
    def _normalize_execution_provider(provider: str) -> str:
        raw = (provider or "").strip().lower()
        aliases = {
            "cudaexecutionprovider": "cuda",
            "cpuexecutionprovider": "cpu",
            "dml": "directml",
            "directmlexecutionprovider": "directml",
        }
        normalized = aliases.get(raw, raw)
        if normalized in {"cuda", "cpu", "directml"}:
            return normalized
        return "cuda"

    @classmethod
    def _provider_fallback_order(cls, provider: str) -> list[str]:
        primary = cls._normalize_execution_provider(provider)
        if primary == "cpu":
            return ["cpu"]
        return [primary, "cpu"]

    @staticmethod
    def _provider_aliases(provider: str) -> list[str]:
        normalized = OnnxLlmClient._normalize_execution_provider(provider)
        mapping = {
            "cuda": ["cuda", "CUDAExecutionProvider"],
            "cpu": ["cpu", "CPUExecutionProvider"],
            "directml": ["directml", "dml", "DmlExecutionProvider", "DML"],
        }
        return mapping.get(normalized, [normalized])

    def _create_model_with_provider(self, og, model_path: str):
        attempts = self._provider_fallback_order(self._config.execution_provider)
        preferred = attempts[0]
        last_error: Exception | None = None
        for provider in attempts:
            for alias in self._provider_aliases(provider):
                try:
                    cfg = og.Config(model_path)
                    cfg.clear_providers()
                    cfg.append_provider(alias)
                    model = og.Model(cfg)
                    self._active_execution_provider = alias
                    self._runtime_device_type = str(
                        getattr(model, "device_type", alias)
                    ).lower()
                    if provider != preferred:
                        logger.warning(
                            f"ONNX fallback provider={provider} alias={alias} "
                            f"(primary={preferred}, device_type={self._runtime_device_type})"
                        )
                    else:
                        logger.info(
                            f"ONNX provider={provider} alias={alias} "
                            f"(device_type={self._runtime_device_type})"
                        )
                    return model
                except Exception as exc:  # pragma: no cover - runtime dependent
                    last_error = exc
                    logger.warning(
                        f"ONNX provider init failed ({provider}/{alias}): {exc}"
                    )

        # Final fallback: let ORT GenAI choose provider automatically.
        model = og.Model(model_path)
        self._active_execution_provider = "auto"
        self._runtime_device_type = str(
            getattr(model, "device_type", "unknown")
        ).lower()
        logger.warning(
            f"ONNX provider fallback=auto (requested={preferred}, "
            f"device_type={self._runtime_device_type}, last_error={last_error})"
        )
        return model

    def ensure_ready(self) -> None:
        if not self.is_enabled():
            raise RuntimeError("ONNX LLM runtime is disabled (ONNX_LLM_ENABLED=false).")
        if not is_onnx_genai_available():
            raise RuntimeError(
                "onnxruntime-genai package is not installed. "
                "Install requirements-extras-onnx."
            )
        resolved_path = self._resolve_runtime_model_path()
        if resolved_path is None:
            raise RuntimeError(
                f"ONNX LLM model path does not exist: {self._config.model_path}"
            )
        self._resolved_model_path = str(resolved_path)

    def _ensure_runtime(self) -> None:
        self.ensure_ready()
        if self._model is not None and self._tokenizer is not None:
            return
        with self._lock:
            if self._model is not None and self._tokenizer is not None:
                return
            import onnxruntime_genai as og  # type: ignore[import-untyped]  # pragma: no cover - runtime import

            model_path = self._resolved_model_path or self._config.model_path
            model = self._create_model_with_provider(og, model_path)
            tokenizer = og.Tokenizer(model)
            tokenizer_stream = tokenizer.create_stream()
            self._model = model
            self._tokenizer = tokenizer
            self._tokenizer_stream = tokenizer_stream

    @staticmethod
    def _messages_to_text(messages: Iterable[dict[str, str]]) -> str:
        lines: list[str] = []
        for item in messages:
            role = str(item.get("role", "user")).strip().lower() or "user"
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{role}: {content}")
        return "\n".join(lines).strip()

    def _build_prompt(self, messages: list[dict[str, str]]) -> str:
        assert self._tokenizer is not None
        fallback = self._messages_to_text(messages)
        try:
            # ORT GenAI expects messages serialized as JSON string.
            return self._tokenizer.apply_chat_template(
                json.dumps(messages, ensure_ascii=False), add_generation_prompt=True
            )
        except Exception:
            return fallback

    def stream_generate(
        self,
        *,
        messages: list[dict[str, str]],
        max_new_tokens: int | None = None,
        temperature: float | None = None,
    ):
        self._ensure_runtime()
        assert self._model is not None
        assert self._tokenizer is not None
        assert self._tokenizer_stream is not None

        import onnxruntime_genai as og  # pragma: no cover - runtime import

        prompt = self._build_prompt(messages)
        input_ids = self._tokenizer.encode(prompt)
        prompt_tokens = int(len(input_ids))
        requested = max_new_tokens or self._config.max_new_tokens
        requested = max(1, int(requested))
        temp = self._config.temperature if temperature is None else float(temperature)
        temp = max(0.0, temp)

        params = og.GeneratorParams(self._model)
        params.set_search_options(
            max_length=prompt_tokens + requested,
            do_sample=temp > 0.0,
            temperature=temp,
        )

        generator = og.Generator(self._model, params)
        generator.append_tokens(input_ids)
        produced = 0
        while not generator.is_done() and produced < requested:
            generator.generate_next_token()
            token_ids = generator.get_next_tokens()
            if token_ids is None:
                break
            # numpy ndarray[int32]
            for token_id in token_ids.tolist():
                produced += 1
                piece = self._tokenizer_stream.decode(int(token_id))
                if piece:
                    yield piece
                if produced >= requested:
                    break

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        max_new_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        return "".join(
            self.stream_generate(
                messages=messages,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
            )
        )
