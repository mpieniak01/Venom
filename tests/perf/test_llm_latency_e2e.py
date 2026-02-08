"""E2E testy latencji LLM: aktywacja modelu + pomiar odpowiedzi."""

import pytest

from .latency_scenarios import run_llm_latency_e2e

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]


@pytest.mark.smoke
async def test_llm_latency_e2e():
    await run_llm_latency_e2e()
