"""CPU autograd and process-boundary contracts for the optional training worker."""

import contextlib
import copy
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")

from venom_core.services.granite_operator import cli, engine, worker  # noqa: E402
from venom_core.services.granite_operator.contract import (  # noqa: E402
    TrainingProfile,
    write_json,
)
from venom_core.services.granite_operator.encoding import collate  # noqa: E402


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        torch.manual_seed(5)
        self.base = torch.nn.Parameter(torch.randn(9, 9), requires_grad=False)
        self.lora_A = torch.nn.Parameter(torch.randn(9, 2) * 0.1)
        self.lora_B = torch.nn.Parameter(torch.zeros(2, 9))
        self.disabled = False

    def forward(self, input_ids, attention_mask, use_cache, logits_to_keep):
        matrix = self.base
        if not self.disabled:
            matrix = matrix + self.lora_A @ self.lora_B
        return SimpleNamespace(logits=matrix[input_ids][:, logits_to_keep])

    @contextlib.contextmanager
    def disable_adapter(self):
        self.disabled = True
        try:
            yield
        finally:
            self.disabled = False

    def save_pretrained(self, path, safe_serialization):
        torch.save(self.state_dict(), path / "tiny.pt")


def tiny_session(monkeypatch):
    monkeypatch.setattr(torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(torch.cuda, "get_rng_state_all", lambda: [])
    monkeypatch.setattr(torch.cuda, "set_rng_state_all", lambda value: None)
    session = engine.Session.__new__(engine.Session)
    session.torch = torch
    session.profile = TrainingProfile(accumulation=2, learning_rate=0.01)
    session.model = TinyModel()
    session.parameters = [p for p in session.model.parameters() if p.requires_grad]
    session.optimizer = torch.optim.AdamW(session.parameters, lr=0.01)
    session.step = 0
    session.target_tokens = 0
    session.logs = []
    session.base_hash = engine.tensor_hash([("base", session.model.base)])
    session.initial_adapter_hash = session.adapter_hash()
    session.tokenizer = SimpleNamespace(
        pad_token_id=0, save_pretrained=lambda path: None
    )
    session.batch = lambda row: collate([row], 0, torch)
    return session


ROW = {
    "input_ids": [1, 2, 3, 4],
    "attention_mask": [1, 1, 1, 1],
    "labels": [-100, -100, 3, 4],
}


def test_loss_matches_full_shift_and_masks_tool_tokens():
    model = TinyModel()
    batch = collate([ROW], 0, torch)
    loss, count = engine.loss_for(model, batch)
    full = model.base[batch["input_ids"]]
    expected = torch.nn.functional.cross_entropy(
        full[:, :-1].reshape(-1, 9),
        batch["labels"][:, 1:].reshape(-1),
        ignore_index=-100,
    )
    assert count == 2
    torch.testing.assert_close(loss, expected)
    loss.backward()
    assert model.base.grad is None
    assert model.lora_B.grad is not None


def test_training_checkpoint_reload_and_resume(tmp_path, monkeypatch):
    session = tiny_session(monkeypatch)
    before = session.evaluate([ROW])["assistant_nll"]
    session.train([ROW], 12)
    assert session.evaluate([ROW])["assistant_nll"] < before
    assert all(session.checks().values())
    assert not torch.equal(session.probe(ROW), session.probe(ROW, disable=True))
    path = tmp_path / "checkpoint"
    session.save(path, ROW, "identity")
    restarted = tiny_session(monkeypatch)
    restarted.model.load_state_dict(torch.load(path / "tiny.pt", weights_only=True))
    assert restarted.restore(path, ROW, "identity")
    assert restarted.step == 12
    session.train([ROW], 2)
    restarted.train([ROW], 2)
    assert restarted.step == 14
    assert restarted.target_tokens == session.target_tokens
    assert restarted.adapter_hash() == session.adapter_hash()
    with pytest.raises(ValueError, match="fingerprint"):
        restarted.restore(path, ROW, "wrong")
    (path / "tiny.pt").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="corrupt"):
        restarted.restore(path, ROW, "identity")


