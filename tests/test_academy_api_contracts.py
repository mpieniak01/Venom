"""Additional Academy API tests for edge-case coverage."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.helpers.academy_wiring import academy_client
from venom_core.api.routes import academy as academy_routes
from venom_core.api.routes import academy_self_learning as academy_self_learning_routes
from venom_core.api.routes import llm_simple as llm_simple_routes
from venom_core.api.schemas.academy import TrainableModelInfo


@pytest.fixture
def client_with_deps():
    with academy_client() as client:
        yield client


@patch("venom_core.config.SETTINGS")
def test_start_training_failure_updates_history(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_TRAINING_DIR = "./data/training"
    mock_settings.ACADEMY_MODELS_DIR = "./data/models"
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.glob", return_value=["./data/training/dataset_123.jsonl"]),
        patch("pathlib.Path.mkdir"),
        patch("venom_core.api.routes.academy._save_job_to_history"),
        patch("venom_core.api.routes.academy._update_job_in_history") as mock_update,
        patch("venom_core.api.routes.academy._get_gpu_habitat") as mock_habitat,
    ):
        mock_habitat.return_value.run_training_job.side_effect = RuntimeError("boom")

        response = client_with_deps.post(
            "/api/v1/academy/train",
            json={"base_model": "unsloth/Phi-3-mini-4k-instruct"},
        )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["reason_code"] == "TRAINING_START_FAILED"
    assert detail["requested_base_model"] == "unsloth/Phi-3-mini-4k-instruct"
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
def test_activate_adapter_missing_adapter_returns_404(
    mock_settings, client_with_deps, tmp_path
):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path / "models")
    response = client_with_deps.post(
        "/api/v1/academy/adapters/activate",
        json={
            "adapter_id": "x",
            "adapter_path": "/invalid/path",
            "runtime_id": "ollama",
        },
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
    assert exc.value.detail["decision"] == "block"
    assert exc.value.detail["reason_code"] == "PERMISSION_DENIED"
    assert (
        exc.value.detail["technical_context"]["operation"] == "academy.localhost_guard"
    )


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
    detail = response.json()["detail"]
    assert detail["reason_code"] == "TRAINING_STATUS_FAILED"
    assert detail["job_id"] == "job-1"
    assert "Failed to get status" in detail["message"]


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
    detail = response.json()["detail"]
    assert detail["reason_code"] == "TRAINING_JOBS_LIST_FAILED"
    assert "Failed to list jobs" in detail["message"]


@patch("venom_core.config.SETTINGS")
def test_list_jobs_normalizes_legacy_history_records(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    with patch(
        "venom_core.api.routes.academy._load_jobs_history",
        return_value=[{"job_name": "legacy_job", "status": "completed"}],
    ):
        response = client_with_deps.get("/api/v1/academy/jobs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["jobs"][0]["job_id"] == "legacy_job"
    assert payload["jobs"][0]["status"] == "finished"


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
        '{"metadata_version":2,"base_model":"bm","effective_base_model":"bm","effective_runtime_id":"ollama","created_at":"2024-01-01","source_flow":"training","parameters":{"epochs":1}}',
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
    assert adapters[0]["target_runtime"] == "ollama"
    assert adapters[0]["metadata_status"] == "canonical"


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
def test_activate_adapter_rejects_incompatible_runtime(mock_settings, client_with_deps):
    mock_settings.ENABLE_ACADEMY = True
    manager = MagicMock()
    manager.activate_adapter.return_value = True
    with (
        patch("venom_core.api.routes.academy._get_model_manager", return_value=manager),
        patch(
            "venom_core.api.routes.academy_models.validate_adapter_runtime_compatibility",
            new=AsyncMock(
                side_effect=ValueError(
                    "ADAPTER_RUNTIME_INCOMPATIBLE: Adapter is incompatible with selected runtime 'onnx'. Compatible runtimes: vllm."
                )
            ),
        ),
        patch("pathlib.Path.exists", return_value=True),
    ):
        response = client_with_deps.post(
            "/api/v1/academy/adapters/activate",
            json={
                "adapter_id": "a1",
                "adapter_path": "/tmp/adapter",
                "runtime_id": "onnx",
            },
        )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["reason_code"] == "ADAPTER_RUNTIME_INCOMPATIBLE"
    assert "Compatible runtimes: vllm" in detail["message"]
    assert detail["adapter_id"] == "a1"
    assert detail["requested_runtime_id"] == "onnx"


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_rejects_runtime_model_family_mismatch_without_side_effects(
    mock_settings, tmp_path
):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path / "models")
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "gemma-3-4b-it"

    adapter_root = Path(mock_settings.ACADEMY_MODELS_DIR) / "self_learning_gemma"
    adapter_dir = adapter_root / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_root / "metadata.json").write_text(
        json.dumps(
            {
                "metadata_version": 2,
                "base_model": "gemma-3-4b-it",
                "effective_base_model": "gemma-3-4b-it",
                "effective_runtime_id": "ollama",
                "created_at": "2026-03-07T12:00:00+00:00",
                "source_flow": "self_learning",
            }
        ),
        encoding="utf-8",
    )

    manager = MagicMock()
    manager.activate_adapter.return_value = True
    manager.list_local_models = AsyncMock(
        return_value=[
            {
                "name": "gemma3:latest",
                "provider": "ollama",
                "path": str(tmp_path / "gemma3"),
            },
            {
                "name": "phi3:mini",
                "provider": "ollama",
                "path": str(tmp_path / "phi3"),
            },
        ]
    )

    with academy_client(model_manager=manager) as client:
        with patch(
            "venom_core.api.routes.academy_models.list_trainable_models",
            AsyncMock(
                return_value=[
                    TrainableModelInfo(
                        model_id="gemma-3-4b-it",
                        label="Gemma 3 4B IT",
                        provider="huggingface",
                        trainable=True,
                        runtime_compatibility={"ollama": True, "vllm": True},
                        recommended_runtime="ollama",
                    )
                ]
            ),
        ):
            response = client.post(
                "/api/v1/academy/adapters/activate",
                json={
                    "adapter_id": "self_learning_gemma",
                    "adapter_path": str(adapter_dir),
                    "runtime_id": "ollama",
                    "model_id": "phi3:mini",
                    "deploy_to_chat_runtime": True,
                },
            )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["reason_code"] == "ADAPTER_BASE_MODEL_MISMATCH"
    assert "selected runtime model" in detail["message"]
    assert detail["adapter_id"] == "self_learning_gemma"
    assert detail["requested_runtime_id"] == "ollama"
    assert detail["requested_model_id"] == "phi3:mini"
    manager.activate_adapter.assert_not_called()


@patch("venom_core.config.SETTINGS")
def test_self_learning_ollama_gemma3_adapter_flow_reaches_chat(mock_settings, tmp_path):
    mock_settings.ENABLE_ACADEMY = True
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path / "models")
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "gemma-3-4b-it"

    class _RuntimeState(SimpleNamespace):
        pass

    current_runtime = _RuntimeState(
        provider="ollama",
        runtime_id="ollama",
        model_name="gemma3:latest",
        endpoint="http://127.0.0.1:11434/v1",
        config_hash="hash-base",
        service_type="local-runtime",
    )

    class _ConfigManager:
        def __init__(self) -> None:
            self._config = {
                "ACTIVE_LLM_SERVER": "ollama",
                "LLM_MODEL_NAME": "gemma3:latest",
                "HYBRID_LOCAL_MODEL": "gemma3:latest",
                "LAST_MODEL_OLLAMA": "gemma3:latest",
            }

        def get_config(self, *, mask_secrets: bool = False) -> dict[str, str]:
            return dict(self._config)

        def update_config(self, updates: dict[str, str]) -> None:
            self._config.update(updates)
            selected_model = str(updates.get("LLM_MODEL_NAME") or "").strip()
            if selected_model:
                current_runtime.model_name = selected_model
            selected_hash = str(updates.get("LLM_CONFIG_HASH") or "").strip()
            if selected_hash:
                current_runtime.config_hash = selected_hash

    class _FakeModelManager:
        def __init__(self) -> None:
            self.active_adapter_id: str | None = None

        def get_active_adapter_info(self) -> dict[str, str] | None:
            if not self.active_adapter_id:
                return None
            return {"adapter_id": self.active_adapter_id}

        def activate_adapter(self, *, adapter_id: str, adapter_path: str) -> bool:
            self.active_adapter_id = adapter_id
            return Path(adapter_path).exists()

        def deactivate_adapter(self) -> bool:
            if not self.active_adapter_id:
                return False
            self.active_adapter_id = None
            return True

        def create_ollama_modelfile(
            self,
            *,
            version_id: str,
            output_name: str,
            from_model: str | None = None,
            use_experimental: bool = False,
        ) -> str:
            assert version_id
            assert from_model
            return output_name

    class _FakeSelfLearningService:
        def __init__(self) -> None:
            self.run_id = "59d9a38d-6d24-478a-8bd7-8d64e09cec65"
            self.adapter_id = f"self_learning_{self.run_id}"
            self.repo_root = tmp_path
            self.models_dir = Path(mock_settings.ACADEMY_MODELS_DIR)
            self.models_dir.mkdir(parents=True, exist_ok=True)
            (self.repo_root / "README_PL.md").write_text(
                "# Venom\n\nVenom to platforma AI.",
                encoding="utf-8",
            )
            self._status_payload: dict[str, object] | None = None

        async def get_capabilities(self) -> dict[str, object]:
            return {
                "trainable_models": [
                    {
                        "model_id": "gemma-3-4b-it",
                        "label": "Gemma 3 4B IT",
                        "provider": "huggingface",
                        "recommended": True,
                        "runtime_compatibility": {"ollama": True, "vllm": True},
                        "recommended_runtime": "ollama",
                    }
                ],
                "embedding_profiles": [
                    {
                        "profile_id": "local:default",
                        "provider": "local",
                        "model": "sentence-transformers/all-MiniLM-L6-v2",
                        "dimension": 384,
                        "healthy": True,
                        "fallback_active": False,
                        "details": {},
                    }
                ],
                "default_embedding_profile_id": "local:default",
            }

        def start_run(
            self,
            *,
            mode: str,
            sources: list[str],
            limits: dict[str, object],
            llm_config: dict[str, object] | None,
            rag_config: dict[str, object] | None,
            dry_run: bool,
        ) -> str:
            assert mode == "llm_finetune"
            assert sources == ["repo_readmes"]
            assert dry_run is False
            assert rag_config is None
            assert limits["max_files"] == 10
            assert llm_config is not None
            assert llm_config["runtime_id"] == "ollama"
            assert llm_config["base_model"] == "gemma-3-4b-it"
            adapter_dir = self.models_dir / self.adapter_id / "adapter"
            adapter_dir.mkdir(parents=True, exist_ok=True)
            (adapter_dir / "adapter_config.json").write_text(
                json.dumps({"base_model_name_or_path": "gemma-3-4b-it"}),
                encoding="utf-8",
            )
            ((self.models_dir / self.adapter_id) / "metadata.json").write_text(
                json.dumps(
                    {
                        "metadata_version": 2,
                        "adapter_id": self.adapter_id,
                        "run_id": self.run_id,
                        "base_model": "gemma-3-4b-it",
                        "requested_base_model": "gemma-3-4b-it",
                        "effective_base_model": "gemma-3-4b-it",
                        "requested_runtime_id": "ollama",
                        "effective_runtime_id": "ollama",
                        "created_at": "2026-03-07T10:00:00+00:00",
                        "started_at": "2026-03-07T10:00:01+00:00",
                        "finished_at": "2026-03-07T10:00:30+00:00",
                        "source_flow": "self_learning",
                        "source": "self_learning",
                        "dataset_path": str(self.repo_root / "README_PL.md"),
                        "parameters": {
                            "runtime_id": "ollama",
                            "training_base_model": "gemma-3-4b-it",
                            "lora_rank": 8,
                            "learning_rate": 0.0002,
                            "num_epochs": 2,
                            "selected_files": ["README_PL.md"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            self._status_payload = {
                "run_id": self.run_id,
                "status": "completed",
                "mode": "llm_finetune",
                "sources": ["repo_readmes"],
                "created_at": "2026-03-07T10:00:00+00:00",
                "started_at": "2026-03-07T10:00:01+00:00",
                "finished_at": "2026-03-07T10:00:30+00:00",
                "progress": {
                    "files_discovered": 1,
                    "files_processed": 1,
                    "chunks_created": 4,
                    "records_created": 4,
                    "indexed_vectors": 0,
                },
                "artifacts": {
                    "adapter_path": str(adapter_dir),
                    "selected_files": [str(self.repo_root / "README_PL.md")],
                },
                "logs": [
                    "Selected file: README_PL.md",
                    "Training completed successfully.",
                ],
                "error_message": None,
                "llm_config": dict(llm_config),
            }
            return self.run_id

        def get_status(self, run_id: str) -> dict[str, object] | None:
            if run_id != self.run_id:
                return None
            return self._status_payload

        def list_runs(self, *, limit: int) -> list[dict[str, object]]:
            assert limit >= 1
            return [self._status_payload] if self._status_payload else []

    async def _fake_stream_simple_chunks(
        *,
        completions_url: str,
        payload: dict[str, object],
        runtime: object,
        request_id: object,
        model_name: str,
    ):
        assert completions_url == "http://runtime.test/v1/chat/completions"
        assert (
            model_name
            == "venom-adapter-self_learning_59d9a38d-6d24-478a-8bd7-8d64e09cec65"
        )
        messages = payload.get("messages")
        assert isinstance(messages, list)
        assert any(
            "co to jest Venom" in str(message.get("content") or "")
            for message in messages
            if isinstance(message, dict)
        )
        yield 'data: {"choices":[{"delta":{"content":"Venom to lokalna platforma AI."}}]}\n\n'
        yield "data: [DONE]\n\n"

    app = FastAPI()
    model_manager = _FakeModelManager()
    self_learning_service = _FakeSelfLearningService()
    config_manager = _ConfigManager()
    academy_routes.set_dependencies(
        professor=MagicMock(),
        dataset_curator=MagicMock(),
        gpu_habitat=MagicMock(training_containers={}),
        lessons_store=MagicMock(),
        model_manager=model_manager,
    )
    academy_self_learning_routes.set_dependencies(
        self_learning_service=self_learning_service
    )
    app.include_router(academy_routes.router)
    app.include_router(academy_self_learning_routes.router)
    app.include_router(llm_simple_routes.router)

    with (
        patch(
            "venom_core.api.routes.academy.require_localhost_request",
            return_value=None,
        ),
        patch(
            "venom_core.api.routes.academy_models.config_manager",
            config_manager,
        ),
        patch(
            "venom_core.api.routes.academy_models.validate_adapter_runtime_compatibility",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "venom_core.api.routes.llm_simple.get_active_llm_runtime",
            lambda: current_runtime,
        ),
        patch(
            "venom_core.api.routes.llm_simple._build_chat_completions_url",
            lambda _runtime: "http://runtime.test/v1/chat/completions",
        ),
        patch(
            "venom_core.api.routes.llm_simple._stream_simple_chunks",
            _fake_stream_simple_chunks,
        ),
        patch(
            "venom_core.services.academy.adapter_runtime_service._ensure_ollama_adapter_gguf",
            return_value=(
                Path(mock_settings.ACADEMY_MODELS_DIR)
                / self_learning_service.adapter_id
                / "adapter"
                / "Adapter-F16-LoRA.gguf"
            ),
        ),
    ):
        client = TestClient(app)

        capabilities = client.get("/api/v1/academy/self-learning/capabilities")
        assert capabilities.status_code == 200
        capabilities_payload = capabilities.json()
        assert (
            capabilities_payload["trainable_models"][0]["model_id"] == "gemma-3-4b-it"
        )
        assert capabilities_payload["trainable_models"][0]["runtime_compatibility"][
            "ollama"
        ]

        start_response = client.post(
            "/api/v1/academy/self-learning/start",
            json={
                "mode": "llm_finetune",
                "sources": ["repo_readmes"],
                "limits": {
                    "max_file_size_kb": 256,
                    "max_files": 10,
                    "max_total_size_mb": 5,
                },
                "llm_config": {
                    "base_model": "gemma-3-4b-it",
                    "runtime_id": "ollama",
                    "dataset_strategy": "reconstruct",
                    "task_mix_preset": "balanced",
                    "lora_rank": 8,
                    "learning_rate": 0.0002,
                    "num_epochs": 2,
                    "batch_size": 1,
                    "max_seq_length": 1024,
                },
                "dry_run": False,
            },
        )
        assert start_response.status_code == 200
        run_id = start_response.json()["run_id"]
        assert run_id == self_learning_service.run_id

        status_response = client.get(f"/api/v1/academy/self-learning/{run_id}/status")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["status"] == "completed"
        assert status_payload["artifacts"]["selected_files"] == [
            str(tmp_path / "README_PL.md")
        ]

        adapters_response = client.get("/api/v1/academy/adapters")
        assert adapters_response.status_code == 200
        adapters_payload = adapters_response.json()
        assert len(adapters_payload) == 1
        assert adapters_payload[0]["adapter_id"] == self_learning_service.adapter_id
        assert adapters_payload[0]["base_model"] == "gemma-3-4b-it"
        assert adapters_payload[0]["metadata_status"] == "canonical"
        assert adapters_payload[0]["target_runtime"] == "ollama"
        assert adapters_payload[0]["source_flow"] == "self_learning"
        assert (
            adapters_payload[0]["training_params"]["training_base_model"]
            == "gemma-3-4b-it"
        )

        activate_response = client.post(
            "/api/v1/academy/adapters/activate",
            json={
                "adapter_id": self_learning_service.adapter_id,
                "adapter_path": str(
                    Path(mock_settings.ACADEMY_MODELS_DIR)
                    / self_learning_service.adapter_id
                    / "adapter"
                ),
                "runtime_id": "ollama",
                "model_id": "gemma3:latest",
                "deploy_to_chat_runtime": True,
            },
        )
        assert activate_response.status_code == 200
        activate_payload = activate_response.json()
        assert activate_payload["deployed"] is True
        assert activate_payload["runtime_id"] == "ollama"
        assert (
            activate_payload["chat_model"]
            == "venom-adapter-self_learning_59d9a38d-6d24-478a-8bd7-8d64e09cec65"
        )

        adapters_after_activation = client.get("/api/v1/academy/adapters")
        assert adapters_after_activation.status_code == 200
        assert adapters_after_activation.json()[0]["is_active"] is True

        chat_response = client.post(
            "/api/v1/llm/simple/stream",
            json={
                "content": "co to jest Venom",
                "session_id": "academy-scenario",
            },
        )
        assert chat_response.status_code == 200
        assert "Venom to lokalna platforma AI." in chat_response.text

    academy_routes.set_dependencies(
        professor=None,
        dataset_curator=None,
        gpu_habitat=None,
        lessons_store=None,
        model_manager=None,
    )
    academy_self_learning_routes.set_dependencies(self_learning_service=None)


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
    assert "default_base_model" not in payload["config"]
