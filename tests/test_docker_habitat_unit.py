"""Unit tests for docker_habitat helpers that do not require a real Docker daemon."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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


def test_wait_until_container_absent_ignores_generic_exception_then_returns(
    monkeypatch,
):
    instance = _make_habitat_instance()
    instance.CONTAINER_REMOVE_WAIT_SECONDS = 1
    instance.CONTAINER_REMOVE_POLL_SECONDS = 0
    calls = {"count": 0}

    def _get(_name):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary docker API glitch")
        raise docker_habitat.NotFound

    instance.client.containers = SimpleNamespace(get=_get)
    monkeypatch.setattr(docker_habitat.time, "sleep", lambda *_args, **_kwargs: None)

    instance._wait_until_container_absent()
    assert calls["count"] >= 1


def test_wait_until_container_absent_handles_repeated_generic_exception(monkeypatch):
    instance = _make_habitat_instance()
    instance.CONTAINER_REMOVE_WAIT_SECONDS = 1
    instance.CONTAINER_REMOVE_POLL_SECONDS = 0
    original_not_found = docker_habitat.NotFound

    class DummyNotFound(Exception):
        pass

    monkeypatch.setattr(docker_habitat, "NotFound", DummyNotFound)

    time_values = iter([0.0, 0.1, 0.2, 1.5])
    monkeypatch.setattr(docker_habitat.time, "time", lambda: next(time_values))
    monkeypatch.setattr(docker_habitat.time, "sleep", lambda *_args, **_kwargs: None)
    instance.client.containers = SimpleNamespace(
        get=lambda _name: (_ for _ in ()).throw(RuntimeError("temporary issue"))
    )

    instance._wait_until_container_absent()
    monkeypatch.setattr(docker_habitat, "NotFound", original_not_found)


def test_init_raises_when_docker_sdk_unavailable(monkeypatch):
    monkeypatch.setattr(docker_habitat, "docker", None)
    with pytest.raises(RuntimeError, match="Docker SDK nie jest dostępny"):
        DockerHabitat()


def test_init_raises_when_docker_connection_fails(monkeypatch):
    class FakeDocker:
        @staticmethod
        def from_env():
            raise RuntimeError("daemon unavailable")

    monkeypatch.setattr(docker_habitat, "docker", FakeDocker)
    with pytest.raises(RuntimeError, match="Nie można połączyć się z Docker daemon"):
        DockerHabitat()


def test_get_or_create_container_starts_existing_stopped(monkeypatch, tmp_path):
    instance = _make_habitat_instance()
    container = SimpleNamespace(
        status="exited",
        start=MagicMock(),
        reload=MagicMock(),
    )
    instance.client.containers = SimpleNamespace(get=lambda _name: container)
    monkeypatch.setattr(
        instance, "_resolve_workspace_path", lambda: tmp_path / "workspace"
    )
    monkeypatch.setattr(instance, "_has_expected_workspace_mount", lambda *_: True)

    returned = instance._get_or_create_container()

    assert returned is container
    container.start.assert_called_once()
    assert container.reload.called


def test_get_or_create_container_recreates_on_workspace_mismatch(monkeypatch, tmp_path):
    instance = _make_habitat_instance()
    existing = SimpleNamespace(status="running")
    created = object()
    instance.client.containers = SimpleNamespace(get=lambda _name: existing)
    monkeypatch.setattr(
        instance, "_resolve_workspace_path", lambda: tmp_path / "workspace"
    )
    monkeypatch.setattr(instance, "_has_expected_workspace_mount", lambda *_: False)
    monkeypatch.setattr(instance, "_recreate_container", MagicMock())
    monkeypatch.setattr(instance, "_create_container", MagicMock(return_value=created))

    returned = instance._get_or_create_container()

    assert returned is created
    instance._recreate_container.assert_called_once_with(existing)
    instance._create_container.assert_called_once()


def test_recover_from_name_conflict_fallbacks_on_reuse_exception(monkeypatch, tmp_path):
    instance = _make_habitat_instance()
    instance.client.containers = SimpleNamespace(
        get=lambda _name: (_ for _ in ()).throw(RuntimeError("cannot inspect"))
    )
    monkeypatch.setattr(
        instance, "_resolve_workspace_path", lambda: tmp_path / "workspace"
    )
    remove_mock = MagicMock()
    create_mock = MagicMock(return_value="created-after-fallback")
    monkeypatch.setattr(instance, "_remove_container_by_name_if_exists", remove_mock)
    monkeypatch.setattr(instance, "_create_container", create_mock)

    result = instance._recover_from_name_conflict(
        error=SimpleNamespace(),
        workspace_path=tmp_path / "workspace",
        retries_left=2,
    )

    assert result == "created-after-fallback"
    remove_mock.assert_called_once()
    create_mock.assert_called_once()


def test_recover_from_name_conflict_handles_generic_exception(monkeypatch, tmp_path):
    instance = _make_habitat_instance()
    original_not_found = docker_habitat.NotFound

    class DummyNotFound(Exception):
        pass

    monkeypatch.setattr(docker_habitat, "NotFound", DummyNotFound)
    instance.client.containers = SimpleNamespace(
        get=lambda _name: (_ for _ in ()).throw(ValueError("unexpected failure"))
    )
    remove_mock = MagicMock()
    create_mock = MagicMock(return_value="created-after-generic")
    monkeypatch.setattr(instance, "_remove_container_by_name_if_exists", remove_mock)
    monkeypatch.setattr(instance, "_create_container", create_mock)

    result = instance._recover_from_name_conflict(
        error=SimpleNamespace(),
        workspace_path=tmp_path / "workspace",
        retries_left=2,
    )

    assert result == "created-after-generic"
    remove_mock.assert_called_once()
    create_mock.assert_called_once()
    monkeypatch.setattr(docker_habitat, "NotFound", original_not_found)


def test_recover_from_name_conflict_recreates_on_mount_mismatch(monkeypatch, tmp_path):
    instance = _make_habitat_instance()
    existing = SimpleNamespace(status="running")
    instance.client.containers = SimpleNamespace(get=lambda _name: existing)
    monkeypatch.setattr(instance, "_has_expected_workspace_mount", lambda *_: False)
    recreate_mock = MagicMock()
    create_mock = MagicMock(return_value="recreated")
    monkeypatch.setattr(instance, "_recreate_container", recreate_mock)
    monkeypatch.setattr(instance, "_create_container", create_mock)

    result = instance._recover_from_name_conflict(
        error=SimpleNamespace(),
        workspace_path=tmp_path / "workspace",
        retries_left=2,
    )

    assert result == "recreated"
    recreate_mock.assert_called_once_with(existing)
    create_mock.assert_called_once()


def test_init_initializes_container_from_get_or_create(monkeypatch):
    fake_client = SimpleNamespace()
    fake_container = SimpleNamespace(status="running")

    monkeypatch.setattr(
        docker_habitat,
        "docker",
        SimpleNamespace(from_env=lambda: fake_client),
    )
    get_or_create = MagicMock(return_value=fake_container)
    monkeypatch.setattr(DockerHabitat, "_get_or_create_container", get_or_create)

    habitat = DockerHabitat()

    assert habitat.client is fake_client
    assert habitat.container is fake_container


def test_get_or_create_container_creates_new_when_not_found(monkeypatch):
    instance = _make_habitat_instance()
    instance.client.containers = SimpleNamespace(
        get=lambda _name: (_ for _ in ()).throw(docker_habitat.NotFound)
    )
    monkeypatch.setattr(instance, "_create_container", MagicMock(return_value="new"))
    assert instance._get_or_create_container() == "new"


def test_create_container_wraps_non_conflict_api_error(monkeypatch, tmp_path):
    instance = _make_habitat_instance()
    monkeypatch.setattr(instance, "_resolve_conflict_retries", lambda *_: 0)
    monkeypatch.setattr(instance, "_ensure_image_present", lambda *_: None)
    monkeypatch.setattr(instance, "_run_container", MagicMock())
    monkeypatch.setattr(instance, "_is_name_conflict_error", lambda *_: False)
    monkeypatch.setattr(docker_habitat.SETTINGS, "DOCKER_IMAGE_NAME", "venom:test")

    class FakeApiError(Exception):
        pass

    instance._run_container.side_effect = FakeApiError("api boom")
    monkeypatch.setattr(docker_habitat, "APIError", FakeApiError)

    with pytest.raises(
        RuntimeError, match="Błąd API Docker podczas tworzenia kontenera"
    ):
        instance._create_container(tmp_path)


def test_recover_from_name_conflict_raises_when_retries_exhausted(tmp_path):
    instance = _make_habitat_instance()
    with pytest.raises(RuntimeError, match="Wyczerpano limit retry"):
        instance._recover_from_name_conflict(
            error=Exception("conflict"),
            workspace_path=tmp_path / "workspace",
            retries_left=0,
        )