def test_reload_checks_logits_and_scheduler(tmp_path, monkeypatch):
    session = tiny_session(monkeypatch)
    session.train([ROW], 1)
    path = tmp_path / "checkpoint"
    session.save(path, ROW, "identity")
    other = tiny_session(monkeypatch)
    with torch.no_grad():
        other.model.lora_B.add_(10)
    with pytest.raises(RuntimeError, match="logits"):
        other.restore(path, ROW, "identity")
    other.model.load_state_dict(session.model.state_dict())
    original_load = torch.load

    def modified(*args, **kwargs):
        state = original_load(*args, **kwargs)
        state["scheduler"]["step"] += 1
        return state

    monkeypatch.setattr(torch, "load", modified)
    with pytest.raises(RuntimeError, match="scheduler"):
        other.restore(path, ROW, "identity")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_fails(value):
    with pytest.raises(RuntimeError, match="nonfinite"):
        engine.finite(value, "test")


def test_empty_shifted_mask():
    row = copy.deepcopy(ROW)
    row["labels"] = [-100] * 4
    _case_value_0 = TinyModel()
    _case_value_1 = collate([row], 0, torch)
    with pytest.raises(ValueError, match="empty_shifted"):
        engine.loss_for(_case_value_0, _case_value_1)


def test_owner_requires_real_parent_lease(tmp_path, monkeypatch):
    monkeypatch.delenv("VENOM_GRANITE_ADMISSION_DB", raising=False)
    with pytest.raises(RuntimeError, match="admission_required"):
        engine.require_owner()
    path = tmp_path / "host.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE lease(pid,owner,engine,run_id,quarantine,cancelled)")
        db.execute(
            "INSERT INTO lease VALUES(?,?,?,?,0,0)",
            (
                os.getppid(),
                "granite-training",
                "granite-training",
                "run",
            ),
        )
    monkeypatch.setenv("VENOM_GRANITE_ADMISSION_DB", str(path))
    monkeypatch.setenv("VENOM_GRANITE_RUN_ID", "run")
    engine.require_owner()
    monkeypatch.setenv("VENOM_GRANITE_RUN_ID", "wrong")
    with pytest.raises(RuntimeError, match="reservation"):
        engine.require_owner()


def test_smoke_receipt_never_promotes_failed_probe():
    checks = dict.fromkeys(
        (
            "mask",
            "updated_adapter",
            "frozen_base",
            "reload",
            "resume",
            "long_context",
            "tool_loop",
            "adapter_effect",
        ),
        True,
    )
    metrics = {"checks": checks, "fingerprint": "identity"}
    assert cli.qualification(metrics, metrics, {})["status"] == "PASS"
    broken = copy.deepcopy(metrics)
    broken["checks"]["tool_loop"] = False
    assert cli.qualification(broken, metrics, {})["status"] == "FAIL"
    broken["fingerprint"] = "changed"
    with pytest.raises(ValueError, match="identity"):
        cli.qualification(broken, metrics, {})


def test_offline_rejects_listener(monkeypatch):
    sock = Mock()
    sock.__enter__ = Mock(return_value=sock)
    sock.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(cli.socket, "socket", lambda: sock)
    sock.connect_ex.return_value = 0
    with pytest.raises(RuntimeError, match="offline_host"):
        cli.require_offline([8800])
    sock.connect_ex.return_value = 1
    cli.require_offline([8800])


def test_smoke_selection_does_not_mix_variants():
    rows = [
        {"problem_group": family, "language": language, "variant": variant}
        for family in ("a", "b")
        for variant in (0, 1)
        for language in ("pl", "en")
    ]
    selected = worker.smoke_subset(rows)
    assert len(selected) == 4
    assert {r["variant"] for r in selected} == {0}


@pytest.mark.parametrize("train_groups,val_groups", [(16, 4), (20, 6)])
def test_smoke_rows_bound_new_families_without_changing_corpus(
    train_groups, val_groups
):
    train = [
        {"problem_group": f"train-{group}", "language": language, "variant": variant}
        for group in range(train_groups)
        for variant in (0, 1)
        for language in ("pl", "en")
    ]
    validation = [
        {
            "problem_group": f"validation-{group}",
            "language": language,
            "variant": variant,
        }
        for group in range(val_groups)
        for variant in (0, 1)
        for language in ("pl", "en")
    ]
    original = copy.deepcopy((train, validation))
    selected, heldout = worker._training_rows(
        {"stage": "smoke-first"}, train, validation, [], [], "unused"
    )
    assert (len(selected), len(heldout)) == (32, 8)
    assert {row["variant"] for row in selected + heldout} == {0}
    assert {row["language"] for row in selected + heldout} == {"pl", "en"}
    assert (train, validation) == original


