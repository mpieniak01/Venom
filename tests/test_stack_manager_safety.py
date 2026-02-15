"""Testy bezpieczeństwa ścieżek dla StackManager (bez Docker Compose)."""

import subprocess

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


def test_check_docker_compose_maps_missing_binary_to_runtime_error(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("docker")),
    )

    with pytest.raises(RuntimeError, match="Docker Compose nie jest dostępny"):
        StackManager(workspace_root=str(tmp_path))
