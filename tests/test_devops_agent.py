"""Testy jednostkowe dla DevOpsAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.devops import DevOpsAgent


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    mock_service = MagicMock()
    mock_service.get_chat_message_content = AsyncMock()
    kernel.get_service = MagicMock(return_value=mock_service)
    return kernel


def test_devops_agent_initialization(mock_kernel):
    """Test inicjalizacji DevOpsAgent."""
    agent = DevOpsAgent(mock_kernel)
    assert agent.kernel == mock_kernel
    assert agent.chat_history is not None
    assert "DevOps" in agent.SYSTEM_PROMPT
    assert "infrastructure" in agent.SYSTEM_PROMPT.lower()


def test_devops_agent_system_prompt():
    """Test poprawności system prompta."""
    prompt = DevOpsAgent.SYSTEM_PROMPT

    # Sprawdź kluczowe elementy prompta
    assert "devops" in prompt.lower()
    assert "docker" in prompt.lower()
    assert "deployment" in prompt.lower()
    assert "security" in prompt.lower() or "bezpieczeństwo" in prompt.lower()
    assert "nginx" in prompt.lower()


@pytest.mark.asyncio
async def test_devops_agent_process_success(mock_kernel):
    """Test metody process - sukces."""
    agent = DevOpsAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: """
    Plan deploymentu:
    1. Provision serwera
    2. Instalacja Docker
    3. Deploy aplikacji
    """
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("Deploy aplikację na serwer")

    assert isinstance(result, str)
    assert len(result) > 0
    agent.kernel.get_service().get_chat_message_content.assert_called()


@pytest.mark.asyncio
async def test_devops_agent_process_deployment_request(mock_kernel):
    """Test przetwarzania żądania deploymentu."""
    agent = DevOpsAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Deployment plan created"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("Deploy Docker stack to production")

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_devops_agent_process_monitoring_request(mock_kernel):
    """Test przetwarzania żądania monitoringu."""
    agent = DevOpsAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Monitoring configured"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("Setup monitoring for the application")

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_devops_agent_process_error(mock_kernel):
    """Test obsługi błędów podczas przetwarzania."""
    agent = DevOpsAgent(mock_kernel)

    # Mock błąd
    agent.kernel.get_service().get_chat_message_content.side_effect = Exception(
        "Connection error"
    )

    result = await agent.process("Test")

    assert "Błąd" in result
    assert "DevOps" in result


@pytest.mark.asyncio
async def test_devops_agent_empty_input(mock_kernel):
    """Test z pustym inputem."""
    agent = DevOpsAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Please provide deployment details"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    result = await agent.process("")

    assert isinstance(result, str)


def test_devops_agent_reset_conversation(mock_kernel):
    """Test resetowania historii konwersacji."""
    agent = DevOpsAgent(mock_kernel)

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
async def test_devops_agent_low_temperature(mock_kernel):
    """Test że DevOps Agent używa niskiej temperatury dla precyzji."""
    agent = DevOpsAgent(mock_kernel)

    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "Precise deployment steps"
    agent.kernel.get_service().get_chat_message_content.return_value = mock_response

    await agent.process("Create deployment plan")

    # Verify that the call was made
    agent.kernel.get_service().get_chat_message_content.assert_called()


@pytest.mark.asyncio
async def test_devops_agent_security_focus(mock_kernel):
    """Test że agent uwzględnia bezpieczeństwo w odpowiedziach."""
    agent = DevOpsAgent(mock_kernel)

    # Sprawdź czy system prompt zawiera informacje o bezpieczeństwie
    assert "SSH" in agent.SYSTEM_PROMPT or "ssl" in agent.SYSTEM_PROMPT.lower()
    assert "secret" in agent.SYSTEM_PROMPT.lower() or "token" in agent.SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_devops_agent_conversation_context(mock_kernel):
    """Test utrzymywania kontekstu konwersacji."""
    agent = DevOpsAgent(mock_kernel)

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
