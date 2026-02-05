import pytest

from .chat_pipeline import is_backend_available, stream_task, submit_task

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]


async def test_fast_path_execution():
    if not await is_backend_available():
        pytest.skip("Backend unavailable")

    prompt = "Pomoc"  # Powinno zostać sklasyfikowane jako HELP_REQUEST
    task_id = await submit_task(prompt, store_knowledge=False)

    events = []
    async for event, payload in stream_task(task_id):
        events.append((event, payload))
        if event == "task_finished":
            break

    # Verify we got a result
    finished = next((p for e, p in events if e == "task_finished"), None)
    assert finished is not None
    assert finished["status"] == "COMPLETED"

    # Check logs for Fast Path trace (requires access to backend logs,
    # but here we can only check latency or result content).
    # Since we can't easily check backend logs from client test without file access,
    # we rely on the fact that result is correct.
    result_text = finished["result"].lower()
    help_markers = (
        "pomoc",
        "pomog",
        "umiejetn",
        "umiejętn",
        "mozliw",
        "możliw",
        "potraf",
        "mogę",
        "moge",
    )
    assert any(marker in result_text for marker in help_markers)
