"""Sandbox settings, evidence capture and preflight fail closed without a GPU."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from venom_core.services.maintenance_comparison import preflight, sandbox
from venom_core.services.maintenance_comparison.sandbox import TrialHabitat, TrialTools


def test_container_has_only_trial_mount_and_no_network(tmp_path):
    habitat = object.__new__(TrialHabitat)
    habitat.trial_image = "sha256:" + "a" * 64
    habitat.trial_readonly_workspace = False
    habitat.client = MagicMock()
    habitat._active_container_name = lambda: "trial"
    habitat._run_container("unused", tmp_path)
    kwargs = habitat.client.containers.run.call_args.kwargs
    assert kwargs["network_mode"] == "none"
    assert kwargs["read_only"]
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["pids_limit"] == 64
    assert list(kwargs["volumes"]) == [str(tmp_path)]
    assert "devices" not in kwargs
    assert "privileged" not in kwargs


def test_actual_exit_stdout_stderr_are_separate_and_output_is_bounded():
    h = object.__new__(TrialHabitat)
    h.client = MagicMock()
    h.container = MagicMock()
    h.client.api.exec_create.return_value = {"Id": "exec"}
    h.client.api.exec_start.return_value = iter([(b"out", b"err")])
    h.client.api.exec_inspect.return_value = {"ExitCode": 7}
    result = h.structured("false", 3)
    assert (result["stdout"], result["stderr"], result["exit_code"]) == (
        "out",
        "err",
        7,
    )
    assert h.client.api.exec_create.call_args.args[1][0] == "timeout"
    h.client.api.exec_start.return_value = iter([(b"x" * 1_048_577, None)])
    result = h.structured("spam", 1)
    assert len(result["stdout"]) == 1048576
    assert result["output_truncated"]
    h.container.kill.assert_called_once()


def test_invalid_image_and_arguments_never_execute(tmp_path):
    with pytest.raises(ValueError, match="immutable"):
        TrialHabitat(tmp_path, "image:latest")
    h = SimpleNamespace(workspace_path=tmp_path, structured=MagicMock())
    tools = TrialTools(h, "localization")
    for name, arguments in [
        ("Terminal", {}),
        ("Terminal", {"command": ""}),
        ("Unknown", {}),
        ("Finish", {"status": "success", "summary": "ok"}),
    ]:
        pending = tools.invoke_tool(name, arguments)
        with pytest.raises(ValueError):
            asyncio.run(pending)
    h.structured.assert_not_called()
    asyncio.run(
        tools.invoke_tool(
            "LocalizationFinish",
            {"status": "not_found", "summary": "absent", "locations": []},
        )
    )
    assert tools.finished["status"] == "not_found"


def test_cleanup_never_removes_differently_labelled_container(monkeypatch):
    from venom_core.infrastructure import docker_habitat

    client = MagicMock()
    container = MagicMock()
    container.attrs = {
        "Config": {
            "Labels": {
                "venom.experiment": "maintenance-comparison",
                "venom.run_id": "other",
            }
        }
    }
    client.containers.list.return_value = [container]
    monkeypatch.setattr(
        docker_habitat, "docker", SimpleNamespace(from_env=lambda: client)
    )
    assert not sandbox.cleanup_run_containers("wanted")
    container.remove.assert_not_called()
    container.attrs["Config"]["Labels"]["venom.run_id"] = "wanted"
    assert sandbox.cleanup_run_containers("wanted")
    container.remove.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_preflight_ignores_remote_providers_and_unconfigured_optional_backend(
    monkeypatch,
):
    monkeypatch.setattr(preflight, "resource_snapshot", lambda: [])
    seen = []

    async def listening(endpoint):
        seen.append(endpoint)
        return False

    monkeypatch.setattr(preflight, "_listening", listening)
    controller = SimpleNamespace(
        list_servers=lambda: [
            {"name": "openrouter", "endpoint": "https://external"},
            {"name": "onnx", "endpoint": None},
            {"name": "vllm", "endpoint": "http://127.0.0.1:8001"},
        ]
    )
    await preflight.require_local_llms_empty(controller)
    assert seen == ["http://127.0.0.1:8001"]


@pytest.mark.asyncio
async def test_preflight_rejects_existing_local_model_and_running_worker(monkeypatch):
    with pytest.raises(ValueError, match="controller"):
        await preflight.require_local_llms_empty(None)
    monkeypatch.setattr(preflight, "resource_snapshot", lambda: [{"category": "llm"}])
    with pytest.raises(ValueError, match="still_loaded"):
        await preflight.require_local_llms_empty(object())
    monkeypatch.setattr(preflight, "resource_snapshot", lambda: [])

    async def listening(_):
        return True

    monkeypatch.setattr(preflight, "_listening", listening)
    controller = SimpleNamespace(
        list_servers=lambda: [{"name": "vllm", "endpoint": "http://127.0.0.1:8001"}]
    )
    with pytest.raises(ValueError, match="runtime_running"):
        await preflight.require_local_llms_empty(controller)


@pytest.mark.parametrize(
    "status", ["running", "exited", "dead", "paused", "restarting"]
)
def test_frozen_verification_accepts_only_quiescent_container_states(status):
    habitat = object.__new__(TrialHabitat)
    habitat.container = MagicMock()
    habitat.container.status = status
    if status == "restarting":
        with pytest.raises(RuntimeError, match="quiescent"):
            habitat.freeze()
    else:
        habitat.freeze()
        assert habitat.container.pause.called == (status == "running")


def test_localization_completion_rejects_malformed_nested_arguments(tmp_path):
    tools = TrialTools(SimpleNamespace(workspace_path=tmp_path), "localization")
    for location in [
        {"path": "a.py"},
        {"path": "a.py", "symbol": 42, "evidence": "bad"},
    ]:
        with pytest.raises(ValueError, match="location_invalid"):
            tools.validate_completion(
                {"status": "success", "summary": "done", "locations": [location]}
            )


def test_oracle_setup_uses_root_owned_read_only_file():
    from venom_core.services.maintenance_comparison.grading import _put_oracle

    container = MagicMock()
    container.exec_run.return_value.exit_code = 0
    _put_oracle(SimpleNamespace(container=container), "assert True")
    kwargs = container.exec_run.call_args.kwargs
    assert kwargs["user"] == "0:0"
    assert "chmod(0o444)" in container.exec_run.call_args.args[0][2]


@pytest.mark.parametrize(
    "observed", ["paused", "exited", "dead", "running", "restarting"]
)
def test_freeze_accepts_pause_failure_only_after_confirming_quiescence(observed):
    habitat = sandbox.TrialHabitat.__new__(sandbox.TrialHabitat)
    container = MagicMock()
    container.status = "running"

    def racing_pause():
        container.status = observed
        raise RuntimeError("pause raced with container state")

    container.pause.side_effect = racing_pause
    habitat.container = container
    if observed in {"paused", "exited", "dead"}:
        habitat.freeze()
    else:
        with pytest.raises(RuntimeError, match="pause raced"):
            habitat.freeze()
    assert container.reload.call_count == 2


@pytest.mark.parametrize("observed", ["paused", "exited", "dead"])
def test_freeze_does_not_pause_an_already_quiescent_container(observed):
    habitat = sandbox.TrialHabitat.__new__(sandbox.TrialHabitat)
    container = MagicMock()
    container.status = observed
    habitat.container = container
    habitat.freeze()
    container.pause.assert_not_called()


@pytest.mark.parametrize("observed", ["exited", "running"])
def test_output_cap_closes_stream_before_kill_and_preserves_unknown_exit(
    monkeypatch, observed
):
    events = []

    class Stream:
        def __iter__(self):
            yield (b"x" * 1_048_577, None)

        def close(self):
            events.append("close")

    habitat = sandbox.TrialHabitat.__new__(sandbox.TrialHabitat)
    habitat.container = MagicMock(id="container", status=observed)
    habitat.container.kill.side_effect = lambda: events.append("kill")
    api = MagicMock()
    api.exec_create.return_value = {"Id": "exec"}
    api.exec_start.return_value = Stream()
    api.exec_inspect.side_effect = RuntimeError("transport lost after kill")
    habitat.client = SimpleNamespace(api=api)
    monkeypatch.setattr(sandbox.threading, "Timer", MagicMock())
    if observed == "running":
        with pytest.raises(RuntimeError, match="transport lost"):
            habitat.structured("bounded output", 1)
    else:
        result = habitat.structured("bounded output", 1)
        assert result["exit_code"] is None
        assert result["output_truncated"] is True
        assert len(result["stdout"]) == 1_048_576
        assert result["transport_error"] == "RuntimeError"
    assert events.index("close") < events.index("kill")
    assert events.count("close") == 1


def test_trial_closes_owned_docker_client_even_when_removal_fails():
    habitat = sandbox.TrialHabitat.__new__(sandbox.TrialHabitat)
    habitat.container = MagicMock()
    habitat.client = MagicMock()
    habitat.container.remove.side_effect = RuntimeError("remove failed")
    with pytest.raises(RuntimeError, match="remove failed"):
        habitat.close()
    habitat.client.close.assert_called_once()
