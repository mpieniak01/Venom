"""Domain helpers for llm_simple payload and stream packet shaping."""

from __future__ import annotations

from typing import Any, Optional


def build_messages(system_prompt: str, user_content: str) -> list[dict[str, str]]:
    messages = [{"role": "user", "content": user_content}]
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})
    return messages


def resolve_output_format(*, request_format: Any, response_format: Any) -> Any:
    output_format = request_format
    if output_format is not None or not isinstance(response_format, dict):
        return output_format

    # Compatibility extraction for OpenAI-style shape:
    # response_format.json_schema.schema -> schema object
    schema_block = response_format.get("json_schema")
    if not isinstance(schema_block, dict):
        return output_format
    return schema_block.get("schema") or schema_block


def apply_output_format_to_payload(
    *,
    payload: dict[str, Any],
    provider: str,
    output_format: Any,
    response_format: Any,
    request_format: Any,
    ollama_structured_outputs_enabled: bool,
) -> None:
    if provider == "ollama":
        if output_format is not None and ollama_structured_outputs_enabled:
            payload["format"] = output_format
            return
        if response_format is not None:
            payload["response_format"] = response_format
        return

    if response_format is not None:
        payload["response_format"] = response_format
    elif request_format is not None:
        payload["format"] = request_format


def ollama_feature_enabled(provider: str, enabled_flag: bool) -> bool:
    return provider != "ollama" or enabled_flag


def apply_optional_features_to_payload(
    *,
    payload: dict[str, Any],
    provider: str,
    tools: Any,
    tool_choice: Any,
    think: Any,
    ollama_enable_tool_calling: bool,
    ollama_enable_think: bool,
) -> None:
    if tools and ollama_feature_enabled(provider, ollama_enable_tool_calling):
        payload["tools"] = tools
    if tool_choice is not None and ollama_feature_enabled(
        provider, ollama_enable_tool_calling
    ):
        payload["tool_choice"] = tool_choice
    if think is not None and ollama_feature_enabled(provider, ollama_enable_think):
        payload["think"] = think


def extract_sse_contents(packet: dict[str, Any]) -> list[str]:
    contents: list[str] = []
    choices = packet.get("choices") or []
    for choice in choices:
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            continue
        content = delta.get("content")
        if content:
            contents.append(content)
    return contents


def extract_sse_tool_calls(packet: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    choices = packet.get("choices") or []
    for choice in choices:
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            continue
        delta_tool_calls = delta.get("tool_calls")
        if isinstance(delta_tool_calls, list):
            tool_calls.extend(
                call for call in delta_tool_calls if isinstance(call, dict)
            )
    return tool_calls


def extract_ollama_telemetry(packet: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in (
        "load_duration",
        "prompt_eval_count",
        "eval_count",
        "prompt_eval_duration",
        "eval_duration",
    ):
        value = packet.get(key)
        if isinstance(value, int):
            out[key] = value
    return out


def normalize_ns_to_ms(value: Optional[int]) -> Optional[float]:
    if value is None:
        return None
    if value <= 0:
        return 0.0
    return round(value / 1_000_000.0, 2)


def build_streaming_headers(request_id: str, session_id: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Request-Id": request_id,
        "X-Session-Id": session_id,
    }


def is_retryable_ollama_status(status_code: Optional[int]) -> bool:
    if status_code is None:
        return False
    return status_code in {429, 500, 502, 503, 504}


def is_retryable_ollama_http_error(
    *, provider: str, status_code: Optional[int], attempt_no: int, max_retries: int
) -> bool:
    if provider != "ollama":
        return False
    if attempt_no >= max_retries:
        return False
    if status_code is None:
        return True
    return is_retryable_ollama_status(status_code)
