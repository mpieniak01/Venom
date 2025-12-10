"""Testy dla optymalizacji samo-naprawy w CodeReviewLoop."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from venom_core.agents.coder import CoderAgent
from venom_core.agents.critic import CriticAgent
from venom_core.core.flows.code_review import (
    MAX_ERROR_REPEATS,
    MAX_HEALING_COST,
    MAX_REPAIR_ATTEMPTS,
    CodeReviewLoop,
)
from venom_core.core.state_manager import StateManager
from venom_core.core.token_economist import TokenEconomist
from venom_core.execution.skills.file_skill import FileSkill


@pytest.fixture
def mock_state_manager():
    """Fixture dla mockowego StateManager."""
    manager = MagicMock(spec=StateManager)
    manager.add_log = MagicMock()
    return manager


@pytest.fixture
def mock_coder_agent():
    """Fixture dla mockowego CoderAgent."""
    agent = MagicMock(spec=CoderAgent)
    agent.process = AsyncMock()
    return agent


@pytest.fixture
def mock_critic_agent():
    """Fixture dla mockowego CriticAgent."""
    agent = MagicMock(spec=CriticAgent)
    agent.process = AsyncMock()
    agent.analyze_error = MagicMock()
    return agent


@pytest.fixture
def mock_token_economist():
    """Fixture dla mockowego TokenEconomist."""
    economist = MagicMock(spec=TokenEconomist)
    economist.estimate_request_cost = MagicMock(
        return_value={"total_cost_usd": 0.01}
    )
    return economist


@pytest.fixture
def mock_file_skill():
    """Fixture dla mockowego FileSkill."""
    skill = MagicMock(spec=FileSkill)
    skill.read_file = AsyncMock()
    return skill


# --- Test wykrywania pętli błędów ---


@pytest.mark.asyncio
async def test_error_loop_detection(
    mock_state_manager,
    mock_coder_agent,
    mock_critic_agent,
    mock_token_economist,
    mock_file_skill,
):
    """Test wykrywania pętli błędów (ten sam błąd powtarza się)."""
    loop = CodeReviewLoop(
        mock_state_manager,
        mock_coder_agent,
        mock_critic_agent,
        mock_token_economist,
        mock_file_skill,
    )

    task_id = uuid4()

    # Mock Coder - zawsze zwraca ten sam kod
    mock_coder_agent.process.return_value = "bad_code = 'error'"

    # Mock Critic - zawsze zwraca ten sam błąd
    same_error = "ODRZUCONO - hardcoded string"
    mock_critic_agent.process.return_value = same_error
    mock_critic_agent.analyze_error.return_value = {
        "analysis": "Same error",
        "suggested_fix": "Fix it",
        "target_file_change": None,
    }

    # Execute
    result = await loop.execute(task_id, "Napisz kod")

    # Assert - powinno wykryć pętlę i przerwać
    assert "🔄 Wykryto pętlę błędów" in result
    assert f"{MAX_ERROR_REPEATS} razy" in result
    # Powinno wykonać dokładnie MAX_ERROR_REPEATS wywołań (pierwsze + naprawy do wykrycia pętli)
    assert mock_coder_agent.process.call_count == MAX_ERROR_REPEATS


# --- Test limitu budżetu ---


@pytest.mark.asyncio
async def test_budget_exceeded(
    mock_state_manager,
    mock_coder_agent,
    mock_critic_agent,
    mock_token_economist,
    mock_file_skill,
):
    """Test przerwania gdy przekroczono budżet sesji."""
    loop = CodeReviewLoop(
        mock_state_manager,
        mock_coder_agent,
        mock_critic_agent,
        mock_token_economist,
        mock_file_skill,
    )

    task_id = uuid4()

    # Mock wysokiego kosztu - każda iteracja kosztuje więcej niż limit
    mock_token_economist.estimate_request_cost.return_value = {
        "total_cost_usd": MAX_HEALING_COST + 0.1
    }

    mock_coder_agent.process.return_value = "some_code"
    mock_critic_agent.process.return_value = "ODRZUCONO"
    mock_critic_agent.analyze_error.return_value = {
        "analysis": "Error",
        "suggested_fix": "Fix",
        "target_file_change": None,
    }

    # Execute
    result = await loop.execute(task_id, "Napisz kod")

    # Assert - powinno przerwać z powodu budżetu
    assert "Przekroczono budżet sesji" in result
    assert f"{MAX_HEALING_COST}" in result
    # Powinno wykonać tylko jedną iterację
    assert mock_coder_agent.process.call_count == 1


# --- Test dynamicznej zmiany pliku docelowego ---


@pytest.mark.asyncio
async def test_target_file_switching(
    mock_state_manager,
    mock_coder_agent,
    mock_critic_agent,
    mock_token_economist,
    mock_file_skill,
):
    """Test przełączania kontekstu naprawy na inny plik."""
    loop = CodeReviewLoop(
        mock_state_manager,
        mock_coder_agent,
        mock_critic_agent,
        mock_token_economist,
        mock_file_skill,
    )

    task_id = uuid4()

    # Mock Coder
    mock_coder_agent.process.side_effect = [
        "first_code",  # Pierwsza próba
        "fixed_code",  # Druga próba po zmianie pliku
    ]

    # Mock Critic - pierwsza próba odrzuca i wskazuje inny plik
    mock_critic_agent.process.side_effect = [
        "ODRZUCONO - błąd w api.py",  # Pierwsza iteracja
        "APPROVED",  # Druga iteracja - zaakceptowane
    ]

    # Mock analyze_error - pierwsza próba wskazuje api.py
    mock_critic_agent.analyze_error.side_effect = [
        {
            "analysis": "ImportError in api.py",
            "suggested_fix": "Add missing function",
            "target_file_change": "api.py",
        },
        {
            "analysis": "Fixed",
            "suggested_fix": "None",
            "target_file_change": None,
        },
    ]

    # Mock read_file - zwróć zawartość api.py
    mock_file_skill.read_file.return_value = "# api.py content"

    # Execute
    result = await loop.execute(task_id, "Napisz test")

    # Assert
    assert result == "fixed_code"
    assert mock_coder_agent.process.call_count == 2
    assert mock_critic_agent.process.call_count == 2

    # Sprawdź czy zalogowano zmianę pliku
    log_calls = [call[0][1] for call in mock_state_manager.add_log.call_args_list]
    assert any("🔀 Zmiana celu naprawy" in log for log in log_calls)
    assert any("api.py" in log for log in log_calls)


# --- Test zatwierdzenia przy pierwszej próbie ---


@pytest.mark.asyncio
async def test_approval_first_attempt_with_cost_tracking(
    mock_state_manager,
    mock_coder_agent,
    mock_critic_agent,
    mock_token_economist,
    mock_file_skill,
):
    """Test zatwierdzenia kodu w pierwszej próbie z trackingiem kosztów."""
    loop = CodeReviewLoop(
        mock_state_manager,
        mock_coder_agent,
        mock_critic_agent,
        mock_token_economist,
        mock_file_skill,
    )

    task_id = uuid4()

    # Mock
    mock_coder_agent.process.return_value = "good_code"
    mock_critic_agent.process.return_value = "APPROVED"
    mock_token_economist.estimate_request_cost.return_value = {
        "total_cost_usd": 0.005
    }

    # Execute
    result = await loop.execute(task_id, "Napisz funkcję")

    # Assert
    assert result == "good_code"
    assert mock_coder_agent.process.call_count == 1
    assert mock_critic_agent.process.call_count == 1

    # Sprawdź czy zalogowano koszt
    log_calls = [call[0][1] for call in mock_state_manager.add_log.call_args_list]
    assert any("Koszt sesji:" in log for log in log_calls)


# --- Test analizy błędu w CriticAgent ---


def test_critic_analyze_error_with_json():
    """Test parsowania JSON z odpowiedzi Krytyka."""
    from venom_core.agents.critic import CriticAgent

    # Nie potrzebujemy pełnego kernela dla tego testu
    critic = MagicMock(spec=CriticAgent)
    critic.analyze_error = CriticAgent.analyze_error.__get__(critic, CriticAgent)

    # Test z poprawnym JSON
    error_with_json = """
    Kod zawiera błąd ImportError.
    {
      "analysis": "Function missing in utils.py",
      "suggested_fix": "Add process_data function",
      "target_file_change": "utils.py"
    }
    Proszę naprawić.
    """

    result = critic.analyze_error(error_with_json)

    assert result["analysis"] == "Function missing in utils.py"
    assert result["suggested_fix"] == "Add process_data function"
    assert result["target_file_change"] == "utils.py"


def test_critic_analyze_error_without_json():
    """Test parsowania błędu bez JSON (fallback)."""
    from venom_core.agents.critic import CriticAgent

    critic = MagicMock(spec=CriticAgent)
    critic.analyze_error = CriticAgent.analyze_error.__get__(critic, CriticAgent)

    # Test bez JSON - tylko tekst
    error_plain = "ODRZUCONO - hardcoded credentials"

    result = critic.analyze_error(error_plain)

    assert "hardcoded credentials" in result["analysis"]
    assert result["suggested_fix"] is not None
    assert result["target_file_change"] is None


# --- Test maksymalnej liczby prób ---


@pytest.mark.asyncio
async def test_max_attempts_exceeded_with_new_features(
    mock_state_manager,
    mock_coder_agent,
    mock_critic_agent,
    mock_token_economist,
    mock_file_skill,
):
    """Test wyczerpania limitu prób z nowymi funkcjami."""
    loop = CodeReviewLoop(
        mock_state_manager,
        mock_coder_agent,
        mock_critic_agent,
        mock_token_economist,
        mock_file_skill,
    )

    task_id = uuid4()

    # Mock - różne błędy (nie pętla), ale nigdy APPROVED
    mock_coder_agent.process.return_value = "code"
    mock_critic_agent.process.side_effect = [
        "ODRZUCONO - błąd 1",
        "ODRZUCONO - błąd 2",
        "ODRZUCONO - błąd 3",
    ]
    mock_critic_agent.analyze_error.return_value = {
        "analysis": "Different error each time",
        "suggested_fix": "Fix",
        "target_file_change": None,
    }

    # Execute
    result = await loop.execute(task_id, "Napisz kod")

    # Assert
    assert "⚠️ OSTRZEŻENIE" in result
    assert "Wyczerpano limit prób" in result or f"{MAX_REPAIR_ATTEMPTS} próbach" in result
    assert mock_coder_agent.process.call_count == MAX_REPAIR_ATTEMPTS + 1
