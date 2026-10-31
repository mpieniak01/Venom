"""The host owns the GPU lease and cleanup; request routing never starts a second stack."""

import asyncio
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.config import SETTINGS
from venom_core.services import benchmark_coding as service_module
from venom_core.services.maintenance_comparison import preflight, sandbox, worker
from venom_core.services.maintenance_comparison.scenarios import Scenario

ROOT = Path(__file__).resolve().parents[1]


class Lease:
    def __init__(self):
        self.release = MagicMock()
        self.operations = []

    def operation(self, **kwargs):
        self.operations.append(kwargs["kind"])
        return nullcontext()

    def cleanup(self, **kwargs):
        assert kwargs["confirm_quiescent"]()
        return nullcontext()


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(SETTINGS, "ENABLE_MAINTENANCE_COMPARISON", True)
    return service_module.CodingBenchmarkService(str(tmp_path), str(ROOT))


@pytest.mark.asyncio
async def test_owned_start_uses_exclusive_lease_not_ollama_scheduler(
    service, monkeypatch
):
    lease = Lease()
    acquire = MagicMock(return_value=lease)
    monkeypatch.setattr(
        service_module,
        "get_runtime_admission",
        lambda: SimpleNamespace(acquire=acquire),
    )
    monkeypatch.setattr(preflight, "require_local_llms_empty", AsyncMock())
    monkeypatch.setattr(service, "_run_owned_maintenance", AsyncMock())
    run_id = await service.start_maintenance(
        models=["mini-coder-1.7b"],
        tasks=["maintenance_operator"],
        trial_seconds=180,
        controller=object(),
    )
    await asyncio.sleep(0)
    assert acquire.call_args.kwargs["owner"] == "coding-maintenance"
    run = service._runs[run_id]
    command = service._build_scheduler_command(run)
    assert "venom_core.services.maintenance_comparison.worker" in command
    assert command[-2:] == ["--phase", "comparison"]
    assert run.config.endpoint == "local-transformers"
    service._run_owned_maintenance.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_preflight_releases_lease_without_spawning(service, monkeypatch):
    lease = Lease()
    monkeypatch.setattr(
        service_module,
        "get_runtime_admission",
        lambda: SimpleNamespace(acquire=lambda **_: lease),
    )
    monkeypatch.setattr(
        preflight,
        "require_local_llms_empty",
        AsyncMock(side_effect=ValueError("maintenance_local_llm_still_loaded")),
    )
    with pytest.raises(ValueError, match="still_loaded"):
        await service.start_maintenance(
            models=["mini-coder-1.7b"],
            tasks=["maintenance_operator"],
            trial_seconds=180,
            controller=object(),
        )
    lease.release.assert_called_once()
    assert not service._runs


@pytest.mark.parametrize("mode", ["success", "spawn_error", "cancel", "cancel_spawn"])
@pytest.mark.asyncio
async def test_owned_process_releases_resources_before_lease(
    service, monkeypatch, mode
):
    lease = Lease()
    run = service_module.CodingBenchmarkRun(
        run_id="11111111-1111-4111-8111-111111111111",
        config=service_module.CodingRunConfig(
            models=["mini-coder-1.7b"],
            tasks=["maintenance_operator"],
            loop_task="",
            first_sieve_task="",
            timeout=180,
            max_rounds=3,
            endpoint="local-transformers",
            stop_on_failure=False,
            options={},
            model_timeout_overrides={},
        ),
        status="pending",
        created_at="now",
    )
    service._runs[run.run_id] = run
    process = MagicMock()
    process.poll.return_value = 0
    process.returncode = 0
    process.communicate.return_value = ("", "")
    if mode == "cancel":
        process.communicate.side_effect = asyncio.CancelledError()
    popen = MagicMock(return_value=process)
    if mode == "spawn_error":
        popen.side_effect = OSError("cannot start")
    entered = threading.Event()
    release = threading.Event()
    if mode == "cancel_spawn":

        def spawning(*_args, **_kwargs):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("spawn control was not released")
            return process

        popen.side_effect = spawning
    monkeypatch.setattr(service_module.subprocess, "Popen", popen)
    monkeypatch.setattr(
        service,
        "_scheduler_environment",
        lambda _: {"ALLOW_SANDBOX_CONTAINERS": "true"},
    )
    cleanup = MagicMock(return_value=True)
    monkeypatch.setattr(sandbox, "cleanup_run_containers", cleanup)
    if mode == "cancel_spawn":
        active = asyncio.create_task(service._run_owned_maintenance(run, lease))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            active.cancel()
            await asyncio.sleep(0)
            lease.release.assert_not_called()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await active
    elif mode == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await service._run_owned_maintenance(run, lease)
    else:
        await service._run_owned_maintenance(run, lease)
    cleanup.assert_called_once_with(run.run_id)
    lease.release.assert_called_once()
    assert run.run_id not in service._active_procs
    assert run.status == ("completed" if mode == "success" else "failed")
    assert popen.call_args.args[0][:3] == ["/usr/bin/setpriv", "--pdeathsig", "TERM"]


