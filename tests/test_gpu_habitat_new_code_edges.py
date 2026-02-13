"""Additional edge-case tests for GPUHabitat branches."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import venom_core.infrastructure.gpu_habitat as gpu_habitat_mod


@pytest.fixture(autouse=True)
def ensure_docker_stub(monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.SETTINGS, "ACADEMY_USE_LOCAL_RUNTIME", False)
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
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=True, use_local_runtime=False)
    assert habitat.is_gpu_available() is False


def test_get_job_container_resolves_container_by_id(monkeypatch):
    class _Client(_DummyDockerClient):
        def __init__(self):
            super().__init__()
            self._container = _DummyContainer(cid="container-xyz")
            self.containers = SimpleNamespace(get=lambda _cid: self._container)

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", lambda: _Client())
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False, use_local_runtime=False)
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
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False, use_local_runtime=False)
    habitat.training_containers["job-missing"] = {"container_id": "missing"}

    with pytest.raises(KeyError):
        habitat._get_job_container("job-missing")


def test_get_training_status_maps_preparing_and_dead(monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", _DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False, use_local_runtime=False)
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
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False, use_local_runtime=False)
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
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False, use_local_runtime=False)
    habitat.training_containers["job-legacy"] = {"container": _LegacyContainer()}

    habitat.cleanup_job("job-legacy")
    assert "job-legacy" not in habitat.training_containers


def test_get_gpu_info_handles_empty_output(monkeypatch):
    class _Client(_DummyDockerClient):
        def __init__(self):
            super().__init__()
            self.containers = SimpleNamespace(run=lambda **_kwargs: b"")

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", lambda: _Client())
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=True, use_local_runtime=False)

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
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False, use_local_runtime=False)
    habitat.training_containers["job-logs"] = {"container_id": "c1"}

    lines = list(habitat.stream_job_logs("job-logs"))
    assert lines == ["valid-line"]


def test_validate_local_job_pid_accepts_matching_proc_metadata(monkeypatch):
    habitat = gpu_habitat_mod.GPUHabitat.__new__(gpu_habitat_mod.GPUHabitat)

    class _FakePath:
        registry = {
            "/proc/123": {"exists": True, "resolve": "/proc/123"},
            "/proc/123/cwd": {"exists": True, "resolve": "/tmp/out"},
            "/proc/123/cmdline": {
                "exists": True,
                "text": "python\x00/tmp/script.py\x00",
            },
            "/tmp/out": {"exists": True, "resolve": "/tmp/out"},
            "/tmp/script.py": {"exists": True, "resolve": "/tmp/script.py"},
        }

        def __init__(self, value):
            self.value = str(value)

        def exists(self):
            return self.registry.get(self.value, {}).get("exists", False)

        def resolve(self):
            resolved = self.registry.get(self.value, {}).get("resolve", self.value)
            return _FakePath(resolved)

        def read_text(self, encoding="utf-8"):
            _ = encoding
            return self.registry[self.value]["text"]

        def __truediv__(self, part):
            return _FakePath(f"{self.value.rstrip('/')}/{part}")

        def __eq__(self, other):
            return isinstance(other, _FakePath) and self.value == other.value

    monkeypatch.setattr(gpu_habitat_mod, "Path", _FakePath)

    pid = habitat._validate_local_job_pid(
        {
            "pid": 123,
            "output_dir": "/tmp/out",
            "script_path": "/tmp/script.py",
        }
    )
    assert pid == 123


def test_validate_local_job_pid_rejects_mismatch_or_invalid(monkeypatch):
    habitat = gpu_habitat_mod.GPUHabitat.__new__(gpu_habitat_mod.GPUHabitat)

    class _FakePath:
        registry = {
            "/proc/123": {"exists": True, "resolve": "/proc/123"},
            "/proc/123/cwd": {"exists": True, "resolve": "/other/cwd"},
            "/proc/123/cmdline": {
                "exists": True,
                "text": "python\x00/other/script.py\x00",
            },
            "/tmp/out": {"exists": True, "resolve": "/tmp/out"},
            "/tmp/script.py": {"exists": True, "resolve": "/tmp/script.py"},
        }

        def __init__(self, value):
            self.value = str(value)

        def exists(self):
            return self.registry.get(self.value, {}).get("exists", False)

        def resolve(self):
            resolved = self.registry.get(self.value, {}).get("resolve", self.value)
            return _FakePath(resolved)

        def read_text(self, encoding="utf-8"):
            _ = encoding
            return self.registry[self.value]["text"]

        def __truediv__(self, part):
            return _FakePath(f"{self.value.rstrip('/')}/{part}")

        def __eq__(self, other):
            return isinstance(other, _FakePath) and self.value == other.value

    monkeypatch.setattr(gpu_habitat_mod, "Path", _FakePath)

    assert (
        habitat._validate_local_job_pid(
            {
                "pid": 123,
                "output_dir": "/tmp/out",
                "script_path": "/tmp/script.py",
            }
        )
        is None
    )
    assert habitat._validate_local_job_pid({"pid": "bad"}) is None


def test_signal_validated_local_job_sends_signal_only_when_pid_valid(monkeypatch):
    habitat = gpu_habitat_mod.GPUHabitat.__new__(gpu_habitat_mod.GPUHabitat)
    calls = []
    monkeypatch.setattr(habitat, "_validate_local_job_pid", lambda _job: 321)
    monkeypatch.setattr(
        gpu_habitat_mod.os, "kill", lambda pid, sig: calls.append((pid, sig))
    )

    sent = habitat._signal_validated_local_job(
        "job-a", {"pid": 321}, gpu_habitat_mod.signal.SIGTERM
    )
    assert sent is True
    assert calls and calls[0][0] == 321

    monkeypatch.setattr(habitat, "_validate_local_job_pid", lambda _job: None)
    sent = habitat._signal_validated_local_job(
        "job-b", {"pid": 999}, gpu_habitat_mod.signal.SIGTERM
    )
    assert sent is False


def test_get_local_job_status_uses_validated_pid_when_process_missing(monkeypatch):
    habitat = gpu_habitat_mod.GPUHabitat.__new__(gpu_habitat_mod.GPUHabitat)
    habitat.training_containers = {
        "job-local": {"pid": 111, "process": None, "log_file": "/tmp/does-not-exist"}
    }
    monkeypatch.setattr(habitat, "_validate_local_job_pid", lambda _job: 111)

    status = habitat._get_local_job_status("job-local")
    assert status["status"] == "running"


def test_cleanup_job_local_pid_without_process_uses_validated_signal(monkeypatch):
    habitat = gpu_habitat_mod.GPUHabitat.__new__(gpu_habitat_mod.GPUHabitat)
    habitat.training_containers = {
        "job-local": {"type": "local", "pid": 222, "process": None}
    }
    called = []
    monkeypatch.setattr(
        habitat,
        "_signal_validated_local_job",
        lambda job_name, job_info, sig: called.append(
            (job_name, job_info.get("pid"), sig)
        )
        or True,
    )

    habitat.cleanup_job("job-local")
    assert called and called[0][0] == "job-local"
    assert "job-local" not in habitat.training_containers
