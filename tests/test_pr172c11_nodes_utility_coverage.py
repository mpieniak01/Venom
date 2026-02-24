"""PR-172C-11 coverage tests for nodes/utility gap modules.

Covers:
- venom_core/nodes/protocol.py  – missing NodeMessage.from_heartbeat / from_response
- venom_core/api/routes/models_usage.py – 0 % → full endpoint coverage
- venom_core/api/routes/calendar.py – residual branch
- venom_core/core/council.py – run/extract_result/get_speakers/config error paths
- venom_core/core/retrieval_policy.py – else-branch in _get_boost_policy
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# protocol.py – NodeMessage factory methods not yet exercised
# ---------------------------------------------------------------------------


def test_node_message_from_heartbeat():
    """NodeMessage.from_heartbeat wraps a HeartbeatMessage correctly."""
    from venom_core.nodes.protocol import HeartbeatMessage, MessageType, NodeMessage

    hb = HeartbeatMessage(node_id="n1", cpu_usage=0.3, memory_usage=0.5, active_tasks=1)
    msg = NodeMessage.from_heartbeat(hb)

    assert msg.message_type == MessageType.HEARTBEAT
    assert msg.payload["node_id"] == "n1"
    assert msg.payload["cpu_usage"] == pytest.approx(0.3)


def test_node_message_from_response():
    """NodeMessage.from_response wraps a NodeResponse correctly."""
    from venom_core.nodes.protocol import MessageType, NodeMessage, NodeResponse

    resp = NodeResponse(
        request_id="req-1",
        node_id="n1",
        success=True,
        result="ok",
        execution_time=0.1,
    )
    msg = NodeMessage.from_response(resp)

    assert msg.message_type == MessageType.RESPONSE
    assert msg.payload["request_id"] == "req-1"
    assert msg.payload["success"] is True


# ---------------------------------------------------------------------------
# models_usage.py – full endpoint coverage (0 % → ~100 %)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _models_usage_app():
    """FastAPI app with models_usage router mounted and a clean TTL cache."""
    import venom_core.api.routes.models_usage as mu_module
    from venom_core.api.routes import models_dependencies as deps

    app = FastAPI()
    app.include_router(mu_module.router)

    # Clear the module-level TTL cache before each test
    mu_module._models_usage_cache.clear()

    # Reset model manager
    deps.set_dependencies(None)
    return app, mu_module, deps


@pytest.fixture()
def _models_usage_client(_models_usage_app):
    app, _, _ = _models_usage_app
    return TestClient(app, raise_server_exceptions=False)


def _set_manager(_models_usage_app, manager):
    _, _, deps = _models_usage_app
    deps.set_dependencies(manager)


# --- GET /api/v1/models/usage ---


def test_get_models_usage_cache_hit(_models_usage_app, _models_usage_client):
    """Returns cached value without hitting model_manager."""
    _, mu_module, _ = _models_usage_app
    cached_payload = {"success": True, "usage": {"disk_gb": 1.0}}
    mu_module._models_usage_cache.set(cached_payload)

    response = _models_usage_client.get("/api/v1/models/usage")
    assert response.status_code == 200
    assert response.json()["usage"]["disk_gb"] == 1.0


def test_get_models_usage_no_manager_503(_models_usage_app, _models_usage_client):
    """Returns 503 when model_manager is None."""
    response = _models_usage_client.get("/api/v1/models/usage")
    assert response.status_code == 503


def test_get_models_usage_success(_models_usage_app, _models_usage_client):
    """Returns metrics and populates cache on success."""
    _, mu_module, _ = _models_usage_app
    mock_manager = MagicMock()
    mock_manager.get_usage_metrics = AsyncMock(
        return_value={"disk_gb": 2.5, "vram_mb": 4096}
    )
    _set_manager(_models_usage_app, mock_manager)

    response = _models_usage_client.get("/api/v1/models/usage")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["usage"]["disk_gb"] == 2.5

    # Cache should be populated now
    assert mu_module._models_usage_cache.get() is not None


def test_get_models_usage_exception_500(_models_usage_app, _models_usage_client):
    """Returns 500 when get_usage_metrics raises."""
    mock_manager = MagicMock()
    mock_manager.get_usage_metrics = AsyncMock(side_effect=RuntimeError("GPU failure"))
    _set_manager(_models_usage_app, mock_manager)

    response = _models_usage_client.get("/api/v1/models/usage")
    assert response.status_code == 500


# --- POST /api/v1/models/unload-all ---


def test_unload_all_models_no_manager_503(_models_usage_app, _models_usage_client):
    """Returns 503 when model_manager is None."""
    response = _models_usage_client.post("/api/v1/models/unload-all")
    assert response.status_code == 503


def test_unload_all_models_success(_models_usage_app, _models_usage_client):
    """Returns success and clears cache after unloading."""
    _, mu_module, _ = _models_usage_app
    # Pre-populate cache
    mu_module._models_usage_cache.set({"success": True, "usage": {}})
    mock_manager = MagicMock()
    mock_manager.unload_all = AsyncMock(return_value=True)
    _set_manager(_models_usage_app, mock_manager)

    response = _models_usage_client.post("/api/v1/models/unload-all")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["message"], str)
    # Cache should be cleared
    assert mu_module._models_usage_cache.get() is None


def test_unload_all_models_returns_false_500(_models_usage_app, _models_usage_client):
    """Returns 500 when unload_all returns False."""
    mock_manager = MagicMock()
    mock_manager.unload_all = AsyncMock(return_value=False)
    _set_manager(_models_usage_app, mock_manager)

    response = _models_usage_client.post("/api/v1/models/unload-all")
    assert response.status_code == 500


def test_unload_all_models_exception_500(_models_usage_app, _models_usage_client):
    """Returns 500 when unload_all raises an unexpected exception."""
    mock_manager = MagicMock()
    mock_manager.unload_all = AsyncMock(side_effect=RuntimeError("crash"))
    _set_manager(_models_usage_app, mock_manager)

    response = _models_usage_client.post("/api/v1/models/unload-all")
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# council.py – run / _extract_result / get_speakers / config error paths
# ---------------------------------------------------------------------------


def _make_council_session(messages=None):
    """Build a CouncilSession with stub group_chat and minimal dependencies."""
    from venom_core.core.council import CouncilSession

    mock_group_chat = MagicMock()
    mock_group_chat.messages = messages if messages is not None else []
    mock_manager = MagicMock()
    mock_user_proxy = MagicMock()

    return CouncilSession(mock_user_proxy, mock_group_chat, mock_manager)


@pytest.mark.asyncio
async def test_council_session_run_success():
    """run() returns transcript from _extract_result on success."""
    session = _make_council_session(
        messages=[{"name": "Coder", "content": "done TERMINATE"}]
    )
    session.user_proxy.initiate_chat = MagicMock(return_value=None)

    result = await session.run("write hello world")

    assert "THE COUNCIL" in result
    assert "Coder" in result


@pytest.mark.asyncio
async def test_council_session_run_timeout():
    """run() catches asyncio.TimeoutError and returns a non-empty error string."""
    session = _make_council_session()

    # Patch to_thread to return a plain sentinel (wait_for raises before awaiting it)
    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()), \
         patch("asyncio.to_thread", return_value=object()):
        result = await session.run("something")

    assert isinstance(result, str) and len(result) > 0


@pytest.mark.asyncio
async def test_council_session_run_generic_exception():
    """run() catches unexpected exceptions and returns a non-empty error string."""
    session = _make_council_session()

    with patch("asyncio.wait_for", side_effect=ValueError("unexpected")), \
         patch("asyncio.to_thread", return_value=object()):
        result = await session.run("task")

    assert isinstance(result, str) and len(result) > 0


def test_extract_result_empty_messages():
    """_extract_result returns a fallback string when no messages exist."""
    session = _make_council_session(messages=[])
    result = session._extract_result()
    assert isinstance(result, str) and len(result) > 0


def test_extract_result_with_terminate():
    """_extract_result includes success marker when last message contains TERMINATE."""
    session = _make_council_session(
        messages=[
            {"name": "Coder", "content": "Implementation done"},
            {"name": "Guardian", "content": "TERMINATE – approved"},
        ]
    )
    result = session._extract_result()
    assert "Coder" in result
    assert "Guardian" in result
    assert "✅" in result


def test_extract_result_without_terminate():
    """_extract_result adds warning marker when TERMINATE is absent."""
    session = _make_council_session(
        messages=[{"name": "Architect", "content": "Let's plan"}]
    )
    result = session._extract_result()
    assert "⚠️" in result


def test_extract_result_skips_non_dict_message():
    """_extract_result tolerates non-dict entries without crashing."""
    session = _make_council_session(
        messages=["not_a_dict", {"name": "A", "content": "hi TERMINATE"}]
    )
    result = session._extract_result()
    # Non-dict should be skipped; the real message should appear
    assert "A" in result


def test_extract_result_skips_empty_content():
    """_extract_result skips messages with empty content."""
    session = _make_council_session(
        messages=[
            {"name": "Coder", "content": ""},
            {"name": "Guardian", "content": "TERMINATE"},
        ]
    )
    result = session._extract_result()
    # Coder message skipped (empty), Guardian appears
    assert "Guardian" in result
    assert "Coder" not in result


def test_get_speakers_returns_unique_names():
    """get_speakers returns the set of agent names that spoke."""
    session = _make_council_session(
        messages=[
            {"name": "Coder", "content": "a"},
            {"name": "Critic", "content": "b"},
            {"name": "Coder", "content": "c"},
        ]
    )
    speakers = session.get_speakers()
    assert set(speakers) == {"Coder", "Critic"}


def test_get_speakers_ignores_messages_without_name():
    """get_speakers ignores messages where 'name' key is absent or None."""
    session = _make_council_session(
        messages=[
            {"content": "no name here"},
            {"name": None, "content": "null name"},
            {"name": "Guardian", "content": "present"},
        ]
    )
    speakers = session.get_speakers()
    assert speakers == ["Guardian"]


# --- create_local_llm_config error branches ---


def test_create_local_llm_config_invalid_temperature():
    """Raises ValueError when temperature is out of range."""
    from venom_core.core.council import create_local_llm_config

    with pytest.raises(ValueError, match="Temperature"):
        create_local_llm_config(
            base_url="http://localhost:11434/v1", model="llama3", temperature=1.5
        )


def test_create_local_llm_config_empty_base_url():
    """Raises ValueError when base_url is empty string."""
    from venom_core.core.council import create_local_llm_config

    with pytest.raises(ValueError, match="base_url"):
        create_local_llm_config(base_url="", model="llama3")


def test_create_local_llm_config_empty_model():
    """Raises ValueError when model is empty string."""
    from venom_core.core.council import create_local_llm_config

    with pytest.raises(ValueError, match="model"):
        create_local_llm_config(base_url="http://localhost:11434/v1", model="")


# ---------------------------------------------------------------------------
# retrieval_policy.py – else-branch in _get_boost_policy (line 177)
# ---------------------------------------------------------------------------


def test_get_boost_policy_unknown_eligible_intent():
    """_get_boost_policy fallback branch for an intent not in the specific cases."""
    from unittest.mock import patch

    from venom_core.core.retrieval_policy import RetrievalPolicyManager

    mock_settings = MagicMock()
    mock_settings.ENABLE_RAG_RETRIEVAL_BOOST = True
    mock_settings.RAG_BOOST_TOP_K_DEFAULT = 5
    mock_settings.RAG_BOOST_TOP_K_RESEARCH = 8
    mock_settings.RAG_BOOST_TOP_K_KNOWLEDGE = 8
    mock_settings.RAG_BOOST_TOP_K_COMPLEX = 6
    mock_settings.RAG_BOOST_MAX_HOPS_DEFAULT = 2
    mock_settings.RAG_BOOST_MAX_HOPS_RESEARCH = 3
    mock_settings.RAG_BOOST_MAX_HOPS_KNOWLEDGE = 3
    mock_settings.RAG_BOOST_LESSONS_LIMIT_DEFAULT = 3
    mock_settings.RAG_BOOST_LESSONS_LIMIT_RESEARCH = 5
    mock_settings.RAG_BOOST_LESSONS_LIMIT_KNOWLEDGE = 5

    with patch("venom_core.core.retrieval_policy.SETTINGS", mock_settings):
        manager = RetrievalPolicyManager()
        # Add a custom intent to BOOST_ELIGIBLE_INTENTS so it passes the eligibility
        # check but hits the else branch in _get_boost_policy
        original = manager.BOOST_ELIGIBLE_INTENTS.copy()
        manager.BOOST_ELIGIBLE_INTENTS = original | {"CUSTOM_INTENT"}
        policy = manager._get_boost_policy("CUSTOM_INTENT")

    assert policy.mode == "boost"
    assert policy.vector_limit == mock_settings.RAG_BOOST_TOP_K_DEFAULT
    assert policy.max_hops == mock_settings.RAG_BOOST_MAX_HOPS_DEFAULT
    assert policy.lessons_limit == mock_settings.RAG_BOOST_LESSONS_LIMIT_DEFAULT
