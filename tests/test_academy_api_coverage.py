"""Additional Academy API tests for edge-case coverage."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy as academy_routes


@pytest.fixture
def client_with_deps():
    app = FastAPI()
    academy_routes.set_dependencies(
        professor=MagicMock(),
        dataset_curator=MagicMock(),
        gpu_habitat=MagicMock(training_containers={}),
        lessons_store=MagicMock(),
        model_manager=MagicMock(),
    )
    app.include_router(academy_routes.router)
    with patch(
        "venom_core.api.routes.academy.require_localhost_request", return_value=None
    ):
        yield TestClient(app)


@patch("venom_core.config.SETTINGS")
def test_start_training_failure_updates_history(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_TRAINING_DIR = "./data/training"
    mock_settings.ACADEMY_MODELS_DIR = "./data/models"
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "test-model"

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.glob", return_value=["./data/training/dataset_123.jsonl"]),
        patch("pathlib.Path.mkdir"),
        patch("venom_core.api.routes.academy._save_job_to_history"),
        patch("venom_core.api.routes.academy._update_job_in_history") as mock_update,
        patch("venom_core.api.routes.academy._get_gpu_habitat") as mock_habitat,
    ):
        mock_habitat.return_value.run_training_job.side_effect = RuntimeError("boom")

        response = client_with_deps.post("/api/v1/academy/train", json={})

    assert response.status_code == 200
    assert response.json()["success"] is False
    status_updates = [
        c.args[1]["status"] for c in mock_update.call_args_list if "status" in c.args[1]
    ]
    assert "failed" in status_updates


@patch("venom_core.config.SETTINGS")
def test_stream_training_logs_missing_job_returns_404(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    with patch("venom_core.api.routes.academy._load_jobs_history", return_value=[]):
        response = client_with_deps.get("/api/v1/academy/train/nonexistent/logs/stream")
    assert response.status_code == 404


@patch("venom_core.config.SETTINGS")
def test_get_training_status_missing_job_returns_404(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    with patch("venom_core.api.routes.academy._load_jobs_history", return_value=[]):
        response = client_with_deps.get("/api/v1/academy/train/nonexistent/status")
    assert response.status_code == 404


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_invalid_path_returns_404(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    with patch("pathlib.Path.exists", return_value=False):
        response = client_with_deps.post(
            "/api/v1/academy/adapters/activate",
            json={"adapter_id": "x", "adapter_path": "/invalid/path"},
        )
    assert response.status_code == 404


def test_normalize_job_status_canonical_mapping():
    assert academy_routes._normalize_job_status(None) == "failed"
    assert academy_routes._normalize_job_status("completed") == "finished"
    assert academy_routes._normalize_job_status("created") == "preparing"
    assert academy_routes._normalize_job_status("unknown") == "failed"
    assert academy_routes._normalize_job_status("running") == "running"
    assert academy_routes._normalize_job_status("bogus") == "failed"


def test_require_localhost_request_allows_loopback():
    req = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    academy_routes.require_localhost_request(req)


def test_require_localhost_request_blocks_remote():
    req = SimpleNamespace(client=SimpleNamespace(host="10.10.10.10"))
    with pytest.raises(academy_routes.AcademyRouteError) as exc:
        academy_routes.require_localhost_request(req)
    assert exc.value.status_code == 403


@patch("venom_core.config.SETTINGS")
def test_get_training_status_runtime_error_returns_500(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    with (
        patch(
            "venom_core.api.routes.academy._load_jobs_history",
            return_value=[{"job_id": "job-1", "job_name": "job-1"}],
        ),
        patch("venom_core.api.routes.academy._get_gpu_habitat") as mock_habitat,
    ):
        mock_habitat.return_value.get_training_status.side_effect = RuntimeError("boom")
        response = client_with_deps.get("/api/v1/academy/train/job-1/status")
    assert response.status_code == 500
    assert "Failed to get status" in response.json()["detail"]


@patch("venom_core.config.SETTINGS")
def test_stream_logs_sse_emits_connected_metrics_and_terminal_status(
    mock_settings, client_with_deps
):
    mock_settings.ENABLE_ACADEMY = True

    class _Metric:
        epoch = 1
        total_epochs = 2
        loss = 0.1
        progress_percent = 50.0

    class _Parser:
        def parse_line(self, _line):
            return _Metric()

        def aggregate_metrics(self, metrics):
            return {"count": len(metrics)}

    class _Habitat:
        def __init__(self):
            self.training_containers = {"job-1": {"id": "x"}}

        def stream_job_logs(self, _job_name):
            for idx in range(10):
                yield f"2024-01-01T00:00:0{idx}Z log line {idx}"

        def get_training_status(self, _job_name):
            return {"status": "finished"}

    with (
        patch(
            "venom_core.api.routes.academy._load_jobs_history",
            return_value=[{"job_id": "job-1", "job_name": "job-1"}],
        ),
        patch(
            "venom_core.api.routes.academy._get_gpu_habitat", return_value=_Habitat()
        ),
        patch(
            "venom_core.learning.training_metrics_parser.TrainingMetricsParser", _Parser
        ),
    ):
        response = client_with_deps.get("/api/v1/academy/train/job-1/logs/stream")

    assert response.status_code == 200
    payload = response.text
    assert '"type": "connected"' in payload
    assert '"type": "metrics"' in payload
    assert '"type": "status"' in payload
    assert '"status": "finished"' in payload


@patch("venom_core.config.SETTINGS")
def test_stream_logs_reports_missing_container(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    habitat = MagicMock(training_containers={})
    with (
        patch(
            "venom_core.api.routes.academy._load_jobs_history",
            return_value=[{"job_id": "job-2", "job_name": "job-2"}],
        ),
        patch("venom_core.api.routes.academy._get_gpu_habitat", return_value=habitat),
    ):
        response = client_with_deps.get("/api/v1/academy/train/job-2/logs/stream")
    assert response.status_code == 200
    assert "Training container not found" in response.text


@patch("venom_core.config.SETTINGS")
def test_list_jobs_error_returns_500(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    with patch(
        "venom_core.api.routes.academy._load_jobs_history",
        side_effect=RuntimeError("history-failed"),
    ):
        response = client_with_deps.get("/api/v1/academy/jobs")
    assert response.status_code == 500
    assert "Failed to list jobs" in response.json()["detail"]


@patch("venom_core.config.SETTINGS")
def test_list_adapters_success_with_metadata_and_active_flag(
    mock_settings, client_with_deps, tmp_path
):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "base-model"
    training_dir = tmp_path / "training_123"
    adapter_dir = training_dir / "adapter"
    adapter_dir.mkdir(parents=True)
    (training_dir / "metadata.json").write_text(
        '{"base_model":"bm","created_at":"2024-01-01","parameters":{"epochs":1}}',
        encoding="utf-8",
    )
    manager = MagicMock()
    manager.get_active_adapter_info.return_value = {"adapter_id": "training_123"}
    with patch(
        "venom_core.api.routes.academy._get_model_manager", return_value=manager
    ):
        response = client_with_deps.get("/api/v1/academy/adapters")
    assert response.status_code == 200
    adapters = response.json()
    assert len(adapters) == 1
    assert adapters[0]["is_active"] is True
    assert adapters[0]["base_model"] == "bm"


@patch("venom_core.config.SETTINGS")
def test_activate_deactivate_return_503_when_model_manager_missing(
    mock_settings, client_with_deps
):
    mock_settings.ENABLE_ACADEMY = True
    with (
        patch("venom_core.api.routes.academy._get_model_manager", return_value=None),
        patch("pathlib.Path.exists", return_value=True),
    ):
        activate = client_with_deps.post(
            "/api/v1/academy/adapters/activate",
            json={"adapter_id": "a1", "adapter_path": "/tmp/adapter"},
        )
        deactivate = client_with_deps.post("/api/v1/academy/adapters/deactivate")
    assert activate.status_code == 503
    assert deactivate.status_code == 503


@patch("venom_core.config.SETTINGS")
def test_academy_status_uses_gpu_info_fallback_on_error(
    mock_settings, client_with_deps
):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_ENABLE_GPU = True
    mock_settings.ACADEMY_MIN_LESSONS = 1
    mock_settings.ACADEMY_TRAINING_INTERVAL_HOURS = 1
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "base-model"
    habitat = MagicMock()
    habitat.is_gpu_available.return_value = True
    habitat.get_gpu_info.side_effect = RuntimeError("nvidia-smi missing")
    with (
        patch("venom_core.api.routes.academy._get_gpu_habitat", return_value=habitat),
        patch(
            "venom_core.api.routes.academy._load_jobs_history",
            return_value=[],
        ),
    ):
        response = client_with_deps.get("/api/v1/academy/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["gpu"]["available"] is True
