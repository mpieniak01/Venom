from __future__ import annotations

from venom_core.core.admin_audit import AdminAuditTrail


def test_log_and_filter_entries_with_limit():
    trail = AdminAuditTrail(max_entries=10)

    trail.log_action("provider_activate", "alice", provider="openai")
    trail.log_action("config_update", "bob", provider="ollama")
    trail.log_action(
        "test_connection",
        "alice",
        provider="openai",
        result="failure",
        error_message="timeout",
    )

    entries = trail.get_entries(limit=2)
    assert len(entries) == 2
    assert entries[0].action == "test_connection"
    assert entries[1].action == "config_update"

    by_user = trail.get_entries(user="alice")
    assert len(by_user) == 2
    assert all(item.user == "alice" for item in by_user)

    by_action_provider = trail.get_entries(
        action="provider_activate", provider="openai"
    )
    assert len(by_action_provider) == 1
    assert by_action_provider[0].action == "provider_activate"


def test_recent_failures_and_max_entries_trim():
    trail = AdminAuditTrail(max_entries=2)

    trail.log_action("a1", "u1", result="success")
    trail.log_action("a2", "u1", provider="openai", result="failure")
    trail.log_action("a3", "u2", provider="ollama", result="failure")

    # max_entries=2 keeps only newest two records
    all_entries = trail.get_entries(limit=10)
    assert len(all_entries) == 2
    assert [item.action for item in all_entries] == ["a3", "a2"]

    failures = trail.get_recent_failures(limit=10)
    assert len(failures) == 2
    assert all(item.result == "failure" for item in failures)

    openai_failures = trail.get_recent_failures(provider="openai")
    assert len(openai_failures) == 1
    assert openai_failures[0].provider == "openai"

    trail.clear()
    assert trail.get_entries(limit=10) == []
