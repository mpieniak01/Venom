"""Actual MAF GroupChat workflow tests; participant models use deterministic fixtures."""

import asyncio

import pytest

from venom_core.core import council as module
from venom_core.core.council import CouncilConfig, CouncilSession


class Participant:
    SYSTEM_PROMPT = "fixture"
    PLANNING_PROMPT = "fixture"

    def __init__(self, name, calls, response=None):
        self.name = name
        self.calls = calls
        self.response = response

    async def process(self, text):
        self.calls.append((self.name, text))
        return self.response or (
            "approved\nTERMINATE" if self.name == "Guardian" else f"{self.name} result"
        )


def session(calls, **overrides):
    actors = {
        name: Participant(name, calls)
        for name in ("Architect", "Coder", "Critic", "Guardian")
    }
    actors.update(overrides)
    config = CouncilConfig(
        actors["Coder"], actors["Critic"], actors["Architect"], actors["Guardian"], {}
    )
    return CouncilSession(*config.create_council())


@pytest.mark.asyncio
async def test_native_group_chat_executes_graph_and_guardian_termination():
    calls = []
    run = session(calls)
    result = await run.run("fixture task")
    assert [name for name, text in calls] == [
        "Architect",
        "Coder",
        "Critic",
        "Coder",
        "Guardian",
    ]
    assert run.get_message_count() == 6
    assert "Zadanie zakończone sukcesem" in result
    assert "fixture task" in calls[-1][1]
    assert "Critic result" in calls[-1][1]


@pytest.mark.asyncio
async def test_only_guardian_can_terminate_native_workflow():
    calls = []
    run = session(calls, Coder=Participant("Coder", calls, "TERMINATE"))
    assert "Zadanie zakończone sukcesem" in await run.run("task")
    assert calls[-1][0] == "Guardian"


@pytest.mark.asyncio
async def test_native_round_limit_returns_incomplete_not_success():
    calls = []
    run = session(calls, Guardian=Participant("Guardian", calls, "repair required"))
    run.group_chat.max_round = 7
    result = await run.run("task")
    assert len(calls) == 7
    assert "Dyskusja przerwana" in result
    assert "Zadanie zakończone sukcesem" not in result


@pytest.mark.asyncio
async def test_participant_failure_is_reported_without_success():
    class Broken(Participant):
        async def process(self, text):
            raise RuntimeError("fixture_provider_error")

    run = session([], Architect=Broken("Architect", []))
    result = await run.run("task")
    assert "Błąd" in result
    assert "Zadanie zakończone sukcesem" not in result


@pytest.mark.asyncio
async def test_native_timeout_cancels_participant(monkeypatch):
    cancelled = asyncio.Event()

    class Slow(Participant):
        async def process(self, text):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    monkeypatch.setattr(module, "COUNCIL_SESSION_TIMEOUT", 0.02)
    run = session([], Architect=Slow("Architect", []))
    assert "timeout" in await run.run("task")
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_native_session_does_not_replay_an_earlier_run():
    calls = []
    run = session(calls)
    await run.run("first task")
    calls.clear()
    await run.run("second task")
    assert "first task" not in calls[0][1]
    assert "second task" in calls[0][1]


@pytest.mark.asyncio
async def test_invalid_transition_never_invokes_an_actor():
    calls = []
    run = session(calls)
    run.group_chat.allowed_or_disallowed_speaker_transitions.clear()
    result = await run.run("task")
    assert calls == []
    assert "council_transition_not_allowed" in result
