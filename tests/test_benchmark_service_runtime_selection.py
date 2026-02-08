import asyncio
import types

import pytest

from tests.helpers.url_fixtures import OLLAMA_LOCAL_V1, VLLM_LOCAL_V1
from venom_core.config import SETTINGS
from venom_core.services.benchmark import (
    BenchmarkQuestion,
    BenchmarkService,
    ModelBenchmarkResult,
)


class DummyRegistry:
    def __init__(self, manifest):
        self.manifest = manifest


class DummyServiceMonitor:
    pass


@pytest.mark.asyncio
async def test_benchmark_uses_vllm_endpoint(monkeypatch):
    # Ustaw niestandardowe endpointy, żeby łatwo asertywać
    monkeypatch.setattr(SETTINGS, "VLLM_ENDPOINT", VLLM_LOCAL_V1)
    monkeypatch.setattr(SETTINGS, "LLM_LOCAL_ENDPOINT", OLLAMA_LOCAL_V1)

    registry = DummyRegistry(
        manifest={"gemma-3-4b-it": types.SimpleNamespace(runtime="vllm", provider=None)}
    )
    service = BenchmarkService(
        model_registry=registry,
        service_monitor=DummyServiceMonitor(),
        llm_controller=None,
        questions_path="./data/datasets/eval_questions.json",
    )

    called = {}

    async def fake_health(endpoint: str, timeout: int = 60):
        await asyncio.sleep(0)
        called["health"] = endpoint

    async def fake_query(question: str, model_name: str, endpoint: str):
        await asyncio.sleep(0)
        called["query"] = (model_name, endpoint)
        return {
            "latency_ms": 10,
            "time_to_first_token_ms": 10,
            "duration_ms": 20,
            "peak_vram_mb": 100,
            "tokens_generated": 5,
        }

    monkeypatch.setattr(service, "_wait_for_healthcheck", fake_health)
    monkeypatch.setattr(service, "_query_model_with_metrics", fake_query)

    result = ModelBenchmarkResult(model_name="gemma-3-4b-it")
    questions = [BenchmarkQuestion(id="q1", question="hi", category="general")]

    await service._test_model("gemma-3-4b-it", questions, result)

    assert called["health"] == VLLM_LOCAL_V1
    assert called["query"] == ("gemma-3-4b-it", VLLM_LOCAL_V1)
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_benchmark_uses_ollama_endpoint(monkeypatch):
    monkeypatch.setattr(SETTINGS, "VLLM_ENDPOINT", VLLM_LOCAL_V1)
    monkeypatch.setattr(SETTINGS, "LLM_LOCAL_ENDPOINT", OLLAMA_LOCAL_V1)

    # model with ":" powinien iść na ollama endpoint
    registry = DummyRegistry(
        manifest={"gemma3:4b": types.SimpleNamespace(runtime="ollama", provider=None)}
    )
    service = BenchmarkService(
        model_registry=registry,
        service_monitor=DummyServiceMonitor(),
        llm_controller=None,
        questions_path="./data/datasets/eval_questions.json",
    )

    called = {}

    async def fake_health(endpoint: str, timeout: int = 60):
        await asyncio.sleep(0)
        called["health"] = endpoint

    async def fake_query(question: str, model_name: str, endpoint: str):
        await asyncio.sleep(0)
        called["query"] = (model_name, endpoint)
        return {
            "latency_ms": 10,
            "time_to_first_token_ms": 10,
            "duration_ms": 20,
            "peak_vram_mb": 100,
            "tokens_generated": 5,
        }

    monkeypatch.setattr(service, "_wait_for_healthcheck", fake_health)
    monkeypatch.setattr(service, "_query_model_with_metrics", fake_query)

    result = ModelBenchmarkResult(model_name="gemma3:4b")
    questions = [BenchmarkQuestion(id="q1", question="hi", category="general")]

    await service._test_model("gemma3:4b", questions, result)

    assert called["health"] == OLLAMA_LOCAL_V1
    assert called["query"] == ("gemma3:4b", OLLAMA_LOCAL_V1)
    assert result.status == "completed"