def test_smoke_rows_reject_incomplete_qualification_corpus():
    rows = [{"problem_group": "only-one", "language": "pl"}]
    with pytest.raises(ValueError, match="granite_smoke_sample_count"):
        worker._training_rows({"stage": "smoke-first"}, rows, rows, [], [], "unused")


@pytest.mark.parametrize("changed_input", ["code", "lock", "weights", "versions"])
def test_environment_fingerprint_covers_lock_code_and_weights(
    tmp_path, monkeypatch, changed_input
):
    """Bind the environment identity to its lock, worker code and weight snapshot."""
    root = tmp_path / "repo"
    package = root / "venom_core/services/granite_operator"
    package.mkdir(parents=True)
    (package / "engine.py").write_text("first")
    lock = root / "requirements/locks/granite-operator-training-linux-py314.txt"
    lock.parent.mkdir(parents=True)
    lock.write_text("locked")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "config.json").write_text("{}")
    (snapshot / "model.safetensors").write_bytes(b"weights")
    monkeypatch.setattr(engine, "__file__", str(package / "engine.py"))
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda index: "test-gpu")
    monkeypatch.setattr(
        torch.cuda,
        "get_device_properties",
        lambda index: SimpleNamespace(total_memory=12),
    )
    monkeypatch.setattr(
        engine.importlib.metadata, "version", lambda name: "test-version"
    )
    identity = engine.environment_identity(
        TrainingProfile(),
        {"datasets": {}},
        SimpleNamespace(chat_template="native"),
        snapshot,
    )
    assert identity["weights"]
    assert identity["code"]
    assert identity["dependency_lock"]
    if changed_input == "versions":
        monkeypatch.setattr(
            engine.importlib.metadata, "version", lambda name: "new-version"
        )
    else:
        artifact = {
            "code": package / "engine.py",
            "lock": lock,
            "weights": snapshot / "model.safetensors",
        }[changed_input]
        artifact.write_text("changed")
    changed = engine.environment_identity(
        TrainingProfile(),
        {"datasets": {}},
        SimpleNamespace(chat_template="native"),
        snapshot,
    )
    assert changed != identity


@pytest.mark.parametrize("padding_role", ["tool", "user"])
def test_long_context_does_backward_without_optimizer_update(monkeypatch, padding_role):
    session = tiny_session(monkeypatch)

    def encoding(row, tokenizer, context):
        size = len(row["messages"][0]["content"])
        if size > context:
            raise ValueError("granite_context_or_offsets_invalid")
        return {
            "input_ids": [1] * size,
            "attention_mask": [1] * size,
            "labels": [-100] * (size - 1) + [2],
        }

    monkeypatch.setattr(engine, "encode", encoding)
    before = session.adapter_hash()
    row = {"messages": [{"role": padding_role, "content": "original"}]}
    result = session.long_context(row)
    assert row["messages"][0]["content"] == "original"
    assert result["tokens"] >= 2040
    assert session.adapter_hash() == before
    assert session.step == 0
    assert all(p.grad is None for p in session.parameters)


def test_long_context_never_pads_a_supervised_assistant_target(monkeypatch):
    session = tiny_session(monkeypatch)
    with pytest.raises(
        ValueError, match="granite_long_context_unsupervised_turn_missing"
    ):
        session.long_context({"messages": [{"role": "assistant", "content": "answer"}]})
    assert session.step == 0


@pytest.mark.parametrize(
    "precision,adapter", [("nf4", None), ("bf16", None), ("nf4", Path("adapter"))]
)
def test_session_load_preserves_precision_and_trains_only_adapter(
    monkeypatch, precision, adapter
):
    import sys

    fake_peft = SimpleNamespace(
        LoraConfig=lambda **kwargs: kwargs,
        get_peft_model=lambda base, config: TinyModel(),
        PeftModel=SimpleNamespace(from_pretrained=lambda *args, **kwargs: TinyModel()),
        prepare_model_for_kbit_training=lambda base, **kwargs: base,
    )
    base = TinyModel()
    base.gradient_checkpointing_enable = Mock()
    base.enable_input_require_grads = Mock()
    base.config = SimpleNamespace(use_cache=True)
    calls = []

    def loader(*args, **kwargs):
        calls.append(kwargs)
        return base

    import transformers

    monkeypatch.setattr(engine, "require_owner", lambda: None)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "manual_seed_all", lambda seed: None)
    monkeypatch.setitem(sys.modules, "peft", fake_peft)
    monkeypatch.setattr(transformers.AutoModelForCausalLM, "from_pretrained", loader)
    monkeypatch.setattr(
        transformers.AutoTokenizer, "from_pretrained", lambda *a, **k: "tokenizer"
    )
    monkeypatch.setattr(transformers, "BitsAndBytesConfig", lambda **kwargs: kwargs)
    session = engine.Session(
        TrainingProfile(quantization=precision), Path("snapshot"), adapter
    )
    assert calls[0]["local_files_only"] is True
    assert ("quantization_config" in calls[0]) == (precision == "nf4")
    assert session.parameters
    assert all(
        ("lora_" in n for n, p in session.model.named_parameters() if p.requires_grad)
    )
    assert base.config.use_cache is False


