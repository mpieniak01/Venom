"""Testy jednostkowe dla GuardianAgent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.agents.guardian import GuardianAgent, RepairTicket


@pytest.fixture
def mock_kernel():
    """Fixture dla mock Kernel."""
    kernel = MagicMock()
    kernel.add_plugin = MagicMock()

    # Mock chat service
    chat_service = MagicMock()
    chat_service.get_chat_message_content = AsyncMock()
    kernel.get_service = MagicMock(return_value=chat_service)

    return kernel


@pytest.fixture
def mock_test_skill():
    """Fixture dla mock TestSkill."""
    test_skill = MagicMock()
    test_skill.run_pytest = AsyncMock(return_value="✅ TESTY PRZESZŁY")
    return test_skill


@pytest.fixture
def guardian_agent(mock_kernel, mock_test_skill):
    """Fixture dla GuardianAgent z mockami."""
    with patch("venom_core.agents.guardian.TestSkill", return_value=mock_test_skill):
        with patch("venom_core.agents.guardian.FileSkill"):
            with patch("venom_core.agents.guardian.GitSkill"):
                agent = GuardianAgent(kernel=mock_kernel, test_skill=mock_test_skill)
                return agent


@pytest.mark.asyncio
async def test_guardian_initialization(mock_kernel, mock_test_skill):
    """Test inicjalizacji GuardianAgent."""
    with patch("venom_core.agents.guardian.FileSkill"):
        with patch("venom_core.agents.guardian.GitSkill"):
            agent = GuardianAgent(kernel=mock_kernel, test_skill=mock_test_skill)

            assert agent is not None
            assert agent.test_skill == mock_test_skill
            assert agent.kernel == mock_kernel


@pytest.mark.asyncio
async def test_guardian_process(guardian_agent):
    """Test przetwarzania przez Guardiana."""
    # Mockuj odpowiedź LLM
    mock_response = MagicMock()
    mock_response.__str__ = lambda _: "Analiza zakończona"

    guardian_agent.chat_service.get_chat_message_content = AsyncMock(
        return_value=mock_response
    )

    result = await guardian_agent.process("Uruchom testy")

    assert result is not None
    assert isinstance(result, str)
    assert "Analiza zakończona" in result


def test_parse_repair_ticket():
    """Test parsowania ticketu naprawczego."""
    guardian_agent = MagicMock()
    guardian_agent._parse_repair_ticket = GuardianAgent._parse_repair_ticket

    llm_response = """
FILE: src/calculator.py
LINE: 15
ERROR: AssertionError: Expected 10, got 0
CAUSE: Funkcja divide() zwraca 0 zamiast wyniku dzielenia
ACTION: Popraw logikę dzielenia - upewnij się że zwracasz a/b zamiast 0
"""

    ticket = guardian_agent._parse_repair_ticket(guardian_agent, llm_response)

    assert isinstance(ticket, RepairTicket)
    assert ticket.file_path == "src/calculator.py"
    assert ticket.line_number == 15
    assert "AssertionError" in ticket.error_message
    assert "zwraca 0" in ticket.cause
    assert "Popraw logikę" in ticket.suggested_action


def test_parse_repair_ticket_without_line_number():
    """Test parsowania ticketu bez numeru linii."""
    guardian_agent = MagicMock()
    guardian_agent._parse_repair_ticket = GuardianAgent._parse_repair_ticket

    llm_response = """
FILE: src/main.py
LINE: UNKNOWN
ERROR: ImportError: cannot import module
CAUSE: Brakuje importu potrzebnej biblioteki
ACTION: Dodaj import sys na początku pliku
"""

    ticket = guardian_agent._parse_repair_ticket(guardian_agent, llm_response)

    assert isinstance(ticket, RepairTicket)
    assert ticket.file_path == "src/main.py"
    assert ticket.line_number is None  # UNKNOWN powinno dać None
    assert "ImportError" in ticket.error_message


@pytest.mark.asyncio
async def test_analyze_test_failure(guardian_agent):
    """Test analizy błędu testu."""
    # Mockuj odpowiedź LLM
    mock_response = MagicMock()
    mock_response.__str__ = (
        lambda _: """
FILE: test.py
LINE: 10
ERROR: Test failed
CAUSE: Wrong logic
ACTION: Fix the code
"""
    )

    guardian_agent.chat_service.get_chat_message_content = AsyncMock(
        return_value=mock_response
    )

    test_output = "FAILED test.py::test_example - AssertionError"

    ticket = await guardian_agent.analyze_test_failure(test_output)

    assert isinstance(ticket, RepairTicket)
    assert ticket.file_path == "test.py"
    assert ticket.line_number == 10


@pytest.mark.asyncio
async def test_analyze_test_failure_with_error(guardian_agent):
    """Test analizy błędu gdy proces zawodzi."""
    # Mockuj błąd podczas analizy
    guardian_agent.chat_service.get_chat_message_content = AsyncMock(
        side_effect=Exception("LLM error")
    )

    test_output = "Some test output"

    ticket = await guardian_agent.analyze_test_failure(test_output)

    # Powinien zwrócić domyślny ticket
    assert isinstance(ticket, RepairTicket)
    assert ticket.file_path == "UNKNOWN"
    assert "Nie udało się przeanalizować" in ticket.cause
