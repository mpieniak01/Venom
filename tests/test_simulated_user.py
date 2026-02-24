"""Unit tests for SimulatedUserAgent."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.agents.simulated_user import EmotionalState, SimulatedUserAgent
from venom_core.simulation.persona_factory import Persona, TechLiteracy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_kernel():
    """Mock Semantic Kernel."""
    kernel = MagicMock()
    kernel.add_plugin = MagicMock()
    kernel.get_service.return_value = MagicMock()
    return kernel


@pytest.fixture
def persona():
    """Basic test persona."""
    return Persona(
        name="Test User",
        age=30,
        tech_literacy=TechLiteracy.MEDIUM,
        patience=0.5,
        goal="Find the login page",
        traits=["curious", "patient"],
        frustration_threshold=5,
    )


@pytest.fixture
def agent(mock_kernel, persona, tmp_path):
    """SimulatedUserAgent instance with mocked BrowserSkill."""
    with patch("venom_core.agents.simulated_user.BrowserSkill") as mock_browser_cls:
        mock_browser_cls.return_value = MagicMock()
        return SimulatedUserAgent(
            kernel=mock_kernel,
            persona=persona,
            target_url="http://example.com",
            session_id="test-session-001",
            workspace_root=str(tmp_path),
        )


# ---------------------------------------------------------------------------
# EmotionalState enum
# ---------------------------------------------------------------------------


def test_emotional_state_values():
    """All expected emotional state values are present."""
    assert EmotionalState.NEUTRAL == "neutral"
    assert EmotionalState.CURIOUS == "curious"
    assert EmotionalState.CONFUSED == "confused"
    assert EmotionalState.FRUSTRATED == "frustrated"
    assert EmotionalState.SATISFIED == "satisfied"
    assert EmotionalState.ANGRY == "angry"


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def test_agent_initialization(agent, persona):
    """Agent initialises with correct default values."""
    assert agent.persona is persona
    assert agent.target_url == "http://example.com"
    assert agent.session_id == "test-session-001"
    assert agent.emotional_state == EmotionalState.NEUTRAL
    assert agent.frustration_level == 0
    assert agent.actions_taken == 0
    assert agent.errors_encountered == 0
    assert agent.goal_achieved is False
    assert agent.rage_quit is False


def test_logs_dir_created(agent):
    """Logs directory is created during initialisation."""
    assert agent.logs_dir.exists()


def test_session_start_log_written(agent):
    """A session_start entry is written to the log file on init."""
    assert agent.log_file.exists()
    with open(agent.log_file, encoding="utf-8") as f:
        first_line = f.readline()
    event = json.loads(first_line)
    assert event["event_type"] == "session_start"
    assert event["session_id"] == "test-session-001"


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------


def test_build_system_prompt_contains_persona_info(agent, persona):
    """System prompt includes persona name and goal."""
    prompt = agent._build_system_prompt()
    assert persona.name in prompt
    assert persona.goal in prompt
    assert str(persona.age) in prompt


def test_build_system_prompt_low_patience(mock_kernel, tmp_path):
    """Low-patience persona gets an impatient description."""
    impatient_persona = Persona(
        name="Impatient User",
        age=25,
        tech_literacy=TechLiteracy.LOW,
        patience=0.1,
        goal="Buy a product",
        traits=["impulsive"],
        frustration_threshold=3,
    )
    with patch("venom_core.agents.simulated_user.BrowserSkill") as mock_browser_cls:
        mock_browser_cls.return_value = MagicMock()
        agent = SimulatedUserAgent(
            kernel=mock_kernel,
            persona=impatient_persona,
            target_url="http://example.com",
            session_id="impatient-session",
            workspace_root=str(tmp_path),
        )
    prompt = agent._build_system_prompt()
    assert "niecierpliw" in prompt  # matches "niecierpliwy"


def test_build_system_prompt_high_patience(mock_kernel, tmp_path):
    """High-patience persona gets a patient description."""
    patient_persona = Persona(
        name="Patient User",
        age=50,
        tech_literacy=TechLiteracy.HIGH,
        patience=0.9,
        goal="Read documentation",
        traits=["methodical"],
        frustration_threshold=10,
    )
    with patch("venom_core.agents.simulated_user.BrowserSkill") as mock_browser_cls:
        mock_browser_cls.return_value = MagicMock()
        agent = SimulatedUserAgent(
            kernel=mock_kernel,
            persona=patient_persona,
            target_url="http://example.com",
            session_id="patient-session",
            workspace_root=str(tmp_path),
        )
    prompt = agent._build_system_prompt()
    assert "cierpliw" in prompt  # matches "cierpliwy"


# ---------------------------------------------------------------------------
# _increase_frustration
# ---------------------------------------------------------------------------


def test_increase_frustration_increments_level(agent):
    """_increase_frustration increments frustration_level and errors_encountered."""
    agent._increase_frustration("Test reason")
    assert agent.frustration_level == 1
    assert agent.errors_encountered == 1


def test_increase_frustration_sets_confused(agent):
    """First frustration event changes state to CONFUSED."""
    agent._increase_frustration("Minor issue")
    assert agent.emotional_state == EmotionalState.CONFUSED


def test_increase_frustration_sets_frustrated(agent):
    """Reaching ~70% of threshold sets state to FRUSTRATED."""
    # threshold=5, 70% = 3.5, so at frustration_level=4 (>= 3.5)
    for i in range(4):
        agent._increase_frustration(f"Issue {i}")
    assert agent.emotional_state == EmotionalState.FRUSTRATED


def test_increase_frustration_sets_angry_and_rage_quit(agent):
    """Reaching the threshold sets state to ANGRY and triggers rage_quit."""
    for i in range(5):
        agent._increase_frustration(f"Issue {i}")
    assert agent.emotional_state == EmotionalState.ANGRY
    assert agent.rage_quit is True


# ---------------------------------------------------------------------------
# _set_emotional_state
# ---------------------------------------------------------------------------


def test_set_emotional_state_changes_state(agent):
    """_set_emotional_state updates the emotional state."""
    agent._set_emotional_state(EmotionalState.SATISFIED, "Goal reached")
    assert agent.emotional_state == EmotionalState.SATISFIED


def test_set_emotional_state_logs_event(agent):
    """_set_emotional_state writes an emotion_change event to the log."""
    agent._set_emotional_state(EmotionalState.CURIOUS, "Starting exploration")
    with open(agent.log_file, encoding="utf-8") as f:
        lines = f.readlines()
    events = [json.loads(line) for line in lines]
    emotion_events = [e for e in events if e["event_type"] == "emotion_change"]
    assert len(emotion_events) >= 1
    last = emotion_events[-1]
    assert last["new_state"] == EmotionalState.CURIOUS
    assert last["reason"] == "Starting exploration"


# ---------------------------------------------------------------------------
# get_session_summary
# ---------------------------------------------------------------------------


def test_get_session_summary_default(agent, persona):
    """Summary contains persona name and NOT achieved status by default."""
    summary = agent.get_session_summary()
    assert persona.name in summary
    assert "NIE OSIĄGNIĘTO CELU" in summary


def test_get_session_summary_goal_achieved(agent):
    """Summary reflects goal achieved when flag is set."""
    agent.goal_achieved = True
    summary = agent.get_session_summary()
    assert "CEL OSIĄGNIĘTY" in summary


def test_get_session_summary_rage_quit(agent):
    """Summary reflects RAGE QUIT when flag is set."""
    agent.rage_quit = True
    summary = agent.get_session_summary()
    assert "RAGE QUIT" in summary


# ---------------------------------------------------------------------------
# process – rage_quit guard (pure logic, no LLM call needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_returns_early_on_rage_quit(agent, persona):
    """process() short-circuits and returns rage-quit message when rage_quit=True."""
    agent.rage_quit = True
    result = await agent.process("Do something")
    assert persona.name in result
    assert "ZREZYGNOWAŁ" in result


@pytest.mark.asyncio
async def test_process_detects_frustration_keywords(agent):
    """process() calls _increase_frustration when response contains keywords."""
    with patch.object(
        agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
    ) as mock_chat:
        # Response includes a frustration keyword ("nie mogę znaleźć")
        mock_chat.return_value = "nie mogę znaleźć tego elementu"
        initial_frustration = agent.frustration_level
        await agent.process("Find the button")
        assert agent.frustration_level > initial_frustration


@pytest.mark.asyncio
async def test_process_handles_exception(agent):
    """process() handles exceptions by increasing frustration and returning error msg."""
    with patch.object(
        agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
    ) as mock_chat:
        mock_chat.side_effect = RuntimeError("LLM unavailable")
        result = await agent.process("Do something")
        assert "❌" in result
        assert agent.errors_encountered > 0
