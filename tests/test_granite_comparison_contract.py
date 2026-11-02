"""Evaluation oracles and paired aggregation, without CUDA or live providers."""

import json

import pytest

from scripts.granite_operator.comparison_support import (
    changed,
    load_frozen,
    oracle,
    percentile,
    snapshot,
    summarize,
)
from venom_core.services.granite_operator.contract import file_digest, snapshot_metadata


def case():
    return {
        "oracle": {
            "status": "success",
            "summary_regexes": ["actual-marker"],
            "observation_regexes": ["actual-marker"],
            "mutable_files": [],
        }
    }


def test_oracle_requires_observed_evidence_and_protected_files(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    before = snapshot(tmp_path)
    finish = {"status": "success", "summary": "actual-marker"}
    assert not oracle(case(), tmp_path, before, [], finish, [], None)["success"]
    ledger = [
        {
            "command": "cat result.txt",
            "result": {"stdout": "actual-marker", "stderr": "", "exit_code": 0},
        }
    ]
    assert oracle(case(), tmp_path, before, ledger, finish, [], None)["success"]
    (tmp_path / "config.json").write_text('{"changed": true}')
    result = oracle(case(), tmp_path, before, ledger, finish, [], None)
    assert result["scope_violations"] == ["config.json"]


def test_snapshot_does_not_follow_symlinks(tmp_path):
    outside = tmp_path.parent / "outside-marker.txt"
    outside.write_text("private")
    (tmp_path / "link").symlink_to(outside)
    state = snapshot(tmp_path)
    assert state["link"].startswith("symlink:")
    assert changed({}, state, ["link"]) == []


def test_oracle_checks_mutation_and_independent_verification(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"x": 1}')
    before = snapshot(tmp_path)
    path.write_text('{"x": 2}')
    rules = {
        "status": "success",
        "mutable_files": ["settings.json"],
        "json_files": [{"path": "settings.json", "value": {"x": 2}}],
        "verify_command": "pytest",
        "verify_exit": 0,
        "verify_regexes": ["passed"],
    }
    spec = {"oracle": rules}
    finish = {"status": "success", "summary": "done"}
    assert not oracle(spec, tmp_path, before, [], finish, [], None)["success"]
    good = {"stdout": "3 passed", "stderr": "", "exit_code": 0}
    assert oracle(spec, tmp_path, before, [], finish, [], good)["success"]
    path.write_text('{"x": 3}')
    assert not oracle(spec, tmp_path, before, [], finish, [], good)["success"]


def test_negative_and_no_tool_cases_are_not_successful_guesses(tmp_path):
    spec = {"oracle": {"status": "needs_input", "no_terminal": True}}
    result = oracle(
        spec, tmp_path, {}, [], {"status": "success", "summary": ""}, [], None
    )
    assert result["incorrect_success_status"]
    assert not oracle(
        spec,
        tmp_path,
        {},
        [{"command": "ls", "result": None}],
        {"status": "needs_input", "summary": ""},
        [],
        None,
    )["success"]
    assert oracle(
        spec, tmp_path, {}, [], {"status": "needs_input", "summary": "Which?"}, [], None
    )["success"]


def test_frozen_dataset_cannot_silently_change(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    cases = tmp_path / "cases.jsonl"
    cases.write_text(json.dumps({"id": "case-1", "fixture": "fixture"}) + "\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": "cases.jsonl",
                "case_count": 1,
                "files": {"cases.jsonl": file_digest(cases)},
            }
        )
    )
    assert len(load_frozen(manifest)[1]) == 1
    cases.write_text("{}")
    with pytest.raises(ValueError, match="dataset_changed"):
        load_frozen(manifest)


