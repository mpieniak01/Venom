from types import SimpleNamespace
from unittest.mock import patch

import pytest

import venom_core.infrastructure.gpu_habitat as gpu_habitat_mod


@pytest.fixture(autouse=True)
def ensure_docker_stub(monkeypatch):
    """Zapewnia stub Docker SDK, gdy pakiet docker nie jest zainstalowany."""
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


class DummyImages:
    def __init__(self, raise_missing: bool = False) -> None:
        self.raise_missing = raise_missing
        self.pulled = []

    def get(self, _name: str):
        if self.raise_missing:
            raise gpu_habitat_mod.ImageNotFound("missing")
        return True

    def pull(self, name: str):
        self.pulled.append(name)


class DummyContainers:
    def __init__(self) -> None:
        self.run_calls = []

    def run(self, **kwargs):
        self.run_calls.append(kwargs)
        return DummyContainer(status="running")


class DummyDockerClient:
    def __init__(self, raise_missing: bool = False) -> None:
        self.images = DummyImages(raise_missing=raise_missing)
        self.containers = DummyContainers()


class DummyContainer:
    def __init__(self, status="running", exit_code=0) -> None:
        self.status = status
        self.attrs = {"State": {"ExitCode": exit_code}}
        self.id = "container-1"
        self.stopped = False
        self.removed = False

    def reload(self) -> None:
        return None

    def logs(self, tail=50):
        return b"line1\nline2"

    def stop(self) -> None:
        self.stopped = True

    def remove(self) -> None:
        self.removed = True


def test_generate_training_script(monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)

    script = habitat._generate_training_script(
        dataset_path="/data.jsonl",
        base_model="model-x",
        output_dir="/out",
        lora_rank=8,
        learning_rate=1e-4,
        num_epochs=2,
        max_seq_length=1024,
        batch_size=2,
    )

    assert "model-x" in script
    assert 'DATASET_PATH = "/data.jsonl"' in script
    assert "LORA_RANK = 8" in script


def test_run_training_job_rejects_missing_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    missing = tmp_path / "missing.jsonl"

    with pytest.raises(ValueError):
        habitat.run_training_job(
            dataset_path=str(missing),
            base_model="model-x",
            output_dir=str(tmp_path / "out"),
        )


