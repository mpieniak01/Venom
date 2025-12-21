"""Tests for Tavily client lazy loading."""

from types import SimpleNamespace

from venom_core.execution.skills import web_skill


def test_get_tavily_client_class_success(monkeypatch):
    class DummyClient:
        pass

    dummy_module = SimpleNamespace(TavilyClient=DummyClient)
    monkeypatch.setattr(web_skill, "import_module", lambda name: dummy_module)

    assert web_skill._get_tavily_client_class() is DummyClient


def test_get_tavily_client_class_failure(monkeypatch):
    def raise_import(_name):
        raise ImportError("missing")

    monkeypatch.setattr(web_skill, "import_module", raise_import)
    assert web_skill._get_tavily_client_class() is None