def test_aggregation_keeps_failed_and_timeout_latencies():
    rows = []
    for ident, family, base_ok, adapter_ok in [
        ("a", "read", False, True),
        ("b", "edit", True, False),
    ]:
        for arm, ok, seconds in [("base", base_ok, 2), ("adapter", adapter_ok, 8)]:
            rows.append(
                {
                    "case_id": ident,
                    "family": family,
                    "language": "pl",
                    "arm": arm,
                    "oracle": {
                        "success": ok,
                        "scope_violations": [],
                        "success_without_oracle_confirmation": False,
                        "incorrect_success_status": False,
                    },
                    "task_seconds": seconds,
                    "timed_out": not ok,
                    "generation_seconds": 1,
                    "tool_seconds": 1,
                    "generated_tokens": 10,
                }
            )
    result = summarize(rows, bootstrap_samples=100)
    assert result["base"]["trials"] == result["adapter"]["trials"] == 2
    assert result["adapter"]["task_p50_seconds"] == 8
    assert (
        result["paired"]["base_only_success"]
        == result["paired"]["adapter_only_success"]
        == 1
    )
    assert result["paired"]["success_gain_pp"] == 0
    assert not result["paired"]["proposed_promotion_gate_passed"]
    assert percentile([1, 2, 3, 4], 0.95) == pytest.approx(3.85)


def native_call(name, **arguments):
    content = "".join(
        f"<parameter={key}>{value}</parameter>" for key, value in arguments.items()
    )
    return f"<tool_call><function={name}>{content}</function></tool_call>"


def evaluation_context(tmp_path, monkeypatch, responses):
    from types import SimpleNamespace

    from scripts.granite_operator import comparison

    dataset = tmp_path / "dataset"
    fixture = dataset / "fixture"
    fixture.mkdir(parents=True)
    (fixture / "result.txt").write_text("actual-marker")
    output = tmp_path / "output"
    output.mkdir()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Terminal",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "Finish",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["status", "summary"],
                    "additionalProperties": False,
                },
            },
        },
    ]
    spec = {
        "id": "eval-1",
        "fixture": "fixture",
        "family": "read",
        "language": "en",
        "problem_group": "group-1",
        "tools": tools,
        "system": "operator",
        "prompt": "read result.txt",
        **case(),
    }
    calls = []

    class Container:
        def __init__(self, workspace, image, run_id, readonly=False):
            self.workspace = workspace
            calls.append(("open", readonly))

        def execute(self, command, timeout):
            calls.append(("execute", command))
            if command == "change":
                (self.workspace / "result.txt").write_text("changed")
            return {
                "stdout": "actual-marker",
                "stderr": "",
                "exit_code": 0,
                "seconds": 0.01,
                "execution_timed_out": False,
                "output_truncated": False,
            }

        def close(self):
            calls.append(("close",))

    iterator = iter(responses)

    def fake_generate(*args):
        if len(args[1]) > 2:
            observation = json.loads(args[1][-1]["content"])
            assert set(observation) == {"stdout", "stderr", "exit_code"}
        item = next(iterator)
        if isinstance(item, Exception):
            raise item
        return {"text": item, "seconds": 0.01, "tokens": 5, "input_tokens": 10}

    monkeypatch.setattr(comparison, "DockerTool", Container)
    monkeypatch.setattr(comparison, "generate", fake_generate)
    session = SimpleNamespace(
        torch=SimpleNamespace(
            cuda=SimpleNamespace(
                reset_peak_memory_stats=lambda: None,
                max_memory_allocated=lambda: 10,
                max_memory_reserved=lambda: 20,
            )
        )
    )
    return comparison, session, spec, dataset, output, calls


def test_actual_operator_loop_requires_terminal_observation_and_finish(
    tmp_path, monkeypatch
):
    responses = [
        native_call("Terminal", command="cat result.txt"),
        native_call("Finish", status="success", summary="actual-marker"),
    ]
    module, session, spec, dataset, output, calls = evaluation_context(
        tmp_path, monkeypatch, responses
    )
    row = module.run_case(session, spec, dataset, output, "image", "run", "adapter")
    assert row["oracle"]["success"]
    assert row["terminal_calls"] == 1
    assert row["generated_tokens"] == 10
    assert calls[-1] == ("close",)
    assert (output / row["workspace"] / "result.txt").read_text() == "actual-marker"


