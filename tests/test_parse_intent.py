"""Testy jednostkowe dla parse_intent w TaskDispatcher."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.models import Intent


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    return kernel


@pytest.fixture
def dispatcher(mock_kernel):
    """Fixture dla TaskDispatcher."""
    return TaskDispatcher(mock_kernel)


@pytest.mark.asyncio
async def test_parse_intent_with_file_path_edit(dispatcher):
    """Test parsowania intencji edycji pliku."""
    content = "proszę popraw błąd w pliku venom_core/main.py"

    intent = await dispatcher.parse_intent(content)

    assert intent.action == "edit"
    assert "venom_core/main.py" in intent.targets
    assert isinstance(intent.params, dict)


@pytest.mark.asyncio
async def test_parse_intent_with_multiple_files(dispatcher):
    """Test parsowania intencji z wieloma plikami."""
    content = "zmień config.py i utils.py oraz settings.json"

    intent = await dispatcher.parse_intent(content)

    assert intent.action == "edit"
    assert "config.py" in intent.targets
    assert "utils.py" in intent.targets
    assert "settings.json" in intent.targets


@pytest.mark.asyncio
async def test_parse_intent_create_action(dispatcher):
    """Test parsowania intencji utworzenia pliku."""
    content = "stwórz nowy plik test.py"

    intent = await dispatcher.parse_intent(content)

    assert intent.action == "create"
    assert "test.py" in intent.targets


@pytest.mark.asyncio
async def test_parse_intent_delete_action(dispatcher):
    """Test parsowania intencji usunięcia pliku."""
    content = "usuń plik old_code.py"

    intent = await dispatcher.parse_intent(content)

    assert intent.action == "delete"
    assert "old_code.py" in intent.targets


@pytest.mark.asyncio
async def test_parse_intent_read_action(dispatcher):
    """Test parsowania intencji odczytu pliku."""
    content = "pokaż mi zawartość readme.md"

    intent = await dispatcher.parse_intent(content)

    assert intent.action == "read"
    assert "readme.md" in intent.targets


@pytest.mark.asyncio
async def test_parse_intent_with_path_separators(dispatcher):
    """Test parsowania ścieżek z separatorami katalogów."""
    content = "edytuj src/components/header.js i tests/test_main.py"

    intent = await dispatcher.parse_intent(content)

    assert intent.action == "edit"
    assert "src/components/header.js" in intent.targets
    assert "tests/test_main.py" in intent.targets


@pytest.mark.asyncio
async def test_parse_intent_various_extensions(dispatcher):
    """Test parsowania różnych rozszerzeń plików."""
    content = "zmień config.yaml, script.ts, style.css i data.json"

    intent = await dispatcher.parse_intent(content)

    assert "config.yaml" in intent.targets
    assert "script.ts" in intent.targets
    assert "style.css" in intent.targets
    assert "data.json" in intent.targets


@pytest.mark.asyncio
async def test_parse_intent_no_files_llm_fallback(dispatcher, mock_kernel):
    """Test fallback do LLM gdy regex nie znajdzie plików."""
    content = "popraw ten kod który jest zepsuty"

    # Mock LLM response
    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: '{"action": "edit", "targets": []}'
    mock_service.get_chat_message_content = AsyncMock(return_value=mock_response)
    mock_kernel.get_service = MagicMock(return_value=mock_service)

    intent = await dispatcher.parse_intent(content)

    # Powinien użyć LLM fallback
    assert isinstance(intent, Intent)
    mock_service.get_chat_message_content.assert_called_once()


@pytest.mark.asyncio
async def test_parse_intent_llm_fallback_with_result(dispatcher, mock_kernel):
    """Test poprawnego parsowania wyniku z LLM."""
    content = "napraw problem w głównym pliku"

    # Mock LLM response z konkretnym wynikiem
    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = (
        lambda self: '{"action": "edit", "targets": ["main.py", "core.py"]}'
    )
    mock_service.get_chat_message_content = AsyncMock(return_value=mock_response)
    mock_kernel.get_service = MagicMock(return_value=mock_service)

    intent = await dispatcher.parse_intent(content)

    assert intent.action == "edit"
    assert "main.py" in intent.targets
    assert "core.py" in intent.targets


@pytest.mark.asyncio
async def test_parse_intent_llm_fallback_json_with_markdown(dispatcher, mock_kernel):
    """Test parsowania JSON z markdown code blocks."""
    content = "zmień konfigurację"

    # Mock LLM response z markdown code blocks
    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: '''```json
{
  "action": "edit",
  "targets": ["config.py"]
}
```'''
    mock_service.get_chat_message_content = AsyncMock(return_value=mock_response)
    mock_kernel.get_service = MagicMock(return_value=mock_service)

    intent = await dispatcher.parse_intent(content)

    assert intent.action == "edit"
    assert "config.py" in intent.targets


@pytest.mark.asyncio
async def test_parse_intent_llm_error_handling(dispatcher, mock_kernel):
    """Test obsługi błędów LLM."""
    content = "zrób coś"

    # Mock LLM który rzuca błąd
    mock_service = MagicMock()
    mock_service.get_chat_message_content = AsyncMock(
        side_effect=Exception("LLM Error")
    )
    mock_kernel.get_service = MagicMock(return_value=mock_service)

    intent = await dispatcher.parse_intent(content)

    # Powinien zwrócić unknown action gdy LLM zawiedzie
    assert intent.action == "unknown"
    assert intent.targets == []


@pytest.mark.asyncio
async def test_parse_intent_empty_content(dispatcher):
    """Test obsługi pustego contentu."""
    content = ""

    intent = await dispatcher.parse_intent(content)

    assert isinstance(intent, Intent)
    assert intent.targets == []
