"""Testy dla modułu benchmark service."""

import asyncio
import json
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core.model_registry import ModelRegistry
from venom_core.core.service_monitor import ServiceHealthMonitor, ServiceRegistry
from venom_core.services.benchmark import BenchmarkService, BenchmarkStatus


@pytest.fixture
def service_monitor():
    """Fixture dla ServiceHealthMonitor."""
    registry = ServiceRegistry()
    return ServiceHealthMonitor(registry)


@pytest.fixture
def model_registry():
    """Fixture dla ModelRegistry."""
    return ModelRegistry()


@pytest.fixture
def benchmark_service(model_registry, service_monitor, tmp_path):
    """Fixture dla BenchmarkService."""
    # Utwórz tymczasowy plik z pytaniami testowymi
    questions_file = tmp_path / "test_questions.json"
    questions_data = {
        "questions": [
            {"id": 1, "question": "Test question 1?", "category": "test"},
            {"id": 2, "question": "Test question 2?", "category": "test"},
            {"id": 3, "question": "Test question 3?", "category": "test"},
        ]
    }
    with open(questions_file, "w", encoding="utf-8") as f:
        json.dump(questions_data, f)

    return BenchmarkService(
        model_registry=model_registry,
        service_monitor=service_monitor,
        questions_path=str(questions_file),
        storage_dir=str(tmp_path / "benchmarks"),
    )


def test_benchmark_service_initialization(benchmark_service):
    """Test inicjalizacji BenchmarkService."""
    assert benchmark_service is not None
    assert benchmark_service.model_registry is not None
    assert benchmark_service.service_monitor is not None
    assert isinstance(benchmark_service.jobs, dict)
    assert len(benchmark_service.jobs) == 0


def test_load_questions(benchmark_service):
    """Test ładowania pytań testowych z pliku."""
    questions = benchmark_service._load_questions()

    assert isinstance(questions, list)
    assert len(questions) == 3
    assert questions[0].question == "Test question 1?"
    assert questions[0].category == "test"


def test_load_questions_file_not_found():
    """Test ładowania pytań gdy plik nie istnieje."""
    service_monitor = ServiceHealthMonitor(ServiceRegistry())
    model_registry = ModelRegistry()
    benchmark_service = BenchmarkService(
        model_registry=model_registry,
        service_monitor=service_monitor,
        questions_path="/nonexistent/path/questions.json",
    )

    with pytest.raises(FileNotFoundError):
        benchmark_service._load_questions()


@pytest.mark.asyncio
async def test_start_benchmark(benchmark_service):
    """Test rozpoczęcia benchmarku."""
    models = ["model1", "model2"]
    num_questions = 2

    # Mock _run_benchmark_task aby nie uruchamiać prawdziwego testu
    with patch.object(benchmark_service, "_run_benchmark_task", new_callable=AsyncMock):
        benchmark_id = await benchmark_service.start_benchmark(
            models=models, num_questions=num_questions
        )

    assert benchmark_id is not None
    assert benchmark_id in benchmark_service.jobs

    job = benchmark_service.jobs[benchmark_id]
    assert job.models == models
    assert job.num_questions == num_questions
    assert job.status == BenchmarkStatus.PENDING
    assert len(job.results) == len(models)


@pytest.mark.asyncio
async def test_start_benchmark_empty_models(benchmark_service):
    """Test rozpoczęcia benchmarku z pustą listą modeli."""
    with pytest.raises(ValueError, match="Lista modeli nie może być pusta"):
        await benchmark_service.start_benchmark(models=[], num_questions=5)


@pytest.mark.asyncio
async def test_start_benchmark_invalid_num_questions(benchmark_service):
    """Test rozpoczęcia benchmarku z nieprawidłową liczbą pytań."""
    with pytest.raises(ValueError, match="Liczba pytań musi być większa niż 0"):
        await benchmark_service.start_benchmark(models=["model1"], num_questions=0)


def test_get_benchmark_status(benchmark_service):
    """Test pobierania statusu benchmarku."""
    # Utwórz testowy job manualnie
    from venom_core.services.benchmark import BenchmarkJob

    benchmark_id = "test-id-123"
    job = BenchmarkJob(benchmark_id=benchmark_id, models=["model1"], num_questions=3)
    benchmark_service.jobs[benchmark_id] = job

    status = benchmark_service.get_benchmark_status(benchmark_id)

    assert status is not None
    assert status["benchmark_id"] == benchmark_id
    assert status["models"] == ["model1"]
    assert status["num_questions"] == 3


def test_get_benchmark_status_not_found(benchmark_service):
    """Test pobierania statusu nieistniejącego benchmarku."""
    status = benchmark_service.get_benchmark_status("nonexistent-id")
    assert status is None


