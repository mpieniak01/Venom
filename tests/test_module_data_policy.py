from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from venom_core.core import module_data_policy


def test_parse_module_data_policy_payload_rejects_invalid_payload() -> None:
    policy, errors = module_data_policy.parse_module_data_policy_payload(
        module_id="brand_studio",
        payload={"storage_mode": "x", "mutation_guard": "y", "state_files": ["../bad"]},
    )
    assert policy is None
    assert errors


def test_parse_module_data_policy_payload_accepts_valid_payload() -> None:
    policy, errors = module_data_policy.parse_module_data_policy_payload(
        module_id="brand_studio",
        payload={
            "storage_mode": "core_prefixed",
            "mutation_guard": "core_environment_policy",
            "state_files": ["runtime-state.json", "accounts-state.json"],
        },
    )
    assert not errors
    assert policy is not None
    assert policy.storage_mode == "core_prefixed"


def test_resolve_module_data_root_uses_storage_prefix_when_present() -> None:
    settings = SimpleNamespace(STORAGE_PREFIX="preprod", ENVIRONMENT_ROLE="dev")
    root = module_data_policy.resolve_module_data_root(
        module_id="brand_studio",
        settings=settings,
        base_dir=Path("/tmp/venom-data"),
    )
    assert root == Path("/tmp/venom-data/preprod/brand_studio")


def test_resolve_module_state_path_rejects_parent_traversal() -> None:
    with pytest.raises(ValueError):
        module_data_policy.resolve_module_state_path(
            module_id="brand_studio",
            file_name="../secrets.json",
        )


def test_ensure_module_mutation_allowed_uses_module_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake_guard(operation_name: str) -> None:
        calls.append(operation_name)

    monkeypatch.setattr(
        module_data_policy,
        "ensure_data_mutation_allowed",
        _fake_guard,
    )
    module_data_policy.ensure_module_mutation_allowed(
        module_id="brand_studio",
        operation_name="post:/api/v1/brand-studio/config/refresh",
    )
    assert calls == ["module.brand_studio.post:/api/v1/brand-studio/config/refresh"]
