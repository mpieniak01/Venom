"""Native FunctionGemma template boundary and schema checked proposals."""

from __future__ import annotations

import copy
from typing import Any

from venom_core.services.gemma4_operator.protocol import (
    ToolCall,
    _validate_history,
    parse_response,
    validate_tools,
)

ACTIVATION_PROMPT = (
    "You are a model that can do function calling with the following functions"
)
CALL_START = "<start_function_call>"
CALL_END = "<end_function_call>"
STOP_SEQUENCES = ("<start_function_response>", "<end_of_turn>", "<eos>")
FILE_TOOLS = frozenset(
    {
        "FileSkill-list_files",
        "FileSkill-file_exists",
        "FileSkill-read_file",
        "FileSkill-write_file",
    }
)


def validate_calls(text: str, tools: list[dict[str, Any]]) -> list[ToolCall]:
    """Decode complete output; calls are proposals and never run here."""
    if not isinstance(text, str) or len(text) > 262144:
        raise ValueError("functiongemma_response_budget_exceeded")
    alien = ("<|tool_call>", "<tool_call|>", '<|"|>', "<|tool_response>", "<turn|>")
    if any(marker in text for marker in alien):
        raise ValueError("functiongemma_foreign_protocol")
    if "<start_function_response>" in text:
        if (
            text.count("<start_function_response>") != 1
            or not text.rstrip().endswith("<start_function_response>")
            or not text.lstrip().startswith(CALL_START)
        ):
            raise ValueError("functiongemma_fabricated_response")
        text = text.rstrip().removesuffix("<start_function_response>")
    if any(
        marker in text
        for marker in (
            "<end_function_response>",
            "<start_function_declaration>",
            "<end_function_declaration>",
        )
    ):
        raise ValueError("functiongemma_unexpected_marker")
    translated = text.replace(CALL_START, "<|tool_call>").replace(
        CALL_END, "<tool_call|>"
    )
    translated = translated.replace("<escape>", '<|"|>').replace(
        "<end_of_turn>", "<turn|>"
    )
    if "<escape>" in text and CALL_START not in text:
        raise ValueError("functiongemma_unexpected_marker")
    return parse_response(translated, tools)


def render_messages(
    tokenizer: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    add_generation_prompt: bool = False,
) -> str:
    """Delegate serialization to a caller-qualified native tokenizer."""
    if not isinstance(getattr(tokenizer, "chat_template", None), str):
        raise ValueError("functiongemma_native_template_required")
    validators = validate_tools(tools)
    if not isinstance(messages, list) or not messages:
        raise ValueError("functiongemma_messages_required")
    _validate_history(messages, validators)
    validate_result_ids(messages)
    native = copy.deepcopy(messages)
    context = ""
    if native[0]["role"] in {"system", "developer"}:
        context = native.pop(0).get("content") or ""
        if not isinstance(context, str):
            raise ValueError("functiongemma_developer_text_required")
    native.insert(
        0,
        {
            "role": "developer",
            "content": ACTIVATION_PROMPT + ("\n" + context if context else ""),
        },
    )
    for message in native:
        if message["role"] == "tool":
            message["content"] = {
                "name": message["name"],
                "response": {"value": message["content"]},
            }
    result = tokenizer.apply_chat_template(
        native,
        tools=copy.deepcopy(tools),
        tokenize=False,
        add_generation_prompt=add_generation_prompt,
    )
    if not isinstance(result, str) or not result:
        raise ValueError("functiongemma_native_text_required")
    return result


def validate_result_ids(messages: list[dict[str, Any]]) -> None:
    """Tie every observation to the original call ID, including parallel calls."""
    pending: dict[str, str] = {}
    seen: set[str] = set()
    for message in messages:
        if message["role"] == "assistant":
            for call in message.get("tool_calls", []):
                ident = call.get("id")
                if not isinstance(ident, str) or not ident or ident in seen:
                    raise ValueError("functiongemma_call_id_invalid")
                seen.add(ident)
                if call["function"]["name"] != "Finish":
                    pending[ident] = call["function"]["name"]
        elif message["role"] == "tool":
            ident = message.get("tool_call_id")
            if ident not in pending or pending.pop(ident) != message.get("name"):
                raise ValueError("functiongemma_tool_result_id_mismatch")
