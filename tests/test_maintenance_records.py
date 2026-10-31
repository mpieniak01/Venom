"""Scheduling, provenance, held-out export and measurements without live inference."""

import json
import os
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from venom_core.services.maintenance_comparison import inference, metrics, worker
from venom_core.services.maintenance_comparison.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_worker_requires_real_parent_lease(tmp_path, monkeypatch):
    monkeypatch.delenv("VENOM_MAINTENANCE_ADMISSION_DB", raising=False)
    with pytest.raises(RuntimeError, match="admission_required"):
        worker.require_host_owner()
    path = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE lease(pid INTEGER,owner TEXT,engine TEXT,run_id TEXT,quarantine INTEGER,cancelled INTEGER)"
        )
        db.execute(
            "INSERT INTO lease VALUES(?,?,?,?,0,0)",
            (os.getppid(), "coding-maintenance", "maintenance", "test"),
        )
    monkeypatch.setenv("VENOM_MAINTENANCE_ADMISSION_DB", str(path))
    monkeypatch.setenv("VENOM_MAINTENANCE_RUN_ID", "test")
    worker.require_host_owner()
    monkeypatch.setenv("VENOM_MAINTENANCE_RUN_ID", "other")
    with pytest.raises(RuntimeError, match="reservation_missing"):
        worker.require_host_owner()


def test_state_keeps_pending_attempts_in_denominator(tmp_path):
    row = {
        "id": "a",
        "model": "m",
        "scenario": "operator-01",
        "role": "operator",
        "repetition": 0,
        "status": "model_finished",
        "passed": True,
    }
    planned = [row, {**row, "id": "b", "scenario": "operator-02"}]
    worker._state([row], tmp_path, tmp_path / "state.json", planned)
    jobs = json.loads((tmp_path / "state.json").read_text())["jobs"]
    assert [j["status"] for j in jobs] == ["completed", "pending"]
    assert (tmp_path / "state.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_complete_schedule_and_finalist_repeats_have_300_held_out_records(
    tmp_path, monkeypatch
):
    from venom_core.core.permission_guard import permission_guard

    models, _ = load_catalog(ROOT / "config/maintenance_comparison")
    monkeypatch.setattr(worker, "require_host_owner", lambda: None)
    monkeypatch.setattr(permission_guard, "set_level", lambda _: True)
    monkeypatch.setattr(worker.importlib.metadata, "version", lambda _: "test")
    monkeypatch.setattr(
        worker,
        "_runtime_environment",
        lambda: {"packages": {"backend": "test"}, "gpu": None},
    )

    class Model:
        def __init__(self, profile, cache):
            self.profile = profile

        def close(self):
            pass

    monkeypatch.setattr(worker, "LocalModel", Model)

    async def attempt(
        model, profile, case, repo, sha, output, repetition, seconds, **_kwargs
    ):
        return {
            "id": str(worker.uuid4()),
            "model": profile["id"],
            "hf_id": profile["hf_id"],
            "revision": profile["revision"],
            "role": case.role,
            "scenario": case.id,
            "repetition": repetition,
            "status": "model_finished",
            "passed": True,
            "model_finished": True,
            "seconds": 1,
            "verification": {"reason": "test_double_only"},
            "calls": [
                {
                    "name": "Terminal",
                    "arguments": {"command": "printf MAINTENANCE_PROTOCOL_OK"},
                    "result": {"stdout": "MAINTENANCE_PROTOCOL_OK", "exit_code": 0},
                },
                {"name": "Finish", "arguments": {}, "result": {}},
            ],
            "messages": [
                {"role": "assistant", "content": "tool"},
                {"role": "tool", "content": "actual"},
                {"role": "assistant", "content": "finished"},
            ],
            "repo_sha": sha,
        }

    monkeypatch.setattr(worker, "trial", attempt)
    args = SimpleNamespace(
        repo=str(ROOT),
        out=str(tmp_path),
        models=",".join(m["id"] for m in models),
        tasks="maintenance_operator,maintenance_repair,maintenance_localization",
        timeout=180,
        state_file=str(tmp_path / "state.json"),
        phase="comparison",
    )
    await worker.execute(args)
    rows = json.loads((tmp_path / "attempts.json").read_text())
    export = json.loads((tmp_path / "training-records.json").read_text())
    assert len(rows) == 300 and sum(r["repetition"] == 0 for r in rows) == 180
    assert len(export) == 300 and all(
        r["training_allowed"] is False and r["split"] == "test" for r in export
    )
    assert all(
        r["revision"] and r["repo_sha"] and r["purpose"] == "held_out_evaluation"
        for r in export
    )
    assert len(json.loads((tmp_path / "plan.json").read_text())) == 300
    report = (tmp_path / "REPORT.md").read_text()
    assert "180/180" in report and "100.0%" in report and "N/A" in report