@pytest.mark.parametrize(
    "response,failure",
    [
        ("plain answer", "invalid_granite_envelope"),
        (TimeoutError("deadline"), "task_timeout"),
        (native_call("Terminal", wrong="missing-command"), "invalid_tool_or_arguments"),
    ],
)
def test_operator_failures_are_recorded_not_discarded(
    tmp_path, monkeypatch, response, failure
):
    module, session, spec, dataset, output, _ = evaluation_context(
        tmp_path, monkeypatch, [response]
    )
    row = module.run_case(session, spec, dataset, output, "image", "run", "base")
    assert row["failure"] == failure
    assert not row["oracle"]["success"]
    assert row["timed_out"] == (failure == "task_timeout")


def test_no_tool_task_does_not_execute_model_command(tmp_path, monkeypatch):
    module, session, spec, dataset, output, calls = evaluation_context(
        tmp_path, monkeypatch, [native_call("Terminal", command="echo actual-marker")]
    )
    spec["oracle"]["no_terminal"] = True
    row = module.run_case(session, spec, dataset, output, "image", "run", "base")
    assert row["failure"] == "unnecessary_tool"
    assert calls == []


def test_scope_violation_and_independent_verification_survive_model_finish(
    tmp_path, monkeypatch
):
    module, session, spec, dataset, output, calls = evaluation_context(
        tmp_path,
        monkeypatch,
        [
            native_call("Terminal", command="change"),
            native_call("Finish", status="success", summary="actual-marker"),
        ],
    )
    spec["oracle"].update(verify_command="verify", verify_exit=0)
    row = module.run_case(session, spec, dataset, output, "image", "run", "adapter")
    assert not row["oracle"]["success"]
    assert row["oracle"]["scope_violations"] == ["result.txt"]
    assert ("open", True) in calls
    first_close = calls.index(("close",))
    assert calls[first_close + 1] == ("open", True)


def test_comparison_cli_requires_concrete_paths(tmp_path, monkeypatch):
    import sys

    from scripts.granite_operator import comparison

    monkeypatch.setattr(sys, "argv", ["comparison"])
    with pytest.raises(SystemExit) as error:
        comparison.main()
    assert error.value.code == 2
    captured = []
    monkeypatch.setattr(comparison, "coordinate", captured.append)
    arguments = ["comparison"]
    for name in ("cases", "training-run", "output", "worker-python", "admission-db"):
        arguments.extend(["--" + name, str(tmp_path / name)])
    monkeypatch.setattr(sys, "argv", arguments)
    comparison.main()
    assert captured[0].output == tmp_path / "output"


@pytest.mark.parametrize(
    "code,elapsed,timed_out",
    [(0, 0.1, False), (124, 8, True), (137, 9, True), (137, 0.1, False)],
)
def test_tool_timeout_handles_forced_kill_and_distinguishes_early_kill(
    monkeypatch, code, elapsed, timed_out
):
    from types import SimpleNamespace

    from scripts.granite_operator import comparison_support as support

    tool = support.DockerTool.__new__(support.DockerTool)
    tool.closed = False
    tool.name = "fixture"
    monkeypatch.setattr(tool, "_sync", lambda: None)
    clock = {"now": 0.0}
    monkeypatch.setattr(support.time, "monotonic", lambda: clock["now"])

    def execute(*args, **kwargs):
        clock["now"] = elapsed
        return SimpleNamespace(returncode=code)

    monkeypatch.setattr(support.subprocess, "run", execute)
    monkeypatch.setattr(tool, "close", lambda: setattr(tool, "closed", True))
    result = tool.execute("fixture", timeout=8)
    assert result["execution_timed_out"] is timed_out
    assert result["execution_killed"] == (code == 137)
    assert tool.closed == (code in {124, 137})


