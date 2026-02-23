"""Moduł: model_manager - Zarządca Modeli i Hot Swap dla Adapterów LoRA."""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, urlunparse

import httpx
import psutil

from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import apply_http_policy_to_url, build_http_url

logger = get_logger(__name__)

# Konfiguracja Resource Guard
MAX_STORAGE_GB = 50  # Limit na modele w GB
DEFAULT_MODEL_SIZE_GB = 4.0  # Szacowany domyślny rozmiar modelu dla Resource Guard
BYTES_IN_GB = 1024**3
ONNX_METADATA_FILENAME = "venom_onnx_metadata.json"


class ModelVersion:
    """
    Reprezentacja wersji modelu.
    """

    def __init__(
        self,
        version_id: str,
        base_model: str,
        adapter_path: Optional[str] = None,
        created_at: Optional[str] = None,
        performance_metrics: Optional[Dict[str, Any]] = None,
        is_active: bool = False,
    ):
        """
        Inicjalizacja wersji modelu.

        Args:
            version_id: Unikalny identyfikator wersji (np. "v1.0", "v1.1")
            base_model: Nazwa bazowego modelu
            adapter_path: Ścieżka do adaptera LoRA (jeśli istnieje)
            created_at: Timestamp utworzenia
            performance_metrics: Metryki wydajności (accuracy, loss, etc.)
            is_active: Czy to aktywna wersja w produkcji
        """
        self.version_id = version_id
        self.base_model = base_model
        self.adapter_path = adapter_path
        self.created_at = created_at
        self.performance_metrics = performance_metrics or {}
        self.is_active = is_active

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje do słownika."""
        return {
            "version_id": self.version_id,
            "base_model": self.base_model,
            "adapter_path": self.adapter_path,
            "created_at": self.created_at,
            "performance_metrics": self.performance_metrics,
            "is_active": self.is_active,
        }


class ModelManager:
    """
    Zarządca Modeli - Hot Swap i Genealogia Inteligencji.

    Funkcjonalności:
    - Rejestracja nowych wersji modeli
    - Ładowanie adapterów LoRA (PEFT)
    - Hot swap (zamiana modelu bez restartu)
    - Historia wersji ("Genealogia Inteligencji")
    - Integracja z Ollama (tworzenie Modelfile z adapterem)
    """

    def __init__(self, models_dir: Optional[str] = None):
        """
        Inicjalizacja ModelManager.

        Args:
            models_dir: Katalog z modelami (domyślnie ./data/models)
        """
        self.models_dir = Path(models_dir or "./data/models")
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.active_adapter_state_path = Path("./data/training/active_adapter.json")
        self.ollama_cache_path = self.models_dir / "ollama_models_cache.json"
        self._last_ollama_warning = 0.0

        # Rejestr wersji modeli
        self.versions: Dict[str, ModelVersion] = {}

        # Aktywna wersja
        self.active_version: Optional[str] = None

        logger.info(f"ModelManager zainicjalizowany (models_dir={self.models_dir})")

    @staticmethod
    def _normalize_onnx_model_slug(model_name: str) -> str:
        """Normalize model id into a filesystem-safe slug."""
        return model_name.strip().replace("/", "--").replace(":", "-").replace(" ", "-")

    @staticmethod
    def _load_onnx_metadata(model_path: Path) -> Dict[str, Any]:
        """Load optional ONNX metadata from model directory/file sibling."""
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
            except Exception as e:
                logger.warning(
                    "Nie udało się wczytać metadanych ONNX (%s): %s",
                    metadata_path,
                    e,
                )
        return {}

    @staticmethod
    def _default_onnx_metadata_for_path(model_path: Path) -> Dict[str, Any]:
        """Infer best-effort ONNX metadata when explicit metadata is missing."""
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

    def build_onnx_llm_model(
        self,
        *,
        model_name: str,
        output_dir: Optional[str] = None,
        execution_provider: str = "cuda",
        precision: str = "int4",
        builder_script: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build ONNX LLM model via onnxruntime-genai builder and persist metadata.

        Returns:
            Dict with success flag and build details/error.
        """
        if not model_name or not re.match(r"^[\w\-.:/]+$", model_name):
            return {
                "success": False,
                "message": "Nieprawidłowa nazwa modelu ONNX.",
            }

        exec_provider = (execution_provider or "cuda").strip().lower()
        prec = (precision or "int4").strip().lower()
        if exec_provider not in {"cuda", "cpu", "directml"}:
            return {
                "success": False,
                "message": "execution_provider musi być jednym z: cuda, cpu, directml",
            }
        if prec not in {"int4", "fp16"}:
            return {"success": False, "message": "precision musi być: int4 lub fp16"}

        default_script = os.getenv(
            "ONNX_GENAI_BUILDER_SCRIPT",
            "third_party/onnxruntime-genai/src/python/py/models/builder.py",
        )
        script_path = Path(builder_script or default_script).expanduser().resolve()
        if not script_path.exists():
            return {
                "success": False,
                "message": (
                    "Nie znaleziono skryptu builder.py. "
                    "Ustaw ONNX_GENAI_BUILDER_SCRIPT lub parametr builder_script."
                ),
                "builder_script": str(script_path),
            }

        if output_dir:
            output_path = Path(output_dir).expanduser().resolve()
        else:
            slug = self._normalize_onnx_model_slug(model_name)
            output_path = (Path("./models") / f"{slug}-onnx").resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        command = [
            sys.executable or "python",
            str(script_path),
            "-m",
            model_name,
            "-e",
            exec_provider,
            "-p",
            prec,
            "-o",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=3600,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Timeout podczas build ONNX modelu."}
        except Exception as e:
            return {"success": False, "message": f"Błąd build ONNX: {e}"}

        if result.returncode != 0:
            return {
                "success": False,
                "message": "Builder ONNX zakończył się błędem.",
                "exit_code": result.returncode,
                "stderr": result.stderr.strip(),
                "stdout": result.stdout.strip(),
            }

        metadata = {
            "provider": "onnx",
            "runtime": "onnx",
            "model_name": model_name,
            "output_dir": str(output_path),
            "precision": prec,
            "execution_provider": exec_provider,
            "builder_script": str(script_path),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        metadata_path = output_path / ONNX_METADATA_FILENAME
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

        logger.info("Zbudowano ONNX model: %s -> %s", model_name, output_path)
        return {
            "success": True,
            "message": "Model ONNX zbudowany pomyślnie.",
            "model_name": model_name,
            "output_dir": str(output_path),
            "metadata_path": str(metadata_path),
            "stdout": result.stdout.strip(),
        }

    def _save_active_adapter_state(
        self, adapter_id: str, adapter_path: str, base_model: str
    ) -> None:
        """Persistuje aktualnie aktywny adapter dla restore po restarcie."""
        self.active_adapter_state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "adapter_id": adapter_id,
            "adapter_path": adapter_path,
            "base_model": base_model,
            "activated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "academy",
        }
        with open(self.active_adapter_state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _load_active_adapter_state(self) -> Optional[Dict[str, Any]]:
        """Wczytuje persistowany stan aktywnego adaptera."""
        if not self.active_adapter_state_path.exists():
            return None
        try:
            with open(self.active_adapter_state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return None
                return data
        except Exception as e:
            logger.warning(f"Nie udało się odczytać stanu aktywnego adaptera: {e}")
            return None

    def _clear_active_adapter_state(self) -> None:
        """Czyści persistowany stan aktywnego adaptera."""
        try:
            self.active_adapter_state_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Nie udało się usunąć stanu aktywnego adaptera: {e}")

    def restore_active_adapter(self) -> bool:
        """
        Próbuje odtworzyć aktywny adapter z persistowanego stanu.

        Returns:
            True jeśli adapter został odtworzony i aktywowany, False w przeciwnym razie.
        """
        state = self._load_active_adapter_state()
        if not state:
            return False

        adapter_id = str(state.get("adapter_id") or "").strip()
        adapter_path = str(state.get("adapter_path") or "").strip()
        base_model = str(state.get("base_model") or "academy-base").strip()
        if not adapter_id or not adapter_path:
            self._clear_active_adapter_state()
            return False

        if not Path(adapter_path).exists():
            logger.warning("Persistowany adapter nie istnieje: %s", adapter_path)
            self._clear_active_adapter_state()
            return False

        restored = self.activate_adapter(
            adapter_id=adapter_id,
            adapter_path=adapter_path,
            base_model=base_model,
        )
        if not restored:
            self._clear_active_adapter_state()
        return restored

    def _resolve_ollama_tags_url(self) -> str:
        """
        Zwraca URL /api/tags dla Ollama zgodny z aktualnym runtime.

        W Dockerze endpoint bywa ustawiony jako ollama:11434/v1,
        a lokalnie często localhost:11434/v1.
        """
        endpoint = os.getenv(
            "LLM_LOCAL_ENDPOINT", build_http_url("localhost", 11434, "/v1")
        )
        endpoint = apply_http_policy_to_url(endpoint)
        parsed = urlparse(endpoint)
        if parsed.scheme and parsed.netloc:
            base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
            return f"{base}/api/tags"
        return build_http_url("localhost", 11434, "/api/tags")

    def register_version(
        self,
        version_id: str,
        base_model: str,
        adapter_path: Optional[str] = None,
        performance_metrics: Optional[Dict[str, Any]] = None,
    ) -> ModelVersion:
        """
        Rejestruje nową wersję modelu.

        Args:
            version_id: ID wersji
            base_model: Nazwa bazowego modelu
            adapter_path: Ścieżka do adaptera LoRA
            performance_metrics: Metryki wydajności

        Returns:
            Zarejestrowana wersja
        """
        from datetime import datetime

        version = ModelVersion(
            version_id=version_id,
            base_model=base_model,
            adapter_path=adapter_path,
            created_at=datetime.now().isoformat(),
            performance_metrics=performance_metrics,
            is_active=False,
        )

        self.versions[version_id] = version
        logger.info(f"Zarejestrowano wersję modelu: {version_id}")

        return version

    def activate_version(self, version_id: str) -> bool:
        """
        Aktywuje wersję modelu (hot swap).

        Args:
            version_id: ID wersji do aktywacji

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        if version_id not in self.versions:
            logger.error("Wersja modelu nie istnieje")
            return False

        # Dezaktywuj poprzednią wersję
        if self.active_version:
            self.versions[self.active_version].is_active = False

        # Aktywuj nową wersję
        self.versions[version_id].is_active = True
        self.active_version = version_id

        logger.info("Aktywowano wersję modelu")
        return True

    def _is_path_within_models_dir(self, path: Path) -> bool:
        """Sprawdza czy ścieżka mieści się w katalogu modeli Academy."""
        try:
            path.relative_to(self.models_dir.resolve())
            return True
        except ValueError:
            return False

    def get_active_version(self) -> Optional[ModelVersion]:
        """
        Zwraca aktywną wersję modelu.

        Returns:
            Aktywna wersja lub None
        """
        if not self.active_version:
            return None

        return self.versions.get(self.active_version)

    def get_version(self, version_id: str) -> Optional[ModelVersion]:
        """
        Pobiera wersję modelu po ID.

        Args:
            version_id: ID wersji

        Returns:
            Wersja modelu lub None
        """
        return self.versions.get(version_id)

    def get_all_versions(self) -> List[ModelVersion]:
        """
        Zwraca wszystkie wersje modeli (sortowane od najnowszych).

        Returns:
            Lista wersji
        """
        return sorted(
            self.versions.values(),
            key=lambda v: v.created_at or "",
            reverse=True,
        )

    def create_ollama_modelfile(
        self, version_id: str, output_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Tworzy Modelfile dla Ollama z adapterem LoRA.

        Args:
            version_id: ID wersji modelu
            output_name: Nazwa wyjściowa modelu w Ollama (domyślnie venom-{version_id})

        Returns:
            Nazwa utworzonego modelu w Ollama lub None w przypadku błędu
        """
        version = self.get_version(version_id)
        if not version:
            logger.error(f"Wersja {version_id} nie istnieje")
            return None

        if not version.adapter_path:
            logger.error(f"Wersja {version_id} nie ma adaptera")
            return None

        output_name = output_name or f"venom-{version_id}"

        try:
            # Utwórz Modelfile
            modelfile_content = f"""FROM {version.base_model}
ADAPTER {version.adapter_path}

# Venom Model - version {version_id}
# Created: {version.created_at}
# Base: {version.base_model}

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
"""

            # Zapisz Modelfile
            modelfile_path = self.models_dir / f"Modelfile.{version_id}"
            with open(modelfile_path, "w") as f:
                f.write(modelfile_content)

            logger.info(f"Utworzono Modelfile: {modelfile_path}")

            # Utwórz model w Ollama
            cmd = ["ollama", "create", output_name, "-f", str(modelfile_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info(f"✅ Utworzono model w Ollama: {output_name}")
                return output_name
            else:
                logger.error(
                    f"❌ Błąd podczas tworzenia modelu w Ollama: {result.stderr}"
                )
                return None

        except subprocess.TimeoutExpired:
            logger.error("Timeout podczas tworzenia modelu w Ollama")
            return None
        except FileNotFoundError:
            logger.error("Ollama nie jest zainstalowane lub niedostępne w PATH")
            return None
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia Modelfile: {e}")
            return None

    def load_adapter_for_kernel(
        self, version_id: str, kernel_builder
    ) -> Union[bool, Tuple[Any, Any]]:
        """
        Ładuje adapter LoRA do KernelBuilder (dla integracji z PEFT).

        Args:
            version_id: ID wersji modelu
            kernel_builder: Instancja KernelBuilder

        Returns:
            Tuple[model, tokenizer] jeśli sukces, False w przeciwnym razie
        """
        version = self.get_version(version_id)
        if not version:
            logger.error(f"Wersja {version_id} nie istnieje")
            return False

        if not version.adapter_path:
            logger.error(f"Wersja {version_id} nie ma adaptera")
            return False

        try:
            # Sprawdź czy ścieżka wskazuje na adapter LoRA
            if not self._is_lora_adapter(version.adapter_path):
                logger.error(
                    f"Ścieżka nie wskazuje na prawidłowy adapter LoRA: {version.adapter_path}"
                )
                return False

            # Próbuj załadować adapter używając PEFT
            try:
                from peft import PeftConfig, PeftModel
                from transformers import AutoModelForCausalLM, AutoTokenizer

                logger.info(f"Ładowanie adaptera LoRA z {version.adapter_path}...")

                # Ładuj konfigurację adaptera
                peft_config = PeftConfig.from_pretrained(version.adapter_path)
                base_model_name = peft_config.base_model_name_or_path

                logger.info(f"Model bazowy: {base_model_name}")

                # Sprawdź dostępność bitsandbytes i ustaw load_in_4bit jeśli możliwe
                try:
                    import bitsandbytes  # noqa: F401

                    quantization_config = {"load_in_4bit": True}
                except ImportError:
                    logger.warning(
                        "bitsandbytes nie jest zainstalowany, ładowanie bez kwantyzacji"
                    )
                    quantization_config = {}

                # Ładuj model bazowy
                base_model = AutoModelForCausalLM.from_pretrained(
                    base_model_name, device_map="auto", **quantization_config
                )

                # Załaduj adapter
                model = PeftModel.from_pretrained(base_model, version.adapter_path)

                # Ładuj tokenizer
                tokenizer = AutoTokenizer.from_pretrained(version.adapter_path)

                logger.info(f"✅ Adapter LoRA załadowany pomyślnie: {version_id}")

                # Tutaj można zintegrować z kernel_builder jeśli ma odpowiednie API
                # Zwracamy model i tokenizer
                return model, tokenizer

            except ImportError:
                logger.warning(
                    "Biblioteka 'peft' nie jest zainstalowana. "
                    "Zainstaluj: pip install peft"
                )
                return False

        except Exception as e:
            logger.error(f"Błąd podczas ładowania adaptera: {e}")
            return False

    def _is_lora_adapter(self, adapter_path: str) -> bool:
        """
        Sprawdza czy ścieżka wskazuje na prawidłowy adapter LoRA.

        Args:
            adapter_path: Ścieżka do adaptera

        Returns:
            True jeśli to prawidłowy adapter LoRA
        """
        from pathlib import Path

        path = Path(adapter_path)
        if not path.exists():
            return False

        # Sprawdź czy istnieją wymagane pliki PEFT
        safetensors_file = "adapter_model.safetensors"

        # Adapter musi mieć co najmniej config i jeden z plików modelu
        has_config = (path / "adapter_config.json").exists()
        has_model = (path / "adapter_model.bin").exists() or (
            path / safetensors_file
        ).exists()

        return has_config and has_model

    def get_genealogy(self) -> Dict[str, Any]:
        """
        Zwraca "Genealogię Inteligencji" - historię wersji modeli.

        Returns:
            Słownik z informacjami o genealogii
        """
        versions_data = [v.to_dict() for v in self.get_all_versions()]

        return {
            "total_versions": len(self.versions),
            "active_version": self.active_version,
            "versions": versions_data,
        }

    def compare_versions(
        self, version_id_1: str, version_id_2: str
    ) -> Optional[Dict[str, Any]]:
        """
        Porównuje dwie wersje modeli.

        Args:
            version_id_1: ID pierwszej wersji
            version_id_2: ID drugiej wersji

        Returns:
            Słownik z porównaniem lub None
        """
        v1 = self.get_version(version_id_1)
        v2 = self.get_version(version_id_2)

        if not v1 or not v2:
            logger.error("Jedna lub obie wersje nie istnieją")
            return None

        comparison = {
            "version_1": v1.to_dict(),
            "version_2": v2.to_dict(),
            "metrics_diff": {},
        }

        # Porównaj metryki
        metric_keys = set(v1.performance_metrics.keys()) | set(
            v2.performance_metrics.keys()
        )
        for key in metric_keys:
            metric_diff = self._compute_metric_diff(
                v1.performance_metrics.get(key),
                v2.performance_metrics.get(key),
            )
            if metric_diff is not None:
                comparison["metrics_diff"][key] = metric_diff

        return comparison

    @staticmethod
    def _compute_metric_diff(val1: Any, val2: Any) -> Optional[Dict[str, Any]]:
        """Wylicza różnicę metryk między dwiema wersjami."""
        if val1 is None or val2 is None:
            return None

        try:
            diff = val2 - val1
            if val1 != 0:
                diff_pct = (diff / val1) * 100
            else:
                # Gdy baza jest zerowa, zmiana procentowa jest nieskończona (o ile val2 != 0).
                diff_pct = float("inf") if val2 != 0 else 0
            return {
                "v1": val1,
                "v2": val2,
                "diff": diff,
                "diff_pct": diff_pct,
            }
        except (TypeError, ValueError):
            return {
                "v1": val1,
                "v2": val2,
                "diff": "N/A",
            }

    def get_models_size_gb(self) -> float:
        """
        Oblicza całkowity rozmiar modeli w katalogu models_dir.

        Returns:
            Rozmiar w GB
        """
        total_size = 0
        if not self.models_dir.exists():
            return 0.0

        for path in self.models_dir.rglob("*"):
            if path.is_file():
                total_size += path.stat().st_size

        # Konwertuj na GB
        return total_size / (1024**3)

    def check_storage_quota(self, additional_size_gb: float = 0.0) -> bool:
        """
        Sprawdza czy dodanie nowego modelu nie przekroczy limitu.
        Resource Guard - chroni przed przepełnieniem dysku.

        Args:
            additional_size_gb: Szacowany rozmiar nowego modelu w GB

        Returns:
            True jeśli jest miejsce, False jeśli limit zostanie przekroczony
        """
        current_usage = self.get_models_size_gb()
        projected_usage = current_usage + additional_size_gb

        if projected_usage > MAX_STORAGE_GB:
            logger.warning(
                f"Resource Guard: Przekroczono limit miejsca na modele! "
                f"Aktualne użycie: {current_usage:.2f} GB, "
                f"Po dodaniu: {projected_usage:.2f} GB, "
                f"Limit: {MAX_STORAGE_GB} GB"
            )
            return False

        logger.info(
            f"Resource Guard: OK. Użycie: {current_usage:.2f} GB / {MAX_STORAGE_GB} GB"
        )
        return True

    def _register_local_entry(
        self,
        models: Dict[str, Dict[str, Any]],
        model_path: Path,
        source: str,
        provider: str = "vllm",
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
            onnx_payload = {
                **inferred,
                **onnx_metadata,
            }

        models[model_path.name] = {
            "name": model_path.name,
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
                "onnx" if "onnx" in model_path.name.lower() else provider
            )
            return "folder", resolved_provider
        return "folder", provider

    def _build_search_dirs(self) -> List[Path]:
        search_dirs = [self.models_dir]
        default_models_dir = Path("./models")
        if default_models_dir.exists() and default_models_dir not in search_dirs:
            search_dirs.append(default_models_dir)
        return search_dirs

    def _scan_local_dirs(
        self,
        search_dirs: List[Path],
        models: Dict[str, Dict[str, Any]],
    ) -> None:
        skip_dirs = {"hf_cache", "__pycache__", ".cache", "manifests", "blobs"}
        for base_dir in search_dirs:
            if not base_dir.exists():
                continue
            for model_path in base_dir.iterdir():
                if not self._is_local_model_candidate(model_path, skip_dirs):
                    continue
                self._try_register_local_entry(models, model_path, base_dir.name)

    @staticmethod
    def _is_local_model_candidate(model_path: Path, skip_dirs: set[str]) -> bool:
        if model_path.name in skip_dirs:
            return False
        return model_path.is_dir() or model_path.suffix in {".onnx", ".gguf", ".bin"}

    def _try_register_local_entry(
        self, models: Dict[str, Dict[str, Any]], model_path: Path, source_name: str
    ) -> None:
        try:
            self._register_local_entry(
                models,
                model_path,
                source=source_name,
                provider="vllm",
            )
        except Exception as e:
            logger.warning(f"Nie udało się odczytać modelu {model_path}: {e}")

    def _load_ollama_manifest_entries(
        self, manifests_dir: Path
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        if not manifests_dir.exists():
            return entries
        for manifest_path in manifests_dir.rglob("*"):
            if not manifest_path.is_file():
                continue
            relative_parts = self._resolve_manifest_relative_parts(
                manifests_dir, manifest_path
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
        manifests_dir: Path, manifest_path: Path
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
        except Exception as e:
            logger.warning(f"Nie udało się odczytać manifestu {manifest_path}: {e}")
        return size_bytes

    def _collect_ollama_entries(
        self, ollama_models: List[Dict[str, Any]]
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
                    "quantization_level", "unknown"
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
        except Exception as e:
            logger.warning(f"Nie udało się zapisać cache modeli Ollama: {e}")

    def _load_ollama_cache(
        self,
        models: Dict[str, Dict[str, Any]],
    ) -> None:
        try:
            if not self.ollama_cache_path.exists():
                return
            cached_entries = json.loads(self.ollama_cache_path.read_text("utf-8"))
            for entry in cached_entries:
                entry_name = entry.get("name")
                if entry_name:
                    models.setdefault(f"ollama::{entry_name}", entry)
        except Exception as cache_error:
            logger.warning(f"Nie udało się wczytać cache modeli Ollama: {cache_error}")

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

    @staticmethod
    def _is_valid_model_name(model_name: str) -> bool:
        return bool(model_name and re.match(r"^[\w\-.:]+$", model_name))

    async def _stream_pull_output(
        self,
        process: asyncio.subprocess.Process,
        progress_callback: Optional[Callable[[str], None]],
    ) -> None:
        if not process.stdout:
            return
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode(errors="replace").strip()
            logger.info(f"Ollama: {line.strip()}")
            if progress_callback:
                progress_callback(line)

    async def _read_process_stderr(self, process: asyncio.subprocess.Process) -> str:
        if not process.stderr:
            return ""
        return (await process.stderr.read()).decode(errors="replace")

    @staticmethod
    def _resolve_models_mount() -> Path:
        disk_mount = Path("/usr/lib/wsl/drivers")
        if disk_mount.exists():
            return disk_mount
        return Path("/")

    async def _collect_gpu_metrics(self) -> Dict[str, Any]:
        gpu_metrics: Dict[str, Any] = {
            "gpu_usage_percent": None,
            "vram_usage_mb": 0,
            "vram_total_mb": None,
            "vram_usage_percent": None,
        }
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return gpu_metrics

            usage_values: list[float] = []
            used_values: list[float] = []
            total_values: list[float] = []
            for line in (
                ln.strip() for ln in result.stdout.strip().split("\n") if ln.strip()
            ):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3:
                    continue
                try:
                    usage_values.append(float(parts[0]))
                    used_values.append(float(parts[1]))
                    total_values.append(float(parts[2]))
                except ValueError:
                    continue

            if usage_values:
                gpu_metrics["gpu_usage_percent"] = round(max(usage_values), 2)
            if not used_values:
                return gpu_metrics

            max_index = used_values.index(max(used_values))
            vram_usage_mb = round(float(used_values[max_index]), 2)
            gpu_metrics["vram_usage_mb"] = vram_usage_mb
            if max_index >= len(total_values):
                return gpu_metrics
            total_mb = total_values[max_index]
            gpu_metrics["vram_total_mb"] = round(total_mb, 2)
            if total_mb > 0:
                gpu_metrics["vram_usage_percent"] = round(
                    (vram_usage_mb / total_mb) * 100, 2
                )
            return gpu_metrics
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return gpu_metrics

    async def _get_model_info_by_name(
        self, model_name: str
    ) -> Optional[Dict[str, Any]]:
        models = await self.list_local_models()
        return next((m for m in models if m["name"] == model_name), None)

    async def _delete_ollama_model(self, model_name: str) -> bool:
        result = await asyncio.to_thread(
            subprocess.run,
            ["ollama", "rm", model_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"✅ Model {model_name} usunięty z Ollama")
            return True
        logger.error(f"❌ Błąd podczas usuwania modelu: {result.stderr}")
        return False

    def _delete_local_model_file(self, model_info: Dict[str, Any]) -> bool:
        model_path = Path(model_info["path"]).resolve()
        # Sprawdź czy ścieżka jest wewnątrz models_dir (ochrona przed path traversal)
        if not model_path.is_relative_to(self.models_dir):
            logger.error(f"Nieprawidłowa ścieżka modelu: {model_path}")
            return False

        if not model_path.exists():
            logger.error(f"Ścieżka modelu nie istnieje: {model_path}")
            return False

        if model_path.is_dir():
            shutil.rmtree(model_path)
        else:
            model_path.unlink()
        return True

    async def list_local_models(self) -> List[Dict[str, Any]]:
        """
        Skanuje katalog models/ i pobiera listę modeli z Ollama.

        Returns:
            Lista słowników z informacjami o modelach:
            {name, size_gb, type, quantization, path, active}
        """
        models: Dict[str, Dict[str, Any]] = {}

        # 1. Skanowanie lokalnych katalogów modeli (data/models oraz ./models)
        search_dirs = self._build_search_dirs()
        self._scan_local_dirs(search_dirs, models)

        # 2. Pobieranie modeli z Ollama API
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
                        f"Nie udało się pobrać listy modeli z Ollama: {response.status_code}"
                    )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            now = time.time()
            if now - self._last_ollama_warning > 60:
                logger.warning(f"Ollama nie jest dostępne: {e}")
                self._last_ollama_warning = now
        except Exception as e:
            logger.error(f"Błąd podczas pobierania modeli z Ollama: {e}")

        return list(models.values())

    async def pull_model(
        self, model_name: str, progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Pobiera model z Ollama lub HuggingFace.

        Args:
            model_name: Nazwa modelu do pobrania
            progress_callback: Opcjonalna funkcja callback do aktualizacji postępu

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        # Sprawdź limit miejsca przed pobraniem
        if not self.check_storage_quota(additional_size_gb=DEFAULT_MODEL_SIZE_GB):
            logger.error("Nie można pobrać modelu - brak miejsca na dysku")
            return False

        # Walidacja nazwy modelu przed subprocess
        if not self._is_valid_model_name(model_name):
            logger.error(f"Nieprawidłowa nazwa modelu: {model_name}")
            return False

        success = False
        try:
            # Próba pobrania z Ollama
            logger.info(f"Rozpoczynam pobieranie modelu: {model_name}")

            # Użyj asynchronicznego subprocess dla ollama pull
            process = await asyncio.create_subprocess_exec(
                "ollama",
                "pull",
                model_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                # Streamuj output
                await self._stream_pull_output(process, progress_callback)

                return_code = await process.wait()
                success = return_code == 0
                if success:
                    logger.info(f"✅ Model {model_name} pobrany pomyślnie")
                else:
                    stderr = await self._read_process_stderr(process)
                    logger.error(f"❌ Błąd podczas pobierania modelu: {stderr}")
            finally:
                # Upewnij się, że proces jest zamknięty nawet przy wyjątku
                if process.returncode is None:
                    process.kill()
                    await process.wait()

        except FileNotFoundError:
            logger.error("Ollama nie jest zainstalowane lub niedostępne w PATH")
            return False
        except Exception as e:
            logger.error(f"Błąd podczas pobierania modelu: {e}")
            return False

        return success

    async def delete_model(self, model_name: str) -> bool:
        """
        Usuwa model z dysku lub Ollama.
        Safety Check: blokuje usunięcie aktywnego modelu.

        Args:
            model_name: Nazwa modelu do usunięcia

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        # Safety check - nie usuwaj aktywnego modelu
        if self.active_version and model_name == self.active_version:
            logger.error(
                f"Nie można usunąć aktywnego modelu: {model_name}. "
                f"Najpierw zmień aktywny model."
            )
            return False

        # Walidacja nazwy modelu przed subprocess
        if not self._is_valid_model_name(model_name):
            logger.error(f"Nieprawidłowa nazwa modelu: {model_name}")
            return False

        try:
            model_info = await self._get_model_info_by_name(model_name)

            if not model_info:
                logger.error(f"Model {model_name} nie znaleziony")
                return False

            if model_info["type"] == "ollama":
                return await self._delete_ollama_model(model_name)

            if not self._delete_local_model_file(model_info):
                return False
            logger.info(f"✅ Model {model_name} usunięty z dysku")
            return True

        except subprocess.TimeoutExpired:
            logger.error("Timeout podczas usuwania modelu z Ollama")
            return False
        except FileNotFoundError:
            logger.error("Ollama nie jest zainstalowane")
            return False
        except Exception as e:
            logger.error(f"Błąd podczas usuwania modelu: {e}")
            return False

    async def unload_all(self) -> bool:
        """
        Panic Button - wymusza zwolnienie pamięci VRAM/RAM.
        Może wymagać restartu serwisu Ollama lub wyczyszczenia sesji.

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        try:
            logger.warning("🚨 PANIC BUTTON: Zwalnianie wszystkich zasobów modeli...")

            # Próba zatrzymania i ponownego uruchomienia Ollama
            # To spowoduje zwolnienie pamięci VRAM/RAM
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["pkill", "-x", "ollama"],  # -x dla dokładnego dopasowania nazwy
                    capture_output=True,
                    timeout=5,
                )
                logger.info("Zatrzymano proces Ollama")
            except Exception as e:
                logger.warning(f"Nie udało się zatrzymać Ollama: {e}")

            # Wyczyść informacje o aktywnej wersji
            self.active_version = None

            logger.info("✅ Zasoby zwolnione")
            return True

        except Exception as e:
            logger.error(f"Błąd podczas zwalniania zasobów: {e}")
            return False

    async def get_usage_metrics(self) -> Dict[str, Any]:
        """
        Zwraca metryki użycia zasobów: zajętość dysku, CPU/RAM oraz VRAM.

        Returns:
            Słownik z metrykami
        """
        disk_usage_gb = self.get_models_size_gb()
        memory = psutil.virtual_memory()
        cpu_usage = psutil.cpu_percent(interval=0.1)
        disk_mount = self._resolve_models_mount()
        disk_system = psutil.disk_usage(str(disk_mount))
        models_count = len(await self.list_local_models())

        metrics = {
            "disk_usage_gb": disk_usage_gb,
            "disk_limit_gb": MAX_STORAGE_GB,
            "disk_usage_percent": (
                (disk_usage_gb / MAX_STORAGE_GB) * 100 if MAX_STORAGE_GB > 0 else 0
            ),
            "disk_system_total_gb": round(disk_system.total / BYTES_IN_GB, 2),
            "disk_system_used_gb": round(disk_system.used / BYTES_IN_GB, 2),
            "disk_system_usage_percent": round(disk_system.percent, 2),
            "disk_system_mount": str(disk_mount),
            "cpu_usage_percent": round(cpu_usage, 2),
            "memory_total_gb": round(memory.total / BYTES_IN_GB, 2),
            "memory_used_gb": round(memory.used / BYTES_IN_GB, 2),
            "memory_usage_percent": round(memory.percent, 2),
            "models_count": models_count,
        }
        metrics.update(await self._collect_gpu_metrics())

        return metrics

    def activate_adapter(
        self, adapter_id: str, adapter_path: str, base_model: Optional[str] = None
    ) -> bool:
        """
        Aktywuje adapter LoRA z Academy.

        Args:
            adapter_id: ID adaptera (np. training_20240101_120000)
            adapter_path: Ścieżka do adaptera
            base_model: Opcjonalnie nazwa bazowego modelu

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        from datetime import datetime

        logger.info("Aktywacja adaptera Academy")

        expected_adapter_path = (
            self.models_dir.resolve() / adapter_id / "adapter"
        ).resolve()

        if adapter_path and Path(adapter_path).resolve() != expected_adapter_path:
            logger.error("Adapter path niezgodny z katalogiem Academy")
            return False

        # Sprawdź czy adapter istnieje
        if not expected_adapter_path.exists():
            logger.error("Adapter nie istnieje")
            return False

        # Jeśli adapter już jest zarejestrowany, aktywuj go
        if adapter_id in self.versions:
            success = self.activate_version(adapter_id)
            if success:
                version = self.versions[adapter_id]
                self._save_active_adapter_state(
                    adapter_id=adapter_id,
                    adapter_path=version.adapter_path or str(expected_adapter_path),
                    base_model=version.base_model,
                )
            return success

        # Zarejestruj nowy adapter jako wersję
        base = base_model or "academy-base"
        self.register_version(
            version_id=adapter_id,
            base_model=base,
            adapter_path=str(expected_adapter_path),
            performance_metrics={
                "source": "academy",
                "created_at": datetime.now().isoformat(),
            },
        )

        # Aktywuj nową wersję
        success = self.activate_version(adapter_id)

        if success:
            logger.info(f"✅ Adapter {adapter_id} aktywowany pomyślnie")
            self._save_active_adapter_state(
                adapter_id=adapter_id,
                adapter_path=str(expected_adapter_path),
                base_model=base,
            )
        else:
            logger.error("❌ Nie udało się aktywować adaptera")

        return success

    def deactivate_adapter(self) -> bool:
        """
        Dezaktywuje aktualny adapter (rollback do bazowego modelu).

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        if not self.active_version:
            logger.warning("Brak aktywnego adaptera do dezaktywacji")
            return False

        logger.info(f"Dezaktywacja adaptera: {self.active_version}")

        # Oznacz jako nieaktywny
        if self.active_version in self.versions:
            self.versions[self.active_version].is_active = False

        self.active_version = None
        self._clear_active_adapter_state()
        logger.info("✅ Adapter zdezaktywowany - powrót do modelu bazowego")

        return True

    def get_active_adapter_info(self) -> Optional[Dict[str, Any]]:
        """
        Zwraca informacje o aktywnym adapterze.

        Returns:
            Słownik z informacjami lub None jeśli brak aktywnego
        """
        if not self.active_version:
            return None

        version = self.get_active_version()
        if not version:
            return None

        return {
            "adapter_id": version.version_id,
            "adapter_path": version.adapter_path,
            "base_model": version.base_model,
            "created_at": version.created_at,
            "performance_metrics": version.performance_metrics,
            "is_active": version.is_active,
        }
