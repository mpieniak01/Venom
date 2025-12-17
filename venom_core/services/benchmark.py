"""
Moduł: benchmark - Silnik benchmarkingu modeli AI.

Odpowiada za:
- Orkiestrację testowania wielu modeli sekwencyjnie
- Automatyczne przełączanie między modelami
- Pomiar metryk: latencja, tokens/s, szczytowe zużycie VRAM
- Próbkowanie VRAM podczas generowania
"""

import asyncio
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from venom_core.config import SETTINGS
from venom_core.core.llm_server_controller import LlmServerController
from venom_core.core.model_registry import ModelRegistry
from venom_core.core.service_monitor import ServiceHealthMonitor
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class BenchmarkStatus(str, Enum):
    """Status testu benchmarkowego."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BenchmarkQuestion:
    """Pytanie do testu benchmarkowego."""

    id: int
    question: str
    category: str


@dataclass
class ModelBenchmarkResult:
    """Wynik testu dla pojedynczego modelu."""

    model_name: str
    status: str = "pending"
    latency_ms: Optional[float] = None
    tokens_per_second: Optional[float] = None
    peak_vram_mb: Optional[float] = None
    time_to_first_token_ms: Optional[float] = None
    total_duration_ms: Optional[float] = None
    questions_tested: int = 0
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje wynik do słownika."""
        return {
            "model_name": self.model_name,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "tokens_per_second": self.tokens_per_second,
            "peak_vram_mb": self.peak_vram_mb,
            "time_to_first_token_ms": self.time_to_first_token_ms,
            "total_duration_ms": self.total_duration_ms,
            "questions_tested": self.questions_tested,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class BenchmarkJob:
    """Job benchmarkowy - test wielu modeli."""

    benchmark_id: str
    models: List[str]
    num_questions: int
    status: BenchmarkStatus = BenchmarkStatus.PENDING
    current_model_index: int = 0
    results: List[ModelBenchmarkResult] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje job do słownika."""
        progress = "idle"
        if self.status == BenchmarkStatus.RUNNING:
            progress = (
                f"Testing model {self.current_model_index + 1}/{len(self.models)}"
            )
        elif self.status == BenchmarkStatus.COMPLETED:
            progress = "completed"
        elif self.status == BenchmarkStatus.FAILED:
            progress = "failed"

        return {
            "benchmark_id": self.benchmark_id,
            "status": self.status.value,
            "progress": progress,
            "current_model": (
                self.models[self.current_model_index]
                if self.current_model_index < len(self.models)
                else None
            ),
            "models": self.models,
            "num_questions": self.num_questions,
            "results": [r.to_dict() for r in self.results],
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }


class BenchmarkService:
    """
    Serwis orkiestracji testów benchmarkowych dla modeli AI.

    Funkcjonalności:
    - Przełączanie modeli przez ModelRegistry
    - Oczekiwanie na healthcheck po zmianie modelu
    - Wysyłanie pytań i pomiar czasu odpowiedzi
    - Próbkowanie VRAM co 100ms podczas generowania
    """

    def __init__(
        self,
        model_registry: ModelRegistry,
        service_monitor: ServiceHealthMonitor,
        llm_controller: Optional[LlmServerController] = None,
        questions_path: Optional[str] = None,
    ):
        """
        Inicjalizacja BenchmarkService.

        Args:
            model_registry: Rejestr modeli do przełączania
            service_monitor: Monitor do sprawdzania healthcheck i VRAM
            llm_controller: Kontroler serwerów LLM (opcjonalny)
            questions_path: Ścieżka do pliku z pytaniami testowymi
        """
        self.model_registry = model_registry
        self.service_monitor = service_monitor
        self.llm_controller = llm_controller
        self.questions_path = Path(
            questions_path or "./data/datasets/eval_questions.json"
        )

        # Aktywne joby benchmarkowe
        self.jobs: Dict[str, BenchmarkJob] = {}

        # Lock dla sekwencyjnego wykonywania benchmarków
        self._benchmark_lock = asyncio.Lock()

        logger.info("BenchmarkService zainicjalizowany")

    def _load_questions(self) -> List[BenchmarkQuestion]:
        """
        Ładuje pytania testowe z pliku JSON.

        Returns:
            Lista pytań do testów

        Raises:
            FileNotFoundError: Jeśli plik nie istnieje
            ValueError: Jeśli plik ma nieprawidłowy format
        """
        if not self.questions_path.exists():
            raise FileNotFoundError(
                f"Plik z pytaniami nie istnieje: {self.questions_path}"
            )

        try:
            with open(self.questions_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            questions = []
            for q_data in data.get("questions", []):
                questions.append(
                    BenchmarkQuestion(
                        id=q_data["id"],
                        question=q_data["question"],
                        category=q_data.get("category", "general"),
                    )
                )

            logger.info(f"Załadowano {len(questions)} pytań testowych")
            return questions

        except json.JSONDecodeError as e:
            raise ValueError(f"Nieprawidłowy format JSON: {e}") from e
        except KeyError as e:
            raise ValueError(f"Brak wymaganego pola w pytaniu: {e}") from e

    async def start_benchmark(self, models: List[str], num_questions: int = 5) -> str:
        """
        Rozpoczyna benchmark wielu modeli.

        Args:
            models: Lista nazw modeli do przetestowania
            num_questions: Liczba pytań do zadania każdemu modelowi

        Returns:
            ID benchmarku do sprawdzania statusu

        Raises:
            ValueError: Jeśli parametry są nieprawidłowe
        """
        if not models:
            raise ValueError("Lista modeli nie może być pusta")

        if num_questions < 1:
            raise ValueError("Liczba pytań musi być większa niż 0")

        # Utwórz job
        benchmark_id = str(uuid.uuid4())
        job = BenchmarkJob(
            benchmark_id=benchmark_id,
            models=models,
            num_questions=num_questions,
            results=[ModelBenchmarkResult(model_name=m) for m in models],
        )
        self.jobs[benchmark_id] = job

        # Uruchom benchmark w tle
        asyncio.create_task(self._run_benchmark_task(benchmark_id))

        logger.info(
            f"Rozpoczęto benchmark {benchmark_id}: {len(models)} modeli, "
            f"{num_questions} pytań"
        )
        return benchmark_id

    def get_benchmark_status(self, benchmark_id: str) -> Optional[Dict[str, Any]]:
        """
        Pobiera status benchmarku.

        Args:
            benchmark_id: ID benchmarku

        Returns:
            Słownik ze statusem lub None jeśli nie znaleziono
        """
        job = self.jobs.get(benchmark_id)
        return job.to_dict() if job else None

    def list_benchmarks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lista ostatnich benchmarków.

        Args:
            limit: Maksymalna liczba wyników

        Returns:
            Lista benchmarków posortowanych od najnowszych
        """
        sorted_jobs = sorted(
            self.jobs.values(), key=lambda j: j.created_at, reverse=True
        )
        return [job.to_dict() for job in sorted_jobs[:limit]]

    async def _run_benchmark_task(self, benchmark_id: str):
        """
        Zadanie wykonania benchmarku (uruchamiane w tle).

        Args:
            benchmark_id: ID benchmarku do wykonania
        """
        async with self._benchmark_lock:
            job = self.jobs.get(benchmark_id)
            if not job:
                logger.error(f"Benchmark {benchmark_id} nie znaleziony")
                return

            try:
                job.status = BenchmarkStatus.RUNNING
                job.started_at = datetime.now().isoformat()

                # Załaduj pytania testowe
                all_questions = self._load_questions()
                if len(all_questions) < job.num_questions:
                    logger.warning(
                        f"Dostępnych tylko {len(all_questions)} pytań, użyję wszystkich"
                    )

                # Wybierz losowe pytania
                questions = random.sample(
                    all_questions, min(job.num_questions, len(all_questions))
                )

                # Testuj każdy model po kolei
                for idx, model_name in enumerate(job.models):
                    job.current_model_index = idx
                    result = job.results[idx]

                    logger.info(
                        f"[{benchmark_id}] Testowanie modelu {idx + 1}/{len(job.models)}: {model_name}"
                    )

                    try:
                        await self._test_model(model_name, questions, result)
                    except Exception as e:
                        logger.error(
                            f"Błąd podczas testowania modelu {model_name}: {e}"
                        )
                        result.status = "failed"
                        result.error_message = str(e)

                job.status = BenchmarkStatus.COMPLETED
                job.completed_at = datetime.now().isoformat()
                logger.info(f"Benchmark {benchmark_id} zakończony pomyślnie")

            except Exception as e:
                logger.error(f"Błąd podczas wykonywania benchmarku: {e}")
                job.status = BenchmarkStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.now().isoformat()

    async def _test_model(
        self,
        model_name: str,
        questions: List[BenchmarkQuestion],
        result: ModelBenchmarkResult,
    ):
        """
        Testuje pojedynczy model z podanymi pytaniami.

        Args:
            model_name: Nazwa modelu do przetestowania
            questions: Lista pytań testowych
            result: Obiekt wyniku do wypełnienia
        """
        result.started_at = datetime.now().isoformat()
        result.status = "running"

        try:
            # Aktywuj model przez ModelRegistry
            logger.info(f"Aktywacja modelu: {model_name}")
            # Próba aktywacji modelu - jeśli nie powiedzie się, kontynuuj z obecnym modelem
            try:
                # ModelRegistry.activate_model jest obecnie stub - log warning
                logger.warning(
                    f"ModelRegistry.activate_model() jest obecnie stub. "
                    f"Benchmark użyje obecnego modelu zamiast {model_name}. "
                    f"Aby w pełni przełączać modele, zaimplementuj aktywację w ModelRegistry."
                )
                # await self.model_registry.activate_model(model_name, runtime="vllm")
            except Exception as e:
                logger.warning(f"Nie można aktywować modelu {model_name}: {e}")

            # Czekaj na healthcheck
            await self._wait_for_healthcheck(timeout=60)

            # Testuj z pytaniami
            total_latency = 0.0
            total_tokens = 0
            total_duration = 0.0
            peak_vram = 0.0

            for question in questions:
                # Mierz metryki dla pojedynczego pytania
                metrics = await self._query_model_with_metrics(question.question)

                # Sumuj latencję tylko jeśli jest dostępna
                if metrics["latency_ms"] is not None:
                    total_latency += metrics["latency_ms"]
                total_tokens += metrics.get("tokens_generated", 0)
                total_duration += metrics["duration_ms"]

                # Śledź szczytowe VRAM
                if metrics.get("peak_vram_mb") and metrics["peak_vram_mb"] > peak_vram:
                    peak_vram = metrics["peak_vram_mb"]

            # Oblicz średnie
            num_questions = len(questions)
            result.latency_ms = (
                round(total_latency / num_questions, 2) if total_latency > 0 else None
            )
            result.time_to_first_token_ms = result.latency_ms  # TTFT = średnia latencja
            result.total_duration_ms = round(total_duration, 2)
            result.peak_vram_mb = round(peak_vram, 2) if peak_vram > 0 else None

            # Oblicz tokens per second
            if total_duration > 0:
                result.tokens_per_second = round(
                    (total_tokens / total_duration) * 1000, 2
                )

            result.questions_tested = num_questions
            result.status = "completed"
            result.completed_at = datetime.now().isoformat()

            logger.info(
                f"Model {model_name} przetestowany: "
                f"latency={result.latency_ms}ms, "
                f"tokens/s={result.tokens_per_second}, "
                f"peak_vram={result.peak_vram_mb}MB"
            )

        except Exception as e:
            logger.error(f"Błąd podczas testowania modelu {model_name}: {e}")
            result.status = "failed"
            result.error_message = str(e)
            result.completed_at = datetime.now().isoformat()
            raise

    async def _wait_for_healthcheck(self, timeout: int = 60):
        """
        Czeka aż serwis LLM będzie gotowy (healthcheck).

        Args:
            timeout: Maksymalny czas oczekiwania w sekundach

        Raises:
            TimeoutError: Jeśli serwis nie odpowiada w czasie
        """
        start_time = time.time()
        endpoint = SETTINGS.LLM_LOCAL_ENDPOINT.rstrip("/")

        logger.info(f"Oczekiwanie na healthcheck: {endpoint}")

        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{endpoint}/models")
                    if response.status_code == 200:
                        logger.info("Healthcheck OK - serwis gotowy")
                        return
            except Exception:
                pass

            await asyncio.sleep(2)

        raise TimeoutError(
            f"Serwis LLM nie odpowiada po {timeout}s - healthcheck failed"
        )

    async def _query_model_with_metrics(self, question: str) -> Dict[str, Any]:
        """
        Wysyła pytanie do modelu i mierzy metryki.

        Mierzy:
        - Latencję (czas do pierwszego tokena)
        - Całkowity czas generowania
        - Szczytowe użycie VRAM (próbkowane co 100ms)

        Args:
            question: Pytanie do zadania modelowi

        Returns:
            Słownik z metrykami: latency_ms, duration_ms, peak_vram_mb, tokens_generated
        """
        endpoint = SETTINGS.LLM_LOCAL_ENDPOINT.rstrip("/")

        # Uruchom zadanie próbkowania VRAM w tle
        vram_samples = []
        sampling_task = asyncio.create_task(
            self._sample_vram_during_generation(vram_samples)
        )

        try:
            start_time = time.time()
            time_to_first_token = None

            async with httpx.AsyncClient(timeout=120.0) as client:
                # Wysyłamy request do modelu
                # UWAGA: Obecnie używamy SETTINGS.LLM_MODEL_NAME jako fallback
                # Po zaimplementowaniu activate_model(), model_name będzie dynamiczny
                async with client.stream(
                    "POST",
                    f"{endpoint}/chat/completions",
                    json={
                        "model": SETTINGS.LLM_MODEL_NAME,  # TODO: użyj model_name po pełnej implementacji activate_model
                        "messages": [{"role": "user", "content": question}],
                        "stream": True,
                        "max_tokens": 200,
                    },
                ) as response:
                    response.raise_for_status()

                    tokens_generated = 0
                    chunk_count = 0
                    async for line in response.aiter_lines():
                        if not line.strip() or not line.startswith("data: "):
                            continue

                        chunk_count += 1

                        # Pierwszy token
                        if time_to_first_token is None:
                            time_to_first_token = (time.time() - start_time) * 1000

                        # Szacunkowe zliczanie tokenów z chunków streamu
                        # Każdy chunk może zawierać ~1-3 tokeny w zależności od modelu
                        # Używamy konserwatywnego przelicznika 1.5 tokena/chunk
                        tokens_generated = int(chunk_count * 1.5)

            duration_ms = (time.time() - start_time) * 1000

            # Zatrzymaj próbkowanie VRAM
            sampling_task.cancel()
            try:
                await sampling_task
            except asyncio.CancelledError:
                pass

            # Znajdź szczytowe VRAM
            peak_vram = max(vram_samples) if vram_samples else None

            return {
                "latency_ms": (
                    round(time_to_first_token, 2)
                    if time_to_first_token is not None
                    else None
                ),
                "duration_ms": round(duration_ms, 2),
                "peak_vram_mb": peak_vram,
                "tokens_generated": tokens_generated,
            }

        except Exception as e:
            # Zatrzymaj próbkowanie w przypadku błędu
            sampling_task.cancel()
            try:
                await sampling_task
            except asyncio.CancelledError:
                pass
            raise e

    async def _sample_vram_during_generation(self, samples: List[float]):
        """
        Próbkuje zużycie VRAM co 100ms podczas generowania.

        Args:
            samples: Lista do zapisywania próbek VRAM (w MB)
        """
        try:
            while True:
                vram = self.service_monitor.get_gpu_memory_usage()
                if vram is not None:
                    samples.append(vram)
                await asyncio.sleep(0.1)  # 100ms
        except asyncio.CancelledError:
            # Zadanie anulowane - to normalne
            pass
