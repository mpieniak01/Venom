"""Sandbox settings, evidence capture and preflight fail closed without a GPU."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from venom_core.services.maintenance_comparison import preflight, sandbox
from venom_core.services.maintenance_comparison.sandbox import TrialHabitat, TrialTools


def test_container_has_only_trial_mount_and_no_network(tmp_path):
    """Verify container has only trial mount and no network."""
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
    assert kwargs["environment"]["TMPDIR"] == sandbox.TEMP_DIRECTORY
    assert "/tmp" not in kwargs["tmpfs"]
    assert "mode=0750" in kwargs["tmpfs"][sandbox.RUNTIME_DIRECTORY]
    assert "mode=0700" in kwargs["tmpfs"][sandbox.TEMP_DIRECTORY]
    assert "uid=1000" in kwargs["tmpfs"][sandbox.TEMP_DIRECTORY]
    habitat.client.containers.run.return_value.exec_run.assert_not_called()


def test_actual_exit_stdout_stderr_are_separate_and_output_is_bounded():
    """Verify actual exit stdout stderr are separate and output is bounded."""
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
    """Verify invalid image and arguments never execute."""
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
    """Verify cleanup never removes differently labelled container."""
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
    """Verify preflight ignores remote providers and unconfigured optional backend."""
    monkeypatch.setattr(preflight, "resource_snapshot", lambda: [])
    seen = []

    async def listening(endpoint):
        """Return the test-specified local endpoint observation."""
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
    """Verify preflight rejects existing local model and running worker."""
    with pytest.raises(ValueError, match="controller"):
        await preflight.require_local_llms_empty(None)
    monkeypatch.setattr(preflight, "resource_snapshot", lambda: [{"category": "llm"}])
    with pytest.raises(ValueError, match="still_loaded"):
        await preflight.require_local_llms_empty(object())
    monkeypatch.setattr(preflight, "resource_snapshot", lambda: [])

    async def listening(_):
        """Return the test-specified local endpoint observation."""
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
    """Verify frozen verification accepts only quiescent container states."""
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
    """Verify localization completion rejects malformed nested arguments."""
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
    """Verify oracle setup uses root owned read only file."""
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
    """Verify freeze accepts pause failure only after confirming quiescence."""
    habitat = sandbox.TrialHabitat.__new__(sandbox.TrialHabitat)
    container = MagicMock()
    container.status = "running"

    def racing_pause():
        """Simulate the container exiting between status observation and pause."""
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
    """Verify freeze does not pause an already quiescent container."""
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
    """Verify output cap closes stream before kill and preserves unknown exit."""
    events = []

    class Stream:
        def __iter__(self):
            """Yield the configured Docker execution stream chunks."""
            yield (b"x" * 1_048_577, None)

        def close(self):
            """Release the test double resources without touching the live stack."""
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
    """Verify trial closes owned docker client even when removal fails."""
    habitat = sandbox.TrialHabitat.__new__(sandbox.TrialHabitat)
    habitat.container = MagicMock()
    habitat.client = MagicMock()
    habitat.container.remove.side_effect = RuntimeError("remove failed")
    with pytest.raises(RuntimeError, match="remove failed"):
        habitat.close()
    habitat.client.close.assert_called_once()


@pytest.mark.parametrize(
    "error", [ValueError("remote"), TimeoutError("timed out"), OSError("unreachable")]
)
@pytest.mark.asyncio
async def test_preflight_runtime_probe_errors_are_controlled(monkeypatch, error):
    """Verify preflight runtime probe errors are controlled."""
    from unittest.mock import AsyncMock

    monkeypatch.setattr(preflight, "resource_snapshot", lambda: [])
    monkeypatch.setattr(preflight, "_listening", AsyncMock(side_effect=error))
    controller = SimpleNamespace(
        list_servers=lambda: [{"name": "vllm", "endpoint": "http://invalid"}]
    )
    with pytest.raises(
        ValueError, match="maintenance_local_llm_runtime_unverified"
    ) as observed:
        await preflight.require_local_llms_empty(controller)
    assert observed.value.__cause__ is error


@pytest.mark.parametrize("value", [[], ["status"], "success", None, 1])
def test_finish_rejects_non_object_reports(value, tmp_path):
    """Verify finish rejects non object reports."""
    tools = TrialTools(SimpleNamespace(workspace_path=tmp_path), "operator")
    with pytest.raises(ValueError, match="finish_arguments_not_object"):
        tools.validate_completion(value)


@pytest.mark.parametrize(
    "status,payload", [(500, {}), (200, {}), (200, {"models": "invalid"})]
)
@pytest.mark.asyncio
async def test_ollama_preflight_metadata_errors_are_controlled(
    monkeypatch, status, payload
):
    """Verify ollama preflight metadata errors are controlled."""
    from unittest.mock import AsyncMock

    import httpx

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=payload))
    )
    monkeypatch.setattr(preflight.httpx, "AsyncClient", lambda **_: client)
    monkeypatch.setattr(preflight, "resource_snapshot", lambda: [])
    monkeypatch.setattr(preflight, "_listening", AsyncMock(return_value=True))
    controller = SimpleNamespace(
        list_servers=lambda: [
            {"name": "ollama", "endpoint": "http://localhost:11434/v1"}
        ]
    )
    with pytest.raises(ValueError, match="maintenance_local_llm_runtime_unverified"):
        await preflight.require_local_llms_empty(controller)