def test_finalists_require_complete_unblocked_baseline():
    rows = [
        {
            "model": "m",
            "role": "operator",
            "scenario": f"operator-{i:02}",
            "repetition": 0,
            "status": "model_finished",
            "passed": True,
            "seconds": 1,
        }
        for i in range(1, 11)
    ]
    assert worker.choose_finalists(rows)["operator"] == ["m"]
    rows[0]["status"] = "blocked"
    assert worker.choose_finalists(rows)["operator"] == []
    rows.pop()
    assert worker.choose_finalists(rows)["operator"] == []


def test_rss_sample_is_measured_or_explicitly_missing(monkeypatch):
    sampler = metrics.MemorySampler()
    original = sampler.stop.wait

    def wait(_):
        sampler.stop.set()
        return original(0)

    monkeypatch.setattr(sampler.stop, "wait", wait)
    monkeypatch.setattr(metrics.Path, "read_text", lambda _: "VmRSS: 42 kB")
    sampler._sample()
    assert sampler.peak == 42 * 1024
    broken = metrics.MemorySampler()
    monkeypatch.setattr(broken.stop, "wait", lambda _: broken.stop.set())
    monkeypatch.setattr(metrics.Path, "read_text", lambda _: "VmRSS: invalid kB")
    broken._sample()
    assert broken.peak is None


@pytest.mark.parametrize("parameters,quantized", [(100, False), (3_000_000_000, True)])
def test_inference_pins_checkpoint_and_preserves_native_tokens(
    tmp_path, monkeypatch, parameters, quantized
):
    import sys

    model = MagicMock()
    model.eval.return_value = model
    model.device = "cuda"
    model.generation_config.eos_token_id = 99
    generated = [7, 99]
    output = MagicMock()
    output.__getitem__.return_value = generated
    model.generate.return_value = output
    tokens = MagicMock()
    tokens.__getitem__.return_value = SimpleNamespace(shape=[1, 3])
    tokens.to.return_value = tokens
    tokenizer = MagicMock()
    tokenizer.return_value = tokens
    tokenizer.apply_chat_template.return_value = "native template"
    tokenizer.decode.return_value = "<tool_call>native</tool_call><eos>"
    tokenizer.eos_token = "<eos>"
    tokenizer.eos_token_id = 99
    torch = SimpleNamespace(
        float16="float16",
        bfloat16="bfloat16",
        __version__="test",
        cuda=MagicMock(),
        manual_seed=MagicMock(),
        inference_mode=lambda: nullcontext(),
    )
    torch.cuda.get_device_name.return_value = "NVIDIA GeForce RTX 3060"
    torch.cuda.get_device_properties.return_value = SimpleNamespace(
        total_memory=12 * 1024**3
    )
    factory = MagicMock()
    factory.from_pretrained.return_value = model
    tokenizer_factory = MagicMock()
    tokenizer_factory.from_pretrained.return_value = tokenizer
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoModelForCausalLM=factory,
            AutoTokenizer=tokenizer_factory,
            BitsAndBytesConfig=lambda **kw: kw,
        ),
    )
    monkeypatch.setattr(inference.importlib.metadata, "version", lambda _: "test")
    profile = {
        "hf_id": "public/test",
        "revision": "a" * 40,
        "parameters": parameters,
        "protocol": "lfm2_tool",
        "profile": {
            "context_tokens": 128,
            "temperature": 0,
            "max_new_tokens": 8,
            "seed": 17,
        },
    }
    local = inference.LocalModel(profile, tmp_path)
    assert factory.from_pretrained.call_args.kwargs["revision"] == "a" * 40
    assert factory.from_pretrained.call_args.kwargs["trust_remote_code"] is False
    assert (
        bool(factory.from_pretrained.call_args.kwargs["quantization_config"])
        == quantized
    )
    assert (
        local.generate([], [{"function": {"name": "Terminal"}}], 1)
        == "<tool_call>native</tool_call>"
    )
    assert tokenizer.call_args.kwargs["add_special_tokens"] is False
    assert local.last_generation_finish == "eos" and local.output_tokens == 2
    assert tokenizer.apply_chat_template.call_args.kwargs["tools"] == [
        {"name": "Terminal"}
    ]
    local.context = 4
    with pytest.raises(ValueError, match="context_limit"):
        local.generate([], [], 1)
    assert "cuda_peak_reserved_bytes" in local.memory()
    local.close()
    torch.cuda.empty_cache.assert_called_once()


@pytest.mark.parametrize("nonfinite", [False, True])
def test_backend_nonfinite_scores_are_infrastructure_errors(nonfinite):
    class Flag(int):
        def any(self):
            return self

        def all(self, **_):
            return self

        def item(self):
            return bool(self)

        def __or__(self, other):
            return Flag(bool(self) or bool(other))

    torch = SimpleNamespace(
        isnan=lambda _: Flag(nonfinite),
        isposinf=lambda _: Flag(False),
        isneginf=lambda _: Flag(False),
    )
    processor = inference._FiniteScores(torch)
    if nonfinite:
        with pytest.raises(inference.InferenceNumericalError):
            processor([], [])
    else:
        scores = []
        assert processor([], scores) is scores
