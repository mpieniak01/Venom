"""Wire contracts are tested independently of model quality and GPU availability."""

import pytest

from venom_core.services.maintenance_comparison.protocol import (
    Call,
    ProtocolError,
    bash_call,
    json_call,
    lfm_calls,
)


def test_bash_action_requires_one_explicit_fence():
    """Verify bash action requires one explicit fence."""
    assert bash_call("Reason\n```bash\ngit status --short\n```") == Call(
        "Terminal", {"command": "git status --short"}
    )
    for text in ["git status", "```bash\n\n```", "```bash\na\n```\n```bash\nb\n```"]:
        with pytest.raises(ProtocolError):
            bash_call(text)


def test_native_call_does_not_supply_missing_arguments():
    """Verify native call does not supply missing arguments."""
    assert json_call({"function": {"name": "finish", "arguments": "{}"}}) == Call(
        "finish", {}
    )
    for response in [
        {"name": "finish"},
        {"name": "read", "arguments": []},
        {"function": None},
        [],
    ]:
        with pytest.raises(ProtocolError):
            json_call(response)


def test_pythonic_calls_accept_only_literal_keyword_arguments():
    """Verify pythonic calls accept only literal keyword arguments."""
    assert lfm_calls(
        "<|tool_call_start|>[read(path='a.py'), finish(status='done')]<|tool_call_end|>"
    ) == [Call("read", {"path": "a.py"}), Call("finish", {"status": "done"})]
    for body in [
        "[read(open('/etc/passwd'))]",
        "[x.read(path='a')]",
        "[read(**{})]",
        "[read(path=__import__('os'))]",
        "[]",
    ]:
        with pytest.raises(ProtocolError):
            lfm_calls("<|tool_call_start|>" + body + "<|tool_call_end|>")


def test_native_envelopes_and_gemma_are_literal_only():
    """Verify native envelopes and gemma are literal only."""
    from venom_core.services.maintenance_comparison.protocol import (
        gemma_calls,
        native_calls,
    )

    assert native_calls('<tool_call>{"name":"Finish","arguments":{}}</tool_call>') == [
        Call("Finish", {})
    ]
    assert gemma_calls(
        "<start_function_call>call:Terminal{command:<escape>git status<escape>}<end_function_call>"
    ) == [Call("Terminal", {"command": "git status"})]
    assert (
        gemma_calls(
            "<start_function_call>call:Finish{status:<escape>success<escape>, summary:<escape>done<escape>, locations:[]}<end_function_call>"
        )[0].arguments["locations"]
        == []
    )
    for text in [
        "<start_function_call>call:F{x:run()}<end_function_call>",
        "<start_function_call>call:F{x:<escape>broken}<end_function_call>",
        "<start_function_call>call:F{x:1,x:2}<end_function_call>",
        "<start_function_call>call:F{x:1}junk<end_function_call>",
    ]:
        with pytest.raises(ProtocolError):
            gemma_calls(text)
    for text in ["prose only", "<tool_call>{}</tool_call>", "<tool_call>{}"]:
        with pytest.raises(ProtocolError):
            native_calls(text)


def test_granite_uses_its_pinned_xml_protocol_not_json_guessing():
    """Verify granite uses its pinned xml protocol not json guessing."""
    from venom_core.services.maintenance_comparison.protocol import granite_calls

    text = "<tool_call>\n<function=Terminal>\n<parameter=command>\npython -m pytest -q test_visible.py\n</parameter>\n</function>\n</tool_call>"
    assert granite_calls(text) == [
        Call("Terminal", {"command": "python -m pytest -q test_visible.py"})
    ]
    with pytest.raises(ProtocolError):
        granite_calls('<tool_call>{"name":"Terminal"}</tool_call>')
    with pytest.raises(ProtocolError):
        granite_calls(
            "<tool_call><function=F><parameter=x>value</function></tool_call>"
        )


def test_gemma_preserves_multiple_explicit_calls():
    """Verify gemma preserves multiple explicit calls."""
    from venom_core.services.maintenance_comparison.protocol import gemma_calls

    calls = gemma_calls(
        "<start_function_call>call:Terminal{command:<escape>printf ok<escape>}<end_function_call><start_function_call>call:Finish{status:<escape>success<escape>,summary:<escape>ok<escape>}<end_function_call><start_function_response>"
    )
    assert [call.name for call in calls] == ["Terminal", "Finish"]


def test_duplicate_json_arguments_are_rejected():
    """Verify duplicate json arguments are rejected."""
    from venom_core.services.maintenance_comparison.protocol import (
        ProtocolError,
        native_calls,
    )

    with pytest.raises(ProtocolError, match="duplicate_json"):
        native_calls(
            '{"name":"Terminal","arguments":{"command":"safe","command":"other"}}'
        )


@pytest.mark.parametrize("key", ["command", '<|"|>command<|"|>', '"command"'])
def test_gemma4_native_function_values_and_tool_handoff(key):
    """Verify gemma4 native function values and tool handoff."""
    from venom_core.services.maintenance_comparison.runner import decode

    text = (
        "<|tool_call>call:Terminal{"
        + key
        + ':<|"|>printf "quoted"\nline<|"|>}<tool_call|><|tool_response>'
    )
    calls = decode("gemma4_tool", text)
    assert calls[0].name == "Terminal"
    assert calls[0].arguments == {"command": 'printf "quoted"\nline'}


def test_gemma4_native_nested_localization_submission():
    """Verify gemma4 native nested localization submission."""
    from venom_core.services.maintenance_comparison.runner import decode

    text = '<|tool_call>call:LocalizationFinish{status:<|"|>success<|"|>,summary:<|"|>Found<|"|>,locations:[{path:<|"|>app.py<|"|>,symbol:<|"|>run<|"|>,evidence:<|"|>def run():<|"|>}]}<tool_call|>'
    call = decode("gemma4_tool", text)[0]
    assert call.arguments["locations"] == [
        {"path": "app.py", "symbol": "run", "evidence": "def run():"}
    ]


@pytest.mark.parametrize(
    "text",
    [
        '<|tool_call>call:Terminal{command:<|"|>missing close}<tool_call|>',
        '<|tool_call>call:Terminal{command:<|"|>one<|"|>,command:<|"|>two<|"|>}<tool_call|>',
        "<|tool_call>call:Terminal{command:run_dangerous()}<tool_call|>",
    ],
)
def test_gemma4_rejects_missing_delimiters_duplicate_arguments_and_expressions(text):
    """Verify gemma4 rejects missing delimiters duplicate arguments and expressions."""
    from venom_core.services.maintenance_comparison.runner import decode

    with pytest.raises(ProtocolError):
        decode("gemma4_tool", text)


def test_qwen35_preserves_native_xml_command_quotes():
    """Verify qwen35 preserves native xml command quotes."""
    from venom_core.services.maintenance_comparison.runner import decode

    text = '<tool_call><function=Terminal><parameter=command>grep -n "def run" app.py</parameter></function></tool_call>'
    assert decode("qwen35_xml", text)[0].arguments == {
        "command": 'grep -n "def run" app.py'
    }
