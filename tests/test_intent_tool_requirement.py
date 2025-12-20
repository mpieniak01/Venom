"""Unit tests for tool-required intent routing."""

from venom_core.core.intent_manager import IntentManager


def test_requires_tool_true_for_tool_required_intent():
    manager = IntentManager()
    assert manager.requires_tool("TIME_REQUEST") is True
    assert manager.requires_tool("INFRA_STATUS") is True


def test_requires_tool_false_for_general_chat():
    manager = IntentManager()
    assert manager.requires_tool("GENERAL_CHAT") is False
