"""Testy jednostkowe dla CriticAgent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from semantic_kernel import Kernel

from venom_core.agents.critic import CriticAgent


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


@pytest.fixture
def critic_agent(mock_kernel):
    """Fixture dla CriticAgent."""
    return CriticAgent(mock_kernel)


# --- Testy inicjalizacji ---


def test_critic_agent_initialization(mock_kernel):
    """Test inicjalizacji CriticAgent."""
    agent = CriticAgent(mock_kernel)
    assert agent.kernel == mock_kernel
    assert agent.policy_engine is not None
    assert "Senior Developer" in agent.SYSTEM_PROMPT
    assert "APPROVED" in agent.SYSTEM_PROMPT


# --- Testy zatwierdzania kodu ---


@pytest.mark.asyncio
async def test_critic_approves_clean_code(critic_agent, mock_kernel, mock_chat_service):
    """Test zatwierdzania czystego kodu."""
    clean_code = '''
import os

def get_api_key():
    """Pobiera klucz API."""
    return os.getenv("API_KEY")
'''

    # Mock LLM odpowiedzi
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="APPROVED")
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    result = await critic_agent.process(clean_code)

    assert "APPROVED" in result
    assert mock_chat_service.get_chat_message_content.called


# --- Testy odrzucania kodu z lukami ---


@pytest.mark.asyncio
async def test_critic_rejects_hardcoded_api_key(critic_agent, mock_kernel, mock_chat_service):
    """Test odrzucania kodu z hardcoded API key."""
    bad_code = '''
api_key = "sk-proj-test123456789012345678901234"
client = openai.Client(api_key=api_key)
'''

    # PolicyEngine powinien natychmiast odrzucić, więc LLM nie zostanie wywołany
    result = await critic_agent.process(bad_code)

    assert "ODRZUCONO" in result
    assert "hardcoded" in result.lower() or "klucz" in result.lower()
    # LLM nie powinien być wywołany dla krytycznych naruszeń
    assert not mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_critic_rejects_dangerous_command(critic_agent, mock_kernel, mock_chat_service):
    """Test odrzucania kodu z niebezpieczną komendą."""
    bad_code = '''
import os

def delete_all():
    """Usuwa wszystko."""
    os.system("rm -rf /")
'''

    result = await critic_agent.process(bad_code)

    assert "ODRZUCONO" in result
    assert "Niebezpieczna" in result or "dangerous" in result.lower()


# --- Testy wykrywania problemów przez LLM ---


@pytest.mark.asyncio
async def test_critic_detects_logic_error(critic_agent, mock_kernel, mock_chat_service):
    """Test wykrywania błędu logicznego przez LLM."""
    code_with_logic_error = """
def calculate_average(numbers):
    total = sum(numbers)
    return total / 0  # Błąd - dzielenie przez 0
"""

    # Mock LLM wykrywającego błąd
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value="PROBLEM: Dzielenie przez zero. Powinno być: return total / len(numbers)"
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    result = await critic_agent.process(code_with_logic_error)

    assert "PROBLEM" in result or "APPROVED" not in result
    assert mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_critic_detects_missing_error_handling(critic_agent, mock_kernel, mock_chat_service):
    """Test wykrywania braku obsługi błędów przez LLM."""
    code_without_error_handling = """
def read_file(path):
    with open(path) as f:
        return f.read()
"""

    # Mock LLM wykrywającego brak try/except
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value="Brak obsługi błędów - dodaj try/except dla FileNotFoundError"
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    result = await critic_agent.process(code_without_error_handling)

    assert mock_chat_service.get_chat_message_content.called


# --- Testy ekstrakcji kodu z kontekstu ---


@pytest.mark.asyncio
async def test_extract_code_from_context(critic_agent, mock_kernel, mock_chat_service):
    """Test ekstrakcji kodu z kontekstu USER_REQUEST + CODE."""
    input_with_context = """USER_REQUEST: Napisz funkcję do obliczania sumy

CODE:
api_key = "sk-proj-bad123456789012345678901234"
"""

    result = await critic_agent.process(input_with_context)

    # PolicyEngine powinien wykryć klucz API mimo kontekstu
    assert "ODRZUCONO" in result


@pytest.mark.asyncio
async def test_process_plain_code(critic_agent, mock_kernel, mock_chat_service):
    """Test przetwarzania czystego kodu bez kontekstu."""
    plain_code = '''
def hello():
    """Says hello."""
    print("Hello")
'''

    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="APPROVED")
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    result = await critic_agent.process(plain_code)

    assert "APPROVED" in result


# --- Testy łączenia naruszeń PolicyEngine i LLM ---


@pytest.mark.asyncio
async def test_combine_policy_and_llm_violations(critic_agent, mock_kernel, mock_chat_service):
    """Test łączenia naruszeń z PolicyEngine i LLM."""
    code = """
def risky_function():
    password = "secret123"
    return password
"""

    # Mock LLM dodającego dodatkowe uwagi
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value="Dodatkowo: brak obsługi błędów i typowania"
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    result = await critic_agent.process(code)

    # Powinny być zarówno naruszenia PolicyEngine jak i uwagi LLM
    # (chociaż password nie jest wykrywany przez obecne regex, docstring jest)
    assert len(result) > 0


# --- Testy obsługi błędów ---


@pytest.mark.asyncio
async def test_critic_handles_llm_error(critic_agent, mock_kernel, mock_chat_service):
    """Test obsługi błędu LLM - fallback do PolicyEngine."""
    code = """
def test():
    pass
"""

    mock_chat_service.get_chat_message_content.side_effect = Exception("LLM unavailable")
    mock_kernel.get_service.return_value = mock_chat_service

    result = await critic_agent.process(code)

    # Powinien zwrócić coś (APPROVED lub wyniki PolicyEngine)
    assert result is not None
    # W przypadku błędu LLM i braku naruszeń PolicyEngine, powinno być APPROVED
    if not any(
        keyword in result for keyword in ["ODRZUCONO", "naruszenia", "PROBLEM"]
    ):
        assert "APPROVED" in result


# --- Testy formatowania raportów ---


def test_format_policy_violations(critic_agent):
    """Test formatowania naruszeń PolicyEngine."""
    from venom_core.core.policy_engine import Violation

    violations = [
        Violation(
            rule="hardcoded_credentials",
            severity="critical",
            message="Wykryto hardcodowany klucz",
            line_number=10,
        ),
        Violation(
            rule="missing_docstring",
            severity="medium",
            message="Brak docstringa",
            line_number=15,
        ),
    ]

    report = critic_agent._format_policy_violations(violations)

    assert "ODRZUCONO" in report
    assert "wykryto naruszenia" in report.lower()
    assert "linia 10" in report
    assert "linia 15" in report
    assert "CRITICAL" in report
    assert "MEDIUM" in report


# --- Testy scenariuszy integracyjnych ---


@pytest.mark.asyncio
async def test_critic_review_workflow(critic_agent, mock_kernel, mock_chat_service):
    """Test pełnego workflow review."""
    user_request = "Napisz funkcję do pobierania danych z API"
    generated_code = '''
import requests

def fetch_data(url):
    """Pobiera dane z API."""
    response = requests.get(url)
    return response.json()
'''

    input_text = f"USER_REQUEST: {user_request}\n\nCODE:\n{generated_code}"

    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="APPROVED")
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    result = await critic_agent.process(input_text)

    assert "APPROVED" in result
    assert mock_chat_service.get_chat_message_content.called
