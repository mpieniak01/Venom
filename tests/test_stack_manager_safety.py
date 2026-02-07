"""Testy bezpieczeństwa ścieżek dla StackManager (bez Docker Compose)."""

import pytest

from venom_core.infrastructure.stack_manager import StackManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(StackManager, "_check_docker_compose", lambda self: None)
    return StackManager(workspace_root=str(tmp_path))


def test_get_stack_dir_rejects_empty_name(manager):
    with pytest.raises(ValueError):
        manager._get_stack_dir("")


def test_get_stack_dir_rejects_path_traversal(manager):
    with pytest.raises(ValueError):
        manager._get_stack_dir("../outside")
