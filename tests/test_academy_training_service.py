from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from venom_core.api.routes import academy_training as at


@pytest.mark.asyncio
async def test_dataset_resolution_and_model_validation(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset_001.jsonl"
    dataset.write_text(
        '{"instruction":"i","input":"","output":"o"}\n', encoding="utf-8"
    )

    assert at.resolve_dataset_path(
        None,
        academy_training_dir=str(tmp_path),
        dataset_required_detail="missing",
    ).endswith("dataset_001.jsonl")
    assert (
        at.resolve_dataset_path(
            "direct.jsonl",
            academy_training_dir=str(tmp_path),
            dataset_required_detail="missing",
        )
        == "direct.jsonl"
    )

    with pytest.raises(HTTPException):
        at.resolve_dataset_path(
            None,
            academy_training_dir=str(tmp_path / "missing"),
            dataset_required_detail="missing",
        )

    assert (
        at.ensure_trainable_base_model(
            request_base_model="phi3",
            is_model_trainable_fn=lambda _name: True,
        )
        == "phi3"
    )

    with pytest.raises(HTTPException) as missing_model_exc:
        at.ensure_trainable_base_model(
            request_base_model=None,
            is_model_trainable_fn=lambda _name: True,
        )
    assert missing_model_exc.value.status_code == 400
    assert missing_model_exc.value.detail["reason_code"] == "MODEL_BASE_MODEL_REQUIRED"

    with pytest.raises(HTTPException):
        at.ensure_trainable_base_model(
            request_base_model="bad",
            is_model_trainable_fn=lambda _name: False,
        )

    manager = MagicMock()
    manager.list_local_models = AsyncMock(
        return_value=[
            {
                "name": "gemma3:latest",
                "provider": "ollama",
                "path": str(tmp_path / "gemma3"),
            }
        ]
    )

    await at.validate_runtime_compatibility_for_base_model(
        base_model="google/gemma-3-4b-it",
        runtime_id="ollama",
        manager=manager,
    )

    with pytest.raises(HTTPException) as exc_info:
        await at.validate_runtime_compatibility_for_base_model(
            base_model="gemma3:latest",
            runtime_id="vllm",
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["reason_code"] == "MODEL_RUNTIME_INCOMPATIBLE"


def test_job_building_and_sync_and_cleanup(tmp_path: Path) -> None:
    req = SimpleNamespace(
        runtime_id="ollama",
        lora_rank=8,
        learning_rate=1e-4,
        num_epochs=2,
        batch_size=2,
        max_seq_length=512,
    )
    record = at.build_job_record(
        dataset_path="d.jsonl",
        base_model="phi3",
        output_dir=tmp_path,
        request=req,
    )
    assert record["status"] == "queued"
    assert record["parameters"]["runtime_id"] == "ollama"
    assert record["parameters"]["requested_runtime_id"] == "ollama"
    assert record["parameters"]["effective_base_model"] == "phi3"
    assert record["parameters"]["num_epochs"] == 2

    job = {"status": "running", "output_dir": str(tmp_path)}
    updates: list[dict[str, object]] = []
    status_info, status = at.sync_job_status_with_habitat(
        habitat=SimpleNamespace(
            get_training_status=lambda _name: {"status": "finished"}
        ),
        job_id="j1",
        job=job,
        job_name="j1",
        normalize_status_fn=lambda s: str(s),
        terminal_statuses={"finished", "failed", "cancelled"},
        update_job_fn=lambda _id, payload: updates.append(payload),
    )
    assert status_info["status"] == "finished"
    assert status == "finished"
    assert updates and updates[-1]["status"] == "finished"

    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    job["adapter_path"] = str(adapter_dir)
    called: list[str] = []
    at.save_finished_job_metadata(
        job=job,
        current_status="finished",
        save_adapter_metadata_fn=lambda _job, _path: called.append("ok"),
        log_internal_operation_failure_fn=lambda _msg: called.append("err"),
    )
    assert called == ["ok"]

    called.clear()
    at.save_finished_job_metadata(
        job=job,
        current_status="finished",
        save_adapter_metadata_fn=lambda _job, _path: (_ for _ in ()).throw(
            RuntimeError("x")
        ),
        log_internal_operation_failure_fn=lambda _msg: called.append("err"),
    )
    assert called == ["err"]

    cleaned: list[dict[str, object]] = []
    at.cleanup_terminal_job_container(
        habitat=SimpleNamespace(cleanup_job=lambda _name: None),
        job_id="j1",
        job={"status": "finished"},
        job_name="j1",
        current_status="finished",
        terminal_statuses={"finished", "failed", "cancelled"},
        update_job_fn=lambda _id, payload: cleaned.append(payload),
        log_internal_operation_failure_fn=lambda _msg: None,
    )
    assert cleaned and cleaned[-1]["container_cleaned"] is True


def test_stream_helpers_and_job_ops() -> None:
    ts, msg = at.parse_stream_log_line("2026-01-01 hello")
    assert ts == "2026-01-01" and msg == "hello"
    assert at.parse_stream_log_line("plain") == (None, "plain")

    parser = SimpleNamespace(
        parse_line=lambda line: SimpleNamespace(
            epoch=1,
            total_epochs=2,
            loss=0.1,
            progress_percent=50.0,
        )
        if "loss" in line
        else None,
        aggregate_metrics=lambda _all: {"avg_loss": 0.1},
    )
    all_metrics: list[object] = []
    metrics = at.extract_metrics_data(
        parser=parser, all_metrics=all_metrics, message="loss=0.1"
    )
    assert metrics and metrics["loss"] == 0.1
    assert (
        at.extract_metrics_data(parser=parser, all_metrics=all_metrics, message="nope")
        is None
    )

    log_event = at.build_log_event(
        line_no=1,
        message="m",
        timestamp="t",
        metrics_data={"loss": 0.1},
    )
    assert log_event["metrics"]["loss"] == 0.1
    assert at.sse_event({"type": "x"}).startswith("data:")

    events, stop = at.periodic_stream_events(
        line_no=10,
        habitat=SimpleNamespace(
            get_training_status=lambda _job: {"status": "finished"}
        ),
        job_name="j1",
        parser=parser,
        all_metrics=all_metrics,
        normalize_status_fn=lambda s: str(s),
        terminal_statuses={"finished", "failed", "cancelled"},
    )
    assert stop is True
    assert any(e["type"] == "status" for e in events)
    assert at.periodic_stream_events(
        line_no=3,
        habitat=SimpleNamespace(get_training_status=lambda _job: {"status": "running"}),
        job_name="j1",
        parser=parser,
        all_metrics=[],
        normalize_status_fn=lambda s: str(s),
        terminal_statuses={"finished", "failed", "cancelled"},
    ) == ([], False)

    jobs = [
        {"job_id": "a"},
        {"job_id": "b"},
    ]
    assert at.find_job_or_404("a", jobs=jobs)["job_id"] == "a"
    with pytest.raises(HTTPException):
        at.find_job_or_404("missing", jobs=jobs)

    summaries = at.list_jobs_response(
        jobs=[
            {"job_id": "1", "status": "finished", "started_at": "2026-01-01T00:00:00"},
            {"job_id": "2", "status": "running", "started_at": "2026-01-02T00:00:00"},
        ],
        to_job_summary_fn=lambda j: SimpleNamespace(
            job_id=j["job_id"],
            status=j["status"],
            started_at=j["started_at"],
        ),
        limit=1,
        status="running",
    )
    assert len(summaries) == 1 and summaries[0].job_id == "2"

    updates: list[dict[str, object]] = []
    out = at.cancel_training_job(
        job_id="j1",
        habitat=SimpleNamespace(cleanup_job=lambda _name: None),
        jobs=[{"job_id": "j1", "job_name": "j1"}],
        update_job_fn=lambda _id, payload: updates.append(payload),
        logger=SimpleNamespace(
            info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None
        ),
    )
    assert out["success"] is True
    assert updates and updates[-1]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_stream_training_logs_events_paths() -> None:
    class _Habitat:
        training_containers = {"j1": True}

        def __init__(self) -> None:
            self._lines = iter(["2026-01-01 loss=0.1", "2026-01-01 done"])

        def stream_job_logs(self, _job_name: str):
            return self._lines

        def get_training_status(self, _job_name: str):
            return {"status": "finished"}

    parser_factory = lambda: SimpleNamespace(  # noqa: E731
        parse_line=lambda line: SimpleNamespace(
            epoch=1, total_epochs=1, loss=0.1, progress_percent=100.0
        )
        if "loss" in line
        else None,
        aggregate_metrics=lambda all_metrics: {"count": len(all_metrics)},
    )

    events = []
    async for payload in at.stream_training_logs_events(
        job_id="j1",
        job_name="j1",
        habitat=_Habitat(),
        parser_factory=parser_factory,
        normalize_status_fn=lambda s: str(s),
        terminal_statuses={"finished", "failed", "cancelled"},
        logger=SimpleNamespace(error=lambda *_a, **_kw: None),
    ):
        events.append(payload)

    assert any('"type": "connected"' in e for e in events)
    assert any('"type": "log"' in e for e in events)

    missing_events = []
    async for payload in at.stream_training_logs_events(
        job_id="j2",
        job_name="j2",
        habitat=SimpleNamespace(training_containers={}),
        parser_factory=parser_factory,
        normalize_status_fn=lambda s: str(s),
        terminal_statuses={"finished", "failed", "cancelled"},
        logger=SimpleNamespace(error=lambda *_a, **_kw: None),
    ):
        missing_events.append(payload)
    assert any("Training container not found" in e for e in missing_events)
