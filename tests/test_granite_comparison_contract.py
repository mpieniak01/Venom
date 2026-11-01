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
from venom_core.services.granite_operator.contract import file_digest


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
    assert row["terminal_calls"] == 1 and row["generated_tokens"] == 10
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
