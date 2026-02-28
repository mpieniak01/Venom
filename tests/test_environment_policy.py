from __future__ import annotations

import pytest

from venom_core.core import environment_policy


def test_validate_environment_policy_accepts_dev(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(environment_policy.SETTINGS, "ENVIRONMENT_ROLE", "dev")
    monkeypatch.setattr(environment_policy.SETTINGS, "DB_SCHEMA", "dev")
    monkeypatch.setattr(environment_policy.SETTINGS, "CACHE_NAMESPACE", "venom")
    monkeypatch.setattr(environment_policy.SETTINGS, "QUEUE_NAMESPACE", "venom")
    monkeypatch.setattr(environment_policy.SETTINGS, "STORAGE_PREFIX", "")

    environment_policy.validate_environment_policy()


def test_validate_environment_policy_rejects_invalid_preprod(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(environment_policy.SETTINGS, "ENVIRONMENT_ROLE", "preprod")
    monkeypatch.setattr(environment_policy.SETTINGS, "DB_SCHEMA", "dev")
    monkeypatch.setattr(environment_policy.SETTINGS, "CACHE_NAMESPACE", "venom")
    monkeypatch.setattr(environment_policy.SETTINGS, "QUEUE_NAMESPACE", "venom")
    monkeypatch.setattr(environment_policy.SETTINGS, "STORAGE_PREFIX", "")

    with pytest.raises(RuntimeError, match="Niepoprawna konfiguracja pre-prod"):
        environment_policy.validate_environment_policy()


def test_ensure_data_mutation_allowed_blocks_preprod(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(environment_policy.SETTINGS, "ENVIRONMENT_ROLE", "preprod")
    monkeypatch.setattr(environment_policy.SETTINGS, "ALLOW_DATA_MUTATION", False)

    with pytest.raises(PermissionError, match="zablokowana na pre-prod"):
        environment_policy.ensure_data_mutation_allowed("test.operation")
