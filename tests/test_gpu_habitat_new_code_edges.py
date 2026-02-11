"""Additional edge-case tests for GPUHabitat branches."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import venom_core.infrastructure.gpu_habitat as gpu_habitat_mod


@pytest.fixture(autouse=True)
def ensure_docker_stub(monkeypatch):
    if gpu_habitat_mod.docker is None:
        docker_stub = SimpleNamespace(
            from_env=lambda: None,
            types=SimpleNamespace(
                DeviceRequest=lambda **kwargs: {
                    "count": kwargs.get("count"),
                    "capabilities": kwargs.get("capabilities"),
                }
            ),
        )
        monkeypatch.setattr(gpu_habitat_mod, "docker", docker_stub)


class _DummyContainer:
    def __init__(self, status="running", exit_code=0, logs=b"ok\n", cid="c-1"):
        self.status = status
        self.attrs = {"State": {"ExitCode": exit_code}}
        self._logs = logs
        self.id = cid

    def reload(self):
        return None

    def logs(self, **_kwargs):
        return self._logs

    def stop(self, *args, **kwargs):  # pragma: no cover - behavior driven by tests
        return None

    def remove(self, *args, **kwargs):  # pragma: no cover - behavior driven by tests
        return None


class _DummyDockerClient:
    def __init__(self):
        self.images = SimpleNamespace(
            get=lambda _name: True,
            pull=lambda _name: True,
        )
        self.containers = SimpleNamespace(
            run=lambda **_kwargs: b"",
            get=lambda _cid: _DummyContainer(),
        )


def test_check_gpu_availability_handles_api_error(monkeypatch):
    class _Client:
        def __init__(self):
            self.images = SimpleNamespace(
                get=lambda _name: True,
                pull=lambda _name: True,
            )
            self.containers = SimpleNamespace(
                run=lambda **_kwargs: (_ for _ in ()).throw(
                    gpu_habitat_mod.APIError("no gpu")
                )
            )

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", lambda: _Client())
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=True)
    assert habitat.is_gpu_available() is False


def test_get_job_container_resolves_container_by_id(monkeypatch):
    class _Client(_DummyDockerClient):
        def __init__(self):
            super().__init__()
            self._container = _DummyContainer(cid="container-xyz")
            self.containers = SimpleNamespace(get=lambda _cid: self._container)

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", lambda: _Client())
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    habitat.training_containers["job-1"] = {"container_id": "container-xyz"}

    container = habitat._get_job_container("job-1")
    assert container.id == "container-xyz"
    assert habitat.training_containers["job-1"]["container"] is container


def test_get_job_container_raises_key_error_when_container_lookup_fails(monkeypatch):
    class _Client(_DummyDockerClient):
        def __init__(self):
            super().__init__()
            self.containers = SimpleNamespace(
                get=lambda _cid: (_ for _ in ()).throw(RuntimeError("not found"))
            )

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", lambda: _Client())
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    habitat.training_containers["job-missing"] = {"container_id": "missing"}

    with pytest.raises(KeyError):
        habitat._get_job_container("job-missing")


def test_get_training_status_maps_preparing_and_dead(monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", _DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    habitat.training_containers["job-prep"] = {
        "container": _DummyContainer(status="created")
    }
    habitat.training_containers["job-dead"] = {
        "container": _DummyContainer(status="dead")
    }

    prep = habitat.get_training_status("job-prep")
    dead = habitat.get_training_status("job-dead")
    assert prep["status"] == "preparing"
    assert dead["status"] == "failed"


def test_get_training_status_returns_error_payload_on_exception(monkeypatch):
    class _ExplodingContainer(_DummyContainer):
        def logs(self, **_kwargs):
            raise RuntimeError("cannot read logs")

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", _DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    habitat.training_containers["job-err"] = {"container": _ExplodingContainer()}

    status = habitat.get_training_status("job-err")
    assert status["status"] == "failed"
    assert "cannot read logs" in status["error"]
    assert status["container_id"] == "c-1"


def test_cleanup_job_falls_back_on_typeerror_stop_remove(monkeypatch):
    class _LegacyContainer(_DummyContainer):
        def stop(self, *args, **kwargs):
            if kwargs.get("timeout") == 10:
                raise TypeError("legacy stop signature")
            return None

        def remove(self, *args, **kwargs):
            if kwargs.get("force"):
                raise TypeError("legacy remove signature")
            return None

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", _DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    habitat.training_containers["job-legacy"] = {"container": _LegacyContainer()}

    habitat.cleanup_job("job-legacy")
    assert "job-legacy" not in habitat.training_containers


def test_get_gpu_info_handles_empty_output(monkeypatch):
    class _Client(_DummyDockerClient):
        def __init__(self):
            super().__init__()
            self.containers = SimpleNamespace(run=lambda **_kwargs: b"")

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", lambda: _Client())
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=True)

    info = habitat.get_gpu_info()
    assert info["available"] is True
    assert info["gpus"] == []


def test_stream_job_logs_skips_unicode_decode_errors(monkeypatch):
    class _Container:
        def logs(self, **_kwargs):
            return iter([b"\xff\xfe", b"valid-line\n"])

    class _Client(_DummyDockerClient):
        def __init__(self):
            super().__init__()
            self.containers = SimpleNamespace(get=lambda _cid: _Container())

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", lambda: _Client())
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    habitat.training_containers["job-logs"] = {"container_id": "c1"}

    lines = list(habitat.stream_job_logs("job-logs"))
    assert lines == ["valid-line"]
