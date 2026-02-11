"""Testy jednostkowe dla Academy API."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy as academy_routes


@pytest.fixture
def mock_professor():
    """Fixture dla zmockowanego Professor."""
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_dataset_curator():
    """Fixture dla zmockowanego DatasetCurator."""
    mock = MagicMock()
    mock.clear = MagicMock()
    mock.collect_from_lessons = MagicMock(return_value=150)
    mock.collect_from_git_history = MagicMock(return_value=50)
    mock.filter_low_quality = MagicMock(return_value=10)
    mock.save_dataset = MagicMock(return_value="./data/training/dataset_123.jsonl")
    mock.get_statistics = MagicMock(
        return_value={
            "total_examples": 190,
            "avg_input_length": 250,
            "avg_output_length": 180,
        }
    )
    return mock


@pytest.fixture
def mock_gpu_habitat():
    """Fixture dla zmockowanego GPUHabitat."""
    mock = MagicMock()
    mock.is_gpu_available = MagicMock(return_value=True)
    mock.run_training_job = MagicMock(
        return_value={
            "job_name": "training_test",
            "container_id": "abc123",
            "adapter_path": "./data/models/training_0/adapter",
        }
    )
    mock.get_training_status = MagicMock(
        return_value={"status": "running", "logs": "Training in progress..."}
    )
    return mock


@pytest.fixture
def mock_lessons_store():
    """Fixture dla zmockowanego LessonsStore."""
    mock = MagicMock()
    mock.get_statistics = MagicMock(return_value={"total_lessons": 250})
    return mock


@pytest.fixture
def mock_model_manager():
    """Fixture dla zmockowanego ModelManager."""
    mock = MagicMock()
    return mock


@pytest.fixture
def app_with_academy(
    mock_professor,
    mock_dataset_curator,
    mock_gpu_habitat,
    mock_lessons_store,
    mock_model_manager,
):
    """Fixture dla FastAPI app z academy routerem."""
    app = FastAPI()
    academy_routes.set_dependencies(
        professor=mock_professor,
        dataset_curator=mock_dataset_curator,
        gpu_habitat=mock_gpu_habitat,
        lessons_store=mock_lessons_store,
        model_manager=mock_model_manager,
    )
    app.include_router(academy_routes.router)
    return app


@pytest.fixture
def client(app_with_academy):
    """Fixture dla test clienta."""
    return TestClient(app_with_academy)


@patch("venom_core.config.SETTINGS")
def test_academy_status_enabled(mock_settings, client, mock_lessons_store):
    """Test pobierania statusu Academy - enabled."""
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_MIN_LESSONS = 100
    mock_settings.ACADEMY_TRAINING_INTERVAL_HOURS = 24
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"
    mock_settings.ACADEMY_ENABLE_GPU = True

    response = client.get("/api/v1/academy/status")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["components"]["professor"] is True
    assert data["components"]["dataset_curator"] is True
    assert data["components"]["gpu_habitat"] is True
    assert data["components"]["lessons_store"] is True
    assert data["gpu"]["enabled"] is True
    assert data["lessons"]["total_lessons"] == 250
    assert data["config"]["min_lessons"] == 100


@patch("venom_core.config.SETTINGS")
def test_curate_dataset_success(mock_settings, client, mock_dataset_curator):
    """Test kuracji datasetu - sukces."""
    mock_settings.ENABLE_ACADEMY = True

    response = client.post(
        "/api/v1/academy/dataset",
        json={"lessons_limit": 200, "git_commits_limit": 100, "format": "alpaca"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["dataset_path"] == "./data/training/dataset_123.jsonl"
    assert data["statistics"]["total_examples"] == 190
    assert data["statistics"]["lessons_collected"] == 150
    assert data["statistics"]["git_commits_collected"] == 50

    # Verify mocks were called
    mock_dataset_curator.clear.assert_called_once()
    mock_dataset_curator.collect_from_lessons.assert_called_once_with(limit=200)
    mock_dataset_curator.collect_from_git_history.assert_called_once_with(
        max_commits=100
    )


@patch("venom_core.config.SETTINGS")
def test_curate_dataset_validation(mock_settings, client):
    """Test walidacji parametrów kuracji datasetu."""
    mock_settings.ENABLE_ACADEMY = True

    # Invalid lessons_limit (too high)
    response = client.post(
        "/api/v1/academy/dataset", json={"lessons_limit": 2000}
    )
    assert response.status_code == 422

    # Invalid format
    response = client.post("/api/v1/academy/dataset", json={"format": "invalid"})
    assert response.status_code == 422


@patch("venom_core.config.SETTINGS")
@patch("venom_core.api.routes.academy._load_jobs_history")
@patch("venom_core.api.routes.academy._save_job_to_history")
def test_start_training_success(
    mock_save_job,
    mock_load_jobs,
    mock_settings,
    client,
    mock_gpu_habitat,
):
    """Test rozpoczęcia treningu - sukces."""
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_TRAINING_DIR = "./data/training"
    mock_settings.ACADEMY_MODELS_DIR = "./data/models"
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"
    mock_load_jobs.return_value = []

    # Mock Path.exists and glob
    with patch("pathlib.Path.exists") as mock_exists, patch(
        "pathlib.Path.glob"
    ) as mock_glob, patch("pathlib.Path.mkdir") as mock_mkdir:
        mock_exists.return_value = True
        mock_glob.return_value = ["./data/training/dataset_123.jsonl"]

        response = client.post(
            "/api/v1/academy/train",
            json={
                "lora_rank": 16,
                "learning_rate": 0.0002,
                "num_epochs": 3,
                "batch_size": 4,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "job_id" in data
    assert data["parameters"]["lora_rank"] == 16
    assert data["parameters"]["learning_rate"] == 0.0002

    # Verify training job was called
    mock_gpu_habitat.run_training_job.assert_called_once()


@patch("venom_core.config.SETTINGS")
def test_start_training_validation(mock_settings, client):
    """Test walidacji parametrów treningu."""
    mock_settings.ENABLE_ACADEMY = True

    # Invalid lora_rank (too high)
    response = client.post(
        "/api/v1/academy/train", json={"lora_rank": 100}
    )
    assert response.status_code == 422

    # Invalid learning_rate (too high)
    response = client.post(
        "/api/v1/academy/train", json={"learning_rate": 1.0}
    )
    assert response.status_code == 422

    # Invalid num_epochs (too high)
    response = client.post(
        "/api/v1/academy/train", json={"num_epochs": 50}
    )
    assert response.status_code == 422


@patch("venom_core.config.SETTINGS")
@patch("venom_core.api.routes.academy._load_jobs_history")
def test_list_jobs(mock_load_jobs, mock_settings, client):
    """Test listowania jobów."""
    mock_settings.ENABLE_ACADEMY = True
    mock_load_jobs.return_value = [
        {
            "job_id": "training_001",
            "status": "finished",
            "started_at": "2024-01-01T10:00:00",
        },
        {
            "job_id": "training_002",
            "status": "running",
            "started_at": "2024-01-02T10:00:00",
        },
    ]

    response = client.get("/api/v1/academy/jobs")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["jobs"]) == 2


@patch("venom_core.config.SETTINGS")
def test_academy_disabled(mock_settings, client):
    """Test gdy Academy jest wyłączone."""
    mock_settings.ENABLE_ACADEMY = False

    # Status endpoint should work but show disabled
    response = client.get("/api/v1/academy/status")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False

    # Other endpoints should return 503
    response = client.post("/api/v1/academy/dataset", json={})
    assert response.status_code == 503

    response = client.post("/api/v1/academy/train", json={})
    assert response.status_code == 503


@patch("venom_core.config.SETTINGS")
@patch("pathlib.Path.exists")
def test_activate_adapter_success(
    mock_exists, mock_settings, client, mock_model_manager
):
    """Test aktywacji adaptera - sukces."""
    mock_settings.ENABLE_ACADEMY = True
    mock_exists.return_value = True
    mock_model_manager.activate_adapter.return_value = True

    response = client.post(
        "/api/v1/academy/adapters/activate",
        json={
            "adapter_id": "training_001",
            "adapter_path": "./data/models/training_001/adapter",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["adapter_id"] == "training_001"

    # Verify model manager was called
    mock_model_manager.activate_adapter.assert_called_once()


@patch("venom_core.config.SETTINGS")
def test_deactivate_adapter_success(mock_settings, client, mock_model_manager):
    """Test dezaktywacji adaptera - sukces."""
    mock_settings.ENABLE_ACADEMY = True
    mock_model_manager.deactivate_adapter.return_value = True

    response = client.post("/api/v1/academy/adapters/deactivate")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "base model" in data["message"].lower()

    # Verify model manager was called
    mock_model_manager.deactivate_adapter.assert_called_once()


@patch("venom_core.config.SETTINGS")
def test_deactivate_adapter_no_active(mock_settings, client, mock_model_manager):
    """Test dezaktywacji adaptera gdy brak aktywnego."""
    mock_settings.ENABLE_ACADEMY = True
    mock_model_manager.deactivate_adapter.return_value = False

    response = client.post("/api/v1/academy/adapters/deactivate")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "no active" in data["message"].lower()


@patch("venom_core.config.SETTINGS")
@patch("venom_core.api.routes.academy._load_jobs_history")
@patch("venom_core.api.routes.academy._update_job_in_history")
def test_cancel_training_with_cleanup(
    mock_update_job,
    mock_load_jobs,
    mock_settings,
    client,
    mock_gpu_habitat,
):
    """Test anulowania treningu z czyszczeniem kontenera."""
    mock_settings.ENABLE_ACADEMY = True
    mock_load_jobs.return_value = [
        {
            "job_id": "training_001",
            "job_name": "training_test",
            "status": "running",
        }
    ]

    response = client.delete("/api/v1/academy/train/training_001")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["job_id"] == "training_001"

    # Verify cleanup was called
    mock_gpu_habitat.cleanup_job.assert_called_once_with("training_test")
    mock_update_job.assert_called_once()


@patch("venom_core.config.SETTINGS")
@patch("venom_core.api.routes.academy._load_jobs_history")
def test_stream_training_logs_not_found(
    mock_load_jobs, mock_settings, client
):
    """Test streamowania logów dla nieistniejącego joba."""
    mock_settings.ENABLE_ACADEMY = True
    mock_load_jobs.return_value = []

    response = client.get("/api/v1/academy/train/nonexistent/logs/stream")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@patch("venom_core.api.routes.academy._load_jobs_history")
def test_stream_training_logs_success(
    mock_load_jobs_history,
    mock_professor, mock_dataset_curator, mock_gpu_habitat, mock_model_manager,
    client
):
    """Test poprawnego streamowania logów."""
    job_data = [{
        "job_id": "test_job",
        "job_name": "training_test",
        "status": "running"
    }]
    mock_load_jobs_history.return_value = job_data
    
    # Mock container exists
    mock_gpu_habitat.training_containers = {"training_test": "container_123"}
    mock_gpu_habitat.stream_job_logs = MagicMock(
        return_value=iter([
            "2024-01-01T10:00:00Z Starting training",
            "2024-01-01T10:00:01Z Epoch 1/3 - Loss: 0.45"
        ])
    )
    mock_gpu_habitat.get_training_status = MagicMock(
        return_value={"status": "running"}
    )
    
    response = client.get("/api/v1/academy/train/test_job/logs/stream")
    
    # SSE endpoint returns 200
    assert response.status_code == 200


def test_get_gpu_info_endpoint(
    mock_professor, mock_dataset_curator, mock_gpu_habitat, mock_model_manager,
    client
):
    """Test endpointu GPU info."""
    mock_gpu_habitat.get_gpu_info = MagicMock(return_value={
        "available": True,
        "count": 1,
        "gpus": [{
            "name": "NVIDIA RTX 3090",
            "memory_total_mb": 24576,
            "memory_used_mb": 2048,
            "memory_free_mb": 22528,
            "utilization_percent": 15.5
        }]
    })
    
    response = client.get("/api/v1/academy/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["gpu"]["available"] is True
    assert data["gpu"]["count"] == 1


@patch("venom_core.api.routes.academy._update_job_status")
@patch("venom_core.api.routes.academy._load_jobs_history")
def test_cancel_job_with_cleanup(
    mock_load_jobs_history,
    mock_update_status,
    mock_professor, mock_dataset_curator, mock_gpu_habitat, mock_model_manager,
    client
):
    """Test anulowania joba z cleanup."""
    job_data = [{
        "job_id": "test_job",
        "job_name": "training_test",
        "status": "running"
    }]
    mock_load_jobs_history.return_value = job_data
    mock_gpu_habitat.cleanup_job = MagicMock()
    
    response = client.delete("/api/v1/academy/train/test_job")
    
    assert response.status_code == 200
    mock_gpu_habitat.cleanup_job.assert_called_once_with("training_test")


def test_activate_adapter_with_model_manager(
    mock_professor, mock_dataset_curator, mock_gpu_habitat, mock_model_manager,
    client
):
    """Test aktywacji adaptera przez ModelManager."""
    mock_model_manager.activate_adapter = MagicMock(return_value=True)
    
    response = client.post(
        "/api/v1/academy/adapters/activate",
        json={"adapter_id": "test_adapter", "adapter_path": "./path/to/adapter"}
    )
    
    assert response.status_code == 200
    mock_model_manager.activate_adapter.assert_called_once()


def test_deactivate_adapter_success(
    mock_professor, mock_dataset_curator, mock_gpu_habitat, mock_model_manager,
    client
):
    """Test dezaktywacji adaptera."""
    mock_model_manager.deactivate_adapter = MagicMock()
    
    response = client.post("/api/v1/academy/adapters/deactivate")
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    mock_model_manager.deactivate_adapter.assert_called_once()


def test_list_adapters_with_active_state(
    mock_professor, mock_dataset_curator, mock_gpu_habitat, mock_model_manager,
    client
):
    """Test listowania adapterów z active state."""
    mock_professor.get_adapters_list = MagicMock(return_value=[
        {
            "adapter_id": "adapter_1",
            "adapter_path": "./path/1",
            "created_at": "2024-01-01T10:00:00"
        }
    ])
    mock_model_manager.get_active_adapter_info = MagicMock(return_value={
        "adapter_id": "adapter_1",
        "adapter_path": "./path/1"
    })
    
    response = client.get("/api/v1/academy/adapters")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["adapters"]) == 1
    assert data["adapters"][0]["is_active"] is True


def test_dataset_curate_with_validation_error(
    mock_professor, mock_dataset_curator, mock_gpu_habitat, mock_model_manager,
    client
):
    """Test walidacji parametrów kuracji datasetu."""
    
    # Invalid lesson limit (too high)
    response = client.post(
        "/api/v1/academy/dataset",
        json={"lessons_limit": 100000, "git_commits_limit": 100}
    )
    
    assert response.status_code == 422  # Validation error


def test_training_start_with_validation_error(
    mock_professor, mock_dataset_curator, mock_gpu_habitat, mock_model_manager,
    client
):
    """Test walidacji parametrów treningu."""
    
    # Invalid LoRA rank (too high)
    response = client.post(
        "/api/v1/academy/train",
        json={"lora_rank": 1000}
    )
    
    assert response.status_code == 422  # Validation error
