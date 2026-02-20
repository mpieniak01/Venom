"""Testy jednostkowe dla Academy API."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy as academy_routes


@pytest.fixture
def mock_professor():
    return MagicMock()


@pytest.fixture
def mock_dataset_curator():
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
    mock = MagicMock()
    mock.training_containers = {}
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
    mock.cleanup_job = MagicMock()
    return mock


@pytest.fixture
def mock_lessons_store():
    mock = MagicMock()
    mock.get_statistics = MagicMock(return_value={"total_lessons": 250})
    return mock


@pytest.fixture
def mock_model_manager():
    return MagicMock()


@pytest.fixture
def app_with_academy(
    mock_professor,
    mock_dataset_curator,
    mock_gpu_habitat,
    mock_lessons_store,
    mock_model_manager,
):
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
    # Domyślnie bypass guarda localhost dla testów funkcjonalnych endpointów.
    with patch(
        "venom_core.api.routes.academy.require_localhost_request", return_value=None
    ):
        yield TestClient(app_with_academy)


@pytest.fixture
def strict_client(app_with_academy):
    # Bez patcha guarda – oczekujemy 403 dla endpointów mutujących.
    return TestClient(app_with_academy)


@patch("venom_core.config.SETTINGS")
def test_academy_status_enabled(mock_settings, client):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_MIN_LESSONS = 100
    mock_settings.ACADEMY_TRAINING_INTERVAL_HOURS = 24
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"
    mock_settings.ACADEMY_ENABLE_GPU = True

    response = client.get("/api/v1/academy/status")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["jobs"]["finished"] == 0


@patch("venom_core.config.SETTINGS")
def test_curate_dataset_success(mock_settings, client, mock_dataset_curator):
    mock_settings.ENABLE_ACADEMY = True

    response = client.post(
        "/api/v1/academy/dataset",
        json={"lessons_limit": 200, "git_commits_limit": 100, "format": "alpaca"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["statistics"]["lessons_collected"] == 150
    mock_dataset_curator.collect_from_git_history.assert_called_once_with(
        max_commits=100
    )


@patch("venom_core.config.SETTINGS")
def test_curate_dataset_validation(mock_settings, client):
    mock_settings.ENABLE_ACADEMY = True

    response = client.post("/api/v1/academy/dataset", json={"lessons_limit": 2000})
    assert response.status_code == 422


@patch("venom_core.config.SETTINGS")
@patch("venom_core.api.routes.academy._update_job_in_history")
@patch("venom_core.api.routes.academy._save_job_to_history")
def test_start_training_tracks_queued_preparing_running(
    mock_save_job,
    mock_update_job,
    mock_settings,
    client,
    mock_gpu_habitat,
):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_TRAINING_DIR = "./data/training"
    mock_settings.ACADEMY_MODELS_DIR = "./data/models"
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch(
            "pathlib.Path.glob",
            return_value=[Path("./data/training/dataset_123.jsonl")],
        ),
        patch("pathlib.Path.mkdir"),
    ):
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
    body = response.json()
    assert body["success"] is True
    assert body["job_id"].startswith("training_")

    run_call = mock_gpu_habitat.run_training_job.call_args.kwargs
    assert run_call["job_name"] == body["job_id"]

    queued_record = mock_save_job.call_args.args[0]
    assert queued_record["status"] == "queued"
    assert queued_record["job_name"] == body["job_id"]

    status_updates = [call.args[1]["status"] for call in mock_update_job.call_args_list]
    assert "preparing" in status_updates
    assert "running" in status_updates


@patch("venom_core.config.SETTINGS")
@patch("venom_core.api.routes.academy._update_job_in_history")
@patch("venom_core.api.routes.academy._load_jobs_history")
def test_get_training_status_maps_completed_to_finished_and_writes_metadata(
    mock_load_jobs,
    mock_update_job,
    mock_settings,
    client,
    mock_gpu_habitat,
    tmp_path,
):
    mock_settings.ENABLE_ACADEMY = True

    job_dir = tmp_path / "training_001"
    adapter_dir = job_dir / "adapter"
    adapter_dir.mkdir(parents=True)

    mock_load_jobs.return_value = [
        {
            "job_id": "training_001",
            "job_name": "training_001",
            "status": "running",
            "started_at": "2024-01-01T10:00:00",
            "output_dir": str(job_dir),
            "base_model": "base-model",
            "parameters": {"num_epochs": 1},
        }
    ]
    mock_gpu_habitat.get_training_status.return_value = {
        "status": "completed",
        "logs": "done",
    }

    response = client.get("/api/v1/academy/train/training_001/status")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "finished"
    assert data["adapter_path"].endswith("/adapter")
    mock_gpu_habitat.cleanup_job.assert_called_once_with("training_001")

    metadata_path = job_dir / "metadata.json"
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["job_id"] == "training_001"
    assert metadata["source"] == "academy"


@patch("venom_core.config.SETTINGS")
def test_list_jobs_filtered(mock_settings, client):
    mock_settings.ENABLE_ACADEMY = True
    with patch(
        "venom_core.api.routes.academy._load_jobs_history",
        return_value=[
            {"job_id": "a", "status": "running", "started_at": "2024-01-02"},
            {"job_id": "b", "status": "failed", "started_at": "2024-01-01"},
        ],
    ):
        response = client.get("/api/v1/academy/jobs?status=running")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["jobs"][0]["job_id"] == "a"


@patch("venom_core.config.SETTINGS")
def test_cancel_training_sets_cancelled_and_cleans_container(
    mock_settings,
    client,
    mock_gpu_habitat,
):
    mock_settings.ENABLE_ACADEMY = True
    with (
        patch(
            "venom_core.api.routes.academy._load_jobs_history",
            return_value=[{"job_id": "job1", "job_name": "job1", "status": "running"}],
        ),
        patch("venom_core.api.routes.academy._update_job_in_history") as mock_update,
    ):
        response = client.delete("/api/v1/academy/train/job1")

    assert response.status_code == 200
    mock_gpu_habitat.cleanup_job.assert_called_with("job1")
    update_payload = mock_update.call_args.args[1]
    assert update_payload["status"] == "cancelled"


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_success(mock_settings, client, mock_model_manager):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_MODELS_DIR = "./data/models"
    mock_model_manager.activate_adapter.return_value = True
    with patch("pathlib.Path.exists", return_value=True):
        response = client.post(
            "/api/v1/academy/adapters/activate",
            json={
                "adapter_id": "training_001",
                "adapter_path": "./data/models/training_001/adapter",
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True


@patch("venom_core.config.SETTINGS")
def test_deactivate_adapter_no_active(mock_settings, client, mock_model_manager):
    mock_settings.ENABLE_ACADEMY = True
    mock_model_manager.deactivate_adapter.return_value = False

    response = client.post("/api/v1/academy/adapters/deactivate")

    assert response.status_code == 200
    assert response.json()["success"] is False


@patch("venom_core.config.SETTINGS")
def test_localhost_guard_blocks_mutating_endpoints(mock_settings, strict_client):
    mock_settings.ENABLE_ACADEMY = True

    r_train = strict_client.post("/api/v1/academy/train", json={})
    r_activate = strict_client.post(
        "/api/v1/academy/adapters/activate",
        json={"adapter_id": "a", "adapter_path": "/tmp/a"},
    )
    r_deactivate = strict_client.post("/api/v1/academy/adapters/deactivate")
    r_cancel = strict_client.delete("/api/v1/academy/train/job1")

    assert r_train.status_code == 403
    assert r_activate.status_code == 403
    assert r_deactivate.status_code == 403
    assert r_cancel.status_code == 403


@patch("venom_core.config.SETTINGS")
def test_read_only_endpoints_not_blocked_by_localhost_guard(
    mock_settings, strict_client
):
    mock_settings.ENABLE_ACADEMY = True

    with patch("venom_core.api.routes.academy._load_jobs_history", return_value=[]):
        status_response = strict_client.get("/api/v1/academy/status")
        jobs_response = strict_client.get("/api/v1/academy/jobs")

    assert status_response.status_code == 200
    assert jobs_response.status_code == 200


@patch("venom_core.config.SETTINGS")
def test_curate_dataset_with_task_history(mock_settings, client, mock_dataset_curator):
    """Test dataset curation z włączonym task_history (PR-132B)."""
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_LOCALHOST_ONLY = False
    mock_dataset_curator.collect_from_task_history = MagicMock(return_value=25)

    response = client.post(
        "/api/v1/academy/dataset",
        json={
            "lessons_limit": 100,
            "git_commits_limit": 50,
            "include_task_history": True,
            "format": "alpaca",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # Sprawdź czy task_history został zebrany
    mock_dataset_curator.collect_from_task_history.assert_called_once_with(
        max_tasks=100
    )

    # Sprawdź statystyki
    assert "task_history_collected" in data["statistics"]
    assert data["statistics"]["task_history_collected"] == 25


@patch("venom_core.config.SETTINGS")
def test_curate_dataset_without_task_history(
    mock_settings, client, mock_dataset_curator
):
    """Test dataset curation bez task_history (PR-132B)."""
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_LOCALHOST_ONLY = False
    mock_dataset_curator.collect_from_task_history = MagicMock(return_value=0)

    response = client.post(
        "/api/v1/academy/dataset",
        json={
            "lessons_limit": 100,
            "git_commits_limit": 50,
            "include_task_history": False,
            "format": "alpaca",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # Sprawdź że task_history NIE został zebrany
    mock_dataset_curator.collect_from_task_history.assert_not_called()

    # Sprawdź statystyki - task_history_collected powinno być 0
    assert "task_history_collected" in data["statistics"]
    assert data["statistics"]["task_history_collected"] == 0


@patch("venom_core.config.SETTINGS")
def test_curate_dataset_includes_converted_files(
    mock_settings, client, mock_dataset_curator
):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_LOCALHOST_ONLY = False

    with (
        patch(
            "venom_core.api.routes.academy._resolve_existing_user_file",
            return_value=(
                {"category": "converted"},
                Path("/tmp/converted_sample.jsonl"),
            ),
        ),
        patch("venom_core.api.routes.academy._ingest_upload_file", return_value=7),
    ):
        response = client.post(
            "/api/v1/academy/dataset",
            json={
                "lessons_limit": 100,
                "git_commits_limit": 50,
                "format": "alpaca",
                "conversion_file_ids": ["converted_1.jsonl"],
            },
            headers={"X-Actor": "tester"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["statistics"]["converted_collected"] == 7
    assert body["statistics"]["by_source"]["converted"] == 7


@patch("venom_core.config.SETTINGS")
def test_preview_dataset_includes_converted_files(
    mock_settings, client, mock_dataset_curator
):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_LOCALHOST_ONLY = False

    with (
        patch(
            "venom_core.api.routes.academy._resolve_existing_user_file",
            return_value=(
                {"category": "converted"},
                Path("/tmp/converted_sample.md"),
            ),
        ),
        patch("venom_core.api.routes.academy._ingest_upload_file", return_value=3),
    ):
        response = client.post(
            "/api/v1/academy/dataset/preview",
            json={
                "lessons_limit": 100,
                "git_commits_limit": 50,
                "include_lessons": False,
                "include_git": False,
                "format": "alpaca",
                "conversion_file_ids": ["converted_2.md"],
            },
            headers={"X-Actor": "tester"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["by_source"]["converted"] == 3
