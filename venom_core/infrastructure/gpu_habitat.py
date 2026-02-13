"""Moduł: gpu_habitat - Siedlisko Treningowe z obsługą GPU."""

import importlib
import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from venom_core.config import SETTINGS
from venom_core.infrastructure.docker_habitat import DockerHabitat
from venom_core.utils.logger import get_logger

docker: Any = None
try:  # pragma: no cover - zależne od środowiska
    docker = importlib.import_module("docker")
    docker_errors = importlib.import_module("docker.errors")
    APIError = docker_errors.APIError
    ImageNotFound = docker_errors.ImageNotFound
except Exception:  # pragma: no cover
    docker = None
    APIError = Exception
    ImageNotFound = Exception

logger = get_logger(__name__)


class GPUHabitat(DockerHabitat):
    """
    Rozszerzone siedlisko Docker z obsługą GPU dla treningu modeli.

    Dziedziczy po DockerHabitat i dodaje funkcjonalność:
    - Detekcję GPU i nvidia-container-toolkit
    - Uruchamianie kontenerów treningowych z GPU
    - Zarządzanie jobami treningowymi (LoRA Fine-tuning)
    """

    # Domyślny obraz treningowy (Unsloth - bardzo szybki fine-tuning)
    DEFAULT_TRAINING_IMAGE = "unsloth/unsloth:latest"
    ALLOWED_LOCAL_JOB_SIGNALS = {
        signal.SIGTERM,
        signal.SIGINT,
        signal.SIGKILL,
    }

    def __init__(
        self,
        enable_gpu: bool = True,
        training_image: Optional[str] = None,
        use_local_runtime: bool = False,
    ):
        """
        Inicjalizacja GPUHabitat.

        Args:
            enable_gpu: Czy włączyć wsparcie GPU (domyślnie True)
            training_image: Obraz Docker dla treningu (domyślnie unsloth)
            use_local_runtime: Czy używać lokalnego środowiska Python (bez Dockera)

        Raises:
            RuntimeError: Jeśli Docker nie jest dostępny

        Note:
            Nie wywołujemy super().__init__() ponieważ GPUHabitat nie tworzy
            standardowego kontenera sandbox - zamiast tego zarządza tymczasowymi
            kontenerami treningowymi. Dziedziczymy po DockerHabitat głównie jako
            marker typologiczny, a nie dla dziedziczenia funkcjonalności.
        """
        # Inicjalizacja klienta Docker (bez tworzenia standardowego kontenera)
        # Jeśli używamy local runtime, Docker nie jest wymagany (chyba że do innych celów)
        self.use_local_runtime = use_local_runtime or SETTINGS.ACADEMY_USE_LOCAL_RUNTIME

        if not self.use_local_runtime:
            if docker is None:
                error_msg = "Docker SDK nie jest dostępny"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            try:
                self.client = docker.from_env()
                logger.info("Połączono z Docker daemon (GPU mode)")
            except Exception as e:
                error_msg = f"Nie można połączyć się z Docker daemon: {e}"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
        else:
            self.client = None
            logger.info("Tryb Local Runtime aktywny (Docker pominięty dla treningu)")

        self.enable_gpu = enable_gpu
        self.training_image = training_image or self.DEFAULT_TRAINING_IMAGE
        self.training_containers: dict[str, Any] = {}
        # Backward-compat: część testów i starszy kod używa `job_registry`.
        self.job_registry = self.training_containers
        self._gpu_available = bool(enable_gpu)

        # Sprawdź dostępność GPU
        if self.enable_gpu:
            if self.use_local_runtime:
                # W trybie lokalnym sprawdź tylko czy PyTorch widzi GPU (nvidia-smi check opcjonalny)
                self._gpu_available = self._check_local_gpu_availability()
            else:
                self._gpu_available = self._check_gpu_availability()

            if not self._gpu_available:
                # Deterministyczny fallback CPU: nie próbujemy już wymuszać GPU.
                self.enable_gpu = False
                logger.warning(
                    "GPU fallback aktywny: trening zostanie uruchomiony na CPU."
                )

        logger.info(
            f"GPUHabitat zainicjalizowany (GPU={'enabled' if enable_gpu else 'disabled'}, "
            f"image={self.training_image}, local_runtime={self.use_local_runtime})"
        )

    def _check_local_gpu_availability(self) -> bool:
        """Sprawdza dostępność GPU w trybie lokalnym (nvidia-smi)."""
        try:
            subprocess.run(["nvidia-smi"], check=True, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _check_local_dependencies(self) -> None:
        """Sprawdza czy wymagane biblioteki są zainstalowane lokalnie."""
        # Podstawowe biblioteki (wymagane zawsze)
        core_packages = ["transformers", "peft", "trl", "datasets", "accelerate"]
        missing = []

        for package in core_packages:
            try:
                importlib.import_module(package)
            except ImportError:
                missing.append(package)

        if missing:
            raise RuntimeError(
                f"Brak wymaganych bibliotek do treningu: {', '.join(missing)}. "
                f"Zainstaluj je komendą: pip install {' '.join(missing)}"
            )

        # Sprawdź Unsloth (opcjonalne, tylko dla GPU)
        try:
            importlib.import_module("unsloth")
            self._has_unsloth = True
        except ImportError:
            self._has_unsloth = False

        if self.enable_gpu and not self._has_unsloth:
            logger.warning(
                "Biblioteka 'unsloth' nie jest zainstalowana. Trening zostanie uruchomiony "
                "bez optymalizacji Unsloth (wolniej/CPU fallback możliwy)."
            )

    def _check_gpu_availability(self) -> bool:
        """
        Sprawdza dostępność GPU i nvidia-container-toolkit.

        Returns:
            True jeśli GPU jest dostępne, False w przeciwnym razie
        """
        try:
            # Uruchom prosty kontener testowy z GPU
            self.client.containers.run(
                image=SETTINGS.DOCKER_CUDA_IMAGE,
                command="nvidia-smi",
                device_requests=[
                    docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
                ],
                remove=True,
                detach=False,
            )

            logger.info("✅ GPU i nvidia-container-toolkit są dostępne")
            return True

        except ImageNotFound:
            logger.warning(
                f"Obraz {SETTINGS.DOCKER_CUDA_IMAGE} nie jest dostępny, pobieram..."
            )
            try:
                self.client.images.pull(SETTINGS.DOCKER_CUDA_IMAGE)
                return self._check_gpu_availability()  # Retry
            except Exception as e:
                logger.error(
                    f"Nie można pobrać obrazu {SETTINGS.DOCKER_CUDA_IMAGE}: {e}"
                )
                return False

        except APIError as e:
            logger.warning(f"GPU lub nvidia-container-toolkit nie są dostępne: {e}")
            logger.warning("Trening będzie dostępny tylko na CPU")
            return False

        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas sprawdzania GPU: {e}")
            return False

    def is_gpu_available(self) -> bool:
        """Zwraca czy GPU jest dostępne do użycia."""
        return bool(self.enable_gpu and self._gpu_available)

    def _get_job_container(self, job_name: str):
        """Pobiera obiekt kontenera dla joba z nowego i legacy rejestru."""
        if job_name not in self.training_containers:
            raise KeyError(f"Job {job_name} nie istnieje")

        job_info = self.training_containers[job_name]
        container = job_info.get("container")
        if container is not None:
            return container

        container_id = job_info.get("container_id")
        if container_id:
            try:
                container = self.client.containers.get(container_id)
                job_info["container"] = container
                return container
            except Exception as e:
                raise KeyError(
                    f"Container for job {job_name} not found: {container_id}"
                ) from e

        raise KeyError(f"Job {job_name} nie ma przypisanego kontenera")

    def _is_path_within_base(self, path: Path, base: Path) -> bool:
        """Sprawdza czy `path` znajduje się w `base`."""
        try:
            path.relative_to(base)
            return True
        except ValueError:
            return False

    def run_training_job(
        self,
        dataset_path: str,
        base_model: str,
        output_dir: str,
        lora_rank: int = 16,
        learning_rate: float = 2e-4,
        num_epochs: int = 3,
        max_seq_length: int = 2048,
        batch_size: int = 4,
        job_name: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Uruchamia zadanie treningowe (LoRA Fine-tuning).

        Args:
            dataset_path: Ścieżka do pliku datasetu (JSONL) na hoście
            base_model: Nazwa bazowego modelu (np. "unsloth/Phi-3-mini-4k-instruct")
            output_dir: Katalog wyjściowy dla wytrenowanego adaptera
            lora_rank: Ranga LoRA (domyślnie 16)
            learning_rate: Learning rate (domyślnie 2e-4)
            num_epochs: Liczba epok (domyślnie 3)
            max_seq_length: Maksymalna długość sekwencji (domyślnie 2048)
            batch_size: Batch size (domyślnie 4)
            job_name: Opcjonalna nazwa joba (do identyfikacji)

        Returns:
            Słownik z informacjami o jobie:
            - container_id: ID kontenera
            - job_name: Nazwa joba
            - status: Status joba
            - adapter_path: Ścieżka do wygenerowanego adaptera (gdy skończony)

        Raises:
            ValueError: Jeśli parametry są nieprawidłowe
            RuntimeError: Jeśli nie można uruchomić kontenera
        """
        # Walidacja parametrów
        training_base_dir = Path(SETTINGS.ACADEMY_TRAINING_DIR).resolve()
        dataset_path_obj = (training_base_dir / Path(dataset_path).name).resolve()
        if not dataset_path_obj.exists():
            raise ValueError("Dataset nie istnieje")

        if not self._is_path_within_base(dataset_path_obj, training_base_dir):
            raise ValueError("Dataset path jest poza katalogiem Academy training")

        models_base_dir = Path(SETTINGS.ACADEMY_MODELS_DIR).resolve()
        output_dir_obj = (models_base_dir / Path(output_dir).name).resolve()
        if not self._is_path_within_base(output_dir_obj, models_base_dir):
            raise ValueError("Output path jest poza katalogiem Academy models")
        output_dir_obj.mkdir(parents=True, exist_ok=True)

        job_name = job_name or f"training_{dataset_path_obj.stem}"

        logger.info(
            f"Uruchamianie treningu ({'LOCAL' if self.use_local_runtime else 'DOCKER'}): "
            f"job={job_name}, model={base_model}, dataset={dataset_path_obj.name}"
        )

        try:
            # Generuj skrypt
            use_unsloth = self.enable_gpu and getattr(
                self, "_has_unsloth", True
            )  # Default True for Docker

            training_script = self._generate_training_script(
                dataset_path=str(dataset_path_obj)
                if self.use_local_runtime
                else "/workspace/dataset.jsonl",
                base_model=base_model,
                output_dir=str(output_dir_obj)
                if self.use_local_runtime
                else "/workspace/output",
                lora_rank=lora_rank,
                learning_rate=learning_rate,
                num_epochs=num_epochs,
                max_seq_length=max_seq_length,
                batch_size=batch_size,
                use_unsloth=use_unsloth,
            )

            # Zapisz skrypt
            script_path = output_dir_obj / "train_script.py"
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(training_script)

            if self.use_local_runtime:
                return self._run_local_training_job(
                    job_name, script_path, output_dir_obj, dataset_path_obj
                )

            # --- DOCKER MODE ---
            # Przygotuj obraz treningowy
            try:
                self.client.images.get(self.training_image)
                logger.info(f"Obraz {self.training_image} już istnieje")
            except ImageNotFound:
                logger.info(f"Pobieranie obrazu {self.training_image}...")
                self.client.images.pull(self.training_image)

            # Przygotuj skrypt treningowy
            # (Generowanie przeniesione wyżej aby obsłużyć oba tryby)

            # --- KONIEC modification ---
            # Oryginalny kod generował skrypt tutaj, ale teraz robimy to wcześniej.
            # Dla Dockera ścieżki w skrypcie muszą być kontenerowe (/workspace/...),
            # co obsłużyliśmy w warunku wyżej.

            # Przygotuj volumes
            volumes = {
                str(dataset_path_obj): {
                    "bind": "/workspace/dataset.jsonl",
                    "mode": "ro",
                },
                str(output_dir_obj): {
                    "bind": "/workspace/output",
                    "mode": "rw",
                },
            }

            # Przygotuj device requests (GPU)
            device_requests = None
            if self.enable_gpu:
                device_requests = [
                    docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
                ]

            # Sanitize job_name dla użycia w nazwie kontenera
            safe_job_name = "".join(
                c if c.isalnum() or c in ("-", "_") else "_" for c in job_name
            )

            # Uruchom kontener treningowy
            container = self.client.containers.run(
                image=self.training_image,
                command="python /workspace/output/train_script.py",
                volumes=volumes,
                device_requests=device_requests,
                detach=True,
                remove=False,
                name=f"venom-training-{safe_job_name}",
                environment={
                    "CUDA_VISIBLE_DEVICES": "0" if self.enable_gpu else "",
                },
            )

            # Zarejestruj kontener
            self.training_containers[job_name] = {
                "container_id": container.id,
                "container": container,
                "dataset_path": str(dataset_path_obj),
                "output_dir": str(output_dir_obj),
                "status": "running",
            }

            logger.info(
                f"Kontener treningowy uruchomiony: {container.id[:12]} (job={job_name})"
            )

            return {
                "container_id": container.id,
                "job_name": job_name,
                "status": "running",
                "adapter_path": str(output_dir_obj / "adapter"),
            }

        except Exception as e:
            error_msg = f"Błąd podczas uruchamiania treningu: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _run_local_training_job(
        self, job_name: str, script_path: Path, output_dir: Path, dataset_path: Path
    ) -> Dict[str, str]:
        """Uruchamia proces treningowy lokalnie (subprocess)."""
        # Sprawdź zależności
        self._check_local_dependencies()

        # Log file
        log_file = output_dir / "training.log"

        # Environment vars
        env = os.environ.copy()
        if self.enable_gpu:
            env["CUDA_VISIBLE_DEVICES"] = "0"

        # Uruchom proces
        with open(log_file, "w") as f_out:
            process = subprocess.Popen(
                ["python3", str(script_path)],
                stdout=f_out,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(output_dir),
                start_new_session=True,  # Odłącz od procesu rodzica
            )

        # Rejestruj job
        self.training_containers[job_name] = {
            "pid": process.pid,
            "process": process,
            "script_path": str(script_path),
            "log_file": str(log_file),
            "dataset_path": str(dataset_path),
            "output_dir": str(output_dir),
            "status": "running",
            "type": "local",
        }

        logger.info(
            f"Proces treningowy uruchomiony lokalnie: PID={process.pid} (job={job_name})"
        )

        return {
            "container_id": f"local-{process.pid}",  # Fake ID dla kompatybilności
            "job_name": job_name,
            "status": "running",
            "adapter_path": str(output_dir / "adapter"),
        }

    def _validate_local_job_pid(self, job_info: Dict[str, Any]) -> Optional[int]:
        """
        Zwraca PID tylko jeśli wskazuje na oczekiwany proces lokalnego treningu.
        """
        raw_pid = job_info.get("pid")
        try:
            pid = int(raw_pid)
        except (TypeError, ValueError):
            return None

        if pid <= 1:
            return None

        proc_dir = Path(f"/proc/{pid}")
        if not proc_dir.exists():
            return None

        output_dir = job_info.get("output_dir")
        if output_dir:
            try:
                expected_cwd = Path(output_dir).resolve()
                actual_cwd = (proc_dir / "cwd").resolve()
                if actual_cwd != expected_cwd:
                    return None
            except OSError:
                return None

        expected_script = job_info.get("script_path")
        if expected_script:
            try:
                cmdline_raw = (proc_dir / "cmdline").read_text(encoding="utf-8")
                args = [part for part in cmdline_raw.split("\x00") if part]
                expected_script_path = Path(expected_script).resolve()
                has_expected_script = any(
                    Path(arg).resolve() == expected_script_path for arg in args
                )
                if not has_expected_script:
                    return None
            except (OSError, ValueError):
                return None

        return pid

    def _signal_validated_local_job(
        self, job_name: str, job_info: Dict[str, Any], sig: signal.Signals
    ) -> bool:
        """
        Wysyła sygnał tylko do zweryfikowanego procesu lokalnego joba.
        """
        pid = self._validate_local_job_pid(job_info)
        if pid is None:
            logger.warning(
                "Pomijam wysłanie sygnału %s dla job=%s: PID niezweryfikowany",
                sig,
                job_name,
            )
            return False

        if not self._is_allowed_local_job_signal(sig):
            logger.warning(
                "Pomijam wysłanie sygnału %s dla job=%s: sygnał poza allowlist",
                sig,
                job_name,
            )
            return False

        if not self._is_pid_owned_by_current_user(pid):
            logger.warning(
                "Pomijam wysłanie sygnału %s dla job=%s: PID=%s nie należy do aktualnego użytkownika",
                sig,
                job_name,
                pid,
            )
            return False

        try:
            os.kill(pid, sig)
            return True
        except OSError:
            return False

    def _is_allowed_local_job_signal(self, sig: signal.Signals) -> bool:
        """Zwraca True tylko dla sygnałów dopuszczonych w local runtime."""
        try:
            normalized_signal = signal.Signals(sig)
        except (TypeError, ValueError):
            return False
        return normalized_signal in self.ALLOWED_LOCAL_JOB_SIGNALS

    def _is_pid_owned_by_current_user(self, pid: int) -> bool:
        """
        Weryfikuje czy PID należy do aktualnego użytkownika systemowego.
        """
        if pid <= 1:
            return False
        try:
            status_content = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
            uid_line = next(
                (
                    line
                    for line in status_content.splitlines()
                    if line.startswith("Uid:")
                ),
                None,
            )
            if uid_line is None:
                return False
            parts = uid_line.split()
            if len(parts) < 2:
                return False
            process_real_uid = int(parts[1])
            return process_real_uid == os.getuid()
        except (OSError, ValueError, StopIteration):
            return False

    def get_training_status(self, job_name: str) -> Dict[str, str | None]:
        """
        Pobiera status zadania treningowego.

        Args:
            job_name: Nazwa joba

        Returns:
            Słownik ze statusem:
            - status: 'running', 'completed', 'failed'
            - logs: Ostatnie linie logów (opcjonalne)

        Raises:
            KeyError: Jeśli job nie istnieje
        """
        job_info = self.training_containers[job_name]

        if job_info.get("type") == "local":
            return self._get_local_job_status(job_name)

        container = self._get_job_container(job_name)

        try:
            container.reload()
            status = container.status

            # Mapuj status Dockera na nasz format
            if status == "running":
                job_status = "running"
            elif status in {"created", "restarting"}:
                job_status = "preparing"
            elif status == "exited":
                exit_code = container.attrs["State"]["ExitCode"]
                job_status = "finished" if exit_code == 0 else "failed"
            elif status in {"dead", "removing"}:
                job_status = "failed"
            else:
                job_status = "failed"

            # Pobierz ostatnie linie logów
            logs = container.logs(tail=50).decode("utf-8")

            # Aktualizuj status w rejestrze
            job_info["status"] = job_status

            return {
                "status": job_status,
                "logs": logs,
                "container_id": container.id,
            }

        except Exception as e:
            logger.error(f"Błąd podczas pobierania statusu: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "container_id": container.id if hasattr(container, "id") else None,
            }

    def _get_local_job_status(self, job_name: str) -> Dict[str, Optional[str]]:
        """Pobiera status lokalnego procesu treningowego."""
        job_info = self.training_containers[job_name]
        pid = job_info.get("pid")
        process = job_info.get("process")  # Popen object
        log_file = Path(job_info.get("log_file", ""))

        status = "unknown"
        if process:
            retcode = process.poll()
            if retcode is None:
                status = "running"
            elif retcode == 0:
                status = "finished"
            else:
                status = "failed"
        else:
            # Po restarcie aplikacji nie mamy Popen; uznaj "running" tylko dla
            # zweryfikowanego PID, aby nie raportować obcego procesu po PID reuse.
            status = (
                "running"
                if self._validate_local_job_pid(job_info) is not None
                else "finished"
            )

        job_info["status"] = status

        # Pobierz logi
        logs = ""
        if log_file.exists():
            try:
                # Ostatnie 2000 znaków
                file_size = log_file.stat().st_size
                with open(log_file, "r") as f:
                    if file_size > 4000:
                        f.seek(file_size - 4000)
                    logs = f.read()
            except Exception as e:
                logs = f"Error reading logs: {e}"

        return {
            "status": status,
            "logs": logs,
            "container_id": f"local-{pid}",
        }

    def _generate_training_script(
        self,
        dataset_path: str,
        base_model: str,
        output_dir: str,
        lora_rank: int,
        learning_rate: float,
        num_epochs: int,
        max_seq_length: int,
        batch_size: int,
        use_unsloth: bool = True,
    ) -> str:
        """
        Generuje skrypt treningowy Pythona.
        """
        if use_unsloth:
            return self._generate_unsloth_script(
                dataset_path,
                base_model,
                output_dir,
                lora_rank,
                learning_rate,
                num_epochs,
                max_seq_length,
                batch_size,
            )
        else:
            return self._generate_hf_script(
                dataset_path,
                base_model,
                output_dir,
                lora_rank,
                learning_rate,
                num_epochs,
                max_seq_length,
                batch_size,
            )

    def _generate_unsloth_script(
        self,
        dataset_path: str,
        base_model: str,
        output_dir: str,
        lora_rank: int,
        learning_rate: float,
        num_epochs: int,
        max_seq_length: int,
        batch_size: int,
    ) -> str:
        """Generuje skrypt dla Unsloth (GPU optimized)."""
        script = f'''#!/usr/bin/env python3
"""
Skrypt treningowy Venom - wygenerowany automatycznie przez GPUHabitat.
Wykorzystuje Unsloth do szybkiego fine-tuningu LoRA.
"""

import json
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import Dataset

# Konfiguracja
BASE_MODEL = "{base_model}"
DATASET_PATH = "{dataset_path}"
OUTPUT_DIR = "{output_dir}"
LORA_RANK = {lora_rank}
LEARNING_RATE = {learning_rate}
NUM_EPOCHS = {num_epochs}
MAX_SEQ_LENGTH = {max_seq_length}
BATCH_SIZE = {batch_size}

print("=" * 60)
print("VENOM TRAINING JOB")
print("=" * 60)
print(f"Base Model: {{BASE_MODEL}}")
print(f"Dataset: {{DATASET_PATH}}")
print(f"Output: {{OUTPUT_DIR}}")
print(f"LoRA Rank: {{LORA_RANK}}")
print(f"Learning Rate: {{LEARNING_RATE}}")
print(f"Epochs: {{NUM_EPOCHS}}")
print("=" * 60)

# Ładuj model
print("\\n[1/5] Ładowanie modelu...")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=MAX_SEQ_LENGTH,
    dtype=None,  # Auto-detect
    load_in_4bit=True,  # Użyj 4-bit quantization dla oszczędności VRAM
)

# Dodaj adapter LoRA
print("\\n[2/5] Dodawanie adaptera LoRA...")
# UWAGA: Lista target_modules poniżej jest specyficzna dla architektury Llama/Phi.
# Jeśli używasz innego modelu (np. BERT, T5), musisz ją odpowiednio zmienić!
model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                   "gate_proj", "up_proj", "down_proj"],
    lora_alpha=LORA_RANK * 2,
    lora_dropout=0.05,
    bias="none",
    use_gradient_checkpointing=True,
    random_state=3407,
)

# Ładuj dataset
print("\\n[3/5] Ładowanie datasetu...")
examples = []
with open(DATASET_PATH, "r", encoding="utf-8") as f:
    for line in f:
        examples.append(json.loads(line))

dataset = Dataset.from_list(examples)
print(f"Załadowano {{len(examples)}} przykładów")

# Formatowanie promptu
def formatting_func(example):
    text = f"### Instruction:\\n{{example['instruction']}}\\n\\n"
    if example.get('input'):
        text += f"### Input:\\n{{example['input']}}\\n\\n"
    text += f"### Response:\\n{{example['output']}}"
    return {{"text": text}}

dataset = dataset.map(formatting_func)

# Konfiguracja treningu
print("\\n[4/5] Konfiguracja treningu...")
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    args=TrainingArguments(
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        num_train_epochs=NUM_EPOCHS,
        learning_rate=LEARNING_RATE,
        fp16=True,
        logging_steps=1,
        output_dir=OUTPUT_DIR,
        optim="adamw_8bit",
        save_strategy="epoch",
    ),
)

# Trenuj
print("\\n[5/5] Rozpoczynam trening...")
trainer.train()

# Zapisz adapter
print("\\nZapisywanie adaptera...")
model.save_pretrained(f"{{OUTPUT_DIR}}/adapter")
tokenizer.save_pretrained(f"{{OUTPUT_DIR}}/adapter")

print("\\n" + "=" * 60)
print("TRENING ZAKOŃCZONY POMYŚLNIE!")
print(f"Adapter zapisany w: {{OUTPUT_DIR}}/adapter")
print("=" * 60)
'''
        return script

    def _generate_hf_script(
        self,
        dataset_path: str,
        base_model: str,
        output_dir: str,
        lora_rank: int,
        learning_rate: float,
        num_epochs: int,
        max_seq_length: int,
        batch_size: int,
    ) -> str:
        """Generuje skrypt dla standardowego HuggingFace Transformers (CPU/Fallback)."""
        script = f'''#!/usr/bin/env python3
"""
Skrypt treningowy Venom - CPU Fallback (HuggingFace Transformers).
Używany gdy Unsloth/GPU nie jest dostępne.
"""

import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer
from datasets import Dataset

# Konfiguracja
BASE_MODEL = "{base_model}"
DATASET_PATH = "{dataset_path}"
OUTPUT_DIR = "{output_dir}"
LORA_RANK = {lora_rank}
LEARNING_RATE = {learning_rate}
NUM_EPOCHS = {num_epochs}
MAX_SEQ_LENGTH = {max_seq_length}
BATCH_SIZE = {batch_size}

print("=" * 60)
print("VENOM CPU TRAINING JOB (Standard Transformers)")
print("=" * 60)

# Ładuj model
print("\\n[1/5] Ładowanie modelu (CPU mode)...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
model = AutoModelForCausalLM.from_pretrained(BASE_MODEL)

# Dodaj adapter LoRA
print("\\n[2/5] Dodawanie adaptera LoRA...")
peft_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    inference_mode=False,
    r=LORA_RANK,
    lora_alpha=LORA_RANK * 2,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"] # Standard flan-t5/llama targets
)
model = get_peft_model(model, peft_config)
model.print_trainable_parameters()

# Ładuj dataset
print("\\n[3/5] Ładowanie datasetu...")
examples = []
with open(DATASET_PATH, "r", encoding="utf-8") as f:
    for line in f:
        examples.append(json.loads(line))

dataset = Dataset.from_list(examples)

# Formatowanie promptu
def formatting_func(example):
    text = f"### Instruction:\\n{{example['instruction']}}\\n\\n"
    if example.get('input'):
        text += f"### Input:\\n{{example['input']}}\\n\\n"
    text += f"### Response:\\n{{example['output']}}"
    return {{"text": text}}

dataset = dataset.map(formatting_func)

# Konfiguracja treningu
print("\\n[4/5] Konfiguracja treningu...")
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=4,
    learning_rate=LEARNING_RATE,
    num_train_epochs=NUM_EPOCHS,
    logging_steps=1,
    save_strategy="epoch",
    use_cpu=True, # Wymuś CPU
    no_cuda=True,
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    args=training_args,
)

# Trenuj
print("\\n[5/5] Rozpoczynam trening...")
trainer.train()

# Zapisz adapter
print("\\nZapisywanie adaptera...")
model.save_pretrained(f"{{OUTPUT_DIR}}/adapter")
tokenizer.save_pretrained(f"{{OUTPUT_DIR}}/adapter")

print("\\n" + "=" * 60)
print("TRENING ZAKOŃCZONY POMYŚLNIE!")
print("=" * 60)
'''
        return script

    def cleanup_job(self, job_name: str) -> None:
        """
        Czyści zadanie treningowe (usuwa kontener lub killuje proces).

        Args:
            job_name: Nazwa joba
        """
        if job_name not in self.training_containers:
            logger.warning(f"Job {job_name} nie istnieje")
            return

        try:
            job_info = self.training_containers[job_name]

            if job_info.get("type") == "local":
                # Local cleanup
                process = job_info.get("process")
                pid = job_info.get("pid")
                if process:
                    if process.poll() is None:  # Running
                        logger.info(f"Terminating local process {pid}")
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                elif pid:
                    self._signal_validated_local_job(job_name, job_info, signal.SIGTERM)

                # Opcjonalnie usuń log file? Nie, zostawmy dla debugu.
            else:
                # Docker cleanup
                container = self._get_job_container(job_name)

                # Zatrzymaj i usuń kontener
                try:
                    container.stop(timeout=10)
                except TypeError:
                    container.stop()
                try:
                    container.remove(force=True)
                except TypeError:
                    container.remove()

            # Usuń z rejestru
            del self.training_containers[job_name]

            logger.info(f"Usunięto job: {job_name}")

        except Exception as e:
            logger.error(f"Błąd podczas czyszczenia joba: {e}")
        finally:
            # Legacy i obecna ścieżka oczekują usunięcia wpisu nawet przy błędzie.
            self.training_containers.pop(job_name, None)

    def get_gpu_info(self) -> Dict[str, Any]:
        """
        Pobiera informacje o GPU (nvidia-smi).

        Returns:
            Słownik z informacjami o GPU
        """
        if not self.enable_gpu:
            return {
                "available": False,
                "message": "GPU disabled in configuration",
            }

        try:
            # Uruchom nvidia-smi w kontenerze
            result = self.client.containers.run(
                image=SETTINGS.DOCKER_CUDA_IMAGE,
                command="nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits",
                device_requests=[
                    docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
                ],
                remove=True,
                detach=False,
            )

            # Parse output
            output = result.decode("utf-8").strip()
            if not output:
                return {
                    "available": True,
                    "gpus": [],
                    "message": "No GPU info available",
                }

            gpus = []
            for line in output.split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    gpus.append(
                        {
                            "name": parts[0],
                            "memory_total_mb": float(parts[1]),
                            "memory_used_mb": float(parts[2]),
                            "memory_free_mb": float(parts[3]),
                            "utilization_percent": float(parts[4]),
                        }
                    )

            return {
                "available": True,
                "count": len(gpus),
                "gpus": gpus,
            }

        except Exception as e:
            logger.warning(f"Failed to get GPU info: {e}")
            return {
                "available": self.is_gpu_available(),
                "message": f"Failed to get GPU details: {str(e)}",
            }

    def stream_job_logs(self, job_name: str, since_timestamp: Optional[int] = None):
        """
        Generator do streamowania logów z zadania treningowego.

        Args:
            job_name: Nazwa joba
            since_timestamp: Timestamp (Unix) od którego pobierać logi (opcjonalne)

        Yields:
            Linie logów jako stringi

        Raises:
            KeyError: Jeśli job nie istnieje
        """
        container = self._get_job_container(job_name)

        try:
            # Stream logów z kontenera
            # since: timestamps od kiedy pobierać logi
            # follow: czy kontynuować czytanie nowych logów
            # stream: zwróć generator zamiast całych logów
            log_stream = container.logs(
                stream=True,
                follow=True,
                timestamps=True,
                since=since_timestamp,
            )

            for log_line in log_stream:
                # Dekoduj i zwróć linię
                try:
                    line = log_line.decode("utf-8").strip()
                    if line:
                        yield line
                except UnicodeDecodeError:
                    # Pomiń linie które nie da się zdekodować
                    continue

        except Exception as e:
            logger.error(f"Błąd podczas streamowania logów: {e}")
            yield f"Error streaming logs: {str(e)}"
