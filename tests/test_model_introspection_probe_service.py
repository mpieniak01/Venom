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


def test_probe_runtime_config_normalizes_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VENOM_INTROSPECTION_PROBE_PROFILE", "unknown-profile")
    monkeypatch.setenv("VENOM_INTROSPECTION_PROBE_TIMEOUT_SECONDS", "bad")
    monkeypatch.setenv("VENOM_INTROSPECTION_PROBE_MAX_ATTEMPTS", "bad")
    monkeypatch.setenv("VENOM_INTROSPECTION_PROBE_MAX_TOP_K", "-5")
    monkeypatch.setenv("VENOM_INTROSPECTION_PROBE_MAX_LAYER_COUNT", "0")
    monkeypatch.setenv("VENOM_INTROSPECTION_PROBE_MAX_PROMPT_TOKENS", "-1")
    monkeypatch.setenv("GEMMA4_AUDIO_PROBE_ENABLED", "weird")

    cfg = probe_service.get_probe_runtime_config()
    assert cfg["profile"] == "dev"
    assert cfg["enabled"] is False
    assert cfg["max_top_k"] == 1
    assert cfg["max_layer_count"] == 1
    assert cfg["max_prompt_tokens"] == 1


@pytest.mark.asyncio
async def test_probe_service_maps_unknown_runtime_status_to_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("multi_runtime", "http://localhost:8014/v1"),
    )

    async def _returns_error_status(**_kwargs):
        return httpx.Response(status_code=200, json={"status": "error", "probe": None})

    monkeypatch.setattr(probe_service, "_post_probe_request", _returns_error_status)
    result = await probe_service.run_model_introspection_probe(
        prompt="q",
        mode="hidden",
        layer_selection=[1],
        top_k=1,
    )
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_probe_service_handles_422_and_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("multi_runtime", "http://localhost:8014/v1"),
    )

    async def _raise_422(**_kwargs):
        return httpx.Response(status_code=422, json={"detail": "invalid"})

    monkeypatch.setattr(probe_service, "_post_probe_request", _raise_422)
    with pytest.raises(ValueError):
        await probe_service.run_model_introspection_probe(
            prompt="q",
            mode="hidden",
            layer_selection=[1],
            top_k=1,
        )

    async def _raise_500(**_kwargs):
        return httpx.Response(status_code=500, json={"detail": "boom"})

    monkeypatch.setattr(probe_service, "_post_probe_request", _raise_500)
    result = await probe_service.run_model_introspection_probe(
        prompt="q",
        mode="hidden",
        layer_selection=[1],
        top_k=1,
    )
    assert result["status"] == "probe_unavailable"
    assert result["code"] == "runtime_error"


@pytest.mark.asyncio
async def test_probe_service_timeout_and_transport_retry_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("multi_runtime", "http://localhost:8014/v1"),
    )
    monkeypatch.setenv("VENOM_INTROSPECTION_PROBE_MAX_ATTEMPTS", "2")
    calls = {"count": 0}

    async def _timeout_then_ok(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.TimeoutException("timeout")
        return httpx.Response(status_code=200, json={"status": "ok", "probe": {}})

    monkeypatch.setattr(probe_service, "_post_probe_request", _timeout_then_ok)
    result = await probe_service.run_model_introspection_probe(
        prompt="q",
        mode="hidden",
        layer_selection=[1],
        top_k=1,
    )
    assert result["status"] == "ok"
    assert calls["count"] == 2

    async def _transport_error(**_kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(probe_service, "_post_probe_request", _transport_error)
    result = await probe_service.run_model_introspection_probe(
        prompt="q",
        mode="hidden",
        layer_selection=[1],
        top_k=1,
    )
    assert result["status"] == "probe_unavailable"
    assert result["code"] == "probe_transport_error"


@pytest.mark.asyncio
async def test_probe_service_retries_transient_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        probe_service,
        "get_active_llm_runtime",
        lambda: _runtime("multi_runtime", "http://localhost:8014/v1"),
    )
    monkeypatch.setenv("VENOM_INTROSPECTION_PROBE_MAX_ATTEMPTS", "2")
    calls = {"count": 0}

    async def _service_unavailable_then_ok(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(status_code=503, json={"detail": "busy"})
        return httpx.Response(status_code=200, json={"status": "ok", "probe": {}})

    monkeypatch.setattr(
        probe_service,
        "_post_probe_request",
        _service_unavailable_then_ok,
    )

    result = await probe_service.run_model_introspection_probe(
        prompt="q",
        mode="hidden",
        layer_selection=[1],
        top_k=1,
    )
    assert result["status"] == "ok"
    assert calls["count"] == 2
