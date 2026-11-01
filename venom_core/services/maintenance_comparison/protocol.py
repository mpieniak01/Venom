"""Strict wire decoders. Never infer missing arguments or execute model text."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from typing import Any

TOOL_CALL_OPEN = "<tool_call>"
TOOL_CALL_CLOSE = "</tool_call>"
GEMMA_ESCAPE = "<escape>"


class ProtocolError(ValueError):
    """A model response does not conform to the selected protocol."""


@dataclass(frozen=True)
class Call:
    name: str
    arguments: dict[str, Any]


def strict_json(text: str):
    """Parse JSON while rejecting duplicate object keys and nonfinite constants."""

    def unique(pairs):
        """Build an object only when every supplied JSON key is unique."""
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProtocolError("duplicate_json_argument")
            result[key] = value
        return result

    def invalid_constant(_value):
        """Reject nonfinite JSON constants instead of accepting backend-specific numbers."""
        raise ProtocolError("nonfinite_json_value")

    return json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant)


def json_call(value: Any) -> Call:
    """Decode one native function object without inventing argument values."""
    if not isinstance(value, dict):
        raise ProtocolError("call_not_object")
    function = value.get("function", value)
    if not isinstance(function, dict):
        raise ProtocolError("function_not_object")
    name, arguments = function.get("name"), function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = strict_json(arguments)
        except json.JSONDecodeError as exc:
            raise ProtocolError("invalid_arguments_json") from exc
    if not isinstance(name, str) or not name or not isinstance(arguments, dict):
        raise ProtocolError("missing_name_or_arguments")
    return Call(name, arguments)


def bash_call(text: str) -> Call:
    """Accept the two documented mini-swe-agent Bash fence labels only."""
    markers = [
        marker for marker in ["```bash\n", "```mswea_bash_command\n"] if marker in text
    ]
    if len(markers) != 1 or text.count(markers[0]) != 1 or text.count("```") != 2:
        raise ProtocolError("expected_one_bash_block")
    command = text.split(markers[0], 1)[1].split("```", 1)[0].strip()
    if not command:
        raise ProtocolError("empty_bash_action")
    return Call("Terminal", {"command": command})


def lfm_calls(text: str) -> list[Call]:
    """Parse Pythonic literal calls via AST; eval/exec are never used."""
    start, end = "<|tool_call_start|>", "<|tool_call_end|>"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ProtocolError("expected_one_tool_block")
    body = text.split(start, 1)[1].split(end, 1)[0]
    try:
        expression = ast.parse(body, mode="eval").body
        if not isinstance(expression, ast.List) or not expression.elts:
            raise ProtocolError("expected_nonempty_call_list")
        return [_literal_call(item) for item in expression.elts]
    except (SyntaxError, ValueError, TypeError) as exc:
        raise ProtocolError("invalid_pythonic_call") from exc


def _literal_call(node: ast.expr) -> Call:
    """Decode a named call with literal keyword values; reject positional or expanded arguments."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        raise ProtocolError("expected_named_call")
    if node.args or any(item.arg is None for item in node.keywords):
        raise ProtocolError("keyword_arguments_required")
    arguments: dict[str, Any] = {}
    for item in node.keywords:
        if item.arg is None:
            raise ProtocolError("keyword_arguments_required")
        arguments[item.arg] = ast.literal_eval(item.value)
    if len(arguments) != len(node.keywords):
        raise ProtocolError("duplicate_arguments")
    return Call(node.func.id, arguments)


