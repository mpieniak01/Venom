"""No-provider progress reads and reconnecting CLI viewer contracts."""

import json
from types import SimpleNamespace

import pytest

from venom_core.services.remote_training import cli, progress
from venom_core.services.remote_training.lifecycle import JobStore, atomic_json
from venom_core.services.remote_training.remote import dispatch
from venom_core.services.remote_training.transport import TransportError


@pytest.fixture
def run(tmp_path):
    store = JobStore(tmp_path / "remote")
    manifest = {"run_id": "run1", "identity": {"limits": {"max_updates": 100}}}
    state = store.prepare(manifest)
    return store, state


def log_for(store, state, text):
    state.update(
        stage="train",
        status="failed",
        attempt=1,
        attempt_root="runs/run1/attempts/0001",
    )
    attempt = store.root / state["attempt_root"]
    attempt.mkdir(parents=True, exist_ok=True)
    (attempt / "worker.log").write_text(text)
    return attempt


def event(step=12, **extra):
    return (
        json.dumps(
            {
                "step": step,
                "loss": 0.4,
                "gradient_norm": 0.6,
                "elapsed_seconds": 10,
                "target_tokens": 900,
                **extra,
            }
        )
        + "\n"
    )


def test_prepared_and_loading_have_no_invented_percentage(run):
    store, state = run
    assert progress.observe(store, "run1", state)["percent"] is None
    attempt = log_for(store, state, "")
    (attempt / "worker.log").unlink()
    assert progress.observe(store, "run1", state)["percent"] is None
    (attempt / "worker.log").write_text(
        '{"event":"remote_training_stage","phase":"loading"}\n'
    )
    state["status"] = "running"
    assert progress.observe(store, "run1", state)["phase"] == "loading"


def test_status_reads_current_attempt_and_native_updates(run):
    store, state = run
    log_for(
        store,
        state,
        "not-json\n[]\n"
        + event()
        + '{"event":"remote_training_stage","phase":"finalizing"}\n',
    )
    # Mark terminal to avoid requiring a real supervisor process.
    atomic_json(store.directory("run1") / "state.json", state)
    result = dispatch(store, "status", {"run_id": "run1"})
    assert result["progress"]["completed_updates"] == 12
    assert result["progress"]["percent"] == 12
    assert result["progress"]["phase"] == "failed"
    assert result["progress"]["loss"] == 0.4
    assert result["progress"]["last_log_age_seconds"] >= 0
    assert "error=test_failure" in progress.format_status(
        {**result, "error": "test_failure"}
    )
    state.update(attempt=2, attempt_root="runs/run1/attempts/0002")
    (store.root / state["attempt_root"]).mkdir()
    assert progress.observe(store, "run1", state)["completed_updates"] is None


def test_smoke_denominator_and_finalizing_are_separate_from_success(run):
    store, state = run
    log_for(
        store,
        state,
        event(20) + '{"event":"remote_training_stage","phase":"finalizing"}\n',
    )
    state.update(stage="smoke", status="running")
    report = progress.observe(store, "run1", state)
    assert report["total_updates"] == 20
    assert report["percent"] == 100
    assert report["phase"] == "finalizing"
    assert "running" in progress.format_status({**state, "progress": report})


@pytest.mark.parametrize(
    "text",
    [
        event(-1),
        event(101),
        event(True),
        event(loss=float("nan")),
        event(gradient_norm=-1),
        event(loss=10**500),
        '{"step":1}\n',
        '{"event":"remote_training_stage","phase":"made-up"}\n',
        event()[:-4],
    ],
)
def test_invalid_or_partial_events_do_not_claim_progress(run, text):
    store, state = run
    log_for(store, state, text)
    assert progress.observe(store, "run1", state)["completed_updates"] is None


def test_log_symlink_rejected_and_large_log_bounded(run, tmp_path):
    store, state = run
    attempt = log_for(store, state, "x" * (progress.LOG_LIMIT + 10) + "\n" + event(88))
    assert progress.observe(store, "run1", state)["percent"] == 88
    path = attempt / "worker.log"
    path.unlink()
    path.symlink_to(tmp_path / "private")
    with pytest.raises(ValueError, match="log_symlink"):
        progress.observe(store, "run1", state)


def fake_client(values):
    values = iter(values)

    def status(_run_id):
        value = next(values)
        if isinstance(value, BaseException):
            raise value
        return value

    return SimpleNamespace(status=status)


def test_watch_recovers_connection_and_reports_terminal(monkeypatch):
    monkeypatch.setattr(progress.time, "sleep", lambda _: None)
    client = fake_client(
        [
            TransportError("offline", retryable=True),
            {"status": "running"},
            {"status": "succeeded"},
        ]
    )
    lines = []
    result = progress.watch(
        client,
        "run1",
        interval=1,
        max_seconds=60,
        json_lines=True,
        emit=lambda line, **_: lines.append(json.loads(line)),
    )
    assert result == {"watch": "finished", "status": "succeeded"}
    assert [line["connection"] for line in lines] == [
        "unavailable",
        "connected",
        "connected",
    ]


@pytest.mark.parametrize("retryable,count", [(True, 3), (False, 1)])
def test_watch_connection_failure_never_stops_training(monkeypatch, retryable, count):
    monkeypatch.setattr(progress.time, "sleep", lambda _: None)
    client = fake_client([TransportError("offline", retryable=retryable)] * count)
    result = progress.watch(
        client, "run1", interval=1, max_seconds=60, emit=lambda *a, **kw: None
    )
    assert result == {"watch": "disconnected", "training_stopped": False}


def test_watch_time_limit_and_interrupt_do_not_stop(monkeypatch):
    clock = iter([0, 2])
    monkeypatch.setattr(progress.time, "monotonic", lambda: next(clock))
    assert (
        progress.watch(
            fake_client([{"status": "running"}]),
            "run1",
            interval=1,
            max_seconds=1,
            emit=lambda *a, **kw: None,
        )["watch"]
        == "time_limit"
    )
    monkeypatch.setattr(progress.time, "monotonic", lambda: 0)
    assert (
        progress.watch(
            fake_client([KeyboardInterrupt()]), "run1", interval=1, max_seconds=1
        )["watch"]
        == "interrupted"
    )


@pytest.mark.parametrize(
    "interval,maximum", [(0, 10), (61, 10), (1, 0), (1, 86401), (float("nan"), 10)]
)
def test_watch_invalid_limits(interval, maximum):
    with pytest.raises(ValueError, match="watch_limits_invalid"):
        progress.watch(None, "run1", interval=interval, max_seconds=maximum)


def test_watch_cli_dispatch_is_read_only(monkeypatch, capsys):
    monkeypatch.setattr(cli, "SSHTransport", lambda config: None)
    monkeypatch.setattr(
        cli, "RemoteClient", lambda transport: fake_client([{"status": "succeeded"}])
    )
    assert (
        cli.main(
            ["--host", "gpu-training", "watch", "--run-id", "run1", "--json-lines"]
        )
        == 0
    )
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records[0]["status"] == "succeeded"
    assert records[-1]["result"]["watch"] == "finished"
