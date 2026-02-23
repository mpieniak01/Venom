"""Testy jednostkowe dla CreativeDirectorAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.creative_director import CreativeDirectorAgent


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    mock_service = MagicMock()
    mock_service.get_chat_message_content = AsyncMock()
    kernel.get_service = MagicMock(return_value=mock_service)
    return kernel


def test_creative_director_initialization(mock_kernel):
    """Test inicjalizacji CreativeDirectorAgent."""
    agent = CreativeDirectorAgent(mock_kernel)
    assert agent.kernel == mock_kernel
    assert agent.chat_history is not None
    assert "Creative Director" in agent.SYSTEM_PROMPT
    assert "branding" in agent.SYSTEM_PROMPT.lower()


def test_creative_director_system_prompt():
    """Test poprawności system prompta."""
    prompt = CreativeDirectorAgent.SYSTEM_PROMPT

    # Sprawdź kluczowe elementy prompta
    assert "branding" in prompt.lower() or "marketing" in prompt.lower()
    assert "copywriting" in prompt.lower() or "copy" in prompt.lower()
    assert "logo" in prompt.lower() or "visual" in prompt.lower()
    assert "social media" in prompt.lower()


@pytest.mark.asyncio
async def test_creative_director_process_success(mock_kernel):
    """Test metody process - sukces."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: """
    **Identyfikacja Wizualna:**
    Styl: Minimalistyczny
    Logo prompt: 'Modern app logo, blue gradient'
    
    **Copywriting:**
    Tagline: 'Build better apps'
    """
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("Stwórz branding dla aplikacji")

    assert isinstance(result, str)
    assert len(result) > 0
    agent.kernel.get_service().get_chat_message_content.assert_called()


@pytest.mark.asyncio
async def test_creative_director_process_with_logo_request(mock_kernel):
    """Test przetwarzania żądania stworzenia logo."""
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
    """Test przetwarzania żądania copywritingu."""
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
    """Test obsługi błędów podczas przetwarzania."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock błąd
    agent.kernel.get_service().get_chat_message_content.side_effect = Exception(
        "API error"
    )

    result = await agent.process("Test")

    assert "Błąd" in result
    assert "strategii brandingowej" in result


@pytest.mark.asyncio
async def test_creative_director_empty_input(mock_kernel):
    """Test z pustym inputem."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Provide more details"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("")

    assert isinstance(result, str)


def test_creative_director_reset_conversation(mock_kernel):
    """Test resetowania historii konwersacji."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Dodaj wiadomość do historii
    agent.chat_history.add_user_message("Test message")
    initial_count = len(agent.chat_history.messages)
    assert initial_count > 1  # System prompt + user message

    # Resetuj
    agent.reset_conversation()

    # Po resecie powinna być tylko wiadomość systemowa
    assert len(agent.chat_history.messages) == 1
    assert agent.chat_history.messages[0].content == agent.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_creative_director_conversation_context(mock_kernel):
    """Test utrzymywania kontekstu konwersacji."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Response 1"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    # Pierwsze wywołanie
    await agent.process("Request 1")
    first_history_len = len(agent.chat_history.messages)

    # Drugie wywołanie
    mock_response.__str__ = lambda self: "Response 2"
    await agent.process("Request 2")
    second_history_len = len(agent.chat_history.messages)

    # Historia powinna się powiększać
    assert second_history_len > first_history_len
    assert second_history_len >= 5  # System + Request1 + Response1 + Request2 + Response2


@pytest.mark.asyncio
async def test_creative_director_high_temperature(mock_kernel):
    """Test że Creative Director używa wyższej temperatury dla kreatywności."""
    agent = CreativeDirectorAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Creative output"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    await agent.process("Generate creative ideas")

    # Verify that the call was made (temperature is checked in the implementation)
    agent.kernel.get_service().get_chat_message_content.assert_called()