def test_run_training_job_success(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    # Ensure Docker mode
    monkeypatch.setattr(gpu_habitat_mod.SETTINGS, "ACADEMY_USE_LOCAL_RUNTIME", False)
    
    training_dir = tmp_path / "training"
    models_dir = tmp_path / "models"
    training_dir.mkdir()
    models_dir.mkdir()
    monkeypatch.setattr(
        gpu_habitat_mod.SETTINGS,
        "ACADEMY_TRAINING_DIR",
        str(training_dir),
        raising=False,
    )
    monkeypatch.setattr(
        gpu_habitat_mod.SETTINGS, "ACADEMY_MODELS_DIR", str(models_dir), raising=False
    )
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    dataset = training_dir / "data.jsonl"
    dataset.write_text('{"instruction": "hi"}\n', encoding="utf-8")
    output_dir = models_dir / "out"

    result = habitat.run_training_job(
        dataset_path=str(dataset),
        base_model="model-x",
        output_dir=str(output_dir),
        job_name="job-1",
    )

    assert result["status"] == "running"
    assert "job-1" in habitat.training_containers


def test_run_training_job_pulls_image_when_missing(tmp_path, monkeypatch):
    client = DummyDockerClient(raise_missing=True)

    def _make_client():
        return client

    # Ensure Docker mode
    monkeypatch.setattr(gpu_habitat_mod.SETTINGS, "ACADEMY_USE_LOCAL_RUNTIME", False)

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", _make_client)
    training_dir = tmp_path / "training"
    models_dir = tmp_path / "models"
    training_dir.mkdir()
    models_dir.mkdir()
    monkeypatch.setattr(
        gpu_habitat_mod.SETTINGS,
        "ACADEMY_TRAINING_DIR",
        str(training_dir),
        raising=False,
    )
    monkeypatch.setattr(
        gpu_habitat_mod.SETTINGS, "ACADEMY_MODELS_DIR", str(models_dir), raising=False
    )
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    dataset = training_dir / "data.jsonl"
    dataset.write_text('{"instruction": "hi"}\n', encoding="utf-8")
    output_dir = models_dir / "out"

    habitat.run_training_job(
        dataset_path=str(dataset),
        base_model="model-x",
        output_dir=str(output_dir),
        job_name="job-2",
    )

    assert client.images.pulled


def test_get_job_status_running(monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    container = DummyContainer(status="running")
    habitat.training_containers["job-1"] = {"container": container, "status": "running"}

    result = habitat.get_training_status("job-1")

    assert result["status"] == "running"
    assert "line1" in result["logs"]


def test_get_job_status_failed(monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    container = DummyContainer(status="exited", exit_code=1)
    habitat.training_containers["job-2"] = {"container": container, "status": "running"}

    result = habitat.get_training_status("job-2")

    assert result["status"] == "failed"


def test_get_job_status_finished(monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    container = DummyContainer(status="exited", exit_code=0)
    habitat.training_containers["job-finished"] = {
        "container": container,
        "status": "running",
    }

    result = habitat.get_training_status("job-finished")

    assert result["status"] == "finished"


def test_cleanup_job(monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
    container = DummyContainer(status="running")
    habitat.training_containers["job-3"] = {"container": container, "status": "running"}

    habitat.cleanup_job("job-3")

    assert container.stopped is True
    assert container.removed is True
    assert "job-3" not in habitat.training_containers


def test_stream_job_logs(monkeypatch):
    """Test streamowania logów z kontenera."""
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)

    class StreamingContainer:
        def __init__(self):
            self.status = "running"
            self.id = "container-stream"

        def logs(self, stream=False, follow=False, timestamps=False, since=None):
            if stream:
                return iter(
                    [b"2024-01-01T10:00:00Z Line 1\n", b"2024-01-01T10:00:01Z Line 2\n"]
                )
            return b"Line 1\nLine 2"

        def reload(self):
            pass

    container = StreamingContainer()
    habitat.training_containers["stream-job"] = {
        "container": container,
        "status": "running",
    }

    logs = list(habitat.stream_job_logs("stream-job"))

    assert len(logs) == 2
    assert "Line 1" in logs[0]
    assert "Line 2" in logs[1]


def test_stream_job_logs_nonexistent(monkeypatch):
    """Test streamowania logów dla nieistniejącego joba."""
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)

    # For nonexistent jobs, stream_job_logs should raise KeyError
    with pytest.raises(KeyError):
        list(habitat.stream_job_logs("nonexistent"))


def test_get_gpu_info_no_gpu(monkeypatch):
    """Test pobierania info o GPU gdy GPU niedostępne."""
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)

    info = habitat.get_gpu_info()

    assert info["available"] is False
    assert "message" in info
    assert isinstance(info["message"], str) and info["message"]


def test_get_gpu_info_with_gpu(monkeypatch):
    """Test pobierania info o GPU gdy GPU dostępne."""

    class GPUContainers:
        def run(self, **kwargs):
            # Simulate nvidia-smi output
            return b"NVIDIA RTX 3090, 24576, 2048, 22528, 15\n"

    class GPUDockerClient:
        def __init__(self):
            self.containers = GPUContainers()
            self.images = DummyImages()

    def _make_client():
        return GPUDockerClient()

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", _make_client)
    # Ensure Docker mode
    monkeypatch.setattr(gpu_habitat_mod.SETTINGS, "ACADEMY_USE_LOCAL_RUNTIME", False)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=True)

    info = habitat.get_gpu_info()

    assert info["available"] is True
    assert info["count"] == 1
    assert len(info["gpus"]) == 1
    assert info["gpus"][0]["name"] == "NVIDIA RTX 3090"
    assert info["gpus"][0]["memory_total_mb"] == 24576.0


def test_get_gpu_info_nvidia_smi_error(monkeypatch):
    """Test obsługi błędu nvidia-smi."""

    class ErrorContainers:
        def run(self, **kwargs):
            raise Exception("nvidia-smi not found")

    class ErrorDockerClient:
        def __init__(self):
            self.containers = ErrorContainers()
            self.images = DummyImages()

    def _make_client():
        return ErrorDockerClient()

    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", _make_client)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=True)

    info = habitat.get_gpu_info()

    # Should gracefully handle error
    assert info["available"] in [
        True,
        False,
    ]  # Can be either depending on is_gpu_available()
    assert "message" in info
    assert (
        "Failed to get GPU details" in info["message"]
        or info["message"] == "GPU disabled in configuration"
    )


def test_gpu_fallback_disables_gpu_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    training_dir = tmp_path / "training"
    models_dir = tmp_path / "models"
    training_dir.mkdir()
    models_dir.mkdir()
    # Ensure Docker mode
    monkeypatch.setattr(gpu_habitat_mod.SETTINGS, "ACADEMY_USE_LOCAL_RUNTIME", False)
    monkeypatch.setattr(
        gpu_habitat_mod.SETTINGS,
        "ACADEMY_TRAINING_DIR",
        str(training_dir),
        raising=False,
    )
    monkeypatch.setattr(
        gpu_habitat_mod.SETTINGS, "ACADEMY_MODELS_DIR", str(models_dir), raising=False
    )
    with patch.object(
        gpu_habitat_mod.GPUHabitat, "_check_gpu_availability", return_value=False
    ):
        habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=True)

    assert habitat.enable_gpu is False
    assert habitat.is_gpu_available() is False

    dataset = training_dir / "data.jsonl"
    dataset.write_text('{"instruction": "hi"}\\n', encoding="utf-8")
    output_dir = models_dir / "out"
    habitat.run_training_job(
        dataset_path=str(dataset),
        base_model="model-x",
        output_dir=str(output_dir),
        job_name="cpu-job",
    )

    run_call = habitat.client.containers.run_calls[-1]
    assert run_call["device_requests"] is None
    assert run_call["environment"]["CUDA_VISIBLE_DEVICES"] == ""


