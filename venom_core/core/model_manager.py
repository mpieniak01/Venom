"""Moduł: model_manager - Zarządca Modeli i Hot Swap dla Adapterów LoRA."""

import asyncio
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, cast

import psutil

from venom_core.core.model_manager_adapter_ops import (
    activate_adapter as activate_adapter_impl,
)
from venom_core.core.model_manager_adapter_ops import (
    clear_active_adapter_state as clear_active_adapter_state_impl,
)
from venom_core.core.model_manager_adapter_ops import (
    deactivate_adapter as deactivate_adapter_impl,
)
from venom_core.core.model_manager_adapter_ops import (
    get_active_adapter_info as get_active_adapter_info_impl,
)
from venom_core.core.model_manager_adapter_ops import (
    load_active_adapter_state as load_active_adapter_state_impl,
)
from venom_core.core.model_manager_adapter_ops import (
    restore_active_adapter as restore_active_adapter_impl,
)
from venom_core.core.model_manager_adapter_ops import (
    save_active_adapter_state as save_active_adapter_state_impl,
)
from venom_core.core.model_manager_discovery import ModelManagerDiscoveryMixin
from venom_core.core.model_manager_onnx import (
    build_onnx_llm_model as build_onnx_llm_model_impl,
)
from venom_core.core.model_manager_storage import (
    delete_local_model_file as delete_local_model_file_impl,
)
from venom_core.core.model_manager_storage import (
    is_valid_model_name,
    resolve_models_mount,
)
from venom_core.core.model_manager_versions import (
    activate_version as activate_version_impl,
)
from venom_core.core.model_manager_versions import (
    compare_versions as compare_versions_impl,
)
from venom_core.core.model_manager_versions import (
    compute_metric_diff as compute_metric_diff_impl,
)
from venom_core.core.model_manager_versions import (
    get_active_version as get_active_version_impl,
)
from venom_core.core.model_manager_versions import (
    get_all_versions as get_all_versions_impl,
)
from venom_core.core.model_manager_versions import get_genealogy as get_genealogy_impl
from venom_core.core.model_manager_versions import get_version as get_version_impl
from venom_core.core.model_manager_versions import (
    register_version as register_version_impl,
)
from venom_core.services.onnx_runtime_cleanup import release_onnx_runtime_best_effort
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Konfiguracja Resource Guard
MAX_STORAGE_GB = 50  # Limit na modele w GB
DEFAULT_MODEL_SIZE_GB = 4.0  # Szacowany domyślny rozmiar modelu dla Resource Guard
BYTES_IN_GB = 1024**3
_OLLAMA_GGUF_ADAPTER_FILENAMES = ("Adapter-F16-LoRA.gguf", "Adapter-F32-LoRA.gguf")


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


