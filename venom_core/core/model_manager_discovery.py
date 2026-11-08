"""Helpers/mixin for ModelManager model discovery and ONNX metadata handling."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from venom_core.core.model_inventory import (
    cached_model_paths,
    is_hf_model_dir,
    is_onnx_model_dir,
    manifest_size,
    nonempty_file,
)
from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.services.ollama_model_identity import (
    ALIAS_TARGETS,
    EXPLICIT_OPERATOR_TAGS,
    canonical_ollama_entries,
)
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
        # Prefer dedicated Ollama base URL over active runtime endpoint.
        # LLM_LOCAL_ENDPOINT can point to a different provider (e.g. multi_runtime:8014).
        endpoint = (
            os.getenv("OLLAMA_BASE_URL", "").strip()
            or os.getenv("OLLAMA_ENDPOINT", "").strip()
            or os.getenv("LLM_LOCAL_ENDPOINT", "").strip()
            or build_http_url("localhost", 11434, "/v1")
        )
        endpoint = apply_http_policy_to_url(endpoint)
        parsed = urlparse(endpoint)
        if parsed.scheme and parsed.netloc:
            base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
            host = (parsed.hostname or "").lower()
            port = parsed.port
            if "ollama" in host or port == 11434:
                return f"{base}/api/tags"
        return build_http_url("localhost", 11434, "/api/tags")

    def _should_query_ollama_runtime(self) -> bool:
        """Return True when remote Ollama tags polling should run.

        In single-runtime mode we avoid background probing of inactive runtimes.
        Set MODEL_DISCOVERY_FORCE_OLLAMA_QUERY=true to override.
        """
        forced = os.getenv("MODEL_DISCOVERY_FORCE_OLLAMA_QUERY", "").strip().lower()
        if forced in {"1", "true", "yes", "on"}:
            return True
        active_server = os.getenv("ACTIVE_LLM_SERVER", "").strip().lower()
        return active_server in {"", "ollama"}

    def _register_local_entry(
        self,
        models: Dict[str, Dict[str, Any]],
        model_path: Path,
        source: str,
        provider: str = "vllm",
        model_name: str | None = None,
        model_key: str | None = None,
    ) -> None:
        """Register one installation with its actual path, provider and measured size."""
        size_bytes = self._calculate_model_size_bytes(model_path)
        onnx_metadata = self._load_onnx_metadata(model_path)
        model_type, provider = self._detect_model_type_and_provider(
            model_path=model_path,
            provider=provider,
        )

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
            "installed": True,
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
        """Classify the installed payload using explicit provider and path evidence."""
        if model_path.suffix.lower() == ".gguf":
            return "gguf", provider
        if model_path.suffix.lower() == ".onnx" or is_onnx_model_dir(model_path):
            return "onnx", "onnx"
        return "folder", provider

    def _build_search_dirs(self) -> List[Path]:
        search_dirs = [self.models_dir]
        default_models_dir = Path("./models")
        if default_models_dir.exists() and default_models_dir not in search_dirs:
            search_dirs.append(default_models_dir)
        return search_dirs

    @staticmethod
    def _looks_like_onnx_runtime_dir(model_path: Path) -> bool:
        """Recognize a directory containing actual ONNX model payloads."""
        return is_onnx_model_dir(model_path)

    @staticmethod
    def _looks_like_hf_runtime_dir(model_path: Path) -> bool:
        """Recognize a complete Hugging Face installation rather than a working directory."""
        return is_hf_model_dir(model_path)

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
            for model_path in base_dir.iterdir():
                if not self._is_local_model_candidate(
                    model_path,
                    skip_dirs,
                ):
                    continue
                self._try_register_local_entry(models, model_path, base_dir.name)

    @staticmethod
    def _is_local_model_candidate(
        model_path: Path,
        skip_dirs: set[str],
    ) -> bool:
        """Reject excluded or incomplete directories before registering model payloads."""
        if model_path.name in skip_dirs:
            return False
        if model_path.suffix.lower() in {".onnx", ".gguf"}:
            return nonempty_file(model_path)
        if not model_path.is_dir():
            return False
        if ModelManagerDiscoveryMixin._is_academy_artifact_dir(model_path):
            return False
        if ModelManagerDiscoveryMixin._looks_like_onnx_runtime_dir(model_path):
            return True
        if ModelManagerDiscoveryMixin._looks_like_hf_runtime_dir(model_path):
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
        provider: str = "vllm",
    ) -> None:
        """Register one candidate and isolate filesystem or metadata errors to that entry."""
        try:
            self._register_local_entry(
                models,
                model_path,
                source=source_name,
                provider=provider,
                model_name=model_name,
                model_key=model_key,
            )
        except Exception as exc:
            logger.warning("Nie udało się odczytać modelu %s: %s", model_path, exc)

    def _load_ollama_manifest_entries(
        self,
        manifests_dir: Path,
    ) -> List[Dict[str, Any]]:
        """Enumerate only manifests whose referenced model blobs are present."""
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
            if not size_bytes:
                continue
            try:
                digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            except OSError:
                continue
            entries.append(
                {
                    "name": entry_name,
                    "size_gb": size_bytes / (1024**3) if size_bytes else None,
                    "type": "ollama",
                    "digest": digest,
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
        if len(relative_parts) >= 4 and relative_parts[0] == "hf.co":
            return f"hf.co/{namespace}/{model}:{tag}"
        if namespace and namespace != "library":
            return f"{namespace}/{model}:{tag}"
        return f"{model}:{tag}"

    @staticmethod
    def _read_manifest_size_bytes(manifest_path: Path) -> int:
        """Return verified manifest payload size or zero when its blobs are incomplete."""
        try:
            return manifest_size(manifest_path)
        except (
            ValueError,
            TypeError,
            KeyError,
            OSError,
            StopIteration,
            AttributeError,
        ):
            return 0

    def _collect_ollama_entries(
        self,
        ollama_models: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        ollama_models_by_digest: Dict[str, Dict[str, Any]] = {}
        entries: List[Dict[str, Any]] = []
        for model in canonical_ollama_entries(ollama_models):
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
                "details": model.get("details", {}),
                "display_name": model.get("display_name", entry_name),
                "aliases": model.get("aliases", []),
                "ollama_alias_evidence": model.get("ollama_alias_evidence", {}),
            }
            capabilities = model.get("capabilities")
            if isinstance(capabilities, list) and capabilities:
                entry["capabilities"] = capabilities
                entry["chat_compatible"] = "completion" in capabilities
            if entry_name in EXPLICIT_OPERATOR_TAGS or entry_name in ALIAS_TARGETS:
                entries.append(entry)
                continue
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
        try:
            self.ollama_cache_path.write_text(
                json.dumps(entries, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Nie udało się zapisać cache modeli Ollama: %s", exc)

    def _load_ollama_cache(self, models: Dict[str, Dict[str, Any]]) -> None:
        """Enrich current manifests only; cached presence/activity is never evidence."""
        try:
            if not self.ollama_cache_path.exists():
                return
            for entry in json.loads(self.ollama_cache_path.read_text("utf-8")):
                current = models.get("ollama::" + str(entry.get("name", "")))
                if (
                    current
                    and current.get("digest")
                    and current["digest"] == entry.get("digest")
                ):
                    current["quantization"] = entry.get("quantization", "unknown")
                    current["details"] = entry.get("details", {})
                    if isinstance(entry.get("capabilities"), list):
                        current["capabilities"] = entry["capabilities"]
                    if isinstance(entry.get("chat_compatible"), bool):
                        current["chat_compatible"] = entry["chat_compatible"]
        except (OSError, ValueError, TypeError, AttributeError):
            logger.debug("Ignoring unavailable historical Ollama metadata")

    def _register_manifest_fallbacks(
        self,
        search_dirs: List[Path],
        models: Dict[str, Dict[str, Any]],
    ) -> None:
        for base_dir in search_dirs:
            for directory in ("manifests-v2", "manifests"):
                for entry in self._load_ollama_manifest_entries(base_dir / directory):
                    entry_name = entry.get("name")
                    if entry_name:
                        models.setdefault(f"ollama::{entry_name}", entry)

    def _replace_ollama_entries(
        self,
        models: Dict[str, Dict[str, Any]],
        entries: List[Dict[str, Any]],
    ) -> None:
        for key in tuple(models):
            if key.startswith("ollama::"):
                models.pop(key, None)
        self._register_ollama_entries(models, entries)
        self._save_ollama_cache(entries)

    async def _fetch_ollama_runtime_entries(self) -> List[Dict[str, Any]] | None:
        try:
            async with TrafficControlledHttpClient(
                provider="ollama",
                timeout=10.0,
            ) as client:
                response = await client.aget(
                    self._resolve_ollama_tags_url(),
                    raise_for_status=False,
                )
            if response.status_code != 200:
                logger.warning(
                    "Nie udało się pobrać listy modeli z Ollama: %s",
                    response.status_code,
                )
                return None
            ollama_data = response.json()
            return self._collect_ollama_entries(ollama_data.get("models", []))
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            now = time.time()
            if now - self._last_ollama_warning > 60:
                logger.warning("Ollama nie jest dostępne: %s", exc)
                self._last_ollama_warning = now
        except httpx.HTTPError as exc:
            logger.error("Błąd HTTP podczas pobierania modeli z Ollama: %s", exc)
        except ValueError as exc:
            logger.error(
                "Błędna odpowiedź JSON podczas pobierania modeli z Ollama: %s", exc
            )
        except Exception as exc:
            logger.warning(
                "Nie udało się pobrać modeli z Ollama (fallback do lokalnego skanu): %s",
                exc,
            )
        return None

    def _discover_local_models(self) -> Dict[str, Dict[str, Any]]:
        """Perform filesystem discovery outside the event loop."""
        models: Dict[str, Dict[str, Any]] = {}
        search_dirs = self._build_search_dirs()
        self._scan_local_dirs(search_dirs, models)
        # Offline evidence is the current manifests AND blobs, never a historical cache.
        self._register_manifest_fallbacks(search_dirs, models)
        self._load_ollama_cache(models)
        self._discover_other_models(search_dirs, models)
        return models

    def _discover_other_models(self, search_dirs, models) -> None:
        """Discover complete cache snapshots and research payloads without loading inference engines."""
        hub_roots = [Path.home() / ".local/share/venom/maintenance-comparison/hub"]
        hub_roots.extend(base / "cache/huggingface/hub" for base in search_dirs)
        hub_roots.extend(base / "hf_cache" for base in search_dirs)
        hub_roots.append(Path.home() / ".cache/huggingface/hub")
        known_paths = {
            Path(m["path"]).resolve()
            for m in models.values()
            if not str(m["path"]).startswith("ollama://")
        }
        for name, path in cached_model_paths(hub_roots):
            try:
                resolved = path.resolve()
                if resolved not in known_paths:
                    self._register_cached_model(models, name, path)
                    known_paths.add(resolved)
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("Skipping unavailable model snapshot %s: %s", path, exc)
        for base in search_dirs:
            for path in (base / "research").glob("*/*"):
                try:
                    self._register_research_models(models, path)
                except (OSError, ValueError, TypeError) as exc:
                    logger.warning(
                        "Skipping unavailable research model %s: %s", path, exc
                    )

    def _register_cached_model(self, models, name, path) -> None:
        """Register one pinned cache snapshot and its revision, skipping invalid entries."""
        config = json.loads((path / "config.json").read_text())
        if not isinstance(config, dict):
            raise ValueError("model_config_not_object")
        provider = (
            "ctranslate2"
            if (path / "model.bin").is_file() and not config.get("model_type")
            else "transformers"
        )
        key = provider + "::" + name + "@" + path.name
        self._register_local_entry(
            models,
            path,
            "huggingface-cache",
            provider=provider,
            model_name=name,
            model_key=key,
        )
        models[key]["revision"] = path.name

    def _register_research_models(self, models, path) -> None:
        """Register one research payload while isolating per-directory metadata errors."""
        if not path.is_dir():
            return
        if is_hf_model_dir(path):
            self._try_register_local_entry(
                models,
                path,
                "research",
                provider="research",
                model_name=path.parent.name,
                model_key="research::" + str(path.resolve()),
            )
        for checkpoint in path.glob("*.pth"):
            if nonempty_file(checkpoint):
                self._try_register_local_entry(
                    models,
                    checkpoint,
                    "research",
                    provider="rwkv",
                    model_name=checkpoint.stem,
                    model_key="rwkv::" + str(checkpoint.resolve()),
                )

    async def list_local_models(self) -> List[Dict[str, Any]]:
        models = await asyncio.to_thread(self._discover_local_models)

        if self._should_query_ollama_runtime():
            entries = await self._fetch_ollama_runtime_entries()
            if entries is not None:
                await asyncio.to_thread(self._replace_ollama_entries, models, entries)
        else:
            logger.debug(
                "Pomijam aktywne odpytywanie Ollama (/api/tags), bo ACTIVE_LLM_SERVER=%s",
                os.getenv("ACTIVE_LLM_SERVER", "").strip().lower() or "unknown",
            )

        local = [
            model for model in models.values() if model.get("provider") != "ollama"
        ]
        ollama = [
            model for model in models.values() if model.get("provider") == "ollama"
        ]
        return local + canonical_ollama_entries(ollama)
