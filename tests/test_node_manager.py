import asyncio
from typing import cast

import pytest
from fastapi import WebSocket

from venom_core.core.node_manager import NodeManager
from venom_core.nodes.protocol import (
    Capabilities,
    HeartbeatMessage,
    NodeHandshake,
    NodeResponse,
)


class DummyWebSocket:
    def __init__(self) -> None:
        self.sent = []

    async def send_json(self, payload) -> None:
        await asyncio.sleep(0)
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_register_node_rejects_invalid_token():
    manager = NodeManager(shared_token="secret")
    handshake = NodeHandshake(
        node_id="node-1",
        node_name="Node One",
        capabilities=Capabilities(skills=["alpha"], tags=["lab"]),
        token="wrong",
    )

    result = await manager.register_node(handshake, cast(WebSocket, DummyWebSocket()))

    assert result is False
    assert manager.nodes == {}


@pytest.mark.asyncio
async def test_register_node_updates_existing_entry():
    manager = NodeManager(shared_token="secret")
    handshake = NodeHandshake(
        node_id="node-1",
        node_name="Node One",
        capabilities=Capabilities(skills=["alpha"], tags=["lab"]),
        token="secret",
    )
    ws1 = DummyWebSocket()
    ws2 = DummyWebSocket()

    assert await manager.register_node(handshake, cast(WebSocket, ws1)) is True
    manager.nodes["node-1"].is_online = False

    assert await manager.register_node(handshake, cast(WebSocket, ws2)) is True
    assert manager.nodes["node-1"].websocket is ws2
    assert manager.nodes["node-1"].is_online is True


@pytest.mark.asyncio
async def test_update_heartbeat_refreshes_node_metrics():
    manager = NodeManager(shared_token="secret")
    handshake = NodeHandshake(
        node_id="node-1",
        node_name="Node One",
        capabilities=Capabilities(skills=["alpha"], tags=["lab"]),
        token="secret",
    )
    await manager.register_node(handshake, cast(WebSocket, DummyWebSocket()))

    heartbeat = HeartbeatMessage(
        node_id="node-1",
        cpu_usage=0.4,
        memory_usage=0.2,
        active_tasks=3,
    )
    await manager.update_heartbeat(heartbeat)

    node = manager.nodes["node-1"]
    assert node.cpu_usage == pytest.approx(0.4)
    assert node.memory_usage == pytest.approx(0.2)
    assert node.active_tasks == 3
    assert node.is_online is True


@pytest.mark.asyncio
async def test_list_and_filter_nodes():
    manager = NodeManager(shared_token="secret")
    node_a = NodeHandshake(
        node_id="node-a",
        node_name="Node A",
        capabilities=Capabilities(skills=["alpha"], tags=["lab"]),
        token="secret",
    )
    node_b = NodeHandshake(
        node_id="node-b",
        node_name="Node B",
        capabilities=Capabilities(skills=["beta"], tags=["prod"]),
        token="secret",
    )
    await manager.register_node(node_a, cast(WebSocket, DummyWebSocket()))
    await manager.register_node(node_b, cast(WebSocket, DummyWebSocket()))
    manager.nodes["node-b"].is_online = False

    assert len(manager.list_nodes()) == 2
    assert [node.node_id for node in manager.list_nodes(online_only=True)] == ["node-a"]
    assert [node.node_id for node in manager.find_nodes_by_skill("alpha")] == ["node-a"]
    assert [node.node_id for node in manager.find_nodes_by_tag("lab")] == ["node-a"]


@pytest.mark.asyncio
async def test_select_best_node_prefers_low_load():
    manager = NodeManager(shared_token="secret")
    await manager.register_node(
        NodeHandshake(
            node_id="node-a",
            node_name="Node A",
            capabilities=Capabilities(skills=["alpha"], tags=[]),
            token="secret",
        ),
        cast(WebSocket, DummyWebSocket()),
    )
    await manager.register_node(
        NodeHandshake(
            node_id="node-b",
            node_name="Node B",
            capabilities=Capabilities(skills=["alpha"], tags=[]),
            token="secret",
        ),
        cast(WebSocket, DummyWebSocket()),
    )
    manager.nodes["node-a"].cpu_usage = 0.1
    manager.nodes["node-a"].memory_usage = 0.1
    manager.nodes["node-a"].active_tasks = 1
    manager.nodes["node-b"].cpu_usage = 0.5
    manager.nodes["node-b"].memory_usage = 0.4
    manager.nodes["node-b"].active_tasks = 4

    best = manager.select_best_node("alpha")

    assert best is not None
    assert best.node_id == "node-a"


@pytest.mark.asyncio
async def test_execute_skill_on_node_success():
    manager = NodeManager(shared_token="secret")
    websocket = DummyWebSocket()
    handshake = NodeHandshake(
        node_id="node-1",
        node_name="Node One",
        capabilities=Capabilities(skills=["alpha"], tags=[]),
        token="secret",
    )
    await manager.register_node(handshake, cast(WebSocket, websocket))

    task = asyncio.create_task(
        manager.execute_skill_on_node("node-1", "alpha", "run", {"value": 1})
    )

    for _ in range(10):
        if websocket.sent:
            break
        await asyncio.sleep(0)

    assert websocket.sent
    request_id = websocket.sent[0]["payload"]["request_id"]
    response = NodeResponse(
        request_id=request_id,
        node_id="node-1",
        success=True,
        result={"ok": True},
    )
    await manager.handle_response(response)

    result = await task
    assert result.success is True
    assert result.result == {"ok": True}


@pytest.mark.asyncio
async def test_execute_skill_on_node_errors():
    manager = NodeManager(shared_token="secret")

    with pytest.raises(ValueError):
        await manager.execute_skill_on_node("missing", "alpha", "run", {})

    handshake = NodeHandshake(
        node_id="node-1",
        node_name="Node One",
        capabilities=Capabilities(skills=["alpha"], tags=[]),
        token="secret",
    )
    await manager.register_node(handshake, cast(WebSocket, DummyWebSocket()))
    manager.nodes["node-1"].is_online = False

    with pytest.raises(ValueError):
        await manager.execute_skill_on_node("node-1", "alpha", "run", {})
