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
    """Verify worker requires real parent lease."""
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
    """Verify state keeps pending attempts in denominator."""
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
    """Verify complete schedule and finalist repeats have 300 held out records."""
    from venom_core.core.permission_guard import permission_guard

    models, cases = load_catalog(ROOT / "config/maintenance_comparison")
    monkeypatch.setattr(worker, "load_all_models", lambda _: (models, cases))
    monkeypatch.setattr(worker, "require_host_owner", lambda: None)
    monkeypatch.setattr(
        worker,
        "validate_worker_paths",
        lambda arguments: (ROOT, tmp_path, tmp_path / "state.json"),
    )
    monkeypatch.setattr(permission_guard, "set_level", lambda _: True)
    monkeypatch.setattr(worker.importlib.metadata, "version", lambda _: "test")
    monkeypatch.setattr(
        worker,
        "_runtime_environment",
        lambda: {"packages": {"backend": "test"}, "gpu": None},
    )

    class Model:
        def __init__(self, profile, cache):
            """Initialize the test double with only the state required by this scenario."""
            self.profile = profile

        def close(self):
            """Release the test double resources without touching the live stack."""
            pass

    monkeypatch.setattr(worker, "LocalModel", Model)

    async def attempt(
        model, profile, case, repo, sha, output, repetition, seconds, **_kwargs
    ):
        """Return a controlled completed attempt with the scheduled identifiers."""
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
    assert len(rows) == 300
    assert sum((r["repetition"] == 0 for r in rows)) == 180
    assert len(export) == 300
    assert all(
        (r["training_allowed"] is False and r["split"] == "test" for r in export)
    )
    assert all(
        r["revision"] and r["repo_sha"] and r["purpose"] == "held_out_evaluation"
        for r in export
    )
    assert len(json.loads((tmp_path / "plan.json").read_text())) == 300
    report = (tmp_path / "REPORT.md").read_text()
    assert "180/180" in report
    assert "100.0%" in report
    assert "N/A" in report


def test_finalists_require_complete_unblocked_baseline():
    """Verify finalists require complete unblocked baseline."""
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
    """Verify rss sample is measured or explicitly missing."""
    sampler = metrics.MemorySampler()
    original = sampler.stop.wait

    def wait(_):
        """Simulate unavailable memory sampling without a live process probe."""
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
@pytest.mark.parametrize("protocol", ["lfm2_tool", "gemma4_tool", "qwen35_xml"])
def test_inference_pins_checkpoint_and_preserves_native_tokens(
    tmp_path, monkeypatch, parameters, quantized, protocol
):
    """Verify inference pins checkpoint and preserves native tokens."""
    import sys

    model = MagicMock()
    model.eval.return_value = model
    model.device = "cuda"
    model.generation_config.eos_token_id = 99
    final_id = 98 if protocol == "qwen35_xml" else 99
    generated = [7, final_id]
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
        "protocol": protocol,
        "profile": {
            "context_tokens": 128,
            "temperature": 0,
            "max_new_tokens": 8,
            "seed": 17,
        },
    }
    if protocol != "lfm2_tool":
        profile["profile"].update(
            temperature=0.7, top_p=0.8, top_k=20, presence_penalty=1.5
        )
    if protocol == "qwen35_xml":
        profile["profile"]["eos_token_ids"] = [98, 99]
    local = inference.LocalModel(profile, tmp_path)
    assert model.generate.call_count == 0
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
    assert local.last_generation_finish == "eos"
    if protocol == "qwen35_xml":
        assert model.generate.call_args.kwargs["eos_token_id"] == [98, 99]
    else:
        assert "eos_token_id" not in model.generate.call_args.kwargs
    assert local.output_tokens == 2
    expected_tools = (
        [{"name": "Terminal"}]
        if protocol == "lfm2_tool"
        else [{"function": {"name": "Terminal"}}]
    )
    assert tokenizer.apply_chat_template.call_args.kwargs["tools"] == expected_tools
    if protocol != "lfm2_tool":
        assert model.generate.call_args.kwargs["top_k"] == 20
        assert len(model.generate.call_args.kwargs["logits_processor"]) == 2
    local.context = 4
    with pytest.raises(ValueError, match="context_limit"):
        local.generate([], [], 1)
    assert "cuda_peak_reserved_bytes" in local.memory()
    local.close()
    torch.cuda.empty_cache.assert_called_once()


