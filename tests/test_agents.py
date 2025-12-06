"""Testy jednostkowe dla agentów."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
from venom_core.agents.chat import ChatAgent
from venom_core.agents.coder import CoderAgent


class ConcreteAgent(BaseAgent):
    """Konkretna implementacja BaseAgent do testów."""

    async def process(self, input_text: str) -> str:
        return f"Processed: {input_text}"


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    return kernel


@pytest.fixture
def mock_chat_service():
    """Fixture dla mockowego serwisu chat."""
    service = MagicMock()
    service.get_chat_message_content = AsyncMock()
    return service


# --- Testy BaseAgent ---


def test_base_agent_initialization(mock_kernel):
    """Test inicjalizacji BaseAgent."""
    agent = ConcreteAgent(mock_kernel)
    assert agent.kernel == mock_kernel


@pytest.mark.asyncio
async def test_base_agent_process(mock_kernel):
    """Test metody process w konkretnej implementacji."""
    agent = ConcreteAgent(mock_kernel)
    result = await agent.process("test input")
    assert result == "Processed: test input"


# --- Testy CoderAgent ---


def test_coder_agent_initialization(mock_kernel):
    """Test inicjalizacji CoderAgent."""
    agent = CoderAgent(mock_kernel)
    assert agent.kernel == mock_kernel
    assert "Senior Developer" in agent.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_coder_agent_generates_code(mock_kernel, mock_chat_service):
    """Test generowania kodu przez CoderAgent."""
    # Mockuj odpowiedź od LLM
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value='```python\ndef hello_world():\n    print("Hello World")\n```'
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    agent = CoderAgent(mock_kernel)
    result = await agent.process("Napisz funkcję Hello World w Python")

    assert "hello_world" in result
    assert "python" in result
    assert mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_coder_agent_handles_error(mock_kernel, mock_chat_service):
    """Test obsługi błędu przez CoderAgent."""
    mock_chat_service.get_chat_message_content.side_effect = Exception(
        "Connection error"
    )
    mock_kernel.get_service.return_value = mock_chat_service

    agent = CoderAgent(mock_kernel)
    result = await agent.process("Napisz kod")

    assert "Błąd" in result
    assert "Connection error" in result


# --- Testy ChatAgent ---


def test_chat_agent_initialization(mock_kernel):
    """Test inicjalizacji ChatAgent."""
    agent = ChatAgent(mock_kernel)
    assert agent.kernel == mock_kernel
    assert "Venom" in agent.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_chat_agent_responds_to_greeting(mock_kernel, mock_chat_service):
    """Test odpowiedzi ChatAgent na powitanie."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value="Cześć! Świetnie się mam, dziękuję. Gotowy do pomocy!"
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel)
    result = await agent.process("Cześć Venom, jak się masz?")

    assert "Cześć" in result or "cześć" in result.lower()
    assert mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_chat_agent_answers_question(mock_kernel, mock_chat_service):
    """Test odpowiedzi ChatAgent na pytanie."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="Stolicą Francji jest Paryż.")
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel)
    result = await agent.process("Jaka jest stolica Francji?")

    assert "Paryż" in result or "pary" in result.lower()
    assert mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_chat_agent_tells_joke(mock_kernel, mock_chat_service):
    """Test opowiadania kawału przez ChatAgent."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value="Dlaczego programiści wolą ciemny motyw? Bo światło przyciąga błędy! 😄"
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel)
    result = await agent.process("Opowiedz kawał")

    assert len(result) > 0
    assert mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_chat_agent_handles_error(mock_kernel, mock_chat_service):
    """Test obsługi błędu przez ChatAgent."""
    mock_chat_service.get_chat_message_content.side_effect = Exception("LLM error")
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel)
    result = await agent.process("Jakieś pytanie")

    assert "Błąd" in result
    assert "LLM error" in result
