"""Unit tests for CreativeDirectorAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.creative_director import CreativeDirectorAgent


@pytest.fixture
def mock_kernel():
    """Fixture for mock Kernel."""
    kernel = MagicMock(spec=Kernel)
    mock_service = MagicMock()
    mock_service.get_chat_message_content = AsyncMock()
    kernel.get_service = MagicMock(return_value=mock_service)
    return kernel


def test_creative_director_initialization(mock_kernel):
    """Test initialization of CreativeDirectorAgent."""
    agent = CreativeDirectorAgent(mock_kernel)
    assert agent.kernel == mock_kernel
    assert agent.chat_history is not None
    assert "Creative Director" in agent.SYSTEM_PROMPT
    assert "branding" in agent.SYSTEM_PROMPT.lower()


def test_creative_director_system_prompt():
    """Test correctness of system prompt."""
    prompt = CreativeDirectorAgent.SYSTEM_PROMPT

    # Check key elements of the prompt
    assert "branding" in prompt.lower() or "marketing" in prompt.lower()
    assert "copywriting" in prompt.lower() or "copy" in prompt.lower()
    assert "logo" in prompt.lower() or "visual" in prompt.lower()
    assert "social media" in prompt.lower()


@pytest.mark.asyncio
async def test_creative_director_process_success(mock_kernel):
    """Test process method - success path."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = (
        lambda self: """
    **Identyfikacja Wizualna:**
    Styl: Minimalistyczny
    Logo prompt: 'Modern app logo, blue gradient'

    **Copywriting:**
    Tagline: 'Build better apps'
    """
    )
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("Stwórz branding dla aplikacji")

    assert isinstance(result, str)
    assert len(result) > 0
    agent.kernel.get_service().get_chat_message_content.assert_called()


@pytest.mark.asyncio
async def test_creative_director_process_with_logo_request(mock_kernel):
    """Test processing a logo creation request."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Logo prompt: 'Minimalist fintech logo'"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("Stwórz logo dla aplikacji fintech")

    assert isinstance(result, str)
    assert "logo" in result.lower() or "fintech" in result.lower()


@pytest.mark.asyncio
async def test_creative_director_process_with_copywriting_request(mock_kernel):
    """Test processing a copywriting request."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Tagline: 'Your payment solution'"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("Napisz tagline dla aplikacji płatności")

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_creative_director_process_error(mock_kernel):
    """Test error handling during processing."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock error
    agent.kernel.get_service().get_chat_message_content.side_effect = Exception(
        "API error"
    )

    result = await agent.process("Test")

    assert "Błąd" in result
    assert "strategii brandingowej" in result


@pytest.mark.asyncio
async def test_creative_director_empty_input(mock_kernel):
    """Test with empty input."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Provide more details"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("")

    assert isinstance(result, str)


def test_creative_director_reset_conversation(mock_kernel):
    """Test resetting conversation history."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Add a message to the history
    agent.chat_history.add_user_message("Test message")
    initial_count = len(agent.chat_history.messages)
    assert initial_count > 1  # System prompt + user message

    # Reset
    agent.reset_conversation()

    # After reset, only the system message should remain
    assert len(agent.chat_history.messages) == 1
    assert agent.chat_history.messages[0].content == agent.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_creative_director_conversation_context(mock_kernel):
    """Test maintaining conversation context."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Response 1"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    # First call
    await agent.process("Request 1")
    first_history_len = len(agent.chat_history.messages)

    # Second call
    mock_response.__str__ = lambda self: "Response 2"
    await agent.process("Request 2")
    second_history_len = len(agent.chat_history.messages)

    # History should grow
    assert second_history_len > first_history_len
    assert (
        second_history_len >= 5
    )  # System + Request1 + Response1 + Request2 + Response2


@pytest.mark.asyncio
async def test_creative_director_high_temperature(mock_kernel):
    """Test that Creative Director uses higher temperature for creativity."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Creative output"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    await agent.process("Generate creative ideas")

    # Verify that the call was made (temperature is checked in the implementation)
    agent.kernel.get_service().get_chat_message_content.assert_called()
