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

    async def deliberate(self, text, **kwargs):
        return await self.process(text)

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
    with pytest.raises(module.CouncilExecutionError, match="no_guardian_approval"):
        await run.run("task")
    assert len(calls) == 7
    assert "Dyskusja przerwana" in run._extract_result()


@pytest.mark.asyncio
async def test_participant_failure_is_reported_without_success():
    class Broken(Participant):
        async def process(self, text):
            raise RuntimeError("fixture_provider_error")

    run = session([], Architect=Broken("Architect", []))
    with pytest.raises(module.CouncilExecutionError, match="fixture_provider_error"):
        await run.run("task")


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
    with pytest.raises(module.CouncilExecutionError, match="timeout"):
        await run.run("task")
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
    with pytest.raises(
        module.CouncilExecutionError, match="council_transition_not_allowed"
    ):
        await run.run("task")
    assert calls == []


@pytest.mark.asyncio
async def test_council_uses_deliberation_and_keeps_request_budget():
    calls = []

    class Consultation(Participant):
        async def process(self, text):
            raise AssertionError("Nested standalone workflow must not execute")

        async def deliberate(self, text, **kwargs):
            calls.append((self.name, kwargs))
            return "verified\nTERMINATE" if self.name == "Guardian" else "role result"

    actors = {
        name: Consultation(name, [])
        for name in ("Architect", "Coder", "Critic", "Guardian")
    }
    run = session([], **actors)
    await run.run("text task", generation_params={"max_tokens": 32, "temperature": 0})
    assert calls and all(
        kwargs["generation_params"] == {"max_tokens": 32, "temperature": 0}
        for _, kwargs in calls
    )
    assert all("Council" in kwargs["system_message"] for _, kwargs in calls)
    assert (
        next(kwargs for name, kwargs in calls if name == "Architect")[
            "enable_functions"
        ]
        is False
    )
    assert (
        next(kwargs for name, kwargs in calls if name == "Guardian")["enable_functions"]
        is True
    )
