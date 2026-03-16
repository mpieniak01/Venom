"""Helpers/mixin for ModelManager model discovery and ONNX metadata handling."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import apply_http_policy_to_url, build_http_url

logger = get_logger(__name__)

ONNX_METADATA_FILENAME = "venom_onnx_metadata.json"


class ModelManagerDiscoveryMixin:
    """Mixin with discovery/listing helpers used by ModelManager."""

    models_dir: Path
    ollama_cache_path: Path
    _last_ollama_warning: float

    @staticmethod
    def _normalize_onnx_model_slug(model_name: str) -> str:
        return model_name.strip().replace("/", "--").replace(":", "-").replace(" ", "-")

    @staticmethod
    def _load_onnx_metadata(model_path: Path) -> Dict[str, Any]:
        candidates: List[Path] = []
        if model_path.is_dir():
            candidates.append(model_path / ONNX_METADATA_FILENAME)
        else:
            candidates.append(model_path.with_suffix(".json"))
            candidates.append(model_path.parent / ONNX_METADATA_FILENAME)

        for metadata_path in candidates:
            if not metadata_path.exists():
                continue
            try:
                payload = json.loads(metadata_path.read_text("utf-8"))
                if isinstance(payload, dict):
                    return payload
            except Exception as exc:
                logger.warning(
                    "Nie udało się wczytać metadanych ONNX (%s): %s",
                    metadata_path,
                    exc,
                )
        return {}

    @staticmethod
    def _default_onnx_metadata_for_path(model_path: Path) -> Dict[str, Any]:
        path_name = model_path.name.lower()
        precision = "unknown"
        if "int4" in path_name:
            precision = "int4"
        elif "fp16" in path_name:
            precision = "fp16"

        execution_provider = "unknown"
        if "cuda" in path_name:
            execution_provider = "cuda"
        elif "cpu" in path_name:
            execution_provider = "cpu"
        elif "directml" in path_name:
            execution_provider = "directml"

        return {
            "provider": "onnx",
            "runtime": "onnx",
            "precision": precision,
            "execution_provider": execution_provider,
        }

    def _resolve_ollama_tags_url(self) -> str:
        endpoint = os.getenv(
            "LLM_LOCAL_ENDPOINT",
            build_http_url("localhost", 11434, "/v1"),
        )
        endpoint = apply_http_policy_to_url(endpoint)
        parsed = urlparse(endpoint)
        if parsed.scheme and parsed.netloc:
            base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
            return f"{base}/api/tags"
        return build_http_url("localhost", 11434, "/api/tags")

    def _register_local_entry(
        self,
        models: Dict[str, Dict[str, Any]],
        model_path: Path,
        source: str,
        provider: str = "vllm",
        model_name: str | None = None,
        model_key: str | None = None,
    ) -> None:
        size_bytes = self._calculate_model_size_bytes(model_path)
        onnx_metadata = self._load_onnx_metadata(model_path)
        metadata_provider = str(onnx_metadata.get("provider", "")).lower()
        model_type, provider = self._detect_model_type_and_provider(
            model_path=model_path,
            provider=provider,
        )
        if metadata_provider == "onnx":
            provider = "onnx"

        onnx_payload: Dict[str, Any] = {}
        if provider == "onnx":
            inferred = self._default_onnx_metadata_for_path(model_path)
            onnx_payload = {**inferred, **onnx_metadata}

        resolved_name = str(model_name or model_path.name).strip() or model_path.name
        resolved_key = str(model_key or resolved_name).strip() or resolved_name

        models[resolved_key] = {
            "name": resolved_name,
            "size_gb": size_bytes / (1024**3) if size_bytes else None,
            "type": model_type,
            "quantization": "unknown",
            "path": str(model_path),
            "source": source,
            "provider": provider,
            "active": False,
            **onnx_payload,
        }

    @staticmethod
    def _calculate_model_size_bytes(model_path: Path) -> int:
        if model_path.is_file():
            return model_path.stat().st_size
        size_bytes = 0
        for file_path in model_path.rglob("*"):
            if file_path.is_file():
                size_bytes += file_path.stat().st_size
        return size_bytes

    @staticmethod
    def _detect_model_type_and_provider(
        *,
        model_path: Path,
        provider: str,
    ) -> tuple[str, str]:
        lower_path = str(model_path).lower()
        if ".gguf" in lower_path:
            return "gguf", provider
        if model_path.suffix in {".onnx", ".bin"}:
            return "onnx", "onnx"
        if model_path.is_dir():
            resolved_provider = (
                "onnx"
                if (
                    "onnx" in model_path.name.lower()
                    or (model_path / ONNX_METADATA_FILENAME).exists()
                    or (model_path / "genai_config.json").exists()
                    or any(model_path.glob("*.onnx"))
                )
                else provider
            )
            return "folder", resolved_provider
        return "folder", provider

    def _build_search_dirs(self) -> List[Path]:
        search_dirs = [self.models_dir]
        default_models_dir = Path("./models")
        if default_models_dir.exists() and default_models_dir not in search_dirs:
            search_dirs.append(default_models_dir)
        return search_dirs

    @staticmethod
    def _looks_like_onnx_runtime_dir(model_path: Path) -> bool:
        if not model_path.is_dir():
            return False
        if (model_path / ONNX_METADATA_FILENAME).exists():
            return True
        if (model_path / "genai_config.json").exists():
            return True
        if (model_path / "model.onnx").exists():
            return True
        return any(model_path.glob("*.onnx"))

    @staticmethod
    def _looks_like_hf_runtime_dir(model_path: Path) -> bool:
        if not model_path.is_dir():
            return False
        if not (model_path / "config.json").exists():
            return False
        if any(model_path.glob("*.safetensors")):
            return True
        if any(model_path.glob("pytorch_model*.bin")):
            return True
        if any(model_path.glob("model*.bin")):
            return True
        return False

    @staticmethod
    def _is_academy_artifact_dir(model_path: Path) -> bool:
        name = model_path.name.lower()
        if name.startswith("self_learning_"):
            return True
        if name.startswith("checkpoint-"):
            return True
        if (model_path / "adapter").exists() and (
            model_path / "train_script.py"
        ).exists():
            return True
        if (model_path / "training.log").exists() and not (
            model_path / "config.json"
        ).exists():
            return True
        return False

    def _register_academy_runtime_vllm_entries(
        self,
        models: Dict[str, Dict[str, Any]],
        base_dir: Path,
    ) -> None:
        for adapter_dir in base_dir.iterdir():
            if not adapter_dir.is_dir():
                continue
            runtime_dir = adapter_dir / "runtime_vllm"
            if not self._looks_like_hf_runtime_dir(runtime_dir):
                continue
            runtime_model_name = f"venom-adapter-{adapter_dir.name}"
            self._try_register_local_entry(
                models,
                runtime_dir,
                source_name=base_dir.name,
                model_name=runtime_model_name,
                model_key=f"academy-runtime-vllm::{runtime_model_name}",
            )

    def _scan_local_dirs(
        self,
        search_dirs: List[Path],
        models: Dict[str, Dict[str, Any]],
    ) -> None:
        skip_dirs = {"hf_cache", "__pycache__", ".cache", "manifests", "blobs"}
        for base_dir in search_dirs:
            if not base_dir.exists():
                continue
            self._register_academy_runtime_vllm_entries(models, base_dir)
            allow_workspace_fallback = base_dir.name == "models"
            for model_path in base_dir.iterdir():
                if not self._is_local_model_candidate(
                    model_path,
                    skip_dirs,
                    allow_workspace_fallback=allow_workspace_fallback,
                ):
                    continue
                self._try_register_local_entry(models, model_path, base_dir.name)

    @staticmethod
    def _is_local_model_candidate(
        model_path: Path,
        skip_dirs: set[str],
        *,
        allow_workspace_fallback: bool = False,
    ) -> bool:
        if model_path.name in skip_dirs:
            return False
        if model_path.suffix in {".onnx", ".gguf", ".bin"}:
            return True
        if not model_path.is_dir():
            return False
        if ModelManagerDiscoveryMixin._is_academy_artifact_dir(model_path):
            return False
        if ModelManagerDiscoveryMixin._looks_like_onnx_runtime_dir(model_path):
            return True
        if ModelManagerDiscoveryMixin._looks_like_hf_runtime_dir(model_path):
            return True
        if allow_workspace_fallback:
            return True
        return False

    def _try_register_local_entry(
        self,
        models: Dict[str, Dict[str, Any]],
        model_path: Path,
        source_name: str,
        *,
        model_name: str | None = None,
        model_key: str | None = None,
    ) -> None:
        try:
            self._register_local_entry(
                models,
                model_path,
                source=source_name,
                provider="vllm",
                model_name=model_name,
                model_key=model_key,
            )
        except Exception as exc:
            logger.warning("Nie udało się odczytać modelu %s: %s", model_path, exc)

    def _load_ollama_manifest_entries(
        self,
        manifests_dir: Path,
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        if not manifests_dir.exists():
            return entries
        for manifest_path in manifests_dir.rglob("*"):
            if not manifest_path.is_file():
                continue
            relative_parts = self._resolve_manifest_relative_parts(
                manifests_dir,
                manifest_path,
            )
            if relative_parts is None or len(relative_parts) < 2:
                continue
            registry = relative_parts[0]
            entry_name = self._build_ollama_manifest_entry_name(relative_parts)
            size_bytes = self._read_manifest_size_bytes(manifest_path)
            entries.append(
                {
                    "name": entry_name,
                    "size_gb": size_bytes / (1024**3) if size_bytes else None,
                    "type": "ollama",
                    "quantization": "unknown",
                    "path": f"ollama://{registry}",
                    "source": "ollama",
                    "provider": "ollama",
                    "active": False,
                }
            )
        return entries

    @staticmethod
    def _resolve_manifest_relative_parts(
        manifests_dir: Path,
        manifest_path: Path,
    ) -> Optional[tuple[str, ...]]:
        try:
            return manifest_path.relative_to(manifests_dir).parts
        except ValueError:
            return None

    @staticmethod
    def _build_ollama_manifest_entry_name(relative_parts: tuple[str, ...]) -> str:
        tag = relative_parts[-1]
        model = relative_parts[-2]
        namespace = relative_parts[-3] if len(relative_parts) >= 3 else ""
        if namespace and namespace != "library":
            return f"{namespace}/{model}:{tag}"
        return f"{model}:{tag}"

    @staticmethod
    def _read_manifest_size_bytes(manifest_path: Path) -> int:
        size_bytes = 0
        try:
            manifest_payload = json.loads(manifest_path.read_text("utf-8"))
            layers = manifest_payload.get("layers") or []
            size_bytes = sum(
                layer.get("size", 0) for layer in layers if isinstance(layer, dict)
            )
            config = manifest_payload.get("config") or {}
            if isinstance(config, dict):
                size_bytes += config.get("size", 0) or 0
        except Exception as exc:
            logger.warning(
                "Nie udało się odczytać manifestu %s: %s", manifest_path, exc
            )
        return size_bytes

    def _collect_ollama_entries(
        self,
        ollama_models: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        ollama_models_by_digest: Dict[str, Dict[str, Any]] = {}
        entries: List[Dict[str, Any]] = []
        for model in ollama_models:
            size_bytes = model.get("size", 0)
            entry_name = model.get("name", "unknown")
            digest = model.get("digest", "")
            entry = {
                "name": entry_name,
                "size_gb": size_bytes / (1024**3),
                "type": "ollama",
                "quantization": model.get("details", {}).get(
                    "quantization_level",
                    "unknown",
                ),
                "path": "ollama://",
                "source": "ollama",
                "provider": "ollama",
                "active": False,
                "digest": digest,
            }
            if not digest:
                entries.append(entry)
                continue
            existing = ollama_models_by_digest.get(digest)
            if existing and (
                not entry_name.endswith(":latest")
                or existing["name"].endswith(":latest")
            ):
                continue
            ollama_models_by_digest[digest] = entry
        entries.extend(ollama_models_by_digest.values())
        return entries

    def _register_ollama_entries(
        self,
        models: Dict[str, Dict[str, Any]],
        entries: List[Dict[str, Any]],
    ) -> None:
        for entry in entries:
            entry_name = entry.get("name")
            if entry_name:
                models[f"ollama::{entry_name}"] = entry

    def _save_ollama_cache(self, entries: List[Dict[str, Any]]) -> None:
        if not entries:
            return
        try:
            self.ollama_cache_path.write_text(
                json.dumps(entries, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Nie udało się zapisać cache modeli Ollama: %s", exc)

    def _load_ollama_cache(self, models: Dict[str, Dict[str, Any]]) -> None:
        try:
            if not self.ollama_cache_path.exists():
                return
            cached_entries = json.loads(self.ollama_cache_path.read_text("utf-8"))
            for entry in cached_entries:
                entry_name = entry.get("name")
                if entry_name:
                    models.setdefault(f"ollama::{entry_name}", entry)
        except Exception as cache_error:
            logger.warning("Nie udało się wczytać cache modeli Ollama: %s", cache_error)

    def _register_manifest_fallbacks(
        self,
        search_dirs: List[Path],
        models: Dict[str, Dict[str, Any]],
    ) -> None:
        for base_dir in search_dirs:
            manifest_root = base_dir / "manifests"
            for entry in self._load_ollama_manifest_entries(manifest_root):
                entry_name = entry.get("name")
                if entry_name:
                    models.setdefault(f"ollama::{entry_name}", entry)

    async def list_local_models(self) -> List[Dict[str, Any]]:
        models: Dict[str, Dict[str, Any]] = {}

        search_dirs = self._build_search_dirs()
        self._scan_local_dirs(search_dirs, models)
        # Keep Ollama model visibility even when daemon is offline.
        self._load_ollama_cache(models)
        self._register_manifest_fallbacks(search_dirs, models)

        try:
            async with TrafficControlledHttpClient(
                provider="ollama",
                timeout=10.0,
            ) as client:
                response = await client.aget(
                    self._resolve_ollama_tags_url(),
                    raise_for_status=False,
                )
                if response.status_code == 200:
                    ollama_data = response.json()
                    entries = self._collect_ollama_entries(
                        ollama_data.get("models", [])
                    )
                    self._register_ollama_entries(models, entries)
                    self._save_ollama_cache(entries)
                else:
                    logger.warning(
                        f"Nie udało się pobrać listy modeli z Ollama: "
                        f"{response.status_code}",
                    )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            now = time.time()
            if now - self._last_ollama_warning > 60:
                logger.warning(f"Ollama nie jest dostępne: {exc}")
                self._last_ollama_warning = now
        except httpx.HTTPError as exc:
            logger.error(f"Błąd HTTP podczas pobierania modeli z Ollama: {exc}")
        except ValueError as exc:
            logger.error(
                f"Błędna odpowiedź JSON podczas pobierania modeli z Ollama: {exc}"
            )
        except Exception as exc:
            logger.warning(
                f"Nie udało się pobrać modeli z Ollama (fallback do lokalnego skanu): {exc}"
            )

        return list(models.values())
