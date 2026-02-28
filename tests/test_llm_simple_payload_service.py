from __future__ import annotations

from venom_core.services import llm_simple_payload_service as svc


def test_build_messages_and_output_format_resolution():
    assert svc.build_messages("", "hello") == [{"role": "user", "content": "hello"}]
    assert svc.build_messages("sys", "hello") == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]

    assert svc.resolve_output_format(request_format={"a": 1}, response_format=None) == {
        "a": 1
    }
    assert svc.resolve_output_format(
        request_format=None,
        response_format={"json_schema": {"schema": {"type": "object"}}},
    ) == {"type": "object"}


def test_apply_output_format_to_payload_for_providers():
    payload_ollama: dict[str, object] = {}
    svc.apply_output_format_to_payload(
        payload=payload_ollama,
        provider="ollama",
        output_format={"type": "object"},
        response_format={"x": 1},
        request_format=None,
        ollama_structured_outputs_enabled=True,
    )
    assert payload_ollama == {"format": {"type": "object"}}

    payload_openai: dict[str, object] = {}
    svc.apply_output_format_to_payload(
        payload=payload_openai,
        provider="openai",
        output_format=None,
        response_format={"json_schema": {}},
        request_format={"unused": True},
        ollama_structured_outputs_enabled=False,
    )
    assert payload_openai == {"response_format": {"json_schema": {}}}


def test_optional_features_and_ollama_gate():
    assert svc.ollama_feature_enabled("openai", False)
    assert not svc.ollama_feature_enabled("ollama", False)

    payload: dict[str, object] = {}
    svc.apply_optional_features_to_payload(
        payload=payload,
        provider="ollama",
        tools=[{"type": "function"}],
        tool_choice="auto",
        think=True,
        ollama_enable_tool_calling=True,
        ollama_enable_think=False,
    )
    assert payload["tools"] == [{"type": "function"}]
    assert payload["tool_choice"] == "auto"
    assert "think" not in payload


def test_sse_extractors_and_ns_normalization():
    packet = {
        "choices": [
            {"delta": {"content": "A", "tool_calls": [{"id": "1"}, "bad"]}},
            {"delta": None},
            {"delta": {"content": "B"}},
        ],
        "load_duration": 3,
        "eval_count": 4,
        "non_metric": "x",
    }

    assert svc.extract_sse_contents(packet) == ["A", "B"]
    assert svc.extract_sse_tool_calls(packet) == [{"id": "1"}]
    assert svc.extract_ollama_telemetry(packet) == {"load_duration": 3, "eval_count": 4}

    assert svc.normalize_ns_to_ms(None) is None
    assert svc.normalize_ns_to_ms(-1) == 0.0
    assert svc.normalize_ns_to_ms(3_000_000) == 3.0


def test_stream_headers_and_retry_heuristics():
    headers = svc.build_streaming_headers("rid", "sid")
    assert headers["X-Request-Id"] == "rid"
    assert headers["X-Session-Id"] == "sid"
    assert headers["X-Accel-Buffering"] == "no"

    assert svc.is_retryable_ollama_status(503)
    assert not svc.is_retryable_ollama_status(404)

    assert svc.is_retryable_ollama_http_error(
        provider="ollama", status_code=None, attempt_no=1, max_retries=2
    )
    assert not svc.is_retryable_ollama_http_error(
        provider="openai", status_code=503, attempt_no=1, max_retries=2
    )
