"""Unit coverage tests for docker_habitat edge paths (without real Docker)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import venom_core.infrastructure.docker_habitat as docker_habitat_mod


class FakeContainer:
    """Simple test double for Docker container object."""

    def __init__(
        self,
        *,
        status: str = "running",
        mounts: list[dict[str, str]] | None = None,
        output: bytes | None = b"",
        exit_code: int = 0,
    ) -> None:
        self.status = status
        self.attrs = {"Mounts": mounts or []}
        self.output = output
        self.exit_code = exit_code
        self.reload_calls = 0
        self.start_calls = 0
        self.stop_calls = 0
        self.remove_calls: list[bool] = []
        self.exec_calls: list[tuple[str, str]] = []

    def reload(self) -> None:
        self.reload_calls += 1

    def start(self) -> None:
        self.start_calls += 1
        self.status = "running"

    def stop(self) -> None:
        self.stop_calls += 1
        self.status = "exited"

    def remove(self, force: bool = False) -> None:
        self.remove_calls.append(force)

    def exec_run(self, *, cmd: str, workdir: str, demux: bool):
        self.exec_calls.append((cmd, workdir))
        return SimpleNamespace(exit_code=self.exit_code, output=self.output)


def _new_habitat_with_client(client) -> docker_habitat_mod.DockerHabitat:
    """Create habitat instance bypassing __init__ to unit test internals."""
    habitat = object.__new__(docker_habitat_mod.DockerHabitat)
    habitat.client = client
    return habitat


def test_init_raises_when_docker_sdk_missing(monkeypatch):
    monkeypatch.setattr(docker_habitat_mod, "docker", None)
    with pytest.raises(RuntimeError, match="Docker SDK nie jest dostępny"):
        docker_habitat_mod.DockerHabitat()


def test_init_raises_when_docker_daemon_unavailable(monkeypatch):
    docker_stub = SimpleNamespace()
    docker_stub.from_env = MagicMock(side_effect=RuntimeError("daemon down"))
    monkeypatch.setattr(docker_habitat_mod, "docker", docker_stub)
    with pytest.raises(RuntimeError, match="Nie można połączyć się z Docker daemon"):
        docker_habitat_mod.DockerHabitat()


def test_container_workspace_mount_and_match(tmp_path):
    expected = tmp_path / "workspace"
    expected.mkdir(parents=True)
    container = FakeContainer(
        mounts=[
            {"Destination": "/other", "Source": str(tmp_path / "x")},
            {
                "Destination": docker_habitat_mod.CONTAINER_WORKDIR,
                "Source": str(expected),
            },
        ]
    )
    habitat = _new_habitat_with_client(client=SimpleNamespace())

    mount = habitat._container_workspace_mount(container)
    assert mount == expected.resolve()
    assert habitat._has_expected_workspace_mount(container, expected.resolve())


def test_has_expected_workspace_mount_returns_false_when_missing(tmp_path):
    expected = tmp_path / "workspace"
    expected.mkdir(parents=True)
    container = FakeContainer(mounts=[])
    habitat = _new_habitat_with_client(client=SimpleNamespace())
    assert habitat._has_expected_workspace_mount(container, expected) is False


def test_recreate_container_stops_removes_and_handles_failures():
    habitat = _new_habitat_with_client(client=SimpleNamespace())
    habitat._remove_container_by_name_if_exists = MagicMock()
    container = FakeContainer(status="running")

    habitat._recreate_container(container)

    assert container.stop_calls == 1
    assert container.remove_calls == [True]
    habitat._remove_container_by_name_if_exists.assert_called_once()


def test_recreate_container_swallow_exceptions():
    habitat = _new_habitat_with_client(client=SimpleNamespace())
    habitat._remove_container_by_name_if_exists = MagicMock()
    container = FakeContainer(status="running")
    container.stop = MagicMock(side_effect=RuntimeError("stop failed"))
    container.remove = MagicMock(side_effect=RuntimeError("remove failed"))

    habitat._recreate_container(container)

    habitat._remove_container_by_name_if_exists.assert_called_once()


def test_remove_container_by_name_if_exists_not_found(monkeypatch):
    class NotFoundError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "NotFound", NotFoundError)
    client = SimpleNamespace(
        containers=SimpleNamespace(get=MagicMock(side_effect=NotFoundError()))
    )
    habitat = _new_habitat_with_client(client)

    habitat._remove_container_by_name_if_exists()


def test_remove_container_by_name_if_exists_remove_error_is_swallowed():
    existing = FakeContainer()
    existing.remove = MagicMock(side_effect=RuntimeError("cannot remove"))
    client = SimpleNamespace(
        containers=SimpleNamespace(get=MagicMock(return_value=existing))
    )
    habitat = _new_habitat_with_client(client)

    habitat._remove_container_by_name_if_exists()
    existing.remove.assert_called_once_with(force=True)


def test_create_container_pulls_missing_image_and_runs(tmp_path, monkeypatch):
    class ImageNotFoundError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "ImageNotFound", ImageNotFoundError)
    container = FakeContainer()
    images = SimpleNamespace(
        get=MagicMock(side_effect=ImageNotFoundError("missing")),
        pull=MagicMock(),
    )
    containers = SimpleNamespace(run=MagicMock(return_value=container))
    client = SimpleNamespace(images=images, containers=containers)
    habitat = _new_habitat_with_client(client)
    monkeypatch.setattr(docker_habitat_mod.SETTINGS, "DOCKER_IMAGE_NAME", "venom-image")

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True)
    created = habitat._create_container(workspace_path=workspace)

    assert created is container
    images.pull.assert_called_once_with("venom-image")
    assert container.reload_calls == 1
    run_kwargs = containers.run.call_args.kwargs
    assert run_kwargs["working_dir"] == docker_habitat_mod.CONTAINER_WORKDIR
    assert (
        run_kwargs["volumes"][str(workspace)]["bind"]
        == docker_habitat_mod.CONTAINER_WORKDIR
    )


def test_create_container_retries_on_name_conflict(monkeypatch, tmp_path):
    class ApiError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "APIError", ApiError)
    monkeypatch.setattr(docker_habitat_mod.time, "sleep", lambda _x: None)
    container = FakeContainer()
    run = MagicMock(side_effect=[ApiError("already in use"), container])
    images = SimpleNamespace(get=MagicMock(), pull=MagicMock())
    client = SimpleNamespace(images=images, containers=SimpleNamespace(run=run))
    habitat = _new_habitat_with_client(client)
    habitat._remove_container_by_name_if_exists = MagicMock()
    monkeypatch.setattr(docker_habitat_mod.SETTINGS, "DOCKER_IMAGE_NAME", "venom-image")

    result = habitat._create_container(workspace_path=tmp_path / "ws")

    assert result is container
    habitat._remove_container_by_name_if_exists.assert_called_once()
    assert run.call_count == 2


def test_create_container_conflict_reuses_existing_container(monkeypatch, tmp_path):
    class ApiError(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.status_code = 409

    monkeypatch.setattr(docker_habitat_mod, "APIError", ApiError)
    monkeypatch.setattr(docker_habitat_mod.SETTINGS, "DOCKER_IMAGE_NAME", "venom-image")

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True)
    existing = FakeContainer(
        status="exited",
        mounts=[
            {
                "Destination": docker_habitat_mod.CONTAINER_WORKDIR,
                "Source": str(workspace.resolve()),
            }
        ],
    )
    run = MagicMock(side_effect=ApiError("409 client error"))
    client = SimpleNamespace(
        images=SimpleNamespace(get=MagicMock(), pull=MagicMock()),
        containers=SimpleNamespace(run=run, get=MagicMock(return_value=existing)),
    )
    habitat = _new_habitat_with_client(client)

    result = habitat._create_container(workspace_path=workspace)

    assert result is existing
    assert existing.start_calls == 1
    assert run.call_count == 1


def test_create_container_conflict_retries_exhausted(monkeypatch, tmp_path):
    class ApiError(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.status_code = 409

    class NotFoundError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "APIError", ApiError)
    monkeypatch.setattr(docker_habitat_mod, "NotFound", NotFoundError)
    monkeypatch.setattr(docker_habitat_mod.SETTINGS, "DOCKER_IMAGE_NAME", "venom-image")

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True)
    run = MagicMock(
        side_effect=[ApiError("409 client error"), ApiError("409 client error")]
    )
    client = SimpleNamespace(
        images=SimpleNamespace(get=MagicMock(), pull=MagicMock()),
        containers=SimpleNamespace(run=run, get=MagicMock(side_effect=NotFoundError())),
    )
    habitat = _new_habitat_with_client(client)
    habitat._remove_container_by_name_if_exists = MagicMock()

    with pytest.raises(RuntimeError, match="Wyczerpano limit retry"):
        habitat._create_container(
            workspace_path=workspace,
            conflict_retries_remaining=1,
        )

    assert run.call_count == 2


def test_create_container_raises_runtime_error_on_non_conflict_api_error(
    monkeypatch, tmp_path
):
    class ApiError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "APIError", ApiError)
    images = SimpleNamespace(get=MagicMock(), pull=MagicMock())
    client = SimpleNamespace(
        images=images,
        containers=SimpleNamespace(
            run=MagicMock(side_effect=ApiError("permission denied"))
        ),
    )
    habitat = _new_habitat_with_client(client)
    monkeypatch.setattr(docker_habitat_mod.SETTINGS, "DOCKER_IMAGE_NAME", "venom-image")

    with pytest.raises(
        RuntimeError, match="Błąd API Docker podczas tworzenia kontenera"
    ):
        habitat._create_container(workspace_path=tmp_path / "ws")


def test_create_container_raises_runtime_error_on_unexpected_error(
    monkeypatch, tmp_path
):
    class ApiError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "APIError", ApiError)
    images = SimpleNamespace(get=MagicMock(), pull=MagicMock())
    client = SimpleNamespace(
        images=images,
        containers=SimpleNamespace(run=MagicMock(side_effect=ValueError("boom"))),
    )
    habitat = _new_habitat_with_client(client)
    monkeypatch.setattr(docker_habitat_mod.SETTINGS, "DOCKER_IMAGE_NAME", "venom-image")

    with pytest.raises(
        RuntimeError, match="Nieoczekiwany błąd podczas tworzenia kontenera"
    ):
        habitat._create_container(workspace_path=tmp_path / "ws")


def test_get_or_create_container_recreates_when_mount_mismatch(tmp_path):
    existing = FakeContainer(status="running")
    client = SimpleNamespace(
        containers=SimpleNamespace(get=MagicMock(return_value=existing))
    )
    habitat = _new_habitat_with_client(client)
    expected = tmp_path / "expected"
    expected.mkdir(parents=True)
    habitat._resolve_workspace_path = MagicMock(return_value=expected)
    habitat._has_expected_workspace_mount = MagicMock(return_value=False)
    recreated = FakeContainer(status="running")
    habitat._create_container = MagicMock(return_value=recreated)
    habitat._recreate_container = MagicMock()

    result = habitat._get_or_create_container()

    assert result is recreated
    habitat._recreate_container.assert_called_once_with(existing)
    habitat._create_container.assert_called_once_with(expected)


def test_get_or_create_container_starts_existing_stopped_container(tmp_path):
    existing = FakeContainer(status="exited")
    client = SimpleNamespace(
        containers=SimpleNamespace(get=MagicMock(return_value=existing))
    )
    habitat = _new_habitat_with_client(client)
    expected = tmp_path / "expected"
    expected.mkdir(parents=True)
    habitat._resolve_workspace_path = MagicMock(return_value=expected)
    habitat._has_expected_workspace_mount = MagicMock(return_value=True)

    result = habitat._get_or_create_container()

    assert result is existing
    assert existing.start_calls == 1
    assert existing.reload_calls >= 1


def test_get_or_create_container_creates_when_not_found(monkeypatch):
    class NotFoundError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "NotFound", NotFoundError)
    client = SimpleNamespace(
        containers=SimpleNamespace(get=MagicMock(side_effect=NotFoundError()))
    )
    habitat = _new_habitat_with_client(client)
    created = FakeContainer()
    habitat._create_container = MagicMock(return_value=created)

    result = habitat._get_or_create_container()

    assert result is created
    habitat._create_container.assert_called_once_with()


def test_execute_raises_when_container_not_running():
    habitat = _new_habitat_with_client(client=SimpleNamespace())
    habitat.container = FakeContainer(status="exited")

    with pytest.raises(RuntimeError, match="nie działa"):
        habitat.execute("echo hi")


def test_execute_returns_output_and_handles_empty_bytes():
    habitat = _new_habitat_with_client(client=SimpleNamespace())
    habitat.container = FakeContainer(status="running", output=b"hello\n", exit_code=0)
    exit_code, output = habitat.execute("echo hello")
    assert exit_code == 0
    assert output == "hello\n"

    habitat.container = FakeContainer(status="running", output=None, exit_code=0)
    exit_code, output = habitat.execute("echo hello")
    assert exit_code == 0
    assert output == ""


def test_execute_wraps_exec_exception():
    habitat = _new_habitat_with_client(client=SimpleNamespace())
    container = FakeContainer(status="running")
    container.exec_run = MagicMock(side_effect=RuntimeError("exec failed"))
    habitat.container = container

    with pytest.raises(RuntimeError, match="Błąd podczas wykonywania komendy"):
        habitat.execute("echo hi")


def test_cleanup_stops_and_removes_container_and_swallows_errors():
    habitat = _new_habitat_with_client(client=SimpleNamespace())
    container = FakeContainer(status="running")
    habitat.container = container

    habitat.cleanup()
    assert container.stop_calls == 1
    assert container.remove_calls == [False]

    container_err = FakeContainer(status="running")
    container_err.stop = MagicMock(side_effect=RuntimeError("stop"))
    habitat.container = container_err
    habitat.cleanup()