def native_calls(text: str) -> list[Call]:
    """Only documented explicit envelopes or a complete JSON value are accepted."""
    if TOOL_CALL_OPEN in text:
        parts = text.split(TOOL_CALL_OPEN)[1:]
        if any(part.count(TOOL_CALL_CLOSE) != 1 for part in parts):
            raise ProtocolError("invalid_tool_envelope")
        try:
            return [
                json_call(strict_json(part.split(TOOL_CALL_CLOSE, 1)[0]))
                for part in parts
            ]
        except json.JSONDecodeError as exc:
            raise ProtocolError("invalid_call_json") from exc
    try:
        value = strict_json(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("invalid_native_call") from exc
    if value == []:
        raise ProtocolError("empty_native_call_list")
    return (
        [json_call(item) for item in value]
        if isinstance(value, list)
        else [json_call(value)]
    )


class _GemmaLiteral:
    def __init__(self, text: str, string_marker: str = GEMMA_ESCAPE):
        """Initialize the cursor and the protocol-specific escaped-string delimiter."""
        self.text, self.position = text, 0
        self.string_marker = string_marker

    def whitespace(self) -> None:
        """Advance past whitespace without consuming the next literal token."""
        while self.position < len(self.text) and self.text[self.position].isspace():
            self.position += 1

    def consume(self, token: str) -> None:
        """Require the next literal token after optional whitespace or raise ProtocolError."""
        self.whitespace()
        if not self.text.startswith(token, self.position):
            raise ProtocolError("invalid_gemma_literal")
        self.position += len(token)

    def _string(self) -> str:
        """Read a delimited native string and reject a missing closing marker."""
        self.position += len(self.string_marker)
        end = self.text.find(self.string_marker, self.position)
        if end < 0:
            raise ProtocolError("unterminated_gemma_string")
        value = self.text[self.position : end]
        self.position = end + len(self.string_marker)
        return value

    def _primitive(self):
        """Decode the next JSON primitive and advance by the consumed source length."""
        try:
            value, used = json.JSONDecoder().raw_decode(self.text[self.position :])
        except json.JSONDecodeError as exc:
            raise ProtocolError("invalid_gemma_value") from exc
        self.position += used
        return value

    def _pair(self, values: dict, depth: int) -> None:
        """Read one unique object key and recursively parse its literal value."""
        if self.text.startswith(self.string_marker, self.position):
            key = self._string()
        elif self.text.startswith('"', self.position):
            key = self._primitive()
        else:
            start = self.position
            while self.position < len(self.text) and (
                self.text[self.position].isalnum() or self.text[self.position] == "_"
            ):
                self.position += 1
            key = self.text[start : self.position]
        if not isinstance(key, str) or not key or key in values:
            raise ProtocolError("invalid_gemma_key")
        self.consume(":")
        values[key] = self.literal(depth + 1)

    def _collection(self, char: str, depth: int):
        """Parse a list or object while rejecting missing separators and trailing commas."""
        self.position += 1
        closing = "]" if char == "[" else "}"
        values: Any = [] if char == "[" else {}
        self.whitespace()
        while not self.text.startswith(closing, self.position):
            if char == "[":
                values.append(self.literal(depth + 1))
            else:
                self._pair(values, depth)
            self.whitespace()
            if self.text.startswith(closing, self.position):
                break
            self.consume(",")
            self.whitespace()
            if self.text.startswith(closing, self.position):
                raise ProtocolError("trailing_gemma_comma")
        self.consume(closing)
        return values

    def literal(self, depth: int = 0) -> Any:
        """Parse the next native literal, rejecting exhausted input and excessive nesting."""
        self.whitespace()
        if depth > 16 or self.position >= len(self.text):
            raise ProtocolError("invalid_gemma_literal")
        if self.text.startswith(self.string_marker, self.position):
            return self._string()
        char = self.text[self.position]
        return self._collection(char, depth) if char in "[{" else self._primitive()


def _gemma_call(body: str, string_marker: str = GEMMA_ESCAPE) -> Call:
    """Parse an explicit function name and complete literal argument object."""
    name, separator, rest = body.partition("{")
    if not separator or not name.isidentifier():
        raise ProtocolError("invalid_gemma_function")
    parser = _GemmaLiteral("{" + rest, string_marker)
    arguments = parser.literal()
    parser.whitespace()
    if parser.position != len(parser.text):
        raise ProtocolError("trailing_gemma_arguments")
    return Call(name, arguments)


def gemma_calls(text: str) -> list[Call]:
    """Decode FunctionGemma envelopes with matching start and end markers."""
    start, end = "<start_function_call>call:", "<end_function_call>"
    parts = text.split(start)[1:]
    if not parts or text.count(end) != len(parts):
        raise ProtocolError("invalid_gemma_call_envelopes")
    return [_gemma_call(part.split(end, 1)[0]) for part in parts]


def gemma4_calls(text: str) -> list[Call]:
    """Pinned Gemma 4 tool markers; literal values remain unchanged."""
    start, end = "<|tool_call>call:", "<tool_call|>"
    parts = text.split(start)[1:]
    if not parts or text.count(end) != len(parts):
        raise ProtocolError("invalid_gemma4_call_envelopes")
    return [_gemma_call(part.split(end, 1)[0], '<|"|>') for part in parts]


def _granite_arguments(parameters: str) -> dict:
    """Parse unique XML parameters, decoding only locations as strict JSON."""
    arguments = {}
    while parameters:
        if not parameters.startswith("<parameter="):
            raise ProtocolError("invalid_granite_parameter")
        key, separator, tail = parameters[len("<parameter=") :].partition(">")
        value, closing, parameters = tail.partition("</parameter>")
        if not separator or not closing or not key.isidentifier() or key in arguments:
            raise ProtocolError("invalid_granite_argument")
        value = value.strip("\n")
        try:
            arguments[key] = strict_json(value) if key == "locations" else value
        except json.JSONDecodeError as exc:
            raise ProtocolError("invalid_granite_locations") from exc
        parameters = parameters.strip()
    return arguments


def granite_calls(text: str) -> list[Call]:
    """Granite 4.2's pinned native function/parameter envelope."""
    parts = text.split(TOOL_CALL_OPEN)[1:]
    if not parts or text.count(TOOL_CALL_CLOSE) != len(parts):
        raise ProtocolError("invalid_granite_envelope")
    result = []
    for part in parts:
        body = part.split(TOOL_CALL_CLOSE, 1)[0].strip()
        if not body.startswith("<function=") or not body.endswith("</function>"):
            raise ProtocolError("invalid_granite_function")
        name, separator, parameters = body[len("<function=") :].partition(">")
        if not separator or not name.isidentifier():
            raise ProtocolError("invalid_granite_name")
        result.append(
            Call(name, _granite_arguments(parameters[: -len("</function>")].strip()))
        )
    return result
