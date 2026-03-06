"""Moduł: gpu_habitat - Siedlisko Treningowe z obsługą GPU."""

import importlib
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from venom_core.config import SETTINGS
from venom_core.infrastructure.docker_habitat import DockerHabitat
from venom_core.infrastructure.gpu_habitat_policy import (
    is_allowed_local_job_signal as is_allowed_local_job_signal_impl,
)
from venom_core.infrastructure.gpu_habitat_policy import (
    is_pid_owned_by_current_user as is_pid_owned_by_current_user_impl,
)
from venom_core.infrastructure.gpu_habitat_policy import (
    resolve_positive_pid as resolve_positive_pid_impl,
)
from venom_core.infrastructure.gpu_habitat_policy import (
    send_signal_to_validated_pid as send_signal_to_validated_pid_impl,
)
from venom_core.infrastructure.gpu_habitat_policy import (
    signal_validated_local_job as signal_validated_local_job_impl,
)
from venom_core.infrastructure.gpu_habitat_policy import (
    validate_local_job_pid as validate_local_job_pid_impl,
)
from venom_core.infrastructure.gpu_habitat_probe import (
    check_gpu_availability as check_gpu_availability_impl,
)
from venom_core.infrastructure.gpu_habitat_probe import (
    check_local_dependencies as check_local_dependencies_impl,
)
from venom_core.infrastructure.gpu_habitat_probe import (
    check_local_gpu_availability as check_local_gpu_availability_impl,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    TrainingJobDeps,
    TrainingJobRequest,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    cleanup_docker_job as cleanup_docker_job_impl,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    cleanup_job as cleanup_job_impl,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    cleanup_local_job as cleanup_local_job_impl,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    get_local_job_status as get_local_job_status_impl,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    get_training_status as get_training_status_impl,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    run_local_training_job as run_local_training_job_impl,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    run_training_job as run_training_job_impl,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    stream_job_logs as stream_job_logs_impl,
)
from venom_core.infrastructure.gpu_habitat_runtime import (
    terminate_local_process as terminate_local_process_impl,
)
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
        return check_local_gpu_availability_impl(run_cmd_fn=subprocess.run)

    def _check_local_dependencies(self) -> None:
        """Sprawdza czy wymagane biblioteki są zainstalowane lokalnie."""
        self._has_unsloth = check_local_dependencies_impl(
            enable_gpu=self.enable_gpu,
            import_module_fn=importlib.import_module,
            logger=logger,
        )

    def _check_gpu_availability(self) -> bool:
        """
        Sprawdza dostępność GPU i nvidia-container-toolkit.

        Returns:
            True jeśli GPU jest dostępne, False w przeciwnym razie
        """
        return check_gpu_availability_impl(
            client=self.client,
            docker_cuda_image=SETTINGS.DOCKER_CUDA_IMAGE,
            device_request_factory=docker.types.DeviceRequest,
            image_not_found_error=ImageNotFound,
            api_error=APIError,
            logger=logger,
            retry_check_fn=self._check_gpu_availability,
        )

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
        return run_training_job_impl(
            manager=self,
            request=TrainingJobRequest(
                dataset_path=dataset_path,
                base_model=base_model,
                output_dir=output_dir,
                lora_rank=lora_rank,
                learning_rate=learning_rate,
                num_epochs=num_epochs,
                max_seq_length=max_seq_length,
                batch_size=batch_size,
                job_name=job_name,
            ),
            deps=TrainingJobDeps(
                settings=SETTINGS,
                logger=logger,
                docker_module=docker,
                image_not_found_error=ImageNotFound,
            ),
        )

    def _run_local_training_job(
        self, job_name: str, script_path: Path, output_dir: Path, dataset_path: Path
    ) -> Dict[str, str]:
        """Uruchamia proces treningowy lokalnie (subprocess)."""
        return run_local_training_job_impl(
            job_name=job_name,
            script_path=script_path,
            output_dir=output_dir,
            dataset_path=dataset_path,
            enable_gpu=self.enable_gpu,
            training_containers=self.training_containers,
            check_local_dependencies_fn=self._check_local_dependencies,
            python_bin=sys.executable or "python3",
            logger=logger,
        )

    def _validate_local_job_pid(self, job_info: Dict[str, Any]) -> Optional[int]:
        """
        Zwraca PID tylko jeśli wskazuje na oczekiwany proces lokalnego treningu.
        """
        return validate_local_job_pid_impl(job_info=job_info, path_factory=Path)

    def _signal_validated_local_job(
        self, job_info: Dict[str, Any], sig: signal.Signals
    ) -> bool:
        """
        Wysyła sygnał tylko do zweryfikowanego procesu lokalnego joba.
        """
        return signal_validated_local_job_impl(
            job_info=job_info,
            sig=sig,
            validate_local_job_pid_fn=self._validate_local_job_pid,
            is_allowed_local_job_signal_fn=self._is_allowed_local_job_signal,
            is_pid_owned_by_current_user_fn=self._is_pid_owned_by_current_user,
            send_signal_to_validated_pid_fn=self._send_signal_to_validated_pid,
            logger=logger,
        )

    def _send_signal_to_validated_pid(self, pid: int, sig: signal.Signals) -> bool:
        """
        Wysyła sygnał do zweryfikowanego PID-a lokalnego joba.

        Preferuje Linux pidfd API (odporne na PID reuse), a jeśli nie jest
        dostępne używa bezpiecznego wywołania `kill` bez shell=True.
        """
        return send_signal_to_validated_pid_impl(
            pid=pid,
            sig=sig,
            signal_module=signal,
            os_module=os,
            subprocess_module=subprocess,
        )

    def _is_allowed_local_job_signal(self, sig: signal.Signals) -> bool:
        """Zwraca True tylko dla sygnałów dopuszczonych w local runtime."""
        return is_allowed_local_job_signal_impl(
            sig=sig,
            allowed_local_job_signals=self.ALLOWED_LOCAL_JOB_SIGNALS,
            signal_module=signal,
        )

    def _is_pid_owned_by_current_user(self, pid: int) -> bool:
        """
        Weryfikuje czy PID należy do aktualnego użytkownika systemowego.
        """
        return is_pid_owned_by_current_user_impl(
            pid=pid,
            path_factory=Path,
            get_uid_fn=os.getuid,
        )

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
        return get_training_status_impl(
            training_containers=self.training_containers,
            job_name=job_name,
            get_job_container_fn=self._get_job_container,
            get_local_job_status_fn=self._get_local_job_status,
            logger=logger,
        )

    def _get_local_job_status(self, job_name: str) -> Dict[str, Optional[str]]:
        """Pobiera status lokalnego procesu treningowego."""
        return get_local_job_status_impl(
            training_containers=self.training_containers,
            job_name=job_name,
            validate_local_job_pid_fn=self._validate_local_job_pid,
        )

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
from datasets import load_dataset

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
dataset = load_dataset("json", data_files=DATASET_PATH, split="train")
print(f"Załadowano {{len(dataset)}} przykładów")