@pytest.mark.parametrize("nonfinite", [False, True])
def test_backend_nonfinite_scores_are_infrastructure_errors(nonfinite):
    """Verify backend nonfinite scores are infrastructure errors."""

    class Flag(int):
        def any(self):
            """Return the configured tensor reduction used to test invalid logits."""
            return self

        def all(self, **_):
            """Return the configured tensor reduction for the requested dimension."""
            return self

        def item(self):
            """Return the scalar value of the fake tensor."""
            return bool(self)

        def __or__(self, other):
            """Combine fake invalid-score flags without importing Torch."""
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


@pytest.mark.parametrize("field", ["repo", "out", "state_file"])
def test_worker_rejects_paths_outside_host_issued_run(tmp_path, monkeypatch, field):
    """Verify worker rejects paths outside host issued run."""
    run_id = "62dc6041-a732-4f9c-adf1-446700df60f9"
    monkeypatch.setenv("VENOM_MAINTENANCE_RUN_ID", run_id)
    monkeypatch.setattr(
        worker,
        "__file__",
        str(tmp_path / "venom_core/services/maintenance_comparison/worker.py"),
    )
    output = tmp_path / "data/benchmarks/coding" / run_id
    arguments = SimpleNamespace(
        repo=str(tmp_path),
        out=str(output),
        state_file=str(output / "scheduler_state.json"),
    )
    worker.validate_worker_paths(arguments)
    setattr(arguments, field, str(tmp_path / "outside.json"))
    with pytest.raises(ValueError, match="worker_path_mismatch"):
        worker.validate_worker_paths(arguments)


def test_worker_rejects_symlinked_output(tmp_path, monkeypatch):
    """Verify worker rejects symlinked output."""
    run_id = "62dc6041-a732-4f9c-adf1-446700df60f9"
    monkeypatch.setenv("VENOM_MAINTENANCE_RUN_ID", run_id)
    monkeypatch.setattr(
        worker,
        "__file__",
        str(tmp_path / "venom_core/services/maintenance_comparison/worker.py"),
    )
    root = tmp_path / "data/benchmarks/coding"
    root.mkdir(parents=True)
    output = root / run_id
    output.symlink_to(tmp_path, target_is_directory=True)
    arguments = SimpleNamespace(
        repo=str(tmp_path),
        out=str(output),
        state_file=str(output / "scheduler_state.json"),
    )
    with pytest.raises(ValueError, match="output_path_invalid"):
        worker.validate_worker_paths(arguments)


def test_worker_uses_host_storage_root_without_trusting_cli_destination(
    tmp_path, monkeypatch
):
    """Verify worker uses host storage root without trusting cli destination."""
    run_id = "62dc6041-a732-4f9c-adf1-446700df60f9"
    monkeypatch.setenv("VENOM_MAINTENANCE_RUN_ID", run_id)
    monkeypatch.setattr(
        worker,
        "__file__",
        str(tmp_path / "venom_core/services/maintenance_comparison/worker.py"),
    )
    root = tmp_path / "operator-storage"
    monkeypatch.setenv("VENOM_MAINTENANCE_OUTPUT_ROOT", str(root))
    output = root / run_id
    arguments = SimpleNamespace(
        repo=str(tmp_path),
        out=str(output),
        state_file=str(output / "scheduler_state.json"),
    )
    assert worker.validate_worker_paths(arguments) == (
        tmp_path,
        output,
        output / "scheduler_state.json",
    )
    monkeypatch.setenv("VENOM_MAINTENANCE_OUTPUT_ROOT", "relative-root")
    with pytest.raises(ValueError, match="output_root_invalid"):
        worker.validate_worker_paths(arguments)


def test_gemma4_history_preserves_named_actual_tool_results():
    """Verify gemma4 history preserves named actual tool results."""
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "Terminal", "arguments": {"command": "false"}}}
            ],
        },
        {
            "role": "tool",
            "name": "Terminal",
            "content": '{"stdout":"","stderr":"actual error","exit_code":1}',
        },
        {"role": "tool", "name": "Other", "content": "tool_not_available"},
        {"role": "user", "content": "next"},
    ]
    native = inference._gemma4_history(messages)
    assert native[0]["tool_responses"] == [
        {
            "name": "Terminal",
            "response": {"stdout": "", "stderr": "actual error", "exit_code": 1},
        },
        {"name": "Other", "response": "tool_not_available"},
    ]
    assert "tool_responses" not in messages[0]
    assert native[1:] == messages[1:]


