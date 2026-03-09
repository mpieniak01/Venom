from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


def test_update_job_in_history_noop_when_job_missing(tmp_path: Path):
    jobs_file = tmp_path / "jobs.jsonl"
    logger = _logger()
    academy_history.save_job_to_history(
        {"job_id": "job-1", "status": "queued"}, jobs_file, logger=logger
    )
    before = jobs_file.read_text(encoding="utf-8")

    academy_history.update_job_in_history(
        "job-does-not-exist",
        {"status": "running"},
        jobs_file,
        logger=logger,
    )

    after = jobs_file.read_text(encoding="utf-8")
    assert after == before


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


def test_save_adapter_metadata_prepares_ollama_gguf_for_ollama_runtime(tmp_path: Path):
    adapter_path = tmp_path / "job-ollama" / "adapter"
    adapter_path.parent.mkdir(parents=True, exist_ok=True)
    adapter_path.mkdir(parents=True, exist_ok=True)
    expected_gguf = adapter_path.parent / "adapter" / "Adapter-F16-LoRA.gguf"
    expected_gguf.parent.mkdir(parents=True, exist_ok=True)
    expected_gguf.write_text("gguf", encoding="utf-8")
    job = {
        "job_id": "job-ollama",
        "base_model": "gemma-3-4b-it",
        "parameters": {"runtime_id": "ollama"},
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:10:00",
    }
    with patch(
        "venom_core.api.routes.academy_history._adapter_runtime._ensure_ollama_adapter_gguf",
        return_value=expected_gguf,
    ) as mock_convert:
        academy_history.save_adapter_metadata(job, adapter_path)

    mock_convert.assert_called_once()
    metadata_file = adapter_path.parent / "metadata.json"
    text = metadata_file.read_text(encoding="utf-8")
    assert '"effective_runtime_id": "ollama"' in text
    assert '"ollama_adapter_gguf_path"' in text
