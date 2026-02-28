"""Unit tests for TaskDispatcher audit fixes."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.core.dispatcher import TaskDispatcher


@pytest.fixture
def mock_kernel():
    """Fixture to provide a mocked semantic kernel."""
    return MagicMock()


@pytest.mark.asyncio
async def test_parse_with_llm_valid_lowercase(mock_kernel):
    """Test parsing with valid lowercase action."""
    dispatcher = TaskDispatcher(mock_kernel)
    mock_service = AsyncMock()
    mock_kernel.get_service.return_value = mock_service

    # Mock LLM response
    mock_response = MagicMock()
    mock_response.__str__.return_value = '{"action": "edit", "targets": ["file1.py"]}'
    mock_service.get_chat_message_content.return_value = mock_response

    intent = await dispatcher._parse_with_llm("Update file1.py")
    assert intent.action == "edit"
    assert intent.targets == ["file1.py"]


@pytest.mark.asyncio
async def test_parse_with_llm_case_insensitive(mock_kernel):
    """Test that LLM actions are normalized to lowercase (PR Feedback)."""
    dispatcher = TaskDispatcher(mock_kernel)
    mock_service = AsyncMock()
    mock_kernel.get_service.return_value = mock_service

    # Mock LLM response with mixed/upper case
    # Note: For the newline case, we must escape it for valid JSON in the f-string
    test_cases = ["EDIT", "Edit ", "  read"]
    expected = ["edit", "edit", "read"]

    for tc, exp in zip(test_cases, expected):
        # We manually construct valid JSON.
        # If tc has extra whitespace, we ensure it's still treated appropriately by the logic post-parsing.
        # But for test simplicity, let's assume the LLM produces valid JSON string values with whitespace.
        mock_response = MagicMock()
        mock_response.__str__.return_value = (
            f'{{"action": "{tc}", "targets": ["file1.py"]}}'
        )
        mock_service.get_chat_message_content.return_value = mock_response

        intent = await dispatcher._parse_with_llm("dummy")
        assert intent.action == exp


@pytest.mark.asyncio
async def test_parse_with_llm_invalid_fallback(mock_kernel):
    """Test fallback to 'unknown' for invalid actions (Audit requirement)."""
    dispatcher = TaskDispatcher(mock_kernel)
    mock_service = AsyncMock()
    mock_kernel.get_service.return_value = mock_service

    # Mock LLM response with non-existent action
    mock_response = MagicMock()
    mock_response.__str__.return_value = '{"action": "hack_the_gibson", "targets": []}'
    mock_service.get_chat_message_content.return_value = mock_response

    intent = await dispatcher._parse_with_llm("hack stuff")
    assert intent.action == "unknown"


@pytest.mark.asyncio
async def test_parse_with_llm_json_error(mock_kernel):
    """Test robustness against malformed JSON from LLM."""
    dispatcher = TaskDispatcher(mock_kernel)
    mock_service = AsyncMock()
    mock_kernel.get_service.return_value = mock_service

    # Mock LLM response with bad JSON
    mock_response = MagicMock()
    mock_response.__str__.return_value = "this is not json"
    mock_service.get_chat_message_content.return_value = mock_response

    intent = await dispatcher._parse_with_llm("dummy")
    assert intent.action == "unknown"
    assert intent.targets == []


def test_prepare_skill_parameters_file_skill(mock_kernel):
    """Test parameter extraction for FileSkill (Audit requirement)."""
    dispatcher = TaskDispatcher(mock_kernel)

    # Standard path
    params = dispatcher._prepare_skill_parameters(
        "FileSkill", "Read venom_core/main.py"
    )
    assert params == {"path": "venom_core/main.py"}

    # Path with special chars
    params = dispatcher._prepare_skill_parameters(
        "FileSkill", "Zapisz plik-test_v1.txt"
    )
    assert params == {"path": "plik-test_v1.txt"}

    # No path
    params = dispatcher._prepare_skill_parameters(
        "FileSkill", "Pokaż coś bez nazwy pliku"
    )
    assert params == {}

    # Multiple paths (take first)
    params = dispatcher._prepare_skill_parameters("FileSkill", "Compare a.py and b.py")
    assert params == {"path": "a.py"}


def test_prepare_skill_parameters_shell_skill(mock_kernel):
    """Test parameter extraction for ShellSkill."""
    dispatcher = TaskDispatcher(mock_kernel)
    params = dispatcher._prepare_skill_parameters("ShellSkill", "ls -la")
    assert params == {"command": "ls -la"}
