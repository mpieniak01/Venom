"""Native MAF participant wrappers and tool schema export contracts."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock

import pytest
from agent_framework import Executor

import venom_core.core.swarm as swarm_mod
from venom_core.agents.base import BaseAgent
from venom_core.execution.agent_contracts import tool_function
from venom_core.execution.maf_runtime import AgentRuntime


class DummyAgent:
    SYSTEM_PROMPT = "dummy prompt"

    def __init__(self, kernel=None, raise_error=False):
        self.kernel = kernel
        self.raise_error = raise_error

    async def process(self, message: str) -> str:
        await asyncio.sleep(0)
        if self.raise_error:
            raise RuntimeError("boom")
        return f"echo:{message}"


class PluginWithMethods:
    @tool_function(name="do", description="Return the given value")
    def do(self, value: int = 2) -> str:
        return str(value)


def test_swarm_wrapper_exports_native_function_schemas():
    runtime = AgentRuntime()
    runtime.add_plugin(PluginWithMethods(), "Alpha")
    agent = DummyAgent(kernel=runtime)
    wrapper = swarm_mod.create_venom_agent_wrapper(cast(BaseAgent, agent), "AlphaAgent")
    tools = swarm_mod.extract_venom_tools(cast(BaseAgent, agent))
    assert isinstance(wrapper, Executor)
    assert wrapper.venom_agent is agent
    assert wrapper.system_message == "dummy prompt"
    assert [t["function"]["name"] for t in tools] == ["Alpha-do"]
    schema = tools[0]["function"]["parameters"]
    assert schema["properties"]["value"]["type"] == "integer"
    assert schema["properties"]["value"]["default"] == 2
    assert not schema.get("required")


@pytest.mark.asyncio
async def test_swarm_wrapper_process_delegates_to_existing_agent_once():
    agent = DummyAgent(kernel=AgentRuntime())
    agent.process = AsyncMock(return_value="controlled result")
    wrapper = swarm_mod.create_venom_agent_wrapper(cast(BaseAgent, agent), "Agent")
    assert await wrapper.a_process_venom("input") == "controlled result"
    agent.process.assert_awaited_once_with("input")


@pytest.mark.asyncio
async def test_swarm_wrapper_process_error():
    wrapper = swarm_mod.create_venom_agent_wrapper(
        cast(BaseAgent, DummyAgent(raise_error=True)), "ErrAgent"
    )
    assert "Błąd" in await wrapper.a_process_venom("hi")


def test_swarm_wrapper_handles_missing_kernel():
    agent = DummyAgent()
    wrapper = swarm_mod.create_venom_agent_wrapper(cast(BaseAgent, agent), "NoKernel")
    assert isinstance(wrapper, Executor)
    assert swarm_mod.extract_venom_tools(cast(BaseAgent, agent)) == []


def test_swarm_wrapper_handles_empty_runtime():
    agent = DummyAgent(kernel=AgentRuntime())
    swarm_mod.create_venom_agent_wrapper(cast(BaseAgent, agent), "NoTools")
    assert swarm_mod.extract_venom_tools(cast(BaseAgent, agent)) == []


def test_swarm_schema_error_is_not_reported_as_empty_success():
    class BrokenRuntime:
        def native_tools(self):
            raise RuntimeError("schema broken")

    agent = DummyAgent(kernel=BrokenRuntime())
    with pytest.raises(RuntimeError, match="schema broken"):
        swarm_mod.extract_venom_tools(cast(BaseAgent, agent))
