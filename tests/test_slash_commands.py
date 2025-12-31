from venom_core.core.slash_commands import (
    normalize_forced_provider,
    parse_slash_command,
    resolve_forced_intent,
)


def test_parse_provider_command():
    result = parse_slash_command("/gpt Napisz podsumowanie")
    assert result is not None
    assert result.forced_provider == "openai"
    assert result.cleaned == "Napisz podsumowanie"


def test_parse_tool_command():
    result = parse_slash_command("/git status")
    assert result is not None
    assert result.forced_tool == "git"
    assert result.forced_intent == "VERSION_CONTROL"
    assert result.cleaned == "status"


def test_parse_clear_command():
    result = parse_slash_command("/clear")
    assert result is not None
    assert result.session_reset is True
    assert result.cleaned == ""


def test_parse_unknown_command():
    result = parse_slash_command("/unknown foo bar")
    assert result is not None
    assert result.forced_tool is None
    assert result.forced_provider is None
    assert result.cleaned == "foo bar"


def test_normalize_forced_provider():
    assert normalize_forced_provider("gpt") == "openai"
    assert normalize_forced_provider("gem") == "google"
    assert normalize_forced_provider("openai") == "openai"


def test_resolve_forced_intent():
    assert resolve_forced_intent("git") == "VERSION_CONTROL"
    assert resolve_forced_intent("docs") == "DOCUMENTATION"
    assert resolve_forced_intent("unknown") is None
