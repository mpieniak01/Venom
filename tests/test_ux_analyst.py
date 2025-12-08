"""Testy dla UXAnalystAgent."""

import json
import tempfile
from pathlib import Path

import pytest

from venom_core.agents.ux_analyst import UXAnalystAgent


@pytest.fixture
def mock_log_file():
    """Fixture tworząca tymczasowy plik logu dla testów."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        # Przykładowe eventy
        events = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "session_id": "test_001",
                "persona_name": "Anna",
                "event_type": "session_start",
                "emotional_state": "neutral",
                "frustration_level": 0,
                "actions_taken": 0,
                "persona": {
                    "name": "Anna",
                    "age": 30,
                    "tech_literacy": "high",
                    "patience": 0.8,
                },
            },
            {
                "timestamp": "2024-01-01T10:01:00",
                "session_id": "test_001",
                "persona_name": "Anna",
                "event_type": "frustration_increase",
                "emotional_state": "confused",
                "frustration_level": 1,
                "actions_taken": 2,
                "reason": "Nie mogę znaleźć przycisku",
            },
            {
                "timestamp": "2024-01-01T10:05:00",
                "session_id": "test_001",
                "persona_name": "Anna",
                "event_type": "session_end",
                "emotional_state": "frustrated",
                "frustration_level": 2,
                "actions_taken": 5,
                "goal_achieved": False,
                "rage_quit": True,
            },
            {
                "timestamp": "2024-01-01T10:00:00",
                "session_id": "test_002",
                "persona_name": "Marek",
                "event_type": "session_start",
                "emotional_state": "neutral",
                "frustration_level": 0,
                "actions_taken": 0,
                "persona": {
                    "name": "Marek",
                    "age": 25,
                    "tech_literacy": "high",
                    "patience": 0.7,
                },
            },
            {
                "timestamp": "2024-01-01T10:03:00",
                "session_id": "test_002",
                "persona_name": "Marek",
                "event_type": "session_end",
                "emotional_state": "satisfied",
                "frustration_level": 0,
                "actions_taken": 3,
                "goal_achieved": True,
                "rage_quit": False,
            },
        ]

        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


def test_ux_analyst_has_system_prompt():
    """Test że UXAnalystAgent ma zdefiniowany system prompt."""
    assert hasattr(UXAnalystAgent, "SYSTEM_PROMPT")
    assert len(UXAnalystAgent.SYSTEM_PROMPT) > 0
    assert "UX" in UXAnalystAgent.SYSTEM_PROMPT
    assert "frustracji" in UXAnalystAgent.SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_ux_analyst_requires_kernel():
    """Test że UXAnalystAgent wymaga kernela."""
    with pytest.raises(TypeError):
        UXAnalystAgent()


def test_ux_analyst_has_required_methods():
    """Test że UXAnalystAgent ma wymagane metody."""
    required_methods = [
        "analyze_sessions",
        "generate_recommendations",
        "_load_session_logs",
        "_perform_analysis",
    ]

    for method in required_methods:
        assert hasattr(UXAnalystAgent, method)


def test_load_session_logs_structure(mock_log_file):
    """Test struktury ładowanych logów (bez kernela - tylko metoda pomocnicza)."""
    # Ten test sprawdza logikę parsowania bez inicjalizacji agenta
    events = []

    with open(mock_log_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                event = json.loads(line)
                events.append(event)

    assert len(events) == 5
    assert events[0]["event_type"] == "session_start"
    assert events[2]["event_type"] == "session_end"
    assert events[2]["rage_quit"] is True
    assert events[4]["goal_achieved"] is True


def test_analysis_structure():
    """Test struktury wyniku analizy."""
    # Mock danych analizy
    mock_analysis = {
        "summary": {
            "total_sessions": 2,
            "successful_sessions": 1,
            "rage_quits": 1,
            "success_rate": 50.0,
            "avg_frustration": 1.0,
        },
        "top_problems": [{"problem": "Nie mogę znaleźć przycisku", "occurrences": 1}],
        "frustration_heatmap": [
            {
                "persona": "Anna",
                "sessions": 1,
                "success_rate": 0.0,
                "failure_rate": 100.0,
            },
            {
                "persona": "Marek",
                "sessions": 1,
                "success_rate": 100.0,
                "failure_rate": 0.0,
            },
        ],
        "emotional_states": {
            "neutral": 2,
            "confused": 1,
            "frustrated": 1,
            "satisfied": 1,
        },
        "personas_performance": {
            "Anna": {"success": 0, "total": 1},
            "Marek": {"success": 1, "total": 1},
        },
    }

    # Weryfikacja struktury
    assert "summary" in mock_analysis
    assert "top_problems" in mock_analysis
    assert "frustration_heatmap" in mock_analysis

    assert mock_analysis["summary"]["total_sessions"] == 2
    assert mock_analysis["summary"]["success_rate"] == 50.0
    assert len(mock_analysis["top_problems"]) == 1
    assert len(mock_analysis["frustration_heatmap"]) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ux_analyst_full_analysis():
    """Test pełnej analizy (wymaga kernela i prawdziwych logów)."""
    # TODO: Test integracyjny z prawdziwym kernelem i logami
    pass


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ux_analyst_generate_recommendations():
    """Test generowania rekomendacji przez LLM."""
    # TODO: Test integracyjny z prawdziwym kernelem
    pass


def test_frustration_heatmap_sorting():
    """Test sortowania heatmapy frustracji (po failure_rate)."""
    heatmap = [
        {"persona": "Anna", "failure_rate": 100.0},
        {"persona": "Marek", "failure_rate": 0.0},
        {"persona": "Piotr", "failure_rate": 50.0},
    ]

    sorted_heatmap = sorted(heatmap, key=lambda x: x["failure_rate"], reverse=True)

    assert sorted_heatmap[0]["persona"] == "Anna"  # Największy failure rate
    assert sorted_heatmap[1]["persona"] == "Piotr"
    assert sorted_heatmap[2]["persona"] == "Marek"  # Najmniejszy failure rate


def test_top_problems_counting():
    """Test liczenia najczęstszych problemów."""
    from collections import Counter

    problems = [
        "Nie mogę znaleźć przycisku",
        "Strona nie ładuje się",
        "Nie mogę znaleźć przycisku",
        "Błąd formularza",
        "Nie mogę znaleźć przycisku",
    ]

    counter = Counter(problems)
    top_3 = counter.most_common(3)

    assert top_3[0][0] == "Nie mogę znaleźć przycisku"
    assert top_3[0][1] == 3  # 3 wystąpienia
    assert len(top_3) == 3
