from __future__ import annotations

import importlib
from types import ModuleType

import pytest


def test_agents_getattr_resolves_symbol_via_import_map(monkeypatch):
    agents_module = importlib.import_module("venom_core.agents")

    fake_base_symbol = object()
    fake_module = ModuleType("venom_core.agents.base")
    fake_module.BaseAgent = fake_base_symbol

    def fake_import_module(module_name: str):
        assert module_name == "venom_core.agents.base"
        return fake_module

    monkeypatch.setattr(agents_module.importlib, "import_module", fake_import_module)

    assert getattr(agents_module, "BaseAgent") is fake_base_symbol


def test_agents_getattr_raises_for_unknown_symbol():
    agents_module = importlib.import_module("venom_core.agents")

    with pytest.raises(AttributeError, match="has no attribute 'UnknownAgent'"):
        getattr(agents_module, "UnknownAgent")