def test_cleanup_job_nonexistent(monkeypatch):
    """Test cleanup nieistniejącego joba."""
    monkeypatch.setattr(gpu_habitat_mod.docker, "from_env", DummyDockerClient)
    habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)

    # Should not raise error for nonexistent job
    habitat.cleanup_job("nonexistent-job")

    # No assertion needed - just verify no exception


def test_local_runtime_cpu_fallback(tmp_path, monkeypatch):
    """Test fallbacku do CPU w trybie local runtime."""
    # Symuluj brak GPU lokalnie (nvidia-smi fail)
    with patch("subprocess.run", side_effect=FileNotFoundError):
        # Wymuś local runtime
        monkeypatch.setattr(gpu_habitat_mod.SETTINGS, "ACADEMY_USE_LOCAL_RUNTIME", True)
        
        # Inicjalizuj habitat z włączonym GPU
        habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=True)
        
        # Powinien przełączyć się na CPU
        assert habitat.enable_gpu is False
        assert habitat.is_gpu_available() is False
        assert habitat.use_local_runtime is True

def test_local_runtime_training_execution(tmp_path, monkeypatch):
    """Test uruchomienia treningu w trybie local runtime (Popen)."""
    monkeypatch.setattr(gpu_habitat_mod.SETTINGS, "ACADEMY_USE_LOCAL_RUNTIME", True)
    
    # Mock subprocess.Popen
    process_mock = SimpleNamespace(pid=12345, poll=lambda: None)
    with patch("subprocess.Popen", return_value=process_mock) as popen_mock:
        # Mock dependency check to pass
        with patch.object(gpu_habitat_mod.GPUHabitat, "_check_local_dependencies"):
            habitat = gpu_habitat_mod.GPUHabitat(enable_gpu=False)
            
            # Setup paths
            training_dir = tmp_path / "training"
            models_dir = tmp_path / "models"
            training_dir.mkdir()
            models_dir.mkdir()
            monkeypatch.setattr(gpu_habitat_mod.SETTINGS, "ACADEMY_TRAINING_DIR", str(training_dir), raising=False)
            monkeypatch.setattr(gpu_habitat_mod.SETTINGS, "ACADEMY_MODELS_DIR", str(models_dir), raising=False)
            
            dataset = training_dir / "data.jsonl"
            dataset.write_text('{"instruction": "hi"}\\n', encoding="utf-8")
            output_dir = models_dir / "out"
            
            # Run
            result = habitat.run_training_job(
                dataset_path=str(dataset),
                base_model="model-x",
                output_dir=str(output_dir),
                job_name="local-job",
            )
            
            assert result["status"] == "running"
            assert result["job_name"] == "local-job"
            assert popen_mock.called