def test_session_refuses_missing_cuda(monkeypatch):
    import sys

    monkeypatch.setattr(engine, "require_owner", lambda: None)
    monkeypatch.setitem(
        sys.modules,
        "peft",
        SimpleNamespace(
            LoraConfig=None,
            PeftModel=None,
            get_peft_model=None,
            prepare_model_for_kbit_training=None,
        ),
    )
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    _case_value_2 = TrainingProfile()
    _case_value_3 = Path("snapshot")
    with pytest.raises(RuntimeError, match="cuda_required"):
        engine.Session(_case_value_2, _case_value_3)


def native_call(name, **arguments):
    body = "".join(
        f"<parameter={key}>{value}</parameter>" for key, value in arguments.items()
    )
    return f"<tool_call><function={name}>{body}</function></tool_call>"


def probe_session(responses):
    iterator = iter(responses)
    tokenizer = SimpleNamespace(
        apply_chat_template=lambda *args, **kwargs: torch.tensor([[1]]),
        decode=lambda *args, **kwargs: next(iterator),
        pad_token_id=0,
    )
    return SimpleNamespace(
        tokenizer=tokenizer,
        torch=torch,
        profile=TrainingProfile(),
        model=SimpleNamespace(
            device="cpu",
            eval=lambda: None,
            generate=lambda **kwargs: torch.tensor([[1, 2]]),
        ),
    )


def test_tool_loop_requires_observed_result_before_finish():
    terminal = native_call("Terminal", command="printf 'G01_SMOKE_OK\\n'")
    finish = native_call("Finish", status="success", summary="Observed G01_SMOKE_OK")
    result = worker.tool_loop(
        probe_session([terminal, finish]),
        {"tools": [], "messages": [{"role": "system", "content": "operator"}]},
    )
    assert result["passed"]
    assert result["trace"][0]["observation"]["stdout"] == "G01_SMOKE_OK\n"
    assert not worker.tool_loop(
        probe_session([finish]),
        {"tools": [], "messages": [{"role": "system", "content": "operator"}]},
    )["passed"]


@pytest.mark.parametrize(
    "response,reason",
    [
        (native_call("Terminal", command="rm -rf /"), "probe_command_not_allowlisted"),
        (native_call("Finish", status="success", summary="unobserved"), None),
        (
            native_call("Finish", status="success", summary="x") * 2,
            "expected_single_call",
        ),
    ],
)
def test_tool_loop_fails_without_executing_other_commands(response, reason):
    result = worker.tool_loop(
        probe_session([response]),
        {"tools": [], "messages": [{"role": "system", "content": "operator"}]},
    )
    assert result["passed"] is False
    if reason:
        assert result["reason"] == reason


