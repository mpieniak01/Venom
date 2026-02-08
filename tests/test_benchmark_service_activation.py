import asyncio
import types
from unittest.mock import AsyncMock, patch

import pytest

from venom_core.services.benchmark import BenchmarkService


class DummyController:
    def __init__(self):
        self.calls = []

    async def run_action(self, runtime: str, action: str):
        await asyncio.sleep(0)
        self.calls.append((runtime, action))
        return types.SimpleNamespace(
            ok=True, action=action, stdout="", stderr="", exit_code=0
        )


@pytest.mark.asyncio
async def test_benchmark_restarts_runtime_on_activate(monkeypatch):
    registry_calls = {}

    class DummyRegistry:
        manifest = {}

        async def activate_model(self, model_name, runtime):
            await asyncio.sleep(0)
            registry_calls["called"] = (model_name, runtime)
            return True

    controller = DummyController()

    service = BenchmarkService(
        model_registry=DummyRegistry(),
        service_monitor=None,
        llm_controller=controller,
        questions_path="./data/datasets/eval_questions.json",
    )

    # stub downstream calls and time
    fake_time = {"t": 100.0}

    def fake_now():
        return fake_time["t"]

    async def fake_health(endpoint: str, timeout: int = 60):
        await asyncio.sleep(0)
        fake_time["t"] += 0.5  # healthcheck trwa 0.5s
        return

    async def fake_query(question: str, model_name: str, endpoint: str):
        await asyncio.sleep(0)
        fake_time["t"] += 0.2  # generowanie 0.2s
        return {
            "latency_ms": 10,
            "time_to_first_token_ms": 10,
            "duration_ms": 20,
            "peak_vram_mb": 100,
            "tokens_generated": 5,
        }

    monkeypatch.setattr("time.time", fake_now)
    monkeypatch.setattr(service, "_wait_for_healthcheck", fake_health)
    monkeypatch.setattr(service, "_query_model_with_metrics", fake_query)

    result = types.SimpleNamespace(
        started_at=None,
        status=None,
        error_message=None,
        questions_tested=0,
        completed_at=None,
        latency_ms=None,
        time_to_first_token_ms=None,
        total_duration_ms=None,
        peak_vram_mb=None,
        tokens_per_second=None,
        startup_latency_ms=None,
    )
    questions = [types.SimpleNamespace(id="q1", question="hi", category="general")]

    # Mock httpx to simulate connection refused (model not running)
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Connection refused")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        await service._test_model("gemma-3-4b-it", questions, result)

    assert registry_calls.get("called") == ("gemma-3-4b-it", "vllm")
    assert ("vllm", "restart") in controller.calls
    # startup_latency_ms powinna uwzględniać healthcheck (0.5s)
    assert result.startup_latency_ms == pytest.approx(500.0, rel=0.01)
