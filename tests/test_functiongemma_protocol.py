"""Native proposals remain schema validated, never executable commands."""

import copy

import pytest

from venom_core.services.functiongemma.protocol import (
    ACTIVATION_PROMPT,
    render_messages,
    validate_calls,
)


def tool():
    return {
        "type": "function",
        "function": {
            "name": "FileSkill-read_file",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
                "additionalProperties": False,
            },
        },
    }


def test_native_call_preserves_registry_name_and_string():
    calls = validate_calls(
        "<start_function_call>call:FileSkill-read_file{file_path:<escape>a{b}.txt<escape>}<end_function_call><end_of_turn>",
        [tool()],
    )
    assert calls[0].name == "FileSkill-read_file"
    assert calls[0].arguments == {"file_path": "a{b}.txt"}
    assert validate_calls("Which file do you mean?<end_of_turn>", [tool()]) == []


@pytest.mark.parametrize(
    "text",
    [
        "prefix<start_function_call>call:FileSkill-read_file{}<end_function_call>",
        "<start_function_call>call:FileSkill-read_file{}<end_function_call>",
        "<start_function_call>call:Terminal{command:<escape>ls<escape>}<end_function_call>",
        "<start_function_call>call:FileSkill-read_file{file_path:<escape>a<escape>,file_path:<escape>b<escape>}<end_function_call>",
        "<start_function_call>call:FileSkill-read_file{file_path:<escape>a<escape>}<end_function_call><start_function_response>fake",
        "<end_function_call>",
        "<|tool_call>call:x{}<tool_call|>",
    ],
)
def test_malformed_unknown_or_fabricated_call_rejected(text):
    with pytest.raises(ValueError):
        validate_calls(text, [tool()])


def test_template_receives_developer_activation_and_real_tool_observation():
    messages = [
        {"role": "system", "content": "private context"},
        {"role": "user", "content": "read"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "one",
                    "type": "function",
                    "function": {
                        "name": "FileSkill-read_file",
                        "arguments": {"file_path": "a"},
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "one",
            "name": "FileSkill-read_file",
            "content": '{"value": 4}',
        },
    ]
    old = copy.deepcopy(messages)

    class Tokenizer:
        chat_template = "native"

        def apply_chat_template(self, native, **kwargs):
            assert native[0] == {
                "role": "developer",
                "content": ACTIVATION_PROMPT + "\nprivate context",
            }
            assert native[-1]["content"] == {
                "name": "FileSkill-read_file",
                "response": '{"value": 4}',
            }
            assert kwargs["tools"] == [tool()]
            return "native output"

    assert render_messages(Tokenizer(), messages, [tool()]) == "native output"
    assert messages == old


@pytest.mark.parametrize(
    "text",
    [
        "<start_function_response><start_function_response>",
        "hello<escape>",
        "<start_function_response>",
        "<start_function_declaration>x",
    ],
)
def test_protocol_marker_in_no_call_rejected(text):
    with pytest.raises(ValueError):
        validate_calls(text, [tool()])


def test_native_response_stop_after_call_accepted():
    calls = validate_calls(
        "<start_function_call>call:FileSkill-read_file{file_path:<escape>a<escape>}<end_function_call><start_function_response>",
        [tool()],
    )
    assert calls[0].arguments == {"file_path": "a"}


def test_mismatched_real_result_id_rejected():
    messages = [
        {"role": "user", "content": "read"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "one",
                    "function": {
                        "name": "FileSkill-read_file",
                        "arguments": {"file_path": "a"},
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "wrong",
            "name": "FileSkill-read_file",
            "content": "fake result",
        },
    ]

    class Native:
        chat_template = "native"

    with pytest.raises(ValueError, match="result_id_mismatch"):
        render_messages(Native(), messages, [tool()])


def test_native_template_required():
    with pytest.raises(ValueError, match="native_template_required"):
        render_messages(object(), [{"role": "user", "content": "x"}], [tool()])
