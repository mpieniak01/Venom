from pathlib import Path
from types import SimpleNamespace

from venom_core.api.routes import academy_history


def _logger():
    return SimpleNamespace(warning=lambda *_a, **_k: None, error=lambda *_a, **_k: None)


def test_load_jobs_history_skips_invalid_jsonl_line(tmp_path: Path):
    jobs_file = tmp_path / "jobs.jsonl"
    jobs_file.write_text(
        '{"job_id":"j1"}\n{bad json}\n{"job_id":"j2"}\n', encoding="utf-8"
    )

    jobs = academy_history.load_jobs_history(jobs_file, logger=_logger())

    assert [j["job_id"] for j in jobs] == ["j1", "j2"]


def test_save_and_update_job_in_history(tmp_path: Path):
    jobs_file = tmp_path / "jobs.jsonl"
    logger = _logger()
    academy_history.save_job_to_history(
        {"job_id": "job-1", "status": "queued"}, jobs_file, logger=logger
    )
    academy_history.update_job_in_history(
        "job-1",
        {"status": "running", "container_id": "abc"},
        jobs_file,
        logger=logger,
    )

    jobs = academy_history.load_jobs_history(jobs_file, logger=logger)
    assert len(jobs) == 1
    assert jobs[0]["status"] == "running"
    assert jobs[0]["container_id"] == "abc"


def test_save_adapter_metadata(tmp_path: Path):
    adapter_path = tmp_path / "job-x" / "adapter"
    adapter_path.parent.mkdir(parents=True, exist_ok=True)
    adapter_path.write_text("adapter", encoding="utf-8")
    job = {
        "job_id": "job-x",
        "base_model": "m1",
        "dataset_path": "/tmp/dataset.jsonl",
        "parameters": {"lora_rank": 8},
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:10:00",
    }

    academy_history.save_adapter_metadata(job, adapter_path)

    metadata_file = adapter_path.parent / "metadata.json"
    assert metadata_file.exists()
    text = metadata_file.read_text(encoding="utf-8")
    assert '"job_id": "job-x"' in text
    assert '"source": "academy"' in text