def test_presence_penalty_ignores_prompt_and_counts_repetition_once():
    """Verify presence penalty ignores prompt and counts repetition once."""
    import numpy as np

    class Mask(np.ndarray):
        def scatter_(self, dim, indices, value):
            """Record one presence penalty per generated token in the fake score matrix."""
            np.put_along_axis(self, indices, value, axis=dim)
            return self

    torch = SimpleNamespace(zeros_like=lambda values: np.zeros_like(values).view(Mask))
    penalty = inference._PresencePenalty(torch, 2, 1.5)
    scores = np.array([[4.0, 3.0, 2.0, 1.0]])
    ids = np.array([[0, 1, 2, 2, 3]])
    np.testing.assert_allclose(penalty(ids, scores), [[4.0, 3.0, 0.5, -0.5]])
    np.testing.assert_allclose(penalty(ids[:, :2], scores), scores)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_presence_penalty_rejects_nonfinite_settings(value):
    """Verify presence penalty rejects nonfinite settings."""
    with pytest.raises(ValueError, match="finite"):
        inference._PresencePenalty(None, 1, value)


@pytest.mark.asyncio
async def test_additional_baseline_plans_sixty_cases_without_repeats(
    tmp_path, monkeypatch
):
    """Verify additional baseline plans sixty cases without repeats."""
    monkeypatch.setattr(
        worker, "_runtime_environment", lambda: {"packages": {}, "gpu": None}
    )
    args = SimpleNamespace(
        repo=str(ROOT),
        out=str(tmp_path),
        models="gemma-4-e2b-it,qwen3.5-9b",
        tasks="maintenance_operator,maintenance_repair,maintenance_localization",
        phase="baseline",
        timeout=180,
        state_file=str(tmp_path / "state.json"),
    )
    experiment = worker.Experiment(args)
    seen = []

    async def complete(profile, cases, repetition):
        """Return controlled case results for baseline scheduling assertions."""
        seen.append((profile["id"], repetition))
        for case in cases:
            experiment.rows.append(
                {
                    "model": profile["id"],
                    "role": case.role,
                    "scenario": case.id,
                    "repetition": repetition,
                    "passed": True,
                    "status": "model_finished",
                    "seconds": 1.0,
                }
            )

    experiment._model = complete
    await experiment.run()
    assert len(experiment.planned) == 60
    assert len(experiment.rows) == 60
    assert seen == [("gemma-4-e2b-it", 0), ("qwen3.5-9b", 0)]


def test_backend_options_pin_only_explicit_kernels(monkeypatch):
    """Verify backend options pin only explicit kernels."""
    import sys

    factory = MagicMock()
    monkeypatch.setitem(
        sys.modules, "transformers", SimpleNamespace(KernelConfig=factory)
    )
    options = inference._backend_options(
        {
            "id": "qwen3.5-9b",
            "profile": {
                "attention_implementation": "sdpa",
                "kernel_profile": "qwen35-deltanet-v1",
            },
        }
    )
    assert options["use_kernels"] is True
    assert options["attn_implementation"] == "sdpa"
    assert factory.call_args.kwargs["inherit_mapping"] is False
    mapping = factory.call_args.kwargs["kernel_mapping"]
    assert len(mapping) == 4
    for name, device in mapping.items():
        repo, metadata = device["cuda"]
        assert repo.startswith("kernels-community/")
        expected = (
            "recurrent_gated_delta_rule"
            if name == "fused_recurrent_gated_delta_rule"
            else name
        )
        assert repo.endswith(":" + expected)
        assert len(metadata["revision"]) == 40
        assert "version" not in metadata


@pytest.mark.parametrize(
    "name, kernel", [("other", "qwen35-deltanet-v1"), ("qwen3.5-9b", "unknown")]
)
def test_backend_rejects_unqualified_kernel_profiles(name, kernel):
    """Verify backend rejects unqualified kernel profiles."""
    with pytest.raises(ValueError, match="unsupported_kernel_profile"):
        inference._backend_options({"id": name, "profile": {"kernel_profile": kernel}})


def test_reference_profile_does_not_enable_hub_kernels():
    """Verify reference profile does not enable hub kernels."""
    assert inference._backend_options({"profile": {}}) == {}


def test_kernel_bindings_report_actual_forward_implementation():
    """Verify kernel bindings report actual forward implementation."""

    def optimized():
        """Stand in for the qualified kernel forward implementation."""
        pass

    module = SimpleNamespace(
        _kernel_funcs={"op": SimpleNamespace(kernel_layer_name="op", forward=optimized)}
    )
    model = SimpleNamespace(named_modules=lambda: [("layer", module)])
    assert inference._kernel_bindings(model) == {
        "op": optimized.__module__ + "." + optimized.__qualname__
    }