class ModelManager(ModelManagerDiscoveryMixin):
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

    def build_onnx_llm_model(
        self,
        *,
        model_name: str,
        output_dir: Optional[str] = None,
        execution_provider: str = "cuda",
        precision: str = "int4",
        builder_script: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build ONNX LLM model via delegated helper module."""
        return build_onnx_llm_model_impl(
            model_name=model_name,
            output_dir=output_dir,
            execution_provider=execution_provider,
            precision=precision,
            builder_script=builder_script,
            normalize_slug_fn=self._normalize_onnx_model_slug,
            logger=logger,
        )

    def _save_active_adapter_state(
        self, adapter_id: str, adapter_path: str, base_model: str
    ) -> None:
        """Persistuje aktualnie aktywny adapter dla restore po restarcie."""
        save_active_adapter_state_impl(
            state_path=self.active_adapter_state_path,
            adapter_id=adapter_id,
            adapter_path=adapter_path,
            base_model=base_model,
        )

    def _load_active_adapter_state(self) -> Optional[Dict[str, Any]]:
        """Wczytuje persistowany stan aktywnego adaptera."""
        return load_active_adapter_state_impl(
            state_path=self.active_adapter_state_path,
            logger=logger,
        )

    def _clear_active_adapter_state(self) -> None:
        """Czyści persistowany stan aktywnego adaptera."""
        clear_active_adapter_state_impl(
            state_path=self.active_adapter_state_path,
            logger=logger,
        )

    def restore_active_adapter(self) -> bool:
        """
        Próbuje odtworzyć aktywny adapter z persistowanego stanu.

        Returns:
            True jeśli adapter został odtworzony i aktywowany, False w przeciwnym razie.
        """
        return restore_active_adapter_impl(manager=self, logger=logger)

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
        return cast(
            ModelVersion,
            register_version_impl(
                manager=self,
                version_id=version_id,
                base_model=base_model,
                adapter_path=adapter_path,
                performance_metrics=performance_metrics,
                model_version_cls=ModelVersion,
                logger=logger,
            ),
        )

    def activate_version(self, version_id: str) -> bool:
        """
        Aktywuje wersję modelu (hot swap).

        Args:
            version_id: ID wersji do aktywacji

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        return activate_version_impl(manager=self, version_id=version_id, logger=logger)

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
        return cast(Optional[ModelVersion], get_active_version_impl(manager=self))

    def get_version(self, version_id: str) -> Optional[ModelVersion]:
        """
        Pobiera wersję modelu po ID.

        Args:
            version_id: ID wersji

        Returns:
            Wersja modelu lub None
        """
        return cast(
            Optional[ModelVersion],
            get_version_impl(manager=self, version_id=version_id),
        )

    def get_all_versions(self) -> List[ModelVersion]:
        """
        Zwraca wszystkie wersje modeli (sortowane od najnowszych).

        Returns:
            Lista wersji
        """
        return cast(List[ModelVersion], get_all_versions_impl(manager=self))

    def create_ollama_modelfile(
        self,
        version_id: str,
        output_name: Optional[str] = None,
        from_model: Optional[str] = None,
        use_experimental: bool = False,
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
            base_for_from = str(from_model or "").strip() or version.base_model
            adapter_reference = self._resolve_ollama_adapter_reference(
                version.adapter_path
            )
            # Utwórz Modelfile
            modelfile_content = f"""FROM {base_for_from}
ADAPTER {adapter_reference}

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
            if use_experimental:
                cmd.append("--experimental")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info(f"✅ Utworzono model w Ollama: {output_name}")
                return output_name
            else:
                stderr = (result.stderr or "").strip()
                stdout = (result.stdout or "").strip()
                details = stderr or stdout or "unknown error"
                logger.error(
                    f"❌ Błąd podczas tworzenia modelu w Ollama "
                    f"(code={result.returncode}): {details}"
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

    def _resolve_ollama_adapter_reference(self, adapter_path: str) -> str:
        path = Path(str(adapter_path or "")).expanduser().resolve()
        if path.is_file():
            return str(path)
        if not path.exists() or not path.is_dir():
            return str(path)
        for filename in _OLLAMA_GGUF_ADAPTER_FILENAMES:
            candidate = path / filename
            if candidate.exists() and candidate.is_file():
                return str(candidate.resolve())
        for candidate in sorted(path.glob("*.gguf")):
            if candidate.is_file():
                return str(candidate.resolve())
        return str(path)

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
        return get_genealogy_impl(manager=self)

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
        return compare_versions_impl(
            manager=self,
            version_id_1=version_id_1,
            version_id_2=version_id_2,
            compute_metric_diff_fn=self._compute_metric_diff,
            logger=logger,
        )

    @staticmethod
    def _compute_metric_diff(val1: Any, val2: Any) -> Optional[Dict[str, Any]]:
        """Wylicza różnicę metryk między dwiema wersjami."""
        return compute_metric_diff_impl(val1, val2)

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

    @staticmethod
    def _is_valid_model_name(model_name: str) -> bool:
        return is_valid_model_name(model_name)

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
        return resolve_models_mount()

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
        return delete_local_model_file_impl(
            model_info=model_info,
            models_dir=self.models_dir,
            logger=logger,
        )

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

            released_targets: list[str] = []

            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["pkill", "-x", "ollama"],
                    capture_output=True,
                    timeout=5,
                )
                released_targets.append("ollama")
                logger.info("Zatrzymano proces Ollama")
            except Exception as e:
                logger.warning(f"Nie udało się zatrzymać Ollama: {e}")

            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["pkill", "-f", "vllm serve"],
                    capture_output=True,
                    timeout=5,
                )
                released_targets.append("vllm")
                logger.info("Zatrzymano proces vLLM")
            except Exception as e:
                logger.warning(f"Nie udało się zatrzymać vLLM: {e}")

            try:
                if release_onnx_runtime_best_effort(wait=False):
                    released_targets.append("onnx")
                    logger.info("Zwolniono cache/runtime ONNX")
            except Exception as e:
                logger.warning(f"Nie udało się zwolnić runtime ONNX: {e}")

            # Wyczyść informacje o aktywnej wersji
            self.active_version = None

            logger.info(
                "✅ Zasoby zwolnione (targets=%s)",
                ",".join(released_targets) or "none",
            )
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
        return activate_adapter_impl(
            manager=self,
            adapter_id=adapter_id,
            adapter_path=adapter_path,
            base_model=base_model,
            logger=logger,
        )

    def deactivate_adapter(self) -> bool:
        """
        Dezaktywuje aktualny adapter (rollback do bazowego modelu).

        Returns:
            True jeśli sukces, False w przeciwnym razie
        """
        return deactivate_adapter_impl(manager=self, logger=logger)

    def get_active_adapter_info(self) -> Optional[Dict[str, Any]]:
        """
        Zwraca informacje o aktywnym adapterze.

        Returns:
            Słownik z informacjami lub None jeśli brak aktywnego
        """
        return get_active_adapter_info_impl(manager=self)