@pytest.mark.parametrize(
    "timed_out,expected_failure", [(True, "tool_timeout"), (False, "tool_killed")]
)
def test_killed_tool_cannot_become_success(
    tmp_path, monkeypatch, timed_out, expected_failure
):
    responses = [
        native_call("Terminal", command="cat result.txt"),
        native_call("Finish", status="success", summary="actual-marker"),
    ]
    module, session, spec, dataset, output, calls = evaluation_context(
        tmp_path, monkeypatch, responses
    )
    original = module.DockerTool.execute

    def execute(self, *args):
        result = original(self, *args)
        result.update(
            exit_code=137, execution_timed_out=timed_out, execution_killed=True
        )
        return result

    monkeypatch.setattr(module.DockerTool, "execute", execute)
    row = module.run_case(session, spec, dataset, output, "image", "run", "adapter")
    assert row["failure"] == expected_failure
    assert not row["oracle"]["success"]
    assert row["timed_out"] is timed_out


@pytest.mark.parametrize("resumed", [False, True])
def test_comparison_uses_verified_final_stage_before_loading_model(
    tmp_path, monkeypatch, resumed
):
    from scripts.granite_operator import comparison
    from venom_core.services.granite_operator import engine
    from venom_core.services.granite_operator.contract import (
        TrainingProfile,
        write_json,
    )

    run = tmp_path / "training"
    snapshot_path = tmp_path / "snapshot"
    snapshot_path.mkdir()
    (snapshot_path / "config.json").write_text("{}")
    first = run / "train-first"
    first.mkdir(parents=True)
    stage = run / "train-resume" if resumed else first
    checkpoint = stage / "checkpoint"
    checkpoint.mkdir(parents=True)
    (checkpoint / "adapter_model.safetensors").write_bytes(b"fixture-adapter")
    write_json(checkpoint / "receipt.json", {"files": {}})
    write_json(
        run / "locations.json",
        {"snapshot": str(snapshot_path), "profile": TrainingProfile().identity()},
    )
    write_json(
        run / "checkpoint-verification.json",
        {
            "status": "PASS",
            "adapter_sha256": file_digest(checkpoint / "adapter_model.safetensors"),
        },
    )
    write_json(
        first / "identity.json",
        {
            "checkpoint_config": file_digest(snapshot_path / "config.json"),
            "snapshot_metadata": snapshot_metadata(snapshot_path),
            "weights": {},
        },
    )
    monkeypatch.setattr(engine, "require_owner", lambda: None)
    monkeypatch.setattr(
        comparison, "load_frozen", lambda _: ({"qualification": {"status": "PASS"}}, [])
    )

    def load_model(profile, snapshot, adapter):
        assert adapter == checkpoint
        raise RuntimeError("model_loading_boundary")

    monkeypatch.setattr(engine, "Session", load_model)
    _case_value_0 = str(tmp_path / "output")
    _case_value_1 = str(tmp_path / "cases.json")
    _case_value_2 = str(run)
    with pytest.raises(RuntimeError, match="model_loading_boundary"):
        comparison.worker(
            {
                "output": _case_value_0,
                "cases": _case_value_1,
                "training_run": _case_value_2,
            }
        )


def test_frozen_manifest_rejects_added_fixture_files_and_unlisted_cases(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    cases = tmp_path / "cases.jsonl"
    cases.write_text(json.dumps({"id": "one", "fixture": "fixture"}) + "\n")
    manifest = tmp_path / "manifest.json"
    value = {
        "cases": "cases.jsonl",
        "case_count": 1,
        "files": {"cases.jsonl": file_digest(cases)},
    }
    manifest.write_text(json.dumps(value))
    load_frozen(manifest)
    (fixture / "unlisted.txt").write_text("changed input")
    with pytest.raises(ValueError, match="inventory_changed"):
        load_frozen(manifest)
    (fixture / "unlisted.txt").unlink()
    value["files"] = {}
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="cases_not_in_manifest"):
        load_frozen(manifest)


