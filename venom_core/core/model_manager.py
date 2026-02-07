"""Moduł: model_manager - Zarządca Modeli i Hot Swap dla Adapterów LoRA."""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, urlunparse

import httpx
import psutil

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Konfiguracja Resource Guard
MAX_STORAGE_GB = 50  # Limit na modele w GB
DEFAULT_MODEL_SIZE_GB = 4.0  # Szacowany domyślny rozmiar modelu dla Resource Guard
BYTES_IN_GB = 1024**3


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
        self.ollama_cache_path = self.models_dir / "ollama_models_cache.json"
        self._last_ollama_warning = 0.0

        # Rejestr wersji modeli
        self.versions: Dict[str, ModelVersion] = {}

        # Aktywna wersja
        self.active_version: Optional[str] = None

        logger.info(f"ModelManager zainicjalizowany (models_dir={self.models_dir})")

    def _resolve_ollama_tags_url(self) -> str:
        """
        Zwraca URL /api/tags dla Ollama zgodny z aktualnym runtime.

        W Dockerze endpoint bywa ustawiony jako http://ollama:11434/v1,
        a lokalnie często http://localhost:11434/v1.
        """
        endpoint = os.getenv("LLM_LOCAL_ENDPOINT", "http://localhost:11434/v1")
        parsed = urlparse(endpoint)
        if parsed.scheme and parsed.netloc:
            base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
            return f"{base}/api/tags"
        return "http://localhost:11434/api/tags"

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
            logger.error(f"Wersja {version_id} nie istnieje")
            return False

        # Dezaktywuj poprzednią wersję
        if self.active_version:
            self.versions[self.active_version].is_active = False

        # Aktywuj nową wersję
        self.versions[version_id].is_active = True
        self.active_version = version_id

        logger.info(f"Aktywowano wersję modelu: {version_id}")
        return True

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
                from peft import PeftConfig, PeftModel  # type: ignore[import-not-found]
                from transformers import AutoModelForCausalLM, AutoTokenizer

                logger.info(f"Ładowanie adaptera LoRA z {version.adapter_path}...")

                # Ładuj konfigurację adaptera
                peft_config = PeftConfig.from_pretrained(version.adapter_path)
                base_model_name = peft_config.base_model_name_or_path

                logger.info(f"Model bazowy: {base_model_name}")

                # Sprawdź dostępność bitsandbytes i ustaw load_in_4bit jeśli możliwe
                try:
                    import bitsandbytes  # type: ignore[import-not-found] # noqa: F401

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
        for key in set(v1.performance_metrics.keys()) | set(
            v2.performance_metrics.keys()
        ):
            val1 = v1.performance_metrics.get(key)
            val2 = v2.performance_metrics.get(key)

            if val1 is not None and val2 is not None:
                try:
                    diff = val2 - val1
                    if val1 != 0:
                        diff_pct = (diff / val1) * 100
                    else:
                        # Jeśli val1 == 0, procentowa zmiana jest nieskończona (lub "N/A"), chyba że oba są zerowe
                        diff_pct = float("inf") if val2 != 0 else 0
                    comparison["metrics_diff"][key] = {
                        "v1": val1,
                        "v2": val2,
                        "diff": diff,
                        "diff_pct": diff_pct,
                    }
                except (TypeError, ValueError):
                    # Metryki niearytmetyczne
                    comparison["metrics_diff"][key] = {
                        "v1": val1,
                        "v2": val2,
                        "diff": "N/A",
                    }

        return comparison

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

    async def list_local_models(self) -> List[Dict[str, Any]]:
        """
        Skanuje katalog models/ i pobiera listę modeli z Ollama.

        Returns:
            Lista słowników z informacjami o modelach:
            {name, size_gb, type, quantization, path, active}
        """
        models: Dict[str, Dict[str, Any]] = {}

        def _register_local_entry(
            model_path: Path, source: str, provider: str = "vllm"
        ):
            size_bytes = 0
            if model_path.is_file():
                size_bytes = model_path.stat().st_size
            else:
                for file_path in model_path.rglob("*"):
                    if file_path.is_file():
                        size_bytes += file_path.stat().st_size

            lower_path = str(model_path).lower()
            if ".gguf" in lower_path:
                model_type = "gguf"
            elif model_path.suffix == ".onnx" or model_path.suffix == ".bin":
                model_type = "onnx"
                provider = "onnx"
            elif model_path.is_dir():
                model_type = "folder"
                if "onnx" in model_path.name.lower():
                    provider = "onnx"
            else:
                model_type = "folder"

            models[model_path.name] = {
                "name": model_path.name,
                "size_gb": size_bytes / (1024**3) if size_bytes else None,
                "type": model_type,
                "quantization": "unknown",
                "path": str(model_path),
                "source": source,
                "provider": provider,
                "active": False,
            }

        # 1. Skanowanie lokalnych katalogów modeli (data/models oraz ./models)
        search_dirs = [self.models_dir]
        default_models_dir = Path("./models")
        if default_models_dir.exists() and default_models_dir not in search_dirs:
            search_dirs.append(default_models_dir)

        skip_dirs = {"hf_cache", "__pycache__", ".cache", "manifests", "blobs"}

        for base_dir in search_dirs:
            if not base_dir.exists():
                continue
            for model_path in base_dir.iterdir():
                if model_path.name in skip_dirs:
                    continue
                if model_path.is_dir() or model_path.suffix in {
                    ".onnx",
                    ".gguf",
                    ".bin",
                }:
                    try:
                        _register_local_entry(
                            model_path, source=base_dir.name, provider="vllm"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Nie udało się odczytać modelu {model_path}: {e}"
                        )

        def _load_ollama_manifest_entries(manifests_dir: Path) -> List[Dict[str, Any]]:
            entries: List[Dict[str, Any]] = []
            if not manifests_dir.exists():
                return entries
            for manifest_path in manifests_dir.rglob("*"):
                if not manifest_path.is_file():
                    continue
                try:
                    relative_parts = manifest_path.relative_to(manifests_dir).parts
                except ValueError:
                    continue
                if len(relative_parts) < 2:
                    continue
                registry = relative_parts[0]
                tag = relative_parts[-1]
                model = relative_parts[-2]
                namespace = relative_parts[-3] if len(relative_parts) >= 3 else ""
                if namespace and namespace != "library":
                    entry_name = f"{namespace}/{model}:{tag}"
                else:
                    entry_name = f"{model}:{tag}"
                size_bytes = 0
                try:
                    manifest_payload = json.loads(manifest_path.read_text("utf-8"))
                    layers = manifest_payload.get("layers") or []
                    size_bytes = sum(
                        layer.get("size", 0)
                        for layer in layers
                        if isinstance(layer, dict)
                    )
                    config = manifest_payload.get("config") or {}
                    if isinstance(config, dict):
                        size_bytes += config.get("size", 0) or 0
                except Exception as e:
                    logger.warning(
                        f"Nie udało się odczytać manifestu {manifest_path}: {e}"
                    )
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

        # 2. Pobieranie modeli z Ollama API
        live_query_success = False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self._resolve_ollama_tags_url())
                if response.status_code == 200:
                    live_query_success = True
                    ollama_data = response.json()
                    # 3. Deduplikacja modeli Ollama po digest (ten sam model pod różnymi tagami)
                    ollama_models_by_digest: Dict[str, Dict[str, Any]] = {}

                    for model in ollama_data.get("models", []):
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
                            models[f"ollama::{entry_name}"] = entry
                            continue

                        # Jeśli mamy już ten digest, sprawdź czy nowy ma lepszy tag
                        if digest in ollama_models_by_digest:
                            existing = ollama_models_by_digest[digest]
                            # Faworyzujemy tag :latest
                            if entry_name.endswith(":latest") and not existing[
                                "name"
                            ].endswith(":latest"):
                                ollama_models_by_digest[digest] = entry
                        else:
                            ollama_models_by_digest[digest] = entry

                    # Zarejestruj wybrane (unikalne) modele
                    cached_entries: List[Dict[str, Any]] = []
                    for entry in ollama_models_by_digest.values():
                        entry_name = entry["name"]
                        models[f"ollama::{entry_name}"] = entry
                        cached_entries.append(entry)
                    if cached_entries:
                        try:
                            self.ollama_cache_path.write_text(
                                json.dumps(cached_entries, indent=2),
                                encoding="utf-8",
                            )
                        except Exception as e:
                            logger.warning(
                                f"Nie udało się zapisać cache modeli Ollama: {e}"
                            )
                else:
                    logger.warning(
                        f"Nie udało się pobrać listy modeli z Ollama: {response.status_code}"
                    )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            now = time.time()
            if now - self._last_ollama_warning > 60:
                logger.warning(f"Ollama nie jest dostępne: {e}")
                self._last_ollama_warning = now
            try:
                if self.ollama_cache_path.exists():
                    cached_entries = json.loads(
                        self.ollama_cache_path.read_text("utf-8")
                    )
                    for entry in cached_entries:
                        entry_name = entry.get("name")
                        if not entry_name:
                            continue
                        models.setdefault(f"ollama::{entry_name}", entry)
            except Exception as cache_error:
                logger.warning(
                    f"Nie udało się wczytać cache modeli Ollama: {cache_error}"
                )
        except Exception as e:
            logger.error(f"Błąd podczas pobierania modeli z Ollama: {e}")

        # 3. Jeśli Ollama jest dostępna (live_query_success), to ufamy jej w 100%.
        # Jeśli nie (live_query_success=False), to ładujemy fallbacki z manifestów.
        if not live_query_success:
            for base_dir in search_dirs:
                manifest_root = base_dir / "manifests"
                for entry in _load_ollama_manifest_entries(manifest_root):
                    entry_name = entry.get("name")
                    if entry_name:
                        models.setdefault(f"ollama::{entry_name}", entry)

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
        if not model_name or not re.match(r"^[\w\-.:]+$", model_name):
            logger.error(f"Nieprawidłowa nazwa modelu: {model_name}")
            return False

        process = None
        success = False
        try:
            # Próba pobrania z Ollama
            logger.info(f"Rozpoczynam pobieranie modelu: {model_name}")

            # Użyj subprocess dla ollama pull
            process = subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                # Streamuj output
                if process.stdout:
                    for line in process.stdout:
                        logger.info(f"Ollama: {line.strip()}")
                        if progress_callback:
                            progress_callback(line.strip())

                return_code = process.wait()
                success = return_code == 0
                if success:
                    logger.info(f"✅ Model {model_name} pobrany pomyślnie")
                else:
                    stderr = process.stderr.read() if process.stderr else ""
                    logger.error(f"❌ Błąd podczas pobierania modelu: {stderr}")
            finally:
                # Upewnij się, że proces jest zamknięty nawet przy wyjątku
                if process.poll() is None:
                    process.kill()
                    process.wait()

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
        if not model_name or not re.match(r"^[\w\-.:]+$", model_name):
            logger.error(f"Nieprawidłowa nazwa modelu: {model_name}")
            return False

        try:
            # Sprawdź czy to model Ollama
            models = await self.list_local_models()
            model_info = next((m for m in models if m["name"] == model_name), None)

            if not model_info:
                logger.error(f"Model {model_name} nie znaleziony")
                return False

            if model_info["type"] == "ollama":
                # Usuń z Ollama
                result = subprocess.run(
                    ["ollama", "rm", model_name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    logger.info(f"✅ Model {model_name} usunięty z Ollama")
                    return True
                else:
                    logger.error(f"❌ Błąd podczas usuwania modelu: {result.stderr}")
                    return False
            else:
                # Usuń lokalny plik/katalog
                model_path = Path(model_info["path"]).resolve()
                # Sprawdź czy ścieżka jest wewnątrz models_dir (ochrona przed path traversal)
                if not model_path.is_relative_to(self.models_dir):
                    logger.error(f"Nieprawidłowa ścieżka modelu: {model_path}")
                    return False

                if model_path.exists():
                    if model_path.is_dir():
                        shutil.rmtree(model_path)
                    else:
                        model_path.unlink()
                    logger.info(f"✅ Model {model_name} usunięty z dysku")
                    return True
                else:
                    logger.error(f"Ścieżka modelu nie istnieje: {model_path}")
                    return False

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
                subprocess.run(
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
        disk_mount = Path("/usr/lib/wsl/drivers")
        if not disk_mount.exists():
            disk_mount = Path("/")
        disk_system = psutil.disk_usage(str(disk_mount))

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
            "gpu_usage_percent": None,
            "vram_usage_mb": 0,
            "vram_total_mb": None,
            "vram_usage_percent": None,
            "models_count": len(await self.list_local_models()),
        }

        # Próba pobrania informacji o GPU/VRAM z nvidia-smi (jeśli dostępne)
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                lines = [
                    line.strip()
                    for line in result.stdout.strip().split("\n")
                    if line.strip()
                ]

                gpu_usage_values = []
                vram_used_values = []
                vram_total_values = []

                for line in lines:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) < 3:
                        continue
                    try:
                        gpu_usage_values.append(float(parts[0]))
                        vram_used_values.append(float(parts[1]))
                        vram_total_values.append(float(parts[2]))
                    except ValueError:
                        continue

                if gpu_usage_values:
                    metrics["gpu_usage_percent"] = round(max(gpu_usage_values), 2)

                if vram_used_values:
                    max_index = vram_used_values.index(max(vram_used_values))
                    vram_usage_mb = round(float(vram_used_values[max_index]), 2)
                    metrics["vram_usage_mb"] = vram_usage_mb
                    if max_index < len(vram_total_values):
                        total_mb = vram_total_values[max_index]
                        metrics["vram_total_mb"] = round(total_mb, 2)
                        if total_mb > 0:
                            metrics["vram_usage_percent"] = round(
                                (vram_usage_mb / total_mb) * 100, 2
                            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # nvidia-smi nie jest dostępne lub wystąpił błąd - ignorujemy
            pass

        return metrics
