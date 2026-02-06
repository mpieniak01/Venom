from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.agents.toolmaker import ToolmakerAgent
from venom_core.execution.skills.file_skill import FileSkill


@pytest.fixture
def mock_kernel():
    kernel = MagicMock()
    kernel.get_service.return_value = MagicMock()
    return kernel


@pytest.fixture
def mock_file_skill():
    skill = MagicMock(spec=FileSkill)
    skill.workspace_root = "/tmp/test_workspace"
    skill.write_file = AsyncMock()
    return skill


@pytest.fixture
def toolmaker(mock_kernel, mock_file_skill):
    with patch("venom_core.agents.toolmaker.FileSkill", return_value=mock_file_skill):
        agent = ToolmakerAgent(mock_kernel, file_skill=mock_file_skill)
        return agent


def test_initialization(toolmaker):
    """Test inicjalizacji agenta."""
    assert toolmaker.file_skill is not None
    assert toolmaker.chat_service is not None
    assert "Toolmaker - Master Craftsman" in toolmaker.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_process_tool_generation(toolmaker):
    """Test generowania kodu narzędzia."""
    # Mock LLM response
    mock_response = """
    Oto Twój kod:
    ```python
    def test_tool():
        return "hello"
    ```
    """

    with patch.object(
        toolmaker, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
    ) as mock_chat:
        mock_chat.return_value = mock_response

        code = await toolmaker.process("Stwórz proste narzędzie")

        # Verify markdown parsing logic
        assert "def test_tool():" in code
        assert "```python" not in code
        assert 'return "hello"' in code

        mock_chat.assert_called_once()


@pytest.mark.asyncio
async def test_create_tool_success(toolmaker):
    """Test pomyślnego utworzenia i zapisania narzędzia."""
    mock_code = "class MyTool:\n    pass"

    with patch.object(toolmaker, "process", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = mock_code

        success, result = await toolmaker.create_tool(
            specification="Tool spec", tool_name="my_tool"
        )

        assert success is True
        assert result == mock_code

        # Verify file write interaction
        toolmaker.file_skill.write_file.assert_called_once_with(
            "custom/my_tool.py", mock_code
        )


@pytest.mark.asyncio
async def test_create_tool_invalid_name(toolmaker):
    """Test walidacji nazwy narzędzia."""
    success, result = await toolmaker.create_tool("spec", "Invalid Name!")

    assert success is False
    assert "Nieprawidłowa nazwa" in result
    toolmaker.file_skill.write_file.assert_not_called()


@pytest.mark.asyncio
async def test_create_tool_error_handling(toolmaker):
    """Test obsługi błędów podczas tworzenia narzędzia."""
    with patch.object(toolmaker, "process", side_effect=Exception("LLM Error")):
        success, result = await toolmaker.create_tool("spec", "my_tool")

        assert success is False
        assert "Błąd podczas tworzenia narzędzia" in result


@pytest.mark.asyncio
async def test_create_test_success(toolmaker):
    """Test generowania testu."""
    mock_test_code = "def test_something(): pass"

    with patch.object(toolmaker, "process", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = mock_test_code

        success, result = await toolmaker.create_test("my_tool", "code...")

        assert success is True
        assert result == mock_test_code

        toolmaker.file_skill.write_file.assert_called_once_with(
            "custom/test_my_tool.py", mock_test_code
        )


@pytest.mark.asyncio
async def test_create_tool_ui_card(toolmaker):
    """Test generowania UI card."""
    card = toolmaker.create_tool_ui_card("my_tool", "Description")

    assert card["type"] == "card"
    assert card["data"]["title"] == "My Tool"
    assert "use_tool:my_tool" in str(card["data"]["actions"])