def test_snapshot_checks_logical_size_before_hashing_sparse_file(tmp_path, monkeypatch):
    from scripts.granite_operator import comparison_support as support

    large = tmp_path / "sparse"
    with large.open("wb") as stream:
        stream.truncate(support.MAX_FILE_BYTES + 1)

    def forbidden_hash(_):
        raise AssertionError("must reject metadata before reading contents")

    monkeypatch.setattr(support, "file_digest", forbidden_hash)
    with pytest.raises(support.WorkspaceLimitError, match="workspace_bytes"):
        support.snapshot(tmp_path)


def test_bounded_export_preserves_deletion_and_rejects_links_and_path_escape(tmp_path):
    import io
    import tarfile

    from scripts.granite_operator.comparison_support import (
        WorkspaceLimitError,
        restore_workspace,
    )

    workspace = tmp_path / "work"
    workspace.mkdir()
    (workspace / "removed").write_text("old")

    def make_archive(name, kind=None):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as output:
            member = tarfile.TarInfo(name)
            if kind:
                member.type = kind
                member.linkname = "../../outside"
                output.addfile(member)
            else:
                member.size = 3
                output.addfile(member, io.BytesIO(b"new"))
        return archive

    archive = make_archive("new.txt")
    restore_workspace(archive, workspace)
    assert not (workspace / "removed").exists()
    assert (workspace / "new.txt").read_text() == "new"
    for archive in (make_archive("../escape"), make_archive("link", tarfile.SYMTYPE)):
        with pytest.raises(WorkspaceLimitError, match="unsafe_archive"):
            restore_workspace(archive, workspace)
        assert (workspace / "new.txt").read_text() == "new"


def test_comparison_rejects_changed_tokenizer_before_model_loading(
    tmp_path, monkeypatch
):
    from scripts.granite_operator import comparison
    from venom_core.services.granite_operator import engine
    from venom_core.services.granite_operator.contract import (
        TrainingProfile,
        write_json,
    )

    run = tmp_path / "run"
    stage = run / "train-first"
    checkpoint = stage / "checkpoint"
    checkpoint.mkdir(parents=True)
    snapshot_path = tmp_path / "snapshot"
    snapshot_path.mkdir()
    (snapshot_path / "config.json").write_text("{}")
    old_metadata = snapshot_metadata(snapshot_path)
    (snapshot_path / "tokenizer.json").write_text("{}")
    (checkpoint / "adapter_model.safetensors").write_bytes(b"a")
    write_json(checkpoint / "receipt.json", {"files": {}})
    write_json(
        run / "locations.json",
        {"snapshot": str(snapshot_path), "profile": TrainingProfile().identity()},
    )
    write_json(
        run / "checkpoint-verification.json",
        {
            "status": "PASS",
            "adapter_sha256": file_digest(checkpoint / "adapter_model.safetensors"),
        },
    )
    write_json(stage / "identity.json", {"snapshot_metadata": old_metadata})
    monkeypatch.setattr(engine, "require_owner", lambda: None)
    monkeypatch.setattr(comparison, "load_frozen", lambda _: ({}, []))
    _case_value_0 = str(tmp_path / "out")
    _case_value_1 = str(tmp_path / "cases")
    _case_value_2 = str(run)
    with pytest.raises(ValueError, match="metadata_changed"):
        comparison.worker(
            {
                "output": _case_value_0,
                "cases": _case_value_1,
                "training_run": _case_value_2,
            }
        )