def test_maintenance_profile_validation_and_child_only_sandbox(
    service, monkeypatch, tmp_path
):
    with pytest.raises(ValueError, match="separate"):
        service._validate_start_request(
            ["mini-coder-1.7b"], ["maintenance_operator", "python_simple"]
        )
    with pytest.raises(ValueError, match="unknown_maintenance"):
        service._validate_start_request(["unknown"], ["maintenance_operator"])
    monkeypatch.setattr(SETTINGS, "ENABLE_MAINTENANCE_COMPARISON", False)
    with pytest.raises(ValueError, match="disabled"):
        service._validate_start_request(["mini-coder-1.7b"], ["maintenance_operator"])
    monkeypatch.setattr(
        service_module,
        "get_runtime_admission",
        lambda: SimpleNamespace(database=tmp_path / "ledger"),
    )
    cfg = SimpleNamespace(tasks=["maintenance_operator"])
    run = SimpleNamespace(config=cfg, run_id="run")
    env = service._scheduler_environment(run)
    assert env["ENABLE_SANDBOX"] == "true"
    assert env["VENOM_MAINTENANCE_RUN_ID"] == "run"
    run.config.tasks = ["python_simple"]
    assert service._scheduler_environment(run) is None


@pytest.mark.asyncio
async def test_trial_records_real_patch_verification_and_removes_copy(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(worker, "require_host_owner", lambda: None)

    def prepare(repo, sha, target, case):
        target.mkdir(parents=True)
        return {}

    monkeypatch.setattr(worker, "prepare", prepare)
    habitat = MagicMock()
    monkeypatch.setattr(worker, "TrialHabitat", lambda *_: habitat)
    model = SimpleNamespace(
        input_tokens=0,
        output_tokens=0,
        torch=MagicMock(),
        configuration={"backend": "fake"},
        load_seconds=1,
        memory=lambda: {"cuda_peak_reserved_bytes": 1024},
    )
    profile = {"id": "m", "hf_id": "test/m", "revision": "a" * 40}
    run = {
        "status": "model_finished",
        "model_finished": True,
        "seconds": 0.1,
        "calls": [
            {
                "name": "Terminal",
                "arguments": {"command": "python -m pytest -q test_visible.py"},
                "result": {"exit_code": 0, "stdout": "1 passed", "stderr": ""},
            }
        ],
        "final": {"status": "success", "summary": "passed"},
        "messages": [],
        "tool_call_count": 1,
    }
    monkeypatch.setattr(worker, "drive", AsyncMock(return_value=run))
    row = await worker.trial(
        model,
        profile,
        Scenario("operator-01", "operator", "run test"),
        ROOT,
        "a" * 40,
        tmp_path,
        0,
        180,
    )
    assert row["passed"]
    assert row["verification"]["reason"] == "operator_contract"
    assert row["seconds"] >= row["setup_seconds"]
    assert row["training_allowed"] is False
    habitat.freeze.assert_called_once()
    habitat.close.assert_called_once()
    assert list((tmp_path / "workspaces").iterdir()) == []


@pytest.mark.asyncio
async def test_api_selects_owned_runner_and_ignores_legacy_default_options(monkeypatch):
    from venom_core.api.routes import benchmark_coding as routes
    from venom_core.api.routes import system_deps
    from venom_core.api.schemas.benchmark_coding import CodingBenchmarkStartRequest

    method = AsyncMock(return_value="11111111-1111-4111-8111-111111111111")
    monkeypatch.setattr(
        routes, "_coding_benchmark_service", SimpleNamespace(start_maintenance=method)
    )
    controller = object()
    monkeypatch.setattr(system_deps, "get_llm_controller", lambda: controller)
    request = CodingBenchmarkStartRequest(
        models=["mini-coder-1.7b"], tasks=["maintenance_operator"], loop_task=""
    )
    response = await routes.start_coding_benchmark(request)
    assert response.run_id == "11111111-1111-4111-8111-111111111111"
    assert method.call_args.kwargs["options"] == {}
    assert method.call_args.kwargs["controller"] is controller
    request.max_rounds = 1
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await routes.start_coding_benchmark(request)
    assert error.value.status_code == 400


def test_profile_endpoint_preserves_all_eight_models_when_disabled(monkeypatch):
    from venom_core.api.routes.benchmark_coding import maintenance_model_profiles

    monkeypatch.setattr(SETTINGS, "ENABLE_MAINTENANCE_COMPARISON", False)
    response = maintenance_model_profiles()
    assert response["enabled"] is False
    assert len(response["models"]) == 8