def worker_context(tmp_path, monkeypatch):
    import transformers

    snapshot = tmp_path / TrainingProfile().revision
    snapshot.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    train = [
        {"problem_group": str(i), "language": lang}
        for i in range(16)
        for lang in ("pl", "en")
    ]
    val = [
        {"problem_group": str(i), "language": lang}
        for i in range(4)
        for lang in ("pl", "en")
    ]
    monkeypatch.setattr(worker, "require_owner", lambda: None)
    monkeypatch.setattr(worker, "load_dataset", lambda *args: (train, val))
    monkeypatch.setattr(
        worker, "environment_identity", lambda *args: {"identity": "test"}
    )
    monkeypatch.setattr(
        transformers.AutoTokenizer, "from_pretrained", lambda *a, **k: "tokenizer"
    )
    monkeypatch.setattr(
        worker, "encoded_rows", lambda rows, *args: [copy.deepcopy(ROW) for row in rows]
    )
    created = []

    class FakeSession:
        def __init__(self, profile, snapshot, adapter):
            created.append(self)
            self.step = 0
            self.target_tokens = 0
            self.load_seconds = 1
            self.logs = []
            self.torch = SimpleNamespace(
                equal=lambda a, b: a == b,
                cuda=SimpleNamespace(
                    max_memory_allocated=lambda: 10, max_memory_reserved=lambda: 20
                ),
            )

        def restore(self, *args):
            self.step = 16
            return True

        def evaluate(self, rows):
            return {"assistant_nll": 1, "target_tokens": len(rows)}

        def train(self, rows, updates):
            self.step += updates
            self.target_tokens += updates * 10
            return 2

        def checks(self):
            return {"mask": True, "updated_adapter": True, "frozen_base": True}

        def long_context(self, row):
            return {"tokens": 2048, "loss": 1}

        def probe(self, row, disable=False):
            return int(disable)

        def save(self, path, row, fingerprint):
            path.mkdir()
            write_json(path / "receipt.json", {"fingerprint": fingerprint})

    monkeypatch.setattr(worker, "Session", FakeSession)
    monkeypatch.setattr(worker, "tool_loop", lambda *args: {"passed": True})
    request = {
        "profile": TrainingProfile().identity(),
        "data_root": str(tmp_path),
        "manifest": str(manifest),
        "snapshot": str(snapshot),
        "output": str(tmp_path / "output"),
        "stage": "smoke-resume",
        "updates": 4,
        "checkpoint": str(tmp_path / "checkpoint"),
        "dataset": "domain",
    }
    return request, created, FakeSession


def test_worker_smoke_end_to_end_receipt(tmp_path, monkeypatch):
    request, created, _ = worker_context(tmp_path, monkeypatch)
    worker.run(request)
    metrics = json.loads((Path(request["output"]) / "metrics.json").read_text())
    assert metrics["global_step"] == 20
    assert all(metrics["checks"].values())
    assert metrics["training_rows"] == 32
    assert metrics["validation_rows"] == 8
    assert len(created) == 1


@pytest.mark.parametrize("dataset", ["domain", "hf", "mixed"])
def test_worker_training_requires_qualified_artifacts(tmp_path, monkeypatch, dataset):
    from venom_core.services.granite_operator.contract import digest, file_digest

    request, created, _ = worker_context(tmp_path, monkeypatch)
    request.update(stage="train-first", dataset=dataset, checkpoint=None)
    artifact = tmp_path / "proof.json"
    artifact.write_text("{}")
    qualification_path = tmp_path / "qualification.json"
    write_json(
        qualification_path,
        {
            "status": "PASS",
            "fingerprint": digest({"identity": "test"}),
            "checks": dict.fromkeys(
                (
                    "mask",
                    "updated_adapter",
                    "frozen_base",
                    "reload",
                    "resume",
                    "long_context",
                    "tool_loop",
                ),
                True,
            ),
            "artifacts": {"proof.json": file_digest(artifact)},
        },
    )
    request["qualification"] = str(qualification_path)
    worker.run(request)
    assert len(created) == 1
    artifact.write_text("changed")
    request["output"] = str(tmp_path / "second")
    with pytest.raises(ValueError, match="artifact_changed"):
        worker.run(request)
    assert len(created) == 1  # Rejected before loading a second model.


def test_worker_stops_if_frozen_base_changed(tmp_path, monkeypatch):
    request, _, FakeSession = worker_context(tmp_path, monkeypatch)
    monkeypatch.setattr(FakeSession, "checks", lambda self: {"frozen_base": False})
    with pytest.raises(RuntimeError, match="invariants_failed"):
        worker.run(request)
    assert not (Path(request["output"]) / "checkpoint").exists()