@pytest.mark.parametrize("error_type", [None, TimeoutError, ValueError])
def test_queue_wait_is_excluded_from_active_task_budget(
    tmp_path, monkeypatch, error_type
):
    responses = [
        native_call("Terminal", command="cat result.txt"),
        native_call("Finish", status="success", summary="actual-marker"),
    ]
    module, session, spec, dataset, output, _ = evaluation_context(
        tmp_path, monkeypatch, responses
    )
    from types import SimpleNamespace

    clock = {"now": 0.0}
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    original = module.generate

    def queued(*args):
        clock["now"] += 4
        if error_type:
            error = error_type(
                "comparison_task_deadline"
                if error_type is TimeoutError
                else "comparison_context_limit"
            )
            error.queue_seconds = 3.0
            raise error
        return {**original(*args), "queue_seconds": 3.0}

    row = module.run_case(
        session,
        spec,
        dataset,
        output,
        "image",
        "run",
        "base",
        generator=queued,
        task_timeout_seconds=5,
    )
    assert row["queue_seconds"] == (3 if error_type else 6)
    assert row["active_task_seconds"] == (1 if error_type else 2)
    assert row["task_seconds"] == (4 if error_type else 8)
    assert row["oracle"]["success"] == (error_type is None)


@pytest.mark.parametrize(
    "kind",
    [
        "clarified",
        "early_finish",
        "wrong_argument",
        "bad_quote",
        "direct",
        "still_missing",
    ],
)
def test_dialogue_must_complete_with_correct_syntax_after_user_input(
    tmp_path, monkeypatch, kind
):
    module, session, spec, dataset, output, _ = evaluation_context(
        tmp_path, monkeypatch, []
    )
    command = (
        "python report.py --source 'input files.json' --destination 'out files.json'"
    )
    spec["oracle"] = {
        "status": "success",
        "mutable_files": [],
        "no_terminal": True,
        "syntax_command_argv": [
            "python",
            "report.py",
            "--source",
            "input files.json",
            "--destination",
            "out files.json",
        ],
        "expected_clarifications": 0 if kind == "direct" else 1,
    }
    spec["followups"] = [] if kind == "direct" else ["Destination is out files.json."]
    outputs = []
    if kind not in ("direct", "early_finish"):
        outputs.append(
            native_call("Finish", status="needs_input", summary="Which destination?")
        )
    if kind == "wrong_argument":
        command = command.replace("out files", "invented")
    if kind == "bad_quote":
        command += "'"
    outputs.append(
        native_call(
            "Finish",
            status="needs_input" if kind == "still_missing" else "success",
            summary=command,
        )
    )
    iterator = iter(outputs)
    seen = []

    def generate(_session, messages, *args):
        seen.append(messages[-1].copy())
        return {
            "text": next(iterator),
            "seconds": 0.01,
            "tokens": 5,
            "input_tokens": 10,
        }

    row = module.run_case(
        session, spec, dataset, output, "image", "run", "adapter", generator=generate
    )
    assert row["oracle"]["success"] == (kind in ("clarified", "direct"))
    if kind not in ("early_finish", "direct"):
        assert seen[1] == {"role": "user", "content": spec["followups"][0]}
        assert len(row["intermediate_finishes"]) == 1


def test_invalid_followup_contract_closes_task_container(tmp_path, monkeypatch):
    module, session, spec, dataset, output, calls = evaluation_context(
        tmp_path, monkeypatch, []
    )
    spec["followups"] = [""]
    with pytest.raises(ValueError, match="followups_invalid"):
        module.run_case(session, spec, dataset, output, "image", "run", "adapter")
    assert calls[-1] == ("close",)


