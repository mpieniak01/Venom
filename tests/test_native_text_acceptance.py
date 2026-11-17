from datetime import datetime, timedelta, timezone

import pytest

from scripts.academy import native_text_acceptance as acceptance
from scripts.academy.native_text_acceptance import run_acceptance


def proof(main):
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "owners": {
            name: {
                "pid": index + 1,
                "cwd": str(main / "web-next" if name == "web" else main),
            }
            for index, name in enumerate(("api", "web", "supervisor"))
        },
        "http_statuses": [200] * 9,
        "supervisor_active": True,
        "test_ports_closed": True,
        "leases": 0,
        "operations": 0,
        "active_experiments": [],
        "gpu_available": True,
        "ollama_models": [],
    }


def steps(main, events, failure=None, override=None):
    def action(name):
        def call():
            events.append(name)
            if failure == name:
                raise RuntimeError(name)
            if name == "verify_restore":
                value = proof(main)
                if override:
                    override(value)
                return value
            return {"observed": name}

        return call

    return {
        name: action(name)
        for name in (
            "preflight",
            "stop_main",
            "start_test",
            "accept",
            "stop_test",
            "restore_main",
            "verify_restore",
        )
    }


def test_success_has_new_complete_receipts(tmp_path):
    events = []
    result = run_acceptance(tmp_path / "new", tmp_path, steps(tmp_path, events))
    assert result["status"] == "passed"
    assert len(events) == len(result["phases"]) == 7
    assert (tmp_path / "new/verify_restore.json").exists()
    actions = steps(tmp_path, [])
    with pytest.raises(FileExistsError):
        run_acceptance(tmp_path / "new", tmp_path, actions)


@pytest.mark.parametrize(
    "failure",
    [
        "stop_main",
        "start_test",
        "accept",
        "stop_test",
        "restore_main",
        "verify_restore",
    ],
)
def test_cleanup_failure_cannot_suppress_main_restore_or_fresh_probe(tmp_path, failure):
    events = []
    result = run_acceptance(
        tmp_path / "attempt", tmp_path, steps(tmp_path, events, failure)
    )
    assert result["status"] == "failed"
    assert events[-3:] == ["stop_test", "restore_main", "verify_restore"]
    assert result["errors"][0]["phase"] == failure


def test_preflight_failure_does_not_take_host(tmp_path):
    events = []
    result = run_acceptance(
        tmp_path / "attempt", tmp_path, steps(tmp_path, events, "preflight")
    )
    assert result["status"] == "failed"
    assert events == ["preflight"]


@pytest.mark.parametrize(
    "override",
    [
        lambda value: value.update(
            checked_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        ),
        lambda value: value.update(http_statuses=[200] * 8),
        lambda value: value.update(http_statuses=[200] * 8 + [503]),
        lambda value: value["owners"]["api"].update(cwd="/tmp/other"),
        lambda value: value["owners"]["web"].update(pid=0),
        lambda value: value.update(owners={}),
        lambda value: value.update(supervisor_active=False),
        lambda value: value.update(test_ports_closed=False),
        lambda value: value.update(leases=1),
        lambda value: value.update(operations=1),
        lambda value: value.update(gpu_available=False),
        lambda value: value.update(ollama_models=["busy"]),
        lambda value: value.update(active_experiments=["running"]),
    ],
)
def test_generation_success_never_masks_stale_or_incomplete_restore(tmp_path, override):
    events = []
    result = run_acceptance(
        tmp_path / "attempt", tmp_path, steps(tmp_path, events, override=override)
    )
    assert result["status"] == "failed"
    assert result["phases"][3]["status"] == "passed"
    assert result["errors"][0]["phase"] == "verify_restore"


def test_incomplete_plan_does_not_create_attempt(tmp_path):
    with pytest.raises(ValueError, match="steps_incomplete"):
        run_acceptance(tmp_path / "attempt", tmp_path, {})
    assert not (tmp_path / "attempt").exists()


def test_missing_fresh_restore_proof_is_failed(tmp_path):
    actions = steps(tmp_path, [])
    actions["verify_restore"] = lambda: None
    result = run_acceptance(tmp_path / "attempt", tmp_path, actions)
    assert result["status"] == "failed"
    assert result["errors"][0]["reason"] == "native_acceptance_restore_proof_missing"


@pytest.mark.parametrize(
    "failure", ["stop_main.json", "stop_test.json", "lifecycle.json"]
)
def test_write_failure_cannot_suppress_restore_and_fresh_probe(
    tmp_path, monkeypatch, failure
):
    events = []
    original = acceptance.atomic_json

    def failing_write(path, value):
        if path.name == failure:
            raise OSError("fixture disk full")
        original(path, value)

    monkeypatch.setattr(acceptance, "atomic_json", failing_write)
    result = run_acceptance(tmp_path / "attempt", tmp_path, steps(tmp_path, events))
    assert result["status"] == "failed"
    if failure != "lifecycle.json":
        assert events[-3:] == ["stop_test", "restore_main", "verify_restore"]
    assert any(error.get("operation") == "write" for error in result["errors"])


def test_final_write_failure_never_returns_pass(tmp_path, monkeypatch):
    original = acceptance.atomic_json

    def fail_final(path, value):
        if path.name == "lifecycle.json" and value.get("status") == "passed":
            raise OSError("fixture final write failure")
        original(path, value)

    monkeypatch.setattr(acceptance, "atomic_json", fail_final)
    result = run_acceptance(tmp_path / "attempt", tmp_path, steps(tmp_path, []))
    assert result["status"] == "failed"
    assert result["errors"][-1]["phase"] == "lifecycle"
