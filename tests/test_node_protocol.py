"""Unit tests for node communication protocol."""

import pytest

from venom_core.nodes.protocol import (
    Capabilities,
    HeartbeatMessage,
    MessageType,
    NodeHandshake,
    NodeMessage,
    NodeResponse,
    SkillExecutionRequest,
)


def test_capabilities_creation():
    """Test creating Capabilities object."""
    caps = Capabilities(
        skills=["ShellSkill", "FileSkill"],
        tags=["location:test", "gpu"],
        cpu_cores=4,
        memory_mb=8192,
        has_gpu=True,
        has_docker=True,
        platform="linux",
    )

    assert "ShellSkill" in caps.skills
    assert "location:test" in caps.tags
    assert caps.cpu_cores == 4
    assert caps.has_gpu is True


def test_node_handshake():
    """Test creating handshake message."""
    caps = Capabilities(skills=["ShellSkill"], tags=["test"])

    handshake = NodeHandshake(
        node_name="test-node", capabilities=caps, token="test-token"
    )

    assert handshake.message_type == MessageType.HANDSHAKE
    assert handshake.node_name == "test-node"
    assert handshake.token == "test-token"
    assert handshake.node_id  # Should be auto-generated


def test_skill_execution_request():
    """Test creating skill execution request."""
    request = SkillExecutionRequest(
        node_id="node-123",
        skill_name="ShellSkill",
        method_name="run",
        parameters={"command": "echo test"},
        timeout=30,
    )

    assert request.message_type == MessageType.EXECUTE_SKILL
    assert request.skill_name == "ShellSkill"
    assert request.method_name == "run"
    assert request.parameters["command"] == "echo test"
    assert request.request_id  # Should be auto-generated


def test_heartbeat_message():
    """Test creating heartbeat message."""
    heartbeat = HeartbeatMessage(
        node_id="node-123", cpu_usage=0.5, memory_usage=0.6, active_tasks=2
    )

    assert heartbeat.message_type == MessageType.HEARTBEAT
    assert heartbeat.node_id == "node-123"
    assert heartbeat.cpu_usage == pytest.approx(0.5)
    assert heartbeat.memory_usage == pytest.approx(0.6)
    assert heartbeat.active_tasks == 2


def test_node_response():
    """Test creating node response."""
    response = NodeResponse(
        request_id="req-123",
        node_id="node-123",
        success=True,
        result="test output",
        execution_time=1.5,
    )

    assert response.message_type == MessageType.RESPONSE
    assert response.request_id == "req-123"
    assert response.success is True
    assert response.result == "test output"
    assert response.execution_time == pytest.approx(1.5)
    assert response.error is None


def test_node_response_with_error():
    """Test creating response with error."""
    response = NodeResponse(
        request_id="req-123",
        node_id="node-123",
        success=False,
        error="Command failed",
        execution_time=0.5,
    )

    assert response.success is False
    assert response.error == "Command failed"
    assert response.result is None


def test_node_message_from_handshake():
    """Test converting handshake to NodeMessage."""
    caps = Capabilities(skills=["ShellSkill"])
    handshake = NodeHandshake(
        node_name="test-node", capabilities=caps, token="test-token"
    )

    message = NodeMessage.from_handshake(handshake)

    assert message.message_type == MessageType.HANDSHAKE
    assert message.payload["node_name"] == "test-node"
    assert message.payload["token"] == "test-token"


def test_node_message_from_execution_request():
    """Test converting SkillExecutionRequest to NodeMessage."""
    request = SkillExecutionRequest(
        node_id="node-123",
        skill_name="ShellSkill",
        method_name="run",
        parameters={"command": "test"},
    )

    message = NodeMessage.from_execution_request(request)

    assert message.message_type == MessageType.EXECUTE_SKILL
    assert message.payload["skill_name"] == "ShellSkill"
    assert message.payload["node_id"] == "node-123"


def test_node_message_serialization():
    """Test NodeMessage serialization to dict."""
    caps = Capabilities(skills=["ShellSkill"])
    handshake = NodeHandshake(
        node_name="test-node", capabilities=caps, token="test-token"
    )
    message = NodeMessage.from_handshake(handshake)

    # Pydantic model should be serializable
    data = message.model_dump()

    assert data["message_type"] == "HANDSHAKE"
    assert "payload" in data
    assert "timestamp" in data


def test_node_message_from_heartbeat_and_response():
    """Test conversion helpers for heartbeat and response payloads."""
    heartbeat = HeartbeatMessage(node_id="node-a")
    hb_msg = NodeMessage.from_heartbeat(heartbeat)
    assert hb_msg.message_type == MessageType.HEARTBEAT
    assert hb_msg.payload["node_id"] == "node-a"

    response = NodeResponse(request_id="req-1", node_id="node-a", success=True)
    resp_msg = NodeMessage.from_response(response)
    assert resp_msg.message_type == MessageType.RESPONSE
    assert resp_msg.payload["request_id"] == "req-1"