@pytest.mark.parametrize(
    "kind",
    ["valid", "changed", "training", "unsupported", "bad_inventory", "extra_fixture"],
)
def test_dialogue_freeze_publishes_only_complete_verified_cases(tmp_path, kind):
    from scripts.granite_operator.dialogue_cases import freeze

    material = tmp_path / "material"
    material.mkdir()
    fixture = material / "holdout/fixtures/cli"
    fixture.mkdir(parents=True)
    (fixture / "help.txt").write_text("local parser")
    row = {
        "record_id": "cli-pl",
        "tools": [
            {
                "type": "function",
                "function": {"name": "Finish", "parameters": {"type": "object"}},
            }
        ],
        "fixture_id": "cli",
        "problem_group": "heldout-cli",
        "family": "cli_clarify_complete",
        "language": "pl",
        "training_allowed": False,
        "split": "holdout",
        "messages": [
            {"role": "system", "content": "operator"},
            {"role": "user", "content": "Destination missing."},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "Destination is out.json."},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "arguments": {
                                "status": "success",
                                "summary": "python tool.py --destination out.json",
                            }
                        }
                    }
                ],
            },
        ],
    }
    if kind == "training":
        row["training_allowed"] = True
    if kind == "unsupported":
        row["family"] = "unknown"
    (material / "holdout/conversations.jsonl").write_text(json.dumps(row) + "\n")
    (material / "holdout/execution-receipts.jsonl").write_text(
        json.dumps(
            {"fixture_id": "cli", "mutable_files": [], "oracle": {"passed": True}}
        )
        + "\n"
    )
    (material / "checks").mkdir()
    (material / "checks/material-audit.json").write_text(
        json.dumps({"status": "PASS_DATA_AUDIT_ONLY"})
    )
    (material / "pilot-manifest.json").write_text(
        json.dumps({"image": "sha256:" + "a" * 64})
    )
    inventory = {
        str(p.relative_to(material)): {"sha256": file_digest(p)}
        for p in material.rglob("*")
        if p.is_file()
    }
    if kind == "bad_inventory":
        inventory.pop("pilot-manifest.json")
    (material / "FROZEN_FILES.json").write_text(json.dumps({"files": inventory}))
    if kind == "changed":
        (fixture / "help.txt").write_text("tampered")
    if kind == "extra_fixture":
        (fixture / "unaudited.txt").write_text("added after audit")
    output = tmp_path / "benchmark"
    if kind != "valid":
        with pytest.raises(ValueError):
            freeze(material, output)
        assert not output.exists()
    else:
        report = freeze(material, output)
        assert report["case_count"] == 1
        _, cases = load_frozen(output / "manifest.json")
        assert cases[0]["followups"] == ["Destination is out.json."]
        assert cases[0]["oracle"]["expected_clarifications"] == 1
        assert freeze(material, output)["status"] == "REFERENCE_DATA_FROZEN"
        assert (fixture / "help.txt").read_text() == "local parser"


@pytest.mark.parametrize(
    "text,valid",
    [
        ("python tool.py --source in.json --destination out.json", True),
        ("python3 ./tool.py --destination=out.json --source=in.json", True),
        ("python tool.py --source out.json --destination in.json", False),
        (
            "python tool.py --source in.json --source in.json --destination out.json",
            False,
        ),
        ("python tool.py --source in.json --destination", False),
        ("python tool.py --source in.json --destination out.json extra", False),
    ],
)
def test_syntax_oracle_checks_bindings_without_requiring_one_option_order(text, valid):
    from scripts.granite_operator.comparison_support import command_syntax_matches

    assert (
        command_syntax_matches(
            text,
            ["python", "tool.py", "--source", "in.json", "--destination", "out.json"],
        )
        == valid
    )
    assert command_syntax_matches("git status", ["git", "status"])


@pytest.mark.parametrize("readonly", [False, True])
def test_git_trust_is_limited_to_isolated_readonly_verifier(
    tmp_path, monkeypatch, readonly
):
    from types import SimpleNamespace

    from scripts.granite_operator import comparison_support as support

    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(support.subprocess, "run", run)
    support.DockerTool(tmp_path, "sha256:" + "a" * 64, "b" * 32, readonly=readonly)
    command = calls[0]
    environment = [command[i + 1] for i, item in enumerate(command) if item == "--env"]
    git_settings = [item for item in environment if item.startswith("GIT_CONFIG_")]
    if readonly:
        assert git_settings == [
            "GIT_CONFIG_COUNT=1",
            "GIT_CONFIG_KEY_0=safe.directory",
            "GIT_CONFIG_VALUE_0=/workspace",
        ]
    else:
        assert git_settings == []
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--user") + 1] == "1000:1001"
    assert command[command.index("--mount") + 1].endswith(",readonly")
