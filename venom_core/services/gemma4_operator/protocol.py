"""Native Gemma tool-call parsing and template delegation; never executes tools."""

from __future__ import annotations

import hashlib
import importlib
import math
import re
from dataclasses import dataclass
from typing import Any

from venom_core.services.gemma4_operator.profile import GemmaProfile

CALL_START = "<|tool_call>"
CALL_END = "<tool_call|>"
STRING = '<|"|>'
STOP_SEQUENCES = ("<|tool_response>", "<turn|>", "<eos>")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
MAX_RESPONSE_CHARS = 262144
MAX_DEPTH = 16


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


def _jsonschema() -> Any:
    try:
        return importlib.import_module("jsonschema")
    except ImportError as exc:
        raise RuntimeError(
            "gemma_schema_dependency_missing: install requirements-gemma4-operator-control.txt"
        ) from exc


def _check_references(value: Any, depth: int = 0) -> None:
    """Permit local schema references only; validation must never fetch a URL."""
    if depth > 32:
        raise ValueError("gemma_tool_schema_depth_exceeded")
    if isinstance(value, dict):
        for keyword in ("$ref", "$dynamicRef", "$recursiveRef"):
            ref = value.get(keyword)
            if ref is not None and (
                not isinstance(ref, str) or not (ref == "#" or ref.startswith("#/"))
            ):
                raise ValueError("gemma_tool_external_schema_reference")
        for child in value.values():
            _check_references(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_references(child, depth + 1)


def validate_tools(tools: list[dict[str, Any]]) -> dict[str, Any]:
    schema_library = _jsonschema()
    if not isinstance(tools, list) or len(tools) > 256:
        raise ValueError("gemma_tools_invalid")
    validators = {}
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type", "function") != "function":
            raise ValueError("gemma_tool_invalid")
        function = tool.get("function")
        if not isinstance(function, dict):
            raise ValueError("gemma_tool_invalid")
        name = function.get("name")
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name in validators:
            raise ValueError("gemma_tool_name_invalid")
        parameters = function.get("parameters")
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            raise ValueError("gemma_tool_parameters_invalid")
        _check_references(parameters)
        try:
            validator = schema_library.validators.validator_for(parameters)
            validator.check_schema(parameters)
            validators[name] = validator(parameters)
        except schema_library.exceptions.SchemaError as exc:
            raise ValueError("gemma_tool_schema_invalid:" + name) from exc
    return validators


class _Reader:
    """Bounded recursive descent for the documented Gemma data block grammar."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def whitespace(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def take(self, token: str) -> bool:
        self.whitespace()
        if self.text.startswith(token, self.pos):
            self.pos += len(token)
            return True
        return False

    def require(self, token: str) -> None:
        if not self.take(token):
            raise ValueError("gemma_call_syntax_invalid")

    def identifier(self) -> str:
        self.whitespace()
        match = _NAME.match(self.text, self.pos)
        if match is None:
            raise ValueError("gemma_call_identifier_invalid")
        self.pos = match.end()
        return match[0]

    def value(self, depth: int = 0) -> Any:
        if depth > MAX_DEPTH:
            raise ValueError("gemma_call_depth_exceeded")
        self.whitespace()
        if self.take(STRING):
            end = self.text.find(STRING, self.pos)
            if end < 0:
                raise ValueError("gemma_call_string_unterminated")
            result = self.text[self.pos : end]
            self.pos = end + len(STRING)
            return result
        if self.text.startswith("{", self.pos):
            return self.mapping(depth + 1)
        if self.take("["):
            return self.sequence(depth)
        return self.scalar()

    def sequence(self, depth: int) -> list[Any]:
        items: list[Any] = []
        if self.take("]"):
            return items
        while True:
            items.append(self.value(depth + 1))
            if self.take("]"):
                return items
            self.require(",")

    def scalar(self) -> Any:
        for literal, result in (("true", True), ("false", False), ("null", None)):
            if self.take(literal):
                return result
        number = _NUMBER.match(self.text, self.pos)
        if number:
            self.pos = number.end()
            token = number[0]
            parsed = float(token) if any(c in token for c in ".eE") else int(token)
            if isinstance(parsed, float) and not math.isfinite(parsed):
                raise ValueError("gemma_call_number_nonfinite")
            return parsed
        raise ValueError("gemma_call_value_invalid")

    def mapping(self, depth: int) -> dict[str, Any]:
        self.require("{")
        values: dict[str, Any] = {}
        if self.take("}"):
            return values
        while True:
            self.whitespace()
            key = (
                self.value(depth)
                if self.text.startswith(STRING, self.pos)
                else self.identifier()
            )
            if not isinstance(key, str) or key in values:
                raise ValueError("gemma_call_duplicate_key")
            self.require(":")
            values[key] = self.value(depth)
            if self.take("}"):
                return values
            self.require(",")


def _without_thought(text: str) -> str:
    """A thinking prefix is context, never an executable call."""
    text = text.strip()
    if text.startswith("<|turn>model"):
        text = text.removeprefix("<|turn>model").lstrip()
    if text.startswith("<|channel>thought"):
        end = text.find("<channel|>")
        if end < 0:
            raise ValueError("gemma_thought_unterminated")
        text = text[end + len("<channel|>") :].strip()
    return text


def _validate_arguments(validator: Any, arguments: Any, name: str) -> None:
    from referencing.exceptions import Unresolvable

    try:
        validator.validate(arguments)
    except _jsonschema().exceptions.ValidationError as exc:
        raise ValueError("gemma_call_arguments_invalid:" + name) from exc
    except (Unresolvable, RecursionError) as exc:
        raise ValueError("gemma_tool_schema_reference_invalid:" + name) from exc


def parse_response(text: str, tools: list[dict[str, Any]]) -> list[ToolCall]:
    """Parse complete generated text; tools remain proposals, not authorization."""
    if not isinstance(text, str) or len(text) > MAX_RESPONSE_CHARS:
        raise ValueError("gemma_response_budget_exceeded")
    validators = validate_tools(tools)
    reader = _Reader(_without_thought(text))
    if not reader.text.startswith(CALL_START):
        if any(
            token in reader.text for token in (CALL_START, CALL_END, "<|tool_response>")
        ):
            raise ValueError("gemma_response_mixed_content")
        return []
    calls: list[ToolCall] = []
    while reader.take(CALL_START):
        if len(calls) >= 16:
            raise ValueError("gemma_call_count_exceeded")
        reader.require("call:")
        name = reader.identifier()
        arguments = reader.mapping(0)
        reader.require(CALL_END)
        if name not in validators:
            raise ValueError("gemma_call_unknown_tool:" + name)
        _validate_arguments(validators[name], arguments, name)
        calls.append(ToolCall(name, arguments))
    # A worker stops at the response marker; accepting content after it could
    # accidentally trust a model-fabricated tool result.
    for stop in STOP_SEQUENCES:
        if reader.take(stop):
            break
    reader.whitespace()
    if reader.pos != len(reader.text):
        raise ValueError("gemma_response_trailing_content")
    return calls


def render_messages(
    renderer: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    profile: GemmaProfile,
    *,
    add_generation_prompt: bool = True,
) -> str:
    """Render prevalidated canonical text history with native template semantics.

    Full dataset qualification belongs to material preparation; this boundary also
    rejects calls attached to user messages and unmatched tool observations.
    """
    profile.validate()
    validators = validate_tools(tools)
    template = getattr(renderer, "chat_template", None)
    if (
        not isinstance(template, str)
        or hashlib.sha256(template.encode()).hexdigest()
        != profile.files["chat_template.jinja"]
    ):
        raise ValueError("gemma_renderer_template_mismatch")
    if not isinstance(messages, list) or not messages:
        raise ValueError("gemma_messages_invalid")
    _validate_history(messages, validators)
    rendered = renderer.apply_chat_template(
        messages,
        tools=tools,
        tokenize=False,
        add_generation_prompt=add_generation_prompt,
        enable_thinking=profile.enable_thinking,
        preserve_thinking=True,
    )
    if not isinstance(rendered, str):
        raise ValueError("gemma_renderer_text_required")
    return rendered


def _history_calls(message: dict[str, Any], validators: dict[str, Any]) -> list[str]:
    names = []
    calls = message.get("tool_calls", [])
    if not isinstance(calls, list):
        raise ValueError("gemma_history_calls_invalid")
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            raise ValueError("gemma_history_call_invalid")
        name, arguments = function.get("name"), function.get("arguments")
        if (
            not isinstance(name, str)
            or name not in validators
            or not isinstance(arguments, dict)
        ):
            raise ValueError("gemma_history_call_invalid")
        _validate_arguments(validators[name], arguments, name)
        names.append(name)
    return names


def _history_role(message: Any, index: int) -> str:
    if not isinstance(message, dict):
        raise ValueError("gemma_history_message_invalid")
    role = message.get("role")
    if not isinstance(role, str) or role not in {
        "system",
        "developer",
        "user",
        "assistant",
        "tool",
    }:
        raise ValueError("gemma_history_role_invalid")
    if role in {"system", "developer"} and index != 0:
        raise ValueError("gemma_history_system_position_invalid")
    if role != "assistant" and (
        message.get("tool_calls") or message.get("tool_responses")
    ):
        raise ValueError("gemma_history_nonassistant_call")
    return role


def _consume_result(name: Any, pending: list[str]) -> None:
    if name not in pending:
        raise ValueError("gemma_history_unmatched_tool_result")
    pending.remove(name)


def _inline_results(message: dict[str, Any], pending: list[str]) -> None:
    responses = message.get("tool_responses", [])
    if not isinstance(responses, list):
        raise ValueError("gemma_history_results_invalid")
    for response in responses:
        name = response.get("name") if isinstance(response, dict) else None
        _consume_result(name, pending)


def _validate_history(
    messages: list[dict[str, Any]], validators: dict[str, Any]
) -> None:
    pending: list[str] = []
    for index, message in enumerate(messages):
        role = _history_role(message, index)
        if role == "tool":
            _consume_result(message.get("name"), pending)
        else:
            if pending:
                raise ValueError("gemma_history_missing_tool_result")
            pending = _history_calls(message, validators) if role == "assistant" else []
            _inline_results(message, pending)