@pytest.mark.parametrize(
    "dataset,expected_updates", [("domain", 48), ("hf", 16), ("mixed", 64)]
)
def test_coordinator_owns_children_until_exit(
    tmp_path, monkeypatch, dataset, expected_updates
):
    from venom_core.services import runtime_admission

    events = []

    class Lease:
        @contextlib.contextmanager
        def operation(self, **kwargs):
            events.append("operation")
            yield
            assert kwargs["confirm_quiescent"]()

        def release(self):
            events.append("release")

    class Admission:
        def __init__(self, *args, **kwargs):
            pass

        def acquire(self, **kwargs):
            events.append("lease")
            assert kwargs["owner"] == "granite-training"
            return Lease()

    monkeypatch.setattr(runtime_admission, "RuntimeAdmission", Admission)
    monkeypatch.setattr(cli, "require_offline", lambda: None)
    monkeypatch.setattr(
        cli,
        "load_dataset",
        lambda root, manifest, name: ([{}] * (192 if name == "domain" else 64), []),
    )
    checks = dict.fromkeys(
        (
            "mask",
            "updated_adapter",
            "frozen_base",
            "reload",
            "resume",
            "long_context",
            "tool_loop",
            "adapter_effect",
        ),
        True,
    )

    class Child:
        def __init__(self, command, **kwargs):
            request = json.loads(Path(command[-1]).read_text())
            events.append(request["stage"])
            assert kwargs["env"]["VENOM_GRANITE_ADMISSION_DB"] == str(
                tmp_path / "host.sqlite3"
            )
            write_json(
                Path(request["output"]) / "metrics.json",
                {"fingerprint": "identity", "checks": checks},
            )

        def wait(self, timeout):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(cli.subprocess, "Popen", Child)
    monkeypatch.setenv("GRANITE_DATA_ROOT", str(tmp_path))
    profile = tmp_path / "profile.json"
    write_json(profile, TrainingProfile().identity())
    manifest = tmp_path / "manifest.json"
    write_json(manifest, {})
    args = SimpleNamespace(
        profile=profile,
        manifest=manifest,
        data_root=tmp_path,
        output=tmp_path / "run",
        snapshot=tmp_path,
        worker_python=Path("/python"),
        admission_db=tmp_path / "host.sqlite3",
        command="smoke",
        qualification=None,
        updates=None,
        dataset=dataset,
        timeout=5,
    )
    cli.run(args)
    assert events == ["lease", "operation", "smoke-first", "smoke-resume", "release"]
    assert (
        json.loads((args.output / "qualification.json").read_text())["status"] == "PASS"
    )
    args.command = "train"
    args.qualification = args.output / "qualification.json"
    args.output = tmp_path / "train"
    cli.run(args)
    assert events[-4:] == ["operation", "train-first", "train-resume", "release"]
    assert (
        json.loads((args.output / "train-resume.request.json").read_text())["updates"]
        == expected_updates - 12
    )
    assert (
        json.loads((args.output / "locations.json").read_text())["dataset"] == dataset
    )