# Formatowanie promptu
def formatting_func(example):
    text = f"### Instruction:\\n{{example['instruction']}}\\n\\n"
    if example.get('input'):
        text += f"### Input:\\n{{example['input']}}\\n\\n"
    text += f"### Response:\\n{{example['output']}}"
    return {{"text": text}}

dataset = dataset.map(formatting_func, remove_columns=dataset.column_names)

# Konfiguracja treningu
print("\\n[4/5] Konfiguracja treningu...")
training_args = TrainingArguments(
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
    report_to="none",
)

trainer_kwargs = dict(
    model=model,
    train_dataset=dataset,
    args=training_args,
)

try:
    trainer = SFTTrainer(
        tokenizer=tokenizer,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        **trainer_kwargs,
    )
except TypeError as exc:
    print(f"Compatibility fallback for SFTTrainer(tokenizer=...): {{exc}}")
    try:
        trainer = SFTTrainer(
            processing_class=tokenizer,
            dataset_text_field="text",
            max_seq_length=MAX_SEQ_LENGTH,
            **trainer_kwargs,
        )
    except TypeError as exc2:
        print(f"Compatibility fallback for SFTTrainer(processing_class=...): {{exc2}}")
        trainer = SFTTrainer(**trainer_kwargs)

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
        """Generuje skrypt dla standardowego HuggingFace Transformers (GPU if available)."""
        script = f'''#!/usr/bin/env python3
"""
Skrypt treningowy Venom - HuggingFace Transformers fallback.
Używany gdy Unsloth nie jest dostępne; używa GPU, jeśli torch.cuda.is_available().
"""

import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer
from datasets import load_dataset

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
print("VENOM TRAINING JOB (Standard Transformers Fallback)")
print("=" * 60)
CUDA_AVAILABLE = torch.cuda.is_available()
print(f"CUDA available: {{CUDA_AVAILABLE}}")

# Ładuj model
print("\\n[1/5] Ładowanie modelu...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16 if CUDA_AVAILABLE else None,
)
if CUDA_AVAILABLE:
    model = model.to("cuda")

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
dataset = load_dataset("json", data_files=DATASET_PATH, split="train")

# Formatowanie promptu
def formatting_func(example):
    text = f"### Instruction:\\n{{example['instruction']}}\\n\\n"
    if example.get('input'):
        text += f"### Input:\\n{{example['input']}}\\n\\n"
    text += f"### Response:\\n{{example['output']}}"
    return {{"text": text}}

dataset = dataset.map(formatting_func, remove_columns=dataset.column_names)

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
    fp16=CUDA_AVAILABLE,
    use_cpu=(not CUDA_AVAILABLE),
    no_cuda=(not CUDA_AVAILABLE),
    report_to="none",
)

try:
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        args=training_args,
    )
except TypeError as exc:
    print(f"Compatibility fallback for SFTTrainer(tokenizer=...): {{exc}}")
    try:
        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=dataset,
            dataset_text_field="text",
            max_seq_length=MAX_SEQ_LENGTH,
            args=training_args,
        )
    except TypeError as exc2:
        print(f"Compatibility fallback for SFTTrainer(processing_class=...): {{exc2}}")
        trainer = SFTTrainer(
            model=model,
            train_dataset=dataset,
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

    def _terminate_local_process(self, process, pid: int) -> None:
        """
        Bezpiecznie terminuje proces lokalny.

        Args:
            process: Obiekt subprocess.Popen
            pid: ID procesu
        """
        terminate_local_process_impl(process=process, pid=pid, logger=logger)

    def _cleanup_local_job(self, job_info: Dict[str, Any]) -> None:
        """
        Czyści zadanie lokalne (process lub pid).

        Args:
            job_info: Informacje o jobie
        """
        cleanup_local_job_impl(
            job_info=job_info,
            resolve_positive_pid_fn=self._resolve_positive_pid,
            terminate_local_process_fn=self._terminate_local_process,
            signal_validated_local_job_fn=self._signal_validated_local_job,
            logger=logger,
        )

    @staticmethod
    def _resolve_positive_pid(pid_raw: Any) -> Optional[int]:
        return resolve_positive_pid_impl(pid_raw)

    def _cleanup_docker_job(self, job_name: str) -> None:
        """
        Czyści zadanie dockerowe (zatrzymuje i usuwa kontener).

        Args:
            job_name: Nazwa joba
        """
        cleanup_docker_job_impl(
            job_name=job_name,
            get_job_container_fn=self._get_job_container,
        )

    def cleanup_job(self, job_name: str) -> None:
        """
        Czyści zadanie treningowe (usuwa kontener lub killuje proces).

        Args:
            job_name: Nazwa joba
        """
        cleanup_job_impl(
            job_name=job_name,
            training_containers=self.training_containers,
            cleanup_local_job_fn=self._cleanup_local_job,
            cleanup_docker_job_fn=self._cleanup_docker_job,
            logger=logger,
        )

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
        yield from stream_job_logs_impl(
            job_name=job_name,
            since_timestamp=since_timestamp,
            get_job_container_fn=self._get_job_container,
            logger=logger,
        )
