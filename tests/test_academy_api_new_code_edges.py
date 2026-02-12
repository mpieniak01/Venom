"""Edge-case coverage tests for Academy API helpers and routes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy as academy_routes


def _make_client() -> TestClient:
    app = FastAPI()
    academy_routes.set_dependencies(
        professor=MagicMock(),
        dataset_curator=MagicMock(),
        gpu_habitat=MagicMock(training_containers={}),
        lessons_store=MagicMock(),
        model_manager=MagicMock(),
    )
    app.include_router(academy_routes.router)
    return TestClient(app)


def test_load_jobs_history_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert academy_routes._load_jobs_history() == []


def test_load_jobs_history_ignores_invalid_json_line(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jobs_file = Path("data/training/jobs.jsonl")
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text('{"job_id":"ok"}\nINVALID\n', encoding="utf-8")

    jobs = academy_routes._load_jobs_history()
    assert jobs == [{"job_id": "ok"}]


def test_save_job_to_history_and_update_job(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    academy_routes._save_job_to_history({"job_id": "job-1", "status": "queued"})
    academy_routes._update_job_in_history("job-1", {"status": "running"})
    jobs = academy_routes._load_jobs_history()
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "job-1"
    assert jobs[0]["status"] == "running"


def test_update_job_in_history_noop_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    academy_routes._update_job_in_history("missing", {"status": "failed"})
    assert not Path("data/training/jobs.jsonl").exists()


@patch("venom_core.config.SETTINGS", new_callable=Mock)
def test_ensure_academy_enabled_raises_when_disabled_even_in_tests(mock_settings):
    mock_settings.ENABLE_ACADEMY = False
    academy_routes.set_dependencies(
        professor=MagicMock(),
        dataset_curator=MagicMock(),
        gpu_habitat=MagicMock(),
        lessons_store=MagicMock(),
        model_manager=MagicMock(),
    )
    with pytest.raises(Exception) as exc:
        academy_routes._ensure_academy_enabled()
    assert "disabled" in str(exc.value).lower()


@patch("venom_core.config.SETTINGS")
def test_ensure_academy_enabled_raises_when_missing_dependencies(mock_settings):
    mock_settings.ENABLE_ACADEMY = True
    academy_routes.set_dependencies(
        professor=None,
        dataset_curator=MagicMock(),
        gpu_habitat=MagicMock(),
        lessons_store=MagicMock(),
        model_manager=MagicMock(),
    )
    with pytest.raises(Exception) as exc:
        academy_routes._ensure_academy_enabled()
    assert "not initialized" in str(exc.value)


@patch("venom_core.config.SETTINGS")
def test_list_adapters_without_metadata_file_uses_defaults(mock_settings, tmp_path):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "base-model"

    adapter_dir = tmp_path / "run-1" / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)

    client = _make_client()
    with patch(
        "venom_core.api.routes.academy.require_localhost_request", return_value=None
    ):
        resp = client.get("/api/v1/academy/adapters")

    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["base_model"] == "base-model"
    assert payload[0]["created_at"] == "unknown"


@patch("venom_core.config.SETTINGS")
def test_stream_logs_sse_handles_generator_exception(mock_settings):
    mock_settings.ENABLE_ACADEMY = True
    client = _make_client()

    class _Habitat:
        def __init__(self):
            self.training_containers = {"job-err": {"container_id": "c1"}}

        def stream_job_logs(self, _job_name):
            raise RuntimeError("stream exploded")

    with (
        patch(
            "venom_core.api.routes.academy._load_jobs_history",
            return_value=[{"job_id": "job-err", "job_name": "job-err"}],
        ),
        patch(
            "venom_core.api.routes.academy._get_gpu_habitat", return_value=_Habitat()
        ),
    ):
        resp = client.get("/api/v1/academy/train/job-err/logs/stream")

    assert resp.status_code == 200
    assert '"type": "error"' in resp.text
    assert "stream exploded" in resp.text


@patch("venom_core.config.SETTINGS")
def test_deactivate_adapter_returns_503_when_model_manager_missing(mock_settings):
    mock_settings.ENABLE_ACADEMY = True
    client = _make_client()
    academy_routes.set_dependencies(
        professor=MagicMock(),
        dataset_curator=MagicMock(),
        gpu_habitat=MagicMock(training_containers={}),
        lessons_store=MagicMock(),
        model_manager=None,
    )
    with patch(
        "venom_core.api.routes.academy.require_localhost_request", return_value=None
    ):
        resp = client.post("/api/v1/academy/adapters/deactivate")
    assert resp.status_code == 503


def test_require_localhost_request_handles_missing_client():
    req = SimpleNamespace(client=None)
    with pytest.raises(Exception) as exc:
        academy_routes.require_localhost_request(req)
    assert "Access denied" in str(exc.value)


def test_save_finished_job_metadata_logs_without_user_data(tmp_path):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    job = {"adapter_path": str(adapter_dir)}
    tainted_job_id = "user-controlled-<script>"

    with (
        patch(
            "venom_core.api.routes.academy._save_adapter_metadata",
            side_effect=RuntimeError("boom"),
        ),
        patch("venom_core.api.routes.academy.logger.warning") as warning_mock,
    ):
        academy_routes._save_finished_job_metadata(tainted_job_id, job, "finished")

    warning_mock.assert_called_once()
    assert "user-controlled" not in str(warning_mock.call_args.args)
    assert warning_mock.call_args.kwargs.get("exc_info") is True


def test_cleanup_terminal_job_container_logs_without_user_data():
    habitat = SimpleNamespace(cleanup_job=Mock(side_effect=RuntimeError("boom")))
    tainted_job_id = "user-controlled-<script>"
    job = {}

    with patch("venom_core.api.routes.academy.logger.warning") as warning_mock:
        academy_routes._cleanup_terminal_job_container(
            habitat=habitat,
            job_id=tainted_job_id,
            job=job,
            job_name="job-name",
            current_status="failed",
        )

    warning_mock.assert_called_once()
    assert "user-controlled" not in str(warning_mock.call_args.args)
    assert warning_mock.call_args.kwargs.get("exc_info") is True
