"""Tests for provider admin endpoints and audit trail."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from venom_core.core.admin_audit import AdminAuditTrail, get_audit_trail
from venom_core.core.error_mappings import (
    get_error_mapping,
    get_user_message_key,
    get_admin_message_key,
    get_runbook_path,
    get_recovery_hint_key,
    get_severity,
)


class TestErrorMappings:
    """Test error code to message mappings."""

    def test_get_error_mapping_connection_failed(self):
        """Test mapping for connection_failed error."""
        mapping = get_error_mapping("connection_failed")
        assert mapping is not None
        assert mapping.reason_code == "connection_failed"
        assert mapping.user_message_key == "errors.provider.connection_failed.user"
        assert mapping.admin_message_key == "errors.provider.connection_failed.admin"
        assert mapping.runbook_path == "/docs/runbooks/provider-offline.md"
        assert mapping.severity == "critical"

    def test_get_error_mapping_auth_error(self):
        """Test mapping for AUTH_ERROR."""
        mapping = get_error_mapping("AUTH_ERROR")
        assert mapping is not None
        assert mapping.reason_code == "AUTH_ERROR"
        assert mapping.runbook_path == "/docs/runbooks/auth-failures.md"
        assert mapping.severity == "critical"

    def test_get_error_mapping_budget_exceeded(self):
        """Test mapping for BUDGET_EXCEEDED."""
        mapping = get_error_mapping("BUDGET_EXCEEDED")
        assert mapping is not None
        assert mapping.reason_code == "BUDGET_EXCEEDED"
        assert mapping.runbook_path == "/docs/runbooks/budget-exhaustion.md"
        assert mapping.severity == "critical"

    def test_get_error_mapping_timeout(self):
        """Test mapping for TIMEOUT."""
        mapping = get_error_mapping("TIMEOUT")
        assert mapping is not None
        assert mapping.runbook_path == "/docs/runbooks/latency-spike.md"
        assert mapping.severity == "warning"

    def test_get_error_mapping_unknown(self):
        """Test mapping for unknown error code."""
        mapping = get_error_mapping("unknown_error_code")
        assert mapping is None

    def test_get_user_message_key(self):
        """Test getting user message key."""
        key = get_user_message_key("connection_failed")
        assert key == "errors.provider.connection_failed.user"

    def test_get_admin_message_key(self):
        """Test getting admin message key."""
        key = get_admin_message_key("connection_failed")
        assert key == "errors.provider.connection_failed.admin"

    def test_get_runbook_path(self):
        """Test getting runbook path."""
        path = get_runbook_path("connection_failed")
        assert path == "/docs/runbooks/provider-offline.md"

    def test_get_recovery_hint_key(self):
        """Test getting recovery hint key."""
        hint = get_recovery_hint_key("connection_failed")
        assert hint == "errors.provider.connection_failed.hint"

    def test_get_severity(self):
        """Test getting severity level."""
        severity = get_severity("connection_failed")
        assert severity == "critical"

        severity = get_severity("TIMEOUT")
        assert severity == "warning"


class TestAdminAuditTrail:
    """Test admin audit trail functionality."""

    def test_audit_trail_singleton(self):
        """Test that get_audit_trail returns singleton."""
        trail1 = get_audit_trail()
        trail2 = get_audit_trail()
        assert trail1 is trail2

    def test_log_action(self):
        """Test logging an admin action."""
        trail = AdminAuditTrail()
        trail.log_action(
            action="test_connection",
            user="admin",
            provider="ollama",
            details={"endpoint": "http://localhost:11434"},
            result="success",
        )

        entries = trail.get_entries(limit=1)
        assert len(entries) == 1
        assert entries[0].action == "test_connection"
        assert entries[0].user == "admin"
        assert entries[0].provider == "ollama"
        assert entries[0].result == "success"

    def test_log_action_with_error(self):
        """Test logging a failed action."""
        trail = AdminAuditTrail()
        trail.log_action(
            action="provider_activate",
            user="admin",
            provider="openai",
            result="failure",
            error_message="API key not configured",
        )

        entries = trail.get_entries(limit=1)
        assert len(entries) == 1
        assert entries[0].result == "failure"
        assert entries[0].error_message == "API key not configured"

    def test_get_entries_with_filter(self):
        """Test filtering audit entries."""
        trail = AdminAuditTrail()
        trail.log_action(action="test_connection", user="admin1", provider="ollama")
        trail.log_action(action="provider_activate", user="admin2", provider="openai")
        trail.log_action(action="test_connection", user="admin1", provider="vllm")

        # Filter by action
        entries = trail.get_entries(action="test_connection")
        assert len(entries) == 2

        # Filter by provider
        entries = trail.get_entries(provider="ollama")
        assert len(entries) == 1

        # Filter by user
        entries = trail.get_entries(user="admin1")
        assert len(entries) == 2

    def test_get_recent_failures(self):
        """Test getting recent failed actions."""
        trail = AdminAuditTrail()
        trail.log_action(action="test1", user="admin", result="success")
        trail.log_action(action="test2", user="admin", result="failure")
        trail.log_action(action="test3", user="admin", result="failure")
        trail.log_action(action="test4", user="admin", result="success")

        failures = trail.get_recent_failures(limit=10)
        assert len(failures) == 2
        assert all(entry.result == "failure" for entry in failures)

    def test_audit_trail_max_entries(self):
        """Test that audit trail limits entries."""
        trail = AdminAuditTrail(max_entries=5)
        for i in range(10):
            trail.log_action(action=f"test_{i}", user="admin")

        entries = trail.get_entries(limit=100)
        assert len(entries) == 5  # Only keeps max_entries

    def test_clear_audit_trail(self):
        """Test clearing audit trail."""
        trail = AdminAuditTrail()
        trail.log_action(action="test", user="admin")
        assert len(trail.get_entries()) > 0

        trail.clear()
        assert len(trail.get_entries()) == 0


class TestProviderAdminEndpoints:
    """Test provider admin API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from venom_core.main import app

        return TestClient(app)

    def test_test_connection_ollama(self, client):
        """Test connection test endpoint for Ollama."""
        # Test will use actual endpoint - this is an integration test
        response = client.post("/api/v1/providers/ollama/test-connection")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "ollama"
        assert "connection_status" in data

    def test_test_connection_invalid_provider(self, client):
        """Test connection test with invalid provider."""
        response = client.post("/api/v1/providers/invalid_provider/test-connection")
        assert response.status_code == 404

    def test_preflight_check(self, client):
        """Test preflight check endpoint."""
        response = client.post("/api/v1/providers/ollama/preflight")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "overall_status" in data
        assert "checks" in data
        assert "connection" in data["checks"]
        assert "credentials" in data["checks"]
        assert "capabilities" in data["checks"]

    def test_get_admin_audit_log(self, client):
        """Test getting admin audit log."""
        # Clear and populate audit trail
        trail = get_audit_trail()
        trail.clear()
        trail.log_action(
            action="test_connection", user="admin", provider="ollama", result="success"
        )
        trail.log_action(
            action="preflight_check", user="admin", provider="openai", result="success"
        )

        response = client.get("/api/v1/admin/audit")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["entries"]) >= 2
        assert data["entries"][0]["action"] in ["test_connection", "preflight_check"]

    def test_get_admin_audit_log_with_filters(self, client):
        """Test getting audit log with filters."""
        trail = get_audit_trail()
        trail.clear()
        trail.log_action(
            action="test_connection", user="admin", provider="ollama", result="success"
        )
        trail.log_action(
            action="provider_activate",
            user="admin",
            provider="openai",
            result="success",
        )

        # Filter by action
        response = client.get("/api/v1/admin/audit?action=test_connection")
        data = response.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["action"] == "test_connection"

        # Filter by provider
        response = client.get("/api/v1/admin/audit?provider=openai")
        data = response.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["provider"] == "openai"

    def test_idempotency_test_connection(self, client):
        """Test that test-connection is idempotent."""
        # Call multiple times
        response1 = client.post("/api/v1/providers/ollama/test-connection")
        response2 = client.post("/api/v1/providers/ollama/test-connection")
        response3 = client.post("/api/v1/providers/ollama/test-connection")

        # All should succeed with same result type
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        data1 = response1.json()
        data2 = response2.json()
        data3 = response3.json()

        # Connection status should be consistent (same provider, same conditions)
        assert data1["connection_status"] == data2["connection_status"]
        assert data2["connection_status"] == data3["connection_status"]

    def test_user_extraction_with_header(self, client):
        """Test that user is extracted from request header."""
        # Clear audit trail
        trail = get_audit_trail()
        trail.clear()

        # Make request with X-Authenticated-User header
        response = client.post(
            "/api/v1/providers/ollama/test-connection",
            headers={"X-Authenticated-User": "test_admin"},
        )
        assert response.status_code == 200

        # Check audit log has the correct user
        entries = trail.get_entries(limit=1)
        assert len(entries) == 1
        assert entries[0].user == "test_admin"
        assert entries[0].action == "test_connection"

    def test_user_extraction_fallback_to_unknown(self, client):
        """Test that user defaults to 'unknown' when no auth present."""
        # Clear audit trail
        trail = get_audit_trail()
        trail.clear()

        # Make request without auth headers
        response = client.post("/api/v1/providers/ollama/test-connection")
        assert response.status_code == 200

        # Check audit log has 'unknown' user
        entries = trail.get_entries(limit=1)
        assert len(entries) == 1
        assert entries[0].user == "unknown"
