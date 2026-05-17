"""Tests for model introspection probe proxy service."""

from __future__ import annotations

import httpx
import pytest

from venom_core.services import model_introspection_probe_service as probe_service
from venom_core.utils.llm_runtime import LLMRuntimeInfo


def _runtime(provider: str, endpoint: str | None) -> LLMRuntimeInfo:
    return LLMRuntimeInfo(
        provider=provider,
        model_name="google/gemma-4-E2B-it",
        endpoint=endpoint,
        service_type="local",
        mode="LOCAL",
    )


@pytest.fixture(autouse=True)
def _enable_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMMA4_AUDIO_PROBE_ENABLED", "true")
    monkeypatch.delenv("VENOM_INTROSPECTION_PROBE_PROFILE", raising=False)


@pytest.mark.asyncio
async def test_probe_service_returns_unavailable_for_non_multi_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("ollama", "http://localhost:11434/v1"),
    )

    result = await probe_service.run_model_introspection_probe(
        prompt="Co to jest słońce?",
        mode="hidden",
        layer_selection=[1],
        top_k=8,
    )

    assert result["status"] == "probe_unavailable"
    assert result["code"] == "runtime_not_supported"


@pytest.mark.asyncio
async def test_probe_service_validates_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("multi_runtime", "http://localhost:8014/v1"),
    )

    with pytest.raises(ValueError):
        await probe_service.run_model_introspection_probe(
            prompt="Co to jest słońce?",
            mode="hidden",
            layer_selection=[1],
            top_k=999,
        )


@pytest.mark.asyncio
async def test_probe_service_validates_layer_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("multi_runtime", "http://localhost:8014/v1"),
    )

    with pytest.raises(ValueError):
        await probe_service.run_model_introspection_probe(
            prompt="Co to jest słońce?",
            mode="hidden",
            layer_selection=list(range(32)),
            top_k=8,
        )


@pytest.mark.asyncio
async def test_probe_service_returns_ok_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("multi_runtime", "http://localhost:8014/v1"),
    )

    async def _fake_post_probe_request(**_kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "status": "ok",
                "probe": {"mode": "hidden", "layers": [{"layer": 1}]},
                "diagnostics": {"limits_hit": []},
            },
        )

    monkeypatch.setattr(probe_service, "_post_probe_request", _fake_post_probe_request)

    result = await probe_service.run_model_introspection_probe(
        prompt="Co to jest słońce?",
        mode="hidden",
        layer_selection=[1, 1, 4],
        top_k=8,
    )

    assert result["status"] == "ok"
    assert result["probe"]["mode"] == "hidden"
    assert "elapsed_ms" in result["diagnostics"]


@pytest.mark.asyncio
async def test_probe_service_maps_404_to_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("multi_runtime", "http://localhost:8014/v1"),
    )

    async def _fake_post_probe_request(**_kwargs):
        return httpx.Response(status_code=404, json={"detail": "not found"})

    monkeypatch.setattr(probe_service, "_post_probe_request", _fake_post_probe_request)

    result = await probe_service.run_model_introspection_probe(
        prompt="Co to jest słońce?",
        mode="hidden",
        layer_selection=[1],
        top_k=8,
    )

    assert result["status"] == "probe_unavailable"
    assert result["code"] == "probe_unavailable"


@pytest.mark.asyncio
async def test_probe_service_maps_timeout_to_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("multi_runtime", "http://localhost:8014/v1"),
    )

    async def _fake_post_probe_request(**_kwargs):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(probe_service, "_post_probe_request", _fake_post_probe_request)

    result = await probe_service.run_model_introspection_probe(
        prompt="Co to jest słońce?",
        mode="hidden",
        layer_selection=[1],
        top_k=8,
    )

    assert result["status"] == "probe_unavailable"
    assert result["code"] == "probe_timeout"


def test_probe_health_payload_contains_profile_and_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VENOM_INTROSPECTION_PROBE_PROFILE", "stage")
    payload = probe_service.build_probe_health_payload(
        _runtime("multi_runtime", "http://localhost:8014/v1")
    )
    assert payload["enabled"] is True
    assert payload["runtime_supported"] is True
    assert payload["endpoint_configured"] is True
    assert payload["profile"] == "stage"
    assert payload["healthy"] is True
    assert payload["limits"]["max_top_k"] <= 32
