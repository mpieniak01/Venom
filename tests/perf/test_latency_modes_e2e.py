"""E2E latency testy dla trybów: fast (direct), normal, complex."""

import pytest

from .latency_scenarios import run_latency_modes_e2e

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.performance,
    pytest.mark.live_venom,
    pytest.mark.live_model,
]


@pytest.mark.smoke
async def test_latency_modes_e2e():
    await run_latency_modes_e2e()
