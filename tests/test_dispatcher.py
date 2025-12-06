"""Testy jednostkowe dla TaskDispatcher."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.chat import ChatAgent
from venom_core.agents.coder import CoderAgent
from venom_core.agents.librarian import LibrarianAgent
from venom_core.core.dispatcher import TaskDispatcher


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    return kernel


@pytest.fixture
def mock_coder_agent():
    """Fixture dla mockowego CoderAgent."""
    agent = MagicMock(spec=CoderAgent)
    agent.process = AsyncMock()
    return agent


@pytest.fixture
def mock_chat_agent():
    """Fixture dla mockowego ChatAgent."""
    agent = MagicMock(spec=ChatAgent)
    agent.process = AsyncMock()
    return agent


@pytest.fixture
def mock_librarian_agent():
    """Fixture dla mockowego LibrarianAgent."""
    agent = MagicMock(spec=LibrarianAgent)
    agent.process = AsyncMock()
    return agent


@pytest.fixture
def dispatcher_with_mocked_agents(
    mock_kernel, mock_coder_agent, mock_chat_agent, mock_librarian_agent
):
    """Fixture dla TaskDispatcher z zamockowanymi agentami."""
    dispatcher = TaskDispatcher(mock_kernel)
    # Zamień prawdziwe agenty na mocki
    dispatcher.coder_agent = mock_coder_agent
    dispatcher.chat_agent = mock_chat_agent
    dispatcher.librarian_agent = mock_librarian_agent
    dispatcher.agent_map = {
        "CODE_GENERATION": mock_coder_agent,
        "GENERAL_CHAT": mock_chat_agent,
        "KNOWLEDGE_SEARCH": mock_librarian_agent,
        "FILE_OPERATION": mock_librarian_agent,
    }
    return dispatcher


def test_dispatcher_initialization(mock_kernel):
    """Test inicjalizacji TaskDispatcher."""
    dispatcher = TaskDispatcher(mock_kernel)
    assert dispatcher.kernel == mock_kernel
    assert isinstance(dispatcher.coder_agent, CoderAgent)
    assert isinstance(dispatcher.chat_agent, ChatAgent)
    assert isinstance(dispatcher.librarian_agent, LibrarianAgent)
    assert "CODE_GENERATION" in dispatcher.agent_map
    assert "GENERAL_CHAT" in dispatcher.agent_map
    assert "KNOWLEDGE_SEARCH" in dispatcher.agent_map
    assert "FILE_OPERATION" in dispatcher.agent_map


def test_dispatcher_agent_map_configuration(mock_kernel):
    """Test poprawnej konfiguracji mapy agentów."""
    dispatcher = TaskDispatcher(mock_kernel)
    assert dispatcher.agent_map["CODE_GENERATION"] == dispatcher.coder_agent
    assert dispatcher.agent_map["GENERAL_CHAT"] == dispatcher.chat_agent
    assert dispatcher.agent_map["KNOWLEDGE_SEARCH"] == dispatcher.librarian_agent
    assert dispatcher.agent_map["FILE_OPERATION"] == dispatcher.librarian_agent


@pytest.mark.asyncio
async def test_dispatcher_routes_code_generation(
    dispatcher_with_mocked_agents, mock_coder_agent
):
    """Test kierowania zadań CODE_GENERATION do CoderAgent."""
    mock_coder_agent.process.return_value = '```python\nprint("Hello")\n```'

    result = await dispatcher_with_mocked_agents.dispatch(
        "CODE_GENERATION", "Napisz funkcję w Python"
    )

    assert result == '```python\nprint("Hello")\n```'
    mock_coder_agent.process.assert_called_once_with("Napisz funkcję w Python")


@pytest.mark.asyncio
async def test_dispatcher_routes_general_chat(
    dispatcher_with_mocked_agents, mock_chat_agent
):
    """Test kierowania zadań GENERAL_CHAT do ChatAgent."""
    mock_chat_agent.process.return_value = "Cześć! Jak mogę pomóc?"

    result = await dispatcher_with_mocked_agents.dispatch(
        "GENERAL_CHAT", "Witaj Venom!"
    )

    assert result == "Cześć! Jak mogę pomóc?"
    mock_chat_agent.process.assert_called_once_with("Witaj Venom!")


@pytest.mark.asyncio
async def test_dispatcher_routes_knowledge_search(
    dispatcher_with_mocked_agents, mock_librarian_agent
):
    """Test kierowania zadań KNOWLEDGE_SEARCH do LibrarianAgent."""
    mock_librarian_agent.process.return_value = "Lista plików: test.py"

    result = await dispatcher_with_mocked_agents.dispatch(
        "KNOWLEDGE_SEARCH", "Jakie mam pliki?"
    )

    assert result == "Lista plików: test.py"
    mock_librarian_agent.process.assert_called_once_with("Jakie mam pliki?")


@pytest.mark.asyncio
async def test_dispatcher_routes_file_operation(
    dispatcher_with_mocked_agents, mock_librarian_agent
):
    """Test kierowania zadań FILE_OPERATION do LibrarianAgent."""
    mock_librarian_agent.process.return_value = "Plik zapisany: test.py"

    result = await dispatcher_with_mocked_agents.dispatch(
        "FILE_OPERATION", "Zapisz plik test.py"
    )

    assert result == "Plik zapisany: test.py"
    mock_librarian_agent.process.assert_called_once_with("Zapisz plik test.py")


@pytest.mark.asyncio
async def test_dispatcher_raises_error_on_unknown_intent(dispatcher_with_mocked_agents):
    """Test rzucania wyjątku dla nieznanej intencji."""
    with pytest.raises(ValueError, match="Nieznana intencja: UNKNOWN_INTENT"):
        await dispatcher_with_mocked_agents.dispatch("UNKNOWN_INTENT", "Jakieś zadanie")


@pytest.mark.asyncio
async def test_dispatcher_propagates_agent_errors(
    dispatcher_with_mocked_agents, mock_coder_agent
):
    """Test propagowania błędów z agentów."""
    mock_coder_agent.process.side_effect = Exception("Agent error")

    with pytest.raises(Exception, match="Agent error"):
        await dispatcher_with_mocked_agents.dispatch("CODE_GENERATION", "Napisz kod")


@pytest.mark.asyncio
async def test_dispatcher_handles_different_content_types(
    dispatcher_with_mocked_agents, mock_chat_agent
):
    """Test obsługi różnych typów treści."""
    test_cases = [
        "Krótkie pytanie",
        "Bardzo długie pytanie " * 50,
        "Pytanie\nz\nnowymi\nliniami",
        "Pytanie z 特殊 znakami ąćęłńóśźż 🎉",
    ]

    for content in test_cases:
        mock_chat_agent.process.return_value = "Odpowiedź"
        result = await dispatcher_with_mocked_agents.dispatch("GENERAL_CHAT", content)
        assert result == "Odpowiedź"
        mock_chat_agent.process.assert_called_with(content)
        mock_chat_agent.reset_mock()
