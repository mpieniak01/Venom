"""Testy jednostkowe dla DesignerAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.designer import DesignerAgent


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    mock_service = MagicMock()
    mock_service.get_chat_message_content = AsyncMock()
    kernel.get_service = MagicMock(return_value=mock_service)
    return kernel


def test_designer_agent_initialization(mock_kernel):
    """Test inicjalizacji DesignerAgent."""
    agent = DesignerAgent(mock_kernel)
    assert agent is not None
    assert agent.kernel == mock_kernel
    assert "UI/UX" in agent.SYSTEM_PROMPT
    assert "Frontend Developer" in agent.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_designer_agent_process(mock_kernel):
    """Test metody process DesignerAgent."""
    agent = DesignerAgent(mock_kernel)
    
    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: '{"type": "chart", "data": {"chartType": "bar"}}'
    agent.chat_service.get_chat_message_content.return_value = mock_response
    
    result = await agent.process("Stwórz wykres")
    
    assert result is not None
    assert isinstance(result, str)
    agent.chat_service.get_chat_message_content.assert_called_once()


@pytest.mark.asyncio
async def test_designer_agent_create_visualization(mock_kernel):
    """Test tworzenia wizualizacji."""
    agent = DesignerAgent(mock_kernel)
    
    # Mock response z JSONem
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: '{"type": "chart", "data": {"chartType": "bar"}}'
    agent.chat_service.get_chat_message_content.return_value = mock_response
    
    data = {"values": [1, 2, 3]}
    result = await agent.create_visualization("Stwórz wykres", data)
    
    assert isinstance(result, dict)
    assert "type" in result


@pytest.mark.asyncio
async def test_designer_agent_create_chart(mock_kernel):
    """Test tworzenia wykresu."""
    agent = DesignerAgent(mock_kernel)
    
    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: '{"type": "chart", "data": {}}'
    agent.chat_service.get_chat_message_content.return_value = mock_response
    
    data = {"labels": ["A", "B"], "values": [1, 2]}
    result = await agent.create_chart("bar", data, "Test Chart")
    
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_designer_agent_create_form(mock_kernel):
    """Test tworzenia formularza."""
    agent = DesignerAgent(mock_kernel)
    
    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: '{"type": "form", "data": {}}'
    agent.chat_service.get_chat_message_content.return_value = mock_response
    
    fields = [{"name": "title", "type": "text"}]
    result = await agent.create_form("Bug Report", fields)
    
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_designer_agent_create_dashboard_card(mock_kernel):
    """Test tworzenia karty dashboardu."""
    agent = DesignerAgent(mock_kernel)
    
    # Mock response
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: '{"type": "card", "data": {}}'
    agent.chat_service.get_chat_message_content.return_value = mock_response
    
    data = {"status": "active"}
    result = await agent.create_dashboard_card("Weather", data, "🌤️")
    
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_designer_agent_error_handling(mock_kernel):
    """Test obsługi błędów."""
    agent = DesignerAgent(mock_kernel)
    
    # Mock błąd
    agent.chat_service.get_chat_message_content.side_effect = Exception("Test error")
    
    result = await agent.process("Test")
    
    assert "Błąd projektanta" in result


@pytest.mark.asyncio
async def test_designer_agent_invalid_json_response(mock_kernel):
    """Test obsługi nieprawidłowego JSON w odpowiedzi."""
    agent = DesignerAgent(mock_kernel)
    
    # Mock response bez JSONa
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "To nie jest JSON"
    agent.chat_service.get_chat_message_content.return_value = mock_response
    
    data = {}
    result = await agent.create_visualization("Test", data)
    
    # Powinien zwrócić markdown widget jako fallback
    assert isinstance(result, dict)
    assert result["type"] == "markdown"


def test_designer_system_prompt():
    """Test poprawności system prompta."""
    prompt = DesignerAgent.SYSTEM_PROMPT
    
    # Sprawdź kluczowe elementy prompta
    assert "UI/UX" in prompt
    assert "Frontend Developer" in prompt
    assert "HTML" in prompt
    assert "TailwindCSS" in prompt
    assert "Chart.js" in prompt
    assert "Mermaid" in prompt
    assert "bezpieczeństwo" in prompt.lower() or "security" in prompt.lower()
    
    # Sprawdź typy komponentów
    assert "chart" in prompt
    assert "table" in prompt
    assert "form" in prompt
    assert "markdown" in prompt
    assert "mermaid" in prompt
    assert "card" in prompt
