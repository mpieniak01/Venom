from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from venom_core.agents.ux_analyst import UXAnalystAgent


@pytest.fixture
def mock_kernel():
    kernel = MagicMock()
    kernel.get_service.return_value = MagicMock()
    return kernel


@pytest.fixture
def ux_analyst(mock_kernel):
    with patch("venom_core.agents.ux_analyst.SETTINGS") as mock_settings:
        mock_settings.WORKSPACE_ROOT = "/tmp/test_workspace"
        agent = UXAnalystAgent(mock_kernel)
        return agent


def test_initialization(ux_analyst):
    assert ux_analyst.logs_dir == Path("/tmp/test_workspace/simulation_logs")
    assert "Jesteś ekspertem UX" in ux_analyst.SYSTEM_PROMPT


def test_load_session_logs_valid(ux_analyst):
    log_content = '{"event_type": "test_event", "session_id": "123"}\n'
    mock_file = Path("/tmp/test_log.jsonl")

    with patch("builtins.open", mock_open(read_data=log_content)):
        with patch.object(Path, "exists", return_value=True):
            events = ux_analyst._load_session_logs([mock_file])

    assert len(events) == 1
    assert events[0]["event_type"] == "test_event"
    assert events[0]["session_id"] == "123"


def test_load_session_logs_missing(ux_analyst):
    mock_file = Path("/tmp/missing_log.jsonl")

    with patch.object(Path, "exists", return_value=False):
        events = ux_analyst._load_session_logs([mock_file])

    assert len(events) == 0


def test_perform_analysis_logic(ux_analyst):
    events = [
        {"event_type": "session_start", "session_id": "s1", "persona_name": "Senior"},
        {
            "event_type": "frustration_increase",
            "session_id": "s1",
            "reason": "UI confusing",
            "frustration_level": 5,
        },
        {
            "event_type": "session_end",
            "session_id": "s1",
            "goal_achieved": True,
            "frustration_level": 5,
            "persona_name": "Senior",
        },
        {"event_type": "session_start", "session_id": "s2", "persona_name": "Junior"},
        {
            "event_type": "session_end",
            "session_id": "s2",
            "goal_achieved": False,
            "rage_quit": True,
            "frustration_level": 10,
            "persona_name": "Junior",
        },
    ]

    result = ux_analyst._perform_analysis(events)

    summary = result["summary"]
    assert summary["total_sessions"] == 2
    assert summary["successful_sessions"] == 1
    assert summary["rage_quits"] == 1
    assert summary["avg_frustration"] == 7.5

    top_problems = result["top_problems"]
    assert len(top_problems) == 1
    assert top_problems[0]["problem"] == "UI confusing"

    heatmap = result["frustration_heatmap"]
    # Junior failed, so failure_rate should be 100%
    junior_metric = next(h for h in heatmap if h["persona"] == "Junior")
    assert junior_metric["failure_rate"] == 100.0

    # Senior succeeded, failure_rate 0%
    senior_metric = next(h for h in heatmap if h["persona"] == "Senior")
    assert senior_metric["failure_rate"] == 0.0


@pytest.mark.asyncio
async def test_process_analysis_request(ux_analyst):
    # Mock analyze_sessions and generate_recommendations
    analysis_result = {
        "summary": {
            "total_sessions": 10,
            "successful_sessions": 8,
            "rage_quits": 1,
            "success_rate": 80.0,
            "avg_frustration": 2.5,
        },
        "top_problems": [{"problem": "Test Problem", "occurrences": 5}],
        "frustration_heatmap": [
            {"persona": "Senior", "failure_rate": 20.0, "sessions": 5}
        ],
    }

    # We patch analyze_sessions (sync)
    with patch.object(ux_analyst, "analyze_sessions", return_value=analysis_result):
        # We patch _invoke_chat_with_fallbacks (async) because patching generate_recommendations is problematic
        with patch.object(
            ux_analyst, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = "## Rekomendacje: Popraw UI"

            # Using "analiza" to match the condition in process()
            response = await ux_analyst.process("Proszę o analiza UX")

            assert "RAPORT ANALIZY UX" in response
            assert "Sesji: 10" in response
            assert "Test Problem (5x)" in response
            # Note: Since we mock the chat result, this string comes from there
            assert "Rekomendacje: Popraw UI" in response


@pytest.mark.asyncio
async def test_process_normal_chat(ux_analyst):
    # Mock invoke_chat
    with patch.object(
        ux_analyst, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
    ) as mock_chat:
        mock_chat.return_value = "To jest odpowiedź LLM"

        response = await ux_analyst.process("Cześć, co robis?")

        assert "To jest odpowiedź LLM" in response
        mock_chat.assert_called_once()
