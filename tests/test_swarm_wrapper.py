import asyncio
from typing import cast

import pytest

import venom_core.core.swarm as swarm_mod
from venom_core.agents.base import BaseAgent


class DummyKernel:
    def __init__(self, plugins=None):
        self.plugins = plugins or {}


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


class PluginWithFunctions:
    def __init__(self):
        self.functions = {"ping": lambda: "pong"}


class PluginWithMethods:
    def do(self):
        return "ok"


PluginWithMethods.do.__kernel_function__ = True


def test_swarm_wrapper_registers_functions(monkeypatch):
    registered = {}

    def fake_register(self, function_map):
        registered.update(function_map)

    monkeypatch.setattr(swarm_mod.VenomAgent, "register_function", fake_register)

    kernel = DummyKernel(
        plugins={
            "Alpha": PluginWithFunctions(),
            "Beta": PluginWithMethods(),
        }
    )
    agent = DummyAgent(kernel=kernel)
    wrapper = swarm_mod.create_venom_agent_wrapper(
        cast(BaseAgent, agent), name="AlphaAgent"
    )

    assert "Alpha_ping" in registered
    assert "Beta_do" in registered
    assert wrapper.system_message == "dummy prompt"


@pytest.mark.asyncio
async def test_swarm_wrapper_process_error():
    agent = DummyAgent(kernel=DummyKernel(), raise_error=True)
    wrapper = swarm_mod.create_venom_agent_wrapper(
        cast(BaseAgent, agent), name="ErrAgent"
    )

    result = await wrapper.a_process_venom("hi")

    assert "Błąd" in result


def test_swarm_wrapper_handles_missing_kernel(monkeypatch):
    registered = {}

    def fake_register(self, function_map):
        registered.update(function_map)

    monkeypatch.setattr(swarm_mod.VenomAgent, "register_function", fake_register)

    agent = DummyAgent(kernel=None)
    swarm_mod.create_venom_agent_wrapper(cast(BaseAgent, agent), name="NoKernelAgent")

    assert registered == {}


def test_swarm_wrapper_handles_missing_plugins(monkeypatch):
    registered = {}

    def fake_register(self, function_map):
        registered.update(function_map)

    monkeypatch.setattr(swarm_mod.VenomAgent, "register_function", fake_register)

    kernel = object()
    agent = DummyAgent(kernel=kernel)
    swarm_mod.create_venom_agent_wrapper(cast(BaseAgent, agent), name="NoPluginsAgent")

    assert registered == {}


def test_swarm_wrapper_register_error(monkeypatch):
    def fake_register(self, function_map):
        raise RuntimeError("boom")

    monkeypatch.setattr(swarm_mod.VenomAgent, "register_function", fake_register)

    kernel = DummyKernel(plugins={"Alpha": PluginWithFunctions()})
    agent = DummyAgent(kernel=kernel)

    swarm_mod.create_venom_agent_wrapper(cast(BaseAgent, agent), name="FailRegister")
