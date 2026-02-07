"""
Moduł: benchmark - Silnik benchmarkingu modeli AI.

Odpowiada za:
- Orkiestrację testowania wielu modeli sekwencyjnie
- Automatyczne przełączanie między modelami
- Pomiar metryk: latencja, tokens/s, szczytowe zużycie VRAM
- Próbkowanie VRAM podczas generowania
"""

import asyncio
import hashlib
import json
import secrets
import time
import uuid
from contextlib import suppress
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


def _is_valid_benchmark_id(value: str) -> bool:
    """Waliduje benchmark_id jako kanoniczny UUID."""
    return _normalize_benchmark_id(value) is not None


def _normalize_benchmark_id(value: str) -> Optional[str]:
    """Zwraca benchmark_id w postaci kanonicznej UUID lub None."""
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
    return str(parsed)


def _redacted_input_fingerprint(value: str) -> str:
    """Zwraca fingerprint wejścia bez logowania pełnej wartości."""
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"len={len(value)},sha256={digest}"


def _secure_sample_without_replacement(
    items: List["BenchmarkQuestion"], sample_size: int
) -> List["BenchmarkQuestion"]:
    """Losuje bez powtórzeń używając kryptograficznego RNG."""
    if sample_size <= 0:
        return []
    if sample_size >= len(items):
        return list(items)

    pool = list(items)
    selected: List["BenchmarkQuestion"] = []
    for _ in range(sample_size):
        idx = secrets.randbelow(len(pool))
        selected.append(pool.pop(idx))
    return selected


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
    startup_latency_ms: Optional[float] = None  # czas restartu/healthchecku runtime
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
            "startup_latency_ms": self.startup_latency_ms,
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
    task: Optional[Any] = field(default=None, repr=False)  # Referencja do asyncio.Task

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
        storage_dir: str = "./data/benchmarks",
    ):
        """
        Inicjalizacja BenchmarkService.

        Args:
            model_registry: Rejestr modeli do przełączania
            service_monitor: Monitor do sprawdzania healthcheck i VRAM
            llm_controller: Kontroler serwerów LLM (opcjonalny)
            questions_path: Ścieżka do pliku z pytaniami testowymi
            storage_dir: Katalog zapisu wyników
        """
        self.model_registry = model_registry
        self.service_monitor = service_monitor
        self.llm_controller = llm_controller
        self.questions_path = Path(
            questions_path or "./data/datasets/eval_questions.json"
        )
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Aktywne joby benchmarkowe (z limitem pamięci)
        self.jobs: Dict[str, BenchmarkJob] = {}
        self._max_jobs = 1000  # Maksymalna liczba przechowywanych jobów

        # Ładowanie historii
        self._load_jobs_from_disk()

        # Lock dla sekwencyjnego wykonywania benchmarków
        self._benchmark_lock = asyncio.Lock()

        logger.info(
            f"BenchmarkService zainicjalizowany. Załadowano {len(self.jobs)} testów."
        )

    def _save_job(self, job: BenchmarkJob):
        """Zapisuje job do pliku JSON."""
        try:
            file_path = self.storage_dir / f"{job.benchmark_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(job.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Nie udało się zapisać benchmarku {job.benchmark_id}: {e}")

    def _load_jobs_from_disk(self):
        """Ładuje joby z plików JSON."""
        if not self.storage_dir.exists():
            return

        for file_path in self.storage_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Rekonstrukcja obiektów (uproszczona)
                results = []
                for r_data in data.get("results", []):
                    results.append(
                        ModelBenchmarkResult(
                            model_name=r_data["model_name"],
                            status=r_data.get("status", "pending"),
                            latency_ms=r_data.get("latency_ms"),
                            tokens_per_second=r_data.get("tokens_per_second"),
                            peak_vram_mb=r_data.get("peak_vram_mb"),
                            time_to_first_token_ms=r_data.get("time_to_first_token_ms"),
                            total_duration_ms=r_data.get("total_duration_ms"),
                            startup_latency_ms=r_data.get("startup_latency_ms"),
                            questions_tested=r_data.get("questions_tested", 0),
                            error_message=r_data.get("error_message"),
                            started_at=r_data.get("started_at"),
                            completed_at=r_data.get("completed_at"),
                        )
                    )

                job = BenchmarkJob(
                    benchmark_id=data["benchmark_id"],
                    models=data.get("models", []),
                    num_questions=data.get("num_questions", 0),
                    status=BenchmarkStatus(data.get("status", "pending")),
                    current_model_index=0,  # Reset indexu, bo po restarcie i tak jest completed
                    results=results,
                    created_at=data.get("created_at"),
                    started_at=data.get("started_at"),
                    completed_at=data.get("completed_at"),
                    error_message=data.get("error_message"),
                )
                self.jobs[job.benchmark_id] = job
            except Exception as e:
                logger.warning(f"Nie udało się załadować benchmarku z {file_path}: {e}")

    def delete_benchmark(self, benchmark_id: str) -> bool:
        """Usuwa benchmark z pamięci i dysku."""
        normalized_id = _normalize_benchmark_id(benchmark_id)
        if normalized_id is None:
            logger.warning(
                "Odrzucono nieprawidłowy benchmark_id (%s)",
                _redacted_input_fingerprint(benchmark_id or ""),
            )
            return False

        if normalized_id in self.jobs:
            del self.jobs[normalized_id]

        file_path = self.storage_dir / f"{normalized_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                return True
            except Exception as e:
                logger.error(f"Nie udało się usunąć pliku {file_path}: {e}")
                return False
        return False

    def clear_all_benchmarks(self) -> int:
        """Usuwa wszystkie benchmarki. Zwraca liczbę usuniętych."""
        count = len(self.jobs)
        self.jobs.clear()

        for file_path in self.storage_dir.glob("*.json"):
            try:
                file_path.unlink()
            except Exception:
                # Ignorowanie błędów usuwania - plik może być już usunięty lub zablokowany
                # Ignorujemy błędy przy usuwaniu plików (np. brak uprawnień)
                pass
        return count

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

        # Zapisz początkowy stan
        self.jobs[benchmark_id] = job
        self._save_job(job)

        # Uruchom benchmark w tle i zachowaj referencję do zadania
        task = asyncio.create_task(self._run_benchmark_task(benchmark_id))
        job.task = task  # Przechowuj referencję do zadania

        logger.info(
            f"Rozpoczęto benchmark {benchmark_id}: {len(models)} modeli, "
            f"pytań: {num_questions}"
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
        # Dla małej liczby jobów (<1000) sortowanie jest akceptowalne
        # Dla większych zbiorów można rozważyć cache lub SortedDict
        sorted_jobs = sorted(
            self.jobs.values(), key=lambda j: j.created_at, reverse=True
        )
        return [job.to_dict() for job in sorted_jobs[:limit]]

    def _cleanup_old_jobs(self):
        """
        Usuwa stare joby z pamięci (nie z dysku, chyba że chcemy autodelete).
        Na razie zostawiamy na dysku, czyścimy tylko RAM jeśli za dużo.
        """
        if len(self.jobs) > self._max_jobs:
            # Proste czyszczenie pamięci
            pass

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
                self._save_job(job)  # Aktualizacja statusu

                # Załaduj pytania testowe
                all_questions = self._load_questions()
                if len(all_questions) < job.num_questions:
                    logger.warning(
                        f"Dostępnych tylko {len(all_questions)} pytań, użyję wszystkich"
                    )

                # Wybierz losowe pytania
                questions = _secure_sample_without_replacement(
                    all_questions,
                    min(job.num_questions, len(all_questions)),
                )

                # Testuj każdy model po kolei
                for idx, model_name in enumerate(job.models):
                    job.current_model_index = idx
                    result = job.results[idx]

                    logger.info(
                        f"[{benchmark_id}] Testowanie modelu {idx + 1}/{len(job.models)}: {model_name}"
                    )

                    # Zapisz postęp przed każdym modelem
                    self._save_job(job)

                    try:
                        await self._test_model(model_name, questions, result)
                    except Exception as e:
                        logger.error(
                            f"Błąd podczas testowania modelu {model_name}: {e}"
                        )
                        result.status = "failed"
                        result.error_message = str(e)

                # Zapisz wynik ostatniego modelu
                self._save_job(job)

                job.status = BenchmarkStatus.COMPLETED
                job.completed_at = datetime.now().isoformat()
                self._save_job(job)  # Finalny zapis
                logger.info(f"Benchmark {benchmark_id} zakończony pomyślnie")

            except Exception as e:
                logger.error(f"Błąd podczas wykonywania benchmarku: {e}")
                job.status = BenchmarkStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.now().isoformat()
                self._save_job(job)

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
            # Ustal endpoint i runtime na podstawie manifestu / nazwy modelu
            runtime = "vllm"
            endpoint = SETTINGS.VLLM_ENDPOINT.rstrip("/")
            if ":" in model_name:
                runtime = "ollama"
                endpoint = SETTINGS.LLM_LOCAL_ENDPOINT.rstrip("/")
            meta = self.model_registry.manifest.get(model_name)
            if meta:
                if meta.runtime:
                    runtime = meta.runtime
                if meta.provider and meta.provider.value == "ollama":
                    runtime = "ollama"
            if runtime == "ollama":
                endpoint = SETTINGS.LLM_LOCAL_ENDPOINT.rstrip("/")
            else:
                endpoint = SETTINGS.VLLM_ENDPOINT.rstrip("/")

            # Sprawdź czy model jest już załadowany aby uniknąć restartu
            model_already_loaded = False
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{endpoint}/models")
                    if resp.status_code == 200:
                        data = resp.json()
                        running_models = []
                        # Obsługa formatu OpenAI (vLLM)
                        if "data" in data and isinstance(data["data"], list):
                            running_models = [m.get("id") for m in data["data"]]
                        # Obsługa formatu Ollama
                        elif "models" in data and isinstance(data["models"], list):
                            running_models = [m.get("name") for m in data["models"]]

                        if model_name in running_models:
                            model_already_loaded = True
                            # Symulujemy czas startu jako 0, skoro model jest gotowy
                            t_startup = time.time()
                            logger.info(
                                f"Model {model_name} jest już aktywny - pomijam restart serwera."
                            )
            except Exception as e:
                logger.debug(
                    f"Nie udało się sprawdzić aktywnych modeli (to normalne przy starcie): {e}"
                )

            if not model_already_loaded:
                # Aktywuj model przez ModelRegistry
                logger.info(f"Aktywacja modelu: {model_name}")
                # Próba aktywacji modelu - jeśli nie powiedzie się, kontynuuj z obecnym modelem
                try:
                    t_startup = time.time()
                    await self.model_registry.activate_model(model_name, runtime)
                    # Jeśli mamy kontroler serwerów, zrestartuj runtime aby załadować model
                    if self.llm_controller:
                        action = "restart"
                        try:
                            await self.llm_controller.run_action(runtime, action)
                            logger.info(
                                f"{runtime} zrestartowany dla modelu {model_name} (benchmark)"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Nie udało się wykonać {action} dla {runtime}: {e}"
                            )
                except Exception as e:
                    logger.warning(f"Nie można aktywować modelu {model_name}: {e}")
            else:
                # Jeśli model był załadowany, upewnij się że t_startup jest zdefiniowane dla metryk
                if "t_startup" not in locals():
                    t_startup = time.time()

            # Czekaj na healthcheck
            await self._wait_for_healthcheck(endpoint=endpoint, timeout=60)
            if "t_startup" in locals():
                result.startup_latency_ms = round((time.time() - t_startup) * 1000, 2)

            # Testuj z pytaniami
            total_latency = 0.0
            total_ttft = 0.0  # Suma time-to-first-token
            ttft_count = 0  # Liczba udanych pomiarów TTFT
            total_tokens = 0
            total_duration = 0.0
            peak_vram = 0.0

            for question in questions:
                # Mierz metryki dla pojedynczego pytania
                metrics = await self._query_model_with_metrics(
                    question=question.question,
                    model_name=model_name,
                    endpoint=endpoint,
                )

                # Sumuj TTFT osobno od latencji
                if metrics.get("time_to_first_token_ms") is not None:
                    total_ttft += metrics["time_to_first_token_ms"]
                    ttft_count += 1

                # Sumuj latencję tylko jeśli jest dostępna (backward compatibility)
                if metrics["latency_ms"] is not None:
                    total_latency += metrics["latency_ms"]

                total_tokens += metrics.get("tokens_generated", 0)

                # Sprawdź czy duration_ms nie jest None
                if metrics["duration_ms"] is not None:
                    total_duration += metrics["duration_ms"]
                else:
                    logger.warning("Brak duration_ms w metrykach - pomijam")

                # Śledź szczytowe VRAM
                if metrics.get("peak_vram_mb") and metrics["peak_vram_mb"] > peak_vram:
                    peak_vram = metrics["peak_vram_mb"]

            # Oblicz średnie
            num_questions = len(questions)
            result.latency_ms = (
                round(total_latency / num_questions, 2) if total_latency > 0 else None
            )
            result.time_to_first_token_ms = (
                round(total_ttft / ttft_count, 2) if ttft_count > 0 else None
            )
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

    async def _wait_for_healthcheck(self, endpoint: str, timeout: int = 60):
        """
        Czeka aż serwis LLM będzie gotowy (healthcheck).

        Args:
            endpoint: Endpoint serwisu (bez trailing slash)
            timeout: Maksymalny czas oczekiwania w sekundach

        Raises:
            TimeoutError: Jeśli serwis nie odpowiada w czasie
        """
        start_time = time.time()
        logger.info(f"Oczekiwanie na healthcheck: {endpoint}")

        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{endpoint}/models")
                    if response.status_code == 200:
                        logger.info("Healthcheck OK - serwis gotowy")
                        return
            except Exception:
                # Ignoruj błędy połączenia - będziemy próbować ponownie
                pass

            await asyncio.sleep(2)

        raise TimeoutError(
            f"Serwis LLM nie odpowiada po {timeout}s - healthcheck failed"
        )

    async def _query_model_with_metrics(
        self, question: str, model_name: str, endpoint: str
    ) -> Dict[str, Any]:
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
        # Uruchom zadanie próbkowania VRAM w tle
        vram_samples: List[float] = []
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
                        "model": model_name,
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
                        # UWAGA: To jest tymczasowe rozwiązanie przybliżone!
                        # Należy zastąpić właściwym zliczaniem tokenów (np. tiktoken
                        # lub parsowanie pola 'usage' z odpowiedzi API)
                        # Każdy chunk może zawierać ~1-3 tokeny w zależności od modelu
                        # Używamy konserwatywnego przelicznika 1.5 tokena/chunk
                        tokens_generated = int(chunk_count * 1.5)

            duration_ms = (time.time() - start_time) * 1000

            # Zatrzymaj próbkowanie VRAM
            sampling_task.cancel()
            with suppress(asyncio.CancelledError):
                await sampling_task

            # Znajdź szczytowe VRAM
            peak_vram = max(vram_samples) if vram_samples else None

            return {
                "latency_ms": (
                    round(time_to_first_token, 2)
                    if time_to_first_token is not None
                    else None
                ),
                "time_to_first_token_ms": (
                    round(time_to_first_token, 2)
                    if time_to_first_token is not None
                    else None
                ),
                "duration_ms": round(duration_ms, 2),
                "peak_vram_mb": peak_vram,
                "tokens_generated": tokens_generated,
            }

        except Exception:
            # Zatrzymaj próbkowanie w przypadku błędu
            sampling_task.cancel()
            with suppress(asyncio.CancelledError):
                await sampling_task
            raise

    async def _sample_vram_during_generation(self, samples: List[float]):
        """
        Próbkuje zużycie VRAM co 100ms podczas generowania.

        Args:
            samples: Lista do zapisywania próbek VRAM (w MB)
        """
        while True:
            vram = self.service_monitor.get_gpu_memory_usage()
            if vram is not None:
                samples.append(vram)
            await asyncio.sleep(0.1)  # 100ms