def test_cli_parser_and_failure_exit(tmp_path, monkeypatch):
    import sys

    arguments = [
        "granite",
        "smoke",
        "--data-root",
        str(tmp_path),
        "--snapshot",
        str(tmp_path),
        "--worker-python",
        "/python",
        "--admission-db",
        str(tmp_path / "host.db"),
        "--output",
        str(tmp_path / "run"),
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    captured = []
    monkeypatch.setattr(cli, "run", lambda args: captured.append(args))
    cli.main()
    assert captured[0].command == "smoke"
    assert captured[0].manifest == tmp_path / "pilot-manifest.json"
    assert captured[0].profile == Path("config/granite_operator_profile.json")
    monkeypatch.setattr(
        sys, "argv", arguments + ["--manifest", str(tmp_path / "custom.json")]
    )
    cli.main()
    assert captured[1].manifest == tmp_path / "custom.json"

    def failed(args):
        raise RuntimeError("expected_failure")

    monkeypatch.setattr(cli, "run", failed)
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 1


def test_worker_parser(tmp_path, monkeypatch):
    import sys

    request = tmp_path / "request.json"
    request.write_text('{"stage":"smoke-first"}')
    monkeypatch.setattr(sys, "argv", ["worker", str(request)])
    captured = []
    monkeypatch.setattr(worker, "run", captured.append)
    worker.main()
    assert captured == [{"stage": "smoke-first"}]


def test_report_distinguishes_training_speed_from_operator_accuracy(tmp_path):
    from scripts.granite_operator.report import percentile, summarize

    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([1, 2, 3, 4], 0.95) == pytest.approx(3.85)
    _case_value_4 = float("nan")
    with pytest.raises(ValueError):
        percentile([_case_value_4], 0.5)
    write_json(tmp_path / "status.json", {"status": "FAIL"})
    with pytest.raises(ValueError, match="did_not_pass"):
        summarize(tmp_path)
    write_json(tmp_path / "status.json", {"status": "PASS"})
    stage = {
        "stage": "train-first",
        "fingerprint": "x",
        "steps": [{"elapsed_seconds": 2}],
        "training_seconds": 2,
        "global_step": 1,
        "training_rows": 192,
        "validation_rows": 48,
        "initial_validation": {"assistant_nll": 2},
        "validation": {"assistant_nll": 1},
        "load_seconds": 3,
        "target_tokens": 100,
        "peak_allocated_bytes": 10,
        "peak_reserved_bytes": 20,
        "checks": {"frozen_base": True},
    }
    write_json(tmp_path / "train-first/metrics.json", stage)
    result = summarize(tmp_path)
    assert result["target_tokens_per_training_second"] == 50
    assert "not held-out" in result["limitation"]


@pytest.mark.parametrize("dataset", [None, "domain", "hf", "mixed"])
def test_final_checkpoint_verifier_reloads_and_checks_actual_loop(
    tmp_path, monkeypatch, dataset
):
    from scripts.granite_operator import verify_checkpoint
    from venom_core.services.granite_operator.contract import digest

    request, _, FakeSession = worker_context(tmp_path, monkeypatch)
    monkeypatch.setattr(engine, "require_owner", lambda: None)
    monkeypatch.setattr(engine, "Session", FakeSession)
    monkeypatch.setattr(FakeSession, "tokenizer", "tokenizer", raising=False)
    monkeypatch.setattr(
        engine, "environment_identity", lambda *args: {"identity": "test"}
    )
    monkeypatch.setattr(engine, "encoded_rows", lambda rows, *args: [ROW] * len(rows))
    original_loader = worker.load_dataset
    domain_rows = original_loader(None, None, "domain")
    original_loop = worker.tool_loop

    def operator_probe(session, row):
        assert row is domain_rows[0][0]
        return original_loop(session, row)

    monkeypatch.setattr(worker, "tool_loop", operator_probe)
    hf_rows = (domain_rows[0][:1], domain_rows[1][:2])
    monkeypatch.setattr(
        verify_checkpoint,
        "load_dataset",
        lambda root, manifest, name: domain_rows if name == "domain" else hf_rows,
    )
    evaluated = []
    original_evaluate = FakeSession.evaluate

    def evaluate(self, rows):
        evaluated.append(len(rows))
        return original_evaluate(self, rows)

    monkeypatch.setattr(FakeSession, "evaluate", evaluate)
    run = tmp_path / "complete-run"
    write_json(
        run / "locations.json",
        {
            "profile": request["profile"],
            "manifest": request["manifest"],
            "data_root": request["data_root"],
            "snapshot": request["snapshot"],
        },
    )
    if dataset is not None:
        location = json.loads((run / "locations.json").read_text())
        location["dataset"] = dataset
        write_json(run / "locations.json", location)
    stage = run / "train-resume"
    stage.mkdir()
    (stage / "checkpoint").mkdir()
    (stage / "checkpoint/adapter_model.safetensors").write_bytes(b"adapter")
    metrics = {
        "fingerprint": digest({"identity": "test"}),
        "global_step": 16,
        "validation": {"assistant_nll": 1},
    }
    write_json(stage / "metrics.json", metrics)
    verify_checkpoint.verify(run)
    receipt = json.loads((run / "checkpoint-verification.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["global_step"] == 16
    assert evaluated[-1] == (2 if dataset == "hf" else 10 if dataset == "mixed" else 8)
    monkeypatch.setattr(worker, "tool_loop", lambda *args: {"passed": False})
    with pytest.raises(RuntimeError, match="tool_loop_failed"):
        verify_checkpoint.verify(run)
    assert (
        json.loads((run / "checkpoint-verification.json").read_text())["status"]
        == "FAIL"
    )
    metrics["fingerprint"] = "stale"
    write_json(stage / "metrics.json", metrics)
    with pytest.raises(ValueError, match="fingerprint_changed"):
        verify_checkpoint.verify(run)


def test_final_verifier_refuses_incomplete_run_or_different_host_ledger(
    tmp_path, monkeypatch
):
    from scripts.granite_operator import verify_checkpoint

    monkeypatch.setattr(cli, "require_offline", lambda: None)
    write_json(tmp_path / "status.json", {"status": "FAIL"})
    _case_value_5 = Path("/python")
    with pytest.raises(ValueError, match="training_did_not_pass"):
        verify_checkpoint.coordinate(tmp_path, tmp_path / "ledger", _case_value_5)
    write_json(tmp_path / "status.json", {"status": "PASS"})
    write_json(
        tmp_path / "locations.json", {"admission_db": str(tmp_path / "actual-ledger")}
    )
    _case_value_6 = Path("/python")
    with pytest.raises(ValueError, match="same_host_ledger"):
        verify_checkpoint.coordinate(tmp_path, tmp_path / "other-ledger", _case_value_6)


def test_epoch_sampling_is_proportional_unique_and_independent_of_rng():
    from venom_core.services.granite_operator.sampling import FamilyEpochOrder

    families = ["large"] * 12 + ["small"] * 4
    sampler = FamilyEpochOrder(families, 17)
    rng = torch.get_rng_state().clone()
    first = [sampler.index(i) for i in range(16)]
    second = [sampler.index(i) for i in range(16, 32)]
    assert sorted(first) == sorted(second) == list(range(16))
    assert first != second
    assert [families[i] for i in first[:8]].count("small") == 2
    assert torch.equal(torch.get_rng_state(), rng)
    restarted = FamilyEpochOrder(families, 17)
    assert [restarted.index(i) for i in range(11, 32)] == (first + second)[11:]
    assert FamilyEpochOrder(families, 18)._epoch_order(0) != first
    for bad in (-1, True, 0.5):
        with pytest.raises(ValueError, match="position"):
            sampler.index(bad)
    for bad in ([], [""], [None]):
        with pytest.raises(ValueError, match="input"):
            FamilyEpochOrder(bad, 17)


def test_family_sampling_resume_preserves_optimizer_and_rejects_changed_rows(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    session = tiny_session(monkeypatch)
    session.profile = replace(session.profile, row_order="family_epoch_v1")
    rows = [ROW, {**ROW, "input_ids": [1, 3, 2, 4]}, ROW]
    families = ["a", "b", "a"]
    with pytest.raises(ValueError, match="families_required"):
        session.train(rows, 1)
    session.train(rows, 2, families=families)
    checkpoint = tmp_path / "ordered"
    session.save(checkpoint, ROW, "identity")
    restarted = tiny_session(monkeypatch)
    restarted.profile = session.profile
    restarted.model.load_state_dict(session.model.state_dict())
    assert restarted.restore(checkpoint, ROW, "identity")
    session.train(rows, 3, families=families)
    restarted.train(rows, 3, families=families)
    assert restarted.adapter_hash() == session.adapter_hash()
    assert restarted.target_tokens == session.target_tokens
    assert restarted.sampling_state == session.sampling_state
    with pytest.raises(ValueError, match="checkpoint_changed"):
        restarted.train(rows, 1, families=["a", "a", "b"])
    legacy = tiny_session(monkeypatch)
    legacy.model.load_state_dict(torch.load(checkpoint / "tiny.pt", weights_only=True))
    with pytest.raises(ValueError, match="policy_mismatch"):
        legacy.restore(checkpoint, ROW, "identity")


def test_row_order_profile_is_opt_in_and_preserves_legacy_identity():
    from dataclasses import replace

    legacy = TrainingProfile()
    assert "row_order" not in legacy.identity()
    assert replace(legacy, row_order="family_epoch_v1").identity()["row_order"]
    with pytest.raises(ValueError, match="row_order"):
        replace(legacy, row_order="unknown").validate()


def test_worker_passes_actual_family_order_for_opt_in_profile(tmp_path, monkeypatch):
    request, _, session_type = worker_context(tmp_path, monkeypatch)
    request["profile"]["row_order"] = "family_epoch_v1"
    train = [
        {"problem_group": str(i), "language": lang, "family": f"f{i % 3}"}
        for i in range(16)
        for lang in ("pl", "en")
    ]
    validation = train[:8]
    monkeypatch.setattr(worker, "load_dataset", lambda *args: (train, validation))
    original = session_type.train
    captured = []

    def training(self, rows, updates, *, families):
        captured.extend(families)
        return original(self, rows, updates)

    monkeypatch.setattr(session_type, "train", training)
    worker.run(request)
    assert captured == [row["family"] for row in train]
