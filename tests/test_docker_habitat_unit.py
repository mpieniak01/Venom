"""Unit tests for docker_habitat helpers that do not require a real Docker daemon."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from venom_core.infrastructure import docker_habitat
from venom_core.infrastructure.docker_habitat import DockerHabitat


def _make_habitat_instance() -> DockerHabitat:
    """Create an instance without invoking Docker."""
    instance = DockerHabitat.__new__(DockerHabitat)
    instance.client = SimpleNamespace()
    return instance


def test_resolve_workspace_path_creates_directory(tmp_path, monkeypatch):
    target = tmp_path / "workspace"
    monkeypatch.setattr(
        docker_habitat.SETTINGS, "WORKSPACE_ROOT", str(target), raising=False
    )

    instance = _make_habitat_instance()
    resolved = instance._resolve_workspace_path()

    assert resolved == target.resolve()
    assert resolved.exists()


def test_container_workspace_mount_and_expected(tmp_path):
    mount_source = tmp_path / "bind"
    mount_source.mkdir()

    class DummyContainer:
        def __init__(self):
            self.attrs = {
                "Mounts": [
                    {
                        "Destination": docker_habitat.CONTAINER_WORKDIR,
                        "Source": str(mount_source),
                    }
                ]
            }

        def reload(self):
            pass

    instance = _make_habitat_instance()
    container = DummyContainer()

    mount = instance._container_workspace_mount(container)
    assert mount == mount_source.resolve()
    assert instance._has_expected_workspace_mount(container, mount_source)

    # When the mount is missing, helper should return False
    container.attrs["Mounts"] = []
    assert instance._container_workspace_mount(container) is None
    assert not instance._has_expected_workspace_mount(container, mount_source)


def test_ensure_image_present_pulls_missing(monkeypatch):
    pulled = SimpleNamespace(count=0)

    def _pull(name):
        pulled.count += 1

    class FakeImages:
        def get(self, name):
            raise docker_habitat.ImageNotFound

        def pull(self, name):
            _pull(name)

    instance = _make_habitat_instance()
    instance.client.images = FakeImages()

    instance._ensure_image_present("venom-image")

    assert pulled.count == 1


def test_resolve_conflict_retries_defaults_and_clamps():
    instance = _make_habitat_instance()
    assert (
        instance._resolve_conflict_retries(None)
        == docker_habitat.DockerHabitat.CONTAINER_CONFLICT_RETRIES
    )
    assert instance._resolve_conflict_retries(-5) == 0
    assert instance._resolve_conflict_retries(2) == 2


def test_is_name_conflict_error_inspects_status_and_text():
    class DummyError(Exception):
        status_code = 409

        def __str__(self):
            return "409 conflict"

    error = DummyError()
    assert DockerHabitat._is_name_conflict_error(error)

    class NonConflictError(Exception):
        status_code = 500

        def __str__(self):
            return "boom"

    assert not DockerHabitat._is_name_conflict_error(NonConflictError())


def test_recover_from_name_conflict_reuses_existing(monkeypatch, tmp_path):
    instance = _make_habitat_instance()

    container = SimpleNamespace(
        status="exited",
        attrs={
            "Mounts": [
                {
                    "Destination": docker_habitat.CONTAINER_WORKDIR,
                    "Source": str(tmp_path / "workspace"),
                }
            ]
        },
        start=MagicMock(),
        reload=MagicMock(),
    )

    instance.client.containers = SimpleNamespace(get=lambda name: container)
    monkeypatch.setattr(
        instance,
        "_has_expected_workspace_mount",
        lambda _obj, _path: True,
    )
    monkeypatch.setattr(
        instance,
        "_resolve_workspace_path",
        lambda: tmp_path / "workspace",
    )

    result = instance._recover_from_name_conflict(
        error=SimpleNamespace(),
        workspace_path=tmp_path / "workspace",
        retries_left=1,
    )

    assert result is container
    container.start.assert_called_once()
    container.reload.assert_called_once()


def test_remove_container_by_name_if_exists_handles_missing(monkeypatch):
    instance = _make_habitat_instance()
    instance.client.containers = SimpleNamespace(
        get=lambda name: (_ for _ in ()).throw(docker_habitat.NotFound)
    )

    # Should not raise
    instance._remove_container_by_name_if_exists()

    class FakeContainer:
        def __init__(self):
            self.remove_called = False

        def remove(self, force=False):
            self.remove_called = True

    fake = FakeContainer()
    instance.client.containers = SimpleNamespace(get=lambda name: fake)
    instance._wait_until_container_absent = MagicMock()

    instance._remove_container_by_name_if_exists()

    assert fake.remove_called
    instance._wait_until_container_absent.assert_called_once()


def test_wait_until_container_absent_returns_on_not_found(monkeypatch):
    instance = _make_habitat_instance()
    instance.client.containers = SimpleNamespace(
        get=lambda name: (_ for _ in ()).throw(docker_habitat.NotFound)
    )

    # Should return quickly without sleeping
    instance._wait_until_container_absent()
