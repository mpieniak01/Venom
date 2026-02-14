from __future__ import annotations

from venom_core.core.error_mappings import (
    ErrorMapping,
    get_admin_message_key,
    get_error_mapping,
    get_recovery_hint_key,
    get_runbook_path,
    get_severity,
    get_user_message_key,
)


def test_get_known_error_mapping_fields():
    mapping = get_error_mapping("PROVIDER_OFFLINE")

    assert isinstance(mapping, ErrorMapping)
    assert mapping is not None
    assert mapping.reason_code == "PROVIDER_OFFLINE"
    assert mapping.runbook_path == "/docs/runbooks/provider-offline.md"
    assert mapping.severity == "critical"


def test_get_unknown_mapping_fallbacks():
    reason_code = "SOMETHING_NEW"

    assert get_error_mapping(reason_code) is None
    assert get_user_message_key(reason_code) == "errors.provider.unknown.user"
    assert get_admin_message_key(reason_code) == "errors.provider.unknown.admin"
    assert get_runbook_path(reason_code) is None
    assert get_recovery_hint_key(reason_code) is None
    assert get_severity(reason_code) == "info"


def test_message_and_severity_resolution_for_known_codes():
    assert (
        get_user_message_key("connection_failed")
        == "errors.provider.connection_failed.user"
    )
    assert (
        get_admin_message_key("missing_api_key")
        == "errors.provider.missing_api_key.admin"
    )
    assert (
        get_recovery_hint_key("RATE_LIMIT_EXCEEDED")
        == "errors.provider.rate_limit.hint"
    )
    assert get_severity("unsupported_provider") == "info"
