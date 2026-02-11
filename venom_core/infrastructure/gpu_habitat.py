"""Moduł: gpu_habitat - Siedlisko Treningowe z obsługą GPU."""

import importlib
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

    def __init__(self, enable_gpu: bool = True, training_image: Optional[str] = None):
        """
        Inicjalizacja GPUHabitat.

        Args:
            enable_gpu: Czy włączyć wsparcie GPU (domyślnie True)
            training_image: Obraz Docker dla treningu (domyślnie unsloth)

        Raises:
            RuntimeError: Jeśli Docker nie jest dostępny

        Note:
            Nie wywołujemy super().__init__() ponieważ GPUHabitat nie tworzy
            standardowego kontenera sandbox - zamiast tego zarządza tymczasowymi
            kontenerami treningowymi. Dziedziczymy po DockerHabitat głównie jako
            marker typologiczny, a nie dla dziedziczenia funkcjonalności.
        """
        # Inicjalizacja klienta Docker (bez tworzenia standardowego kontenera)
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

        self.enable_gpu = enable_gpu
        self.training_image = training_image or self.DEFAULT_TRAINING_IMAGE
        self.training_containers: dict[str, Any] = {}
        # Backward-compat: część testów i starszy kod używa `job_registry`.
        self.job_registry = self.training_containers
        self._gpu_available = bool(enable_gpu)

        # Sprawdź dostępność GPU
        if self.enable_gpu:
            self._gpu_available = self._check_gpu_availability()
            if not self._gpu_available:
                # Deterministyczny fallback CPU: nie próbujemy już wymuszać GPU.
                self.enable_gpu = False
                logger.warning(
                    "GPU fallback aktywny: trening zostanie uruchomiony na CPU."
                )

        logger.info(
            f"GPUHabitat zainicjalizowany (GPU={'enabled' if enable_gpu else 'disabled'}, "
            f"image={self.training_image})"
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
        dataset_path_obj = Path(dataset_path)
        if not dataset_path_obj.exists():
            raise ValueError(f"Dataset nie istnieje: {dataset_path_obj}")

        output_dir_obj = Path(output_dir)
        output_dir_obj.mkdir(parents=True, exist_ok=True)

        job_name = job_name or f"training_{dataset_path_obj.stem}"

        logger.info(
            f"Uruchamianie treningu: job={job_name}, model={base_model}, "
            f"dataset={dataset_path_obj.name}"
        )

        try:
            # Przygotuj obraz treningowy
            try:
                self.client.images.get(self.training_image)
                logger.info(f"Obraz {self.training_image} już istnieje")
            except ImageNotFound:
                logger.info(f"Pobieranie obrazu {self.training_image}...")
                self.client.images.pull(self.training_image)

            # Przygotuj skrypt treningowy
            training_script = self._generate_training_script(
                dataset_path="/workspace/dataset.jsonl",
                base_model=base_model,
                output_dir="/workspace/output",
                lora_rank=lora_rank,
                learning_rate=learning_rate,
                num_epochs=num_epochs,
                max_seq_length=max_seq_length,
                batch_size=batch_size,
            )

            # Zapisz skrypt w output_dir
            script_path = output_dir_obj / "train_script.py"
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(training_script)

            # Przygotuj volumes
            volumes = {
                str(dataset_path_obj.resolve()): {
                    "bind": "/workspace/dataset.jsonl",
                    "mode": "ro",
                },
                str(output_dir_obj.resolve()): {
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
    ) -> str:
        """
        Generuje skrypt treningowy Pythona dla Unsloth.

        Args:
            Parametry treningu (patrz run_training_job)

        Returns:
            Kod źródłowy skryptu Pythona
        """
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

    def cleanup_job(self, job_name: str) -> None:
        """
        Czyści zadanie treningowe (usuwa kontener).

        Args:
            job_name: Nazwa joba
        """
        if job_name not in self.training_containers:
            logger.warning(f"Job {job_name} nie istnieje")
            return

        try:
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
