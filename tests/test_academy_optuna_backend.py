"""The Optuna journal preserves assignments and judgments across interruptions."""

import io
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing, redirect_stdout
from types import SimpleNamespace

import pytest

from venom_core.services.training_experiments import optuna_backend as backend

PLAN = {
    "plan_sha256": "a" * 64,
    "sampler_seed": 17,
    "search_space": {
        "rank": {"low": 2, "high": 32},
        "alpha": {"low": 4, "high": 64, "log": True},
        "learning_rate": {"low": 1e-6, "high": 1e-3},
        "dropout": {"low": 0.0, "high": 0.3},
    },
}


def test_search_space_canonicalizes_distributions():
    space = backend.validate_search_space(PLAN["search_space"])
    assert space["learning_rate"]["log"] is True
    assert space["dropout"]["log"] is False
    assert space["alpha"]["log"] is True
    assert list(space) == ["alpha", "dropout", "learning_rate", "rank"]
    assert isinstance(space["rank"]["low"], int)


@pytest.mark.parametrize(
    "space",
    [
        {},
        {"steps": {"low": 1, "high": 10}},
        {"rank": {"low": 1.5, "high": 32}},
        {"rank": {"low": True, "high": 32}},
        {"rank": {"low": 2, "high": 128}},
        {"rank": {"low": 8, "high": 8}},
        {"learning_rate": {"low": float("nan"), "high": 0.01}},
        {"learning_rate": {"low": 0, "high": 0.01}},
        {"dropout": {"low": 0, "high": 0.5, "log": True}},
    ],
)
def test_search_space_rejects_unbounded_or_unsupported_values(space):
    with pytest.raises(ValueError, match="campaign_"):
        backend.validate_search_space(space)


def test_no_optional_interpreter_has_controlled_failure(monkeypatch):
    monkeypatch.delenv(backend.OPTUNA_PYTHON, raising=False)
    with pytest.raises(ValueError, match="campaign_optuna_unavailable"):
        backend.require_optuna()


def test_trial_recovery_reuses_assignment_and_outcome(tmp_path, monkeypatch):
    candidate = {"rank": 8, "alpha": 16, "dropout": 0.1, "learning_rate": 0.001}
    calls = []

    def sample(_optuna, _contract, history, index):
        calls.append((len(history), index))
        return candidate

    monkeypatch.setattr(backend, "_sample", sample)
    contract = backend._contract(PLAN)
    with backend._transaction(tmp_path, contract) as db:
        first = backend._ask(db, None, contract, 0)
    # The planner committed just before the campaign saved the assignment.
    with backend._transaction(tmp_path, contract) as db:
        assert backend._ask(db, None, contract, 0) == first
    assert calls == [(0, 0)]
    with (
        pytest.raises(ValueError, match="campaign_optuna_trial_pending"),
        backend._transaction(tmp_path, contract) as db,
    ):
        backend._ask(db, None, contract, 1)

    judgment = {
        "trial_number": 0,
        "outcome": "COMPLETE",
        "value": 0.25,
        "constraints": [0.1, -0.25],
    }
    with backend._transaction(tmp_path, contract) as db:
        backend._tell(db, judgment)
    # The campaign can retry its update after the planner committed the result.
    with backend._transaction(tmp_path, contract) as db:
        backend._tell(db, judgment)
        assert backend._ask(db, None, contract, 0) == first
    with (
        pytest.raises(ValueError, match="campaign_optuna_result_conflict"),
        backend._transaction(tmp_path, contract) as db,
    ):
        backend._tell(db, {**judgment, "value": 0.5})
    with (
        pytest.raises(ValueError, match="campaign_optuna_plan_changed"),
        backend._transaction(tmp_path, {**contract, "sampler_seed": 18}),
    ):
        pass

    with backend._transaction(tmp_path, contract) as db:
        backend._ask(db, None, contract, 1)
        backend._tell(db, {"trial_number": 1, "outcome": "FAIL"})
        failed = db.execute(
            "SELECT outcome, value FROM trial WHERE number = 1"
        ).fetchone()
    assert failed == ("FAIL", None)