def test_delete_benchmark_rejects_invalid_id(benchmark_service):
    """Nieprawidlowy benchmark_id (path traversal) powinien byc odrzucony."""
    safe_file = benchmark_service.storage_dir / "safe-id.json"
    safe_file.write_text("{}", encoding="utf-8")

    deleted = benchmark_service.delete_benchmark("../../etc/passwd")

    assert deleted is False
    assert safe_file.exists()


def test_list_benchmarks(benchmark_service):
    """Test listowania benchmarków."""
    from venom_core.services.benchmark import BenchmarkJob

    # Dodaj kilka testowych jobów
    for i in range(3):
        job = BenchmarkJob(
            benchmark_id=f"test-id-{i}", models=["model1"], num_questions=3
        )
        benchmark_service.jobs[f"test-id-{i}"] = job

    benchmarks = benchmark_service.list_benchmarks(limit=10)

    assert isinstance(benchmarks, list)
    assert len(benchmarks) == 3


@pytest.mark.asyncio
async def test_wait_for_healthcheck_success(benchmark_service):
    """Test oczekiwania na healthcheck - sukces."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        # Powinno zakończyć się bez błędu
        await benchmark_service._wait_for_healthcheck(
            endpoint="http://localhost:8000", timeout=5
        )


@pytest.mark.asyncio
async def test_wait_for_healthcheck_timeout(benchmark_service):
    """Test oczekiwania na healthcheck - timeout."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        with pytest.raises(TimeoutError, match="healthcheck failed"):
            await benchmark_service._wait_for_healthcheck(
                endpoint="http://localhost:8000", timeout=1
            )


@pytest.mark.asyncio
async def test_query_model_with_metrics(benchmark_service):
    """Test wysyłania pytania do modelu i pomiaru metryk."""
    question = "Test question?"

    # Mock get_gpu_memory_usage
    with patch.object(
        benchmark_service.service_monitor, "get_gpu_memory_usage", return_value=1500.0
    ):
        # Mock httpx client
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200

            # Symuluj streaming response
            async def mock_aiter_lines():
                yield "data: {}"
                yield "data: {}"
                yield "data: {}"

            mock_response.aiter_lines = mock_aiter_lines
            mock_response.raise_for_status = MagicMock()
            mock_response.__aenter__.return_value = mock_response
            mock_response.__aexit__.return_value = None

            mock_client = MagicMock()
            mock_client.stream.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_client_class.return_value = mock_client

            metrics = await benchmark_service._query_model_with_metrics(
                question, model_name="model1", endpoint="http://localhost:8000"
            )

            assert "latency_ms" in metrics
            assert "duration_ms" in metrics
            assert "peak_vram_mb" in metrics
            assert "tokens_generated" in metrics
            assert metrics["latency_ms"] > 0
            assert metrics["duration_ms"] > 0
            assert metrics["tokens_generated"] >= 0


@pytest.mark.asyncio
async def test_sample_vram_during_generation(benchmark_service):
    """Test próbkowania VRAM podczas generowania."""
    samples = []

    # Mock get_gpu_memory_usage
    vram_series = [100.0, 150.0, 200.0]
    with patch.object(
        benchmark_service.service_monitor,
        "get_gpu_memory_usage",
        side_effect=vram_series + [vram_series[-1]] * 5,
    ):
        # Uruchom sampling task na krótki czas
        task = asyncio.create_task(
            benchmark_service._sample_vram_during_generation(samples)
        )

        # Czekaj trochę
        await asyncio.sleep(0.35)  # 3 próbki po 100ms

        # Anuluj task
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    # Sprawdź czy zebrano próbki
    assert len(samples) >= 2  # Powinno być co najmniej kilka próbek


def test_get_gpu_memory_usage(service_monitor):
    """Test metody get_gpu_memory_usage."""
    # Test gdy nvidia-smi nie jest dostępne
    with patch("shutil.which", return_value=None):
        result = service_monitor.get_gpu_memory_usage()
        assert result is None

    # Test gdy nvidia-smi jest dostępne
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "1500.25\n2000.50"
            mock_run.return_value = mock_result

            result = service_monitor.get_gpu_memory_usage()

            assert result is not None
            assert result == pytest.approx(2000.50)  # Największe użycie z dwóch GPU


def test_get_gpu_memory_usage_error_handling(service_monitor):
    """Test obsługi błędów w get_gpu_memory_usage."""
    # Test gdy nvidia-smi zwraca błąd
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result

            result = service_monitor.get_gpu_memory_usage()
            assert result is None

    # Test gdy subprocess rzuca wyjątek
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
        with patch("subprocess.run", side_effect=Exception("Error")):
            result = service_monitor.get_gpu_memory_usage()
            assert result is None
