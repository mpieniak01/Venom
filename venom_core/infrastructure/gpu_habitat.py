"""Moduł: gpu_habitat - Siedlisko Treningowe z obsługą GPU."""

from pathlib import Path
from typing import Dict, Optional

import docker
from docker.errors import APIError, ImageNotFound

from venom_core.infrastructure.docker_habitat import DockerHabitat
from venom_core.utils.logger import get_logger

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

    def __init__(self, enable_gpu: bool = True, training_image: str = None):
        """
        Inicjalizacja GPUHabitat.

        Args:
            enable_gpu: Czy włączyć wsparcie GPU (domyślnie True)
            training_image: Obraz Docker dla treningu (domyślnie unsloth)

        Raises:
            RuntimeError: Jeśli Docker nie jest dostępny
        """
        # Nie wywołujemy super().__init__() aby nie tworzyć standardowego kontenera
        try:
            self.client = docker.from_env()
            logger.info("Połączono z Docker daemon (GPU mode)")
        except Exception as e:
            error_msg = f"Nie można połączyć się z Docker daemon: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

        self.enable_gpu = enable_gpu
        self.training_image = training_image or self.DEFAULT_TRAINING_IMAGE
        self.training_containers = {}  # Rejestr aktywnych kontenerów treningowych

        # Sprawdź dostępność GPU
        if self.enable_gpu:
            self._check_gpu_availability()

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
                image="nvidia/cuda:12.0.0-base-ubuntu22.04",
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
            logger.warning("Obraz nvidia/cuda nie jest dostępny, pobieram...")
            try:
                self.client.images.pull("nvidia/cuda:12.0.0-base-ubuntu22.04")
                return self._check_gpu_availability()  # Retry
            except Exception as e:
                logger.error(f"Nie można pobrać obrazu nvidia/cuda: {e}")
                return False

        except APIError as e:
            logger.warning(f"GPU lub nvidia-container-toolkit nie są dostępne: {e}")
            logger.warning("Trening będzie dostępny tylko na CPU")
            self.enable_gpu = False
            return False

        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas sprawdzania GPU: {e}")
            self.enable_gpu = False
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
        dataset_path = Path(dataset_path)
        if not dataset_path.exists():
            raise ValueError(f"Dataset nie istnieje: {dataset_path}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        job_name = job_name or f"training_{dataset_path.stem}"

        logger.info(
            f"Uruchamianie treningu: job={job_name}, model={base_model}, "
            f"dataset={dataset_path.name}"
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
            script_path = output_dir / "train_script.py"
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(training_script)

            # Przygotuj volumes
            volumes = {
                str(dataset_path.resolve()): {
                    "bind": "/workspace/dataset.jsonl",
                    "mode": "ro",
                },
                str(output_dir.resolve()): {"bind": "/workspace/output", "mode": "rw"},
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
                "dataset_path": str(dataset_path),
                "output_dir": str(output_dir),
                "status": "running",
            }

            logger.info(
                f"Kontener treningowy uruchomiony: {container.id[:12]} (job={job_name})"
            )

            return {
                "container_id": container.id,
                "job_name": job_name,
                "status": "running",
                "adapter_path": str(output_dir / "adapter"),
            }

        except Exception as e:
            error_msg = f"Błąd podczas uruchamiania treningu: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def get_training_status(self, job_name: str) -> Dict[str, str]:
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
        if job_name not in self.training_containers:
            raise KeyError(f"Job {job_name} nie istnieje")

        job_info = self.training_containers[job_name]
        container = job_info["container"]

        try:
            container.reload()
            status = container.status

            # Mapuj status Dockera na nasz format
            if status == "running":
                job_status = "running"
            elif status == "exited":
                exit_code = container.attrs["State"]["ExitCode"]
                job_status = "completed" if exit_code == 0 else "failed"
            else:
                job_status = "unknown"

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
                "status": "error",
                "logs": str(e),
                "container_id": container.id,
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
            job_info = self.training_containers[job_name]
            container = job_info["container"]

            # Zatrzymaj i usuń kontener
            container.stop()
            container.remove()

            # Usuń z rejestru
            del self.training_containers[job_name]

            logger.info(f"Usunięto job: {job_name}")

        except Exception as e:
            logger.error(f"Błąd podczas czyszczenia joba: {e}")