def test_read_assignment_does_not_create_a_journal_or_require_optuna(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(backend.OPTUNA_PYTHON, raising=False)
    assert backend.assigned(tmp_path, PLAN, 0) is None
    assert not list(tmp_path.iterdir())
    contract = backend._contract(PLAN)
    monkeypatch.setattr(backend, "_sample", lambda *_: {"rank": 8})
    with backend._transaction(tmp_path, contract) as db:
        expected = backend._ask(db, None, contract, 0)
    assert backend.assigned(tmp_path, PLAN, 0) == expected
    assert backend.assigned(tmp_path, PLAN, 1) is None
    with pytest.raises(ValueError, match="campaign_optuna_plan_changed"):
        backend.assigned(tmp_path, {**PLAN, "sampler_seed": 18}, 0)


def test_failed_or_missing_results_are_not_scored(tmp_path):
    contract = backend._contract(PLAN)
    with (
        pytest.raises(ValueError, match="campaign_optuna_trial_missing"),
        backend._transaction(tmp_path, contract) as db,
    ):
        backend._tell(db, {"trial_number": 0, "outcome": "FAIL"})
    for request in (
        {"outcome": "FAIL", "value": 0.0},
        {"outcome": "COMPLETE", "value": None},
        {"outcome": "COMPLETE", "value": float("inf")},
        {"outcome": "COMPLETE", "value": 0.5, "constraints": [0]},
    ):
        with (
            pytest.raises(ValueError, match="campaign_optuna_result_invalid"),
            backend._transaction(tmp_path, contract) as db,
        ):
            backend._tell(db, {"trial_number": 0, **request})


def test_client_and_tool_exchange_versioned_requests_without_optional_packages(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(backend.OPTUNA_PYTHON, sys.executable)
    versions = {"optuna": backend.OPTUNA_VERSION, "numpy": backend.NUMPY_VERSION}
    monkeypatch.setattr(backend, "version", versions.__getitem__)
    module = SimpleNamespace(
        logging=SimpleNamespace(WARNING=30, set_verbosity=lambda _level: None)
    )
    monkeypatch.setattr(backend, "import_module", lambda _name: module)
    candidate = {"rank": 8, "alpha": 16, "dropout": 0.1, "learning_rate": 0.001}
    monkeypatch.setattr(backend, "_sample", lambda *_args: candidate)

    def run_tool(args, *, cwd, input, encoding, capture_output, timeout, check):
        assert args == [sys.executable, "-I", backend.__file__]
        assert encoding == "utf-8" and capture_output and timeout == 30 and not check
        request = json.loads(input)
        assert "directory" not in request
        assert cwd == (None if request["operation"] == "probe" else tmp_path)
        stdout = io.StringIO()
        with monkeypatch.context() as tool, redirect_stdout(stdout):
            if cwd is not None:
                tool.chdir(cwd)
            tool.setattr(sys, "stdin", io.StringIO(input))
            status = backend._main()
        return subprocess.CompletedProcess(args, status, stdout.getvalue())

    monkeypatch.setattr(backend.subprocess, "run", run_tool)
    backend._probe.cache_clear()
    try:
        assert backend.require_optuna() == backend.OPTUNA_VERSION
        assert backend.ask(tmp_path, PLAN, 0) == {
            "trial_number": 0,
            "params": candidate,
        }
        backend.tell(tmp_path, PLAN, 0, "COMPLETE", 0.25, [0.1, -0.25])
        with pytest.raises(ValueError, match="campaign_optuna_result_conflict"):
            backend.tell(tmp_path, PLAN, 0, "COMPLETE", 0.5)
        # Every actual operation rechecks the interpreter's package versions.
        versions["optuna"] = "4.0.0"
        with pytest.raises(ValueError, match="campaign_optuna_version_mismatch"):
            backend.ask(tmp_path, PLAN, 1)
    finally:
        backend._probe.cache_clear()


def test_tool_payload_cannot_select_journal_path(tmp_path, monkeypatch):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    monkeypatch.chdir(campaign)
    with pytest.raises(ValueError, match="campaign_optuna_request_invalid"):
        backend._tool_request(
            {
                "operation": "ask",
                "directory": str(tmp_path),
                "contract": backend._contract(PLAN),
                "trial_number": 0,
            }
        )
    assert not (tmp_path / "optuna.sqlite3").exists()
    assert not (campaign / "optuna.sqlite3").exists()


@pytest.mark.parametrize("output", ["not JSON", json.dumps(["wrong", "shape"])])
def test_client_rejects_invalid_tool_output(monkeypatch, output):
    monkeypatch.setattr(
        backend.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, output),
    )
    with pytest.raises(ValueError, match="campaign_optuna_"):
        backend._invoke(sys.executable, {"operation": "probe"})


def test_optional_real_optuna_reproduces_tpe_sequence_after_restart(tmp_path):
    if not os.getenv(backend.OPTUNA_PYTHON):
        pytest.skip("Set VENOM_OPTUNA_PYTHON to test the optional pinned CPU runtime")
    assert backend.require_optuna() == backend.OPTUNA_VERSION

    def execute(directory, *, replay):
        directory.mkdir()
        assignments = []
        for index, result in enumerate(
            [
                ("COMPLETE", 0.1, [-0.2, -0.1]),
                ("FAIL", None, None),
                ("COMPLETE", 0.3, [0.1, -0.3]),
                ("COMPLETE", 0.2, [-0.1, -0.2]),
            ]
        ):
            assignment = backend.ask(directory, PLAN, index)
            assert assignment["trial_number"] == index
            if replay:
                assert backend.ask(directory, PLAN, index) == assignment
            backend.tell(directory, PLAN, index, *result)
            if replay:
                backend.tell(directory, PLAN, index, *result)
            assignments.append(assignment)
        return assignments

    left, right = tmp_path / "left", tmp_path / "right"
    assert execute(left, replay=True) == execute(right, replay=False)
    with closing(sqlite3.connect(left / "optuna.sqlite3")) as db:
        assert db.execute("SELECT COUNT(*) FROM trial").fetchone() == (4,)
        assert db.execute(
            "SELECT value FROM trial WHERE outcome = 'FAIL'"
        ).fetchone() == (None,)
