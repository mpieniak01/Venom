"""Supervise the offline runner and release GPU ownership after child exit."""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import time
from pathlib import Path
from socket import socket as probe_socket

import httpx
from dotenv import dotenv_values
from fastapi import HTTPException

from scripts.academy.omni_pl_chat_evaluate import validate_dev_cases
from venom_core.config import SETTINGS, _settings_env_file
from venom_core.core.llm_server_controller import LlmServerController
from venom_core.services.remote_training.lifecycle import (
    atomic_json,
    file_lock,
    group_alive,
    process_identity,
)
from venom_core.services.remote_training.supervisor import _drain, _terminate
from venom_core.services.runtime_admission import (
    ACADEMY_TRAINING_OWNER,
    RuntimeAdmission,
    RuntimeLease,
    get_runtime_admission,
)
from venom_core.services.runtime_release_service import (
    TRAINING_CLEANUP_HEADER,
    memory_snapshot,
    release_all_runtime_models,
)

from .evidence import calibrated_judgments, review_data
from .profiles import Profile, check_inputs, digest, resolve_input, rows, stable_hash
from .service import REPO, ExperimentService

RUNNER = REPO / "scripts/academy/omni_pl_chat_p1.sh"
EVALUATOR = REPO / "scripts/academy/omni_pl_chat_evaluate.sh"


class StopRequested(Exception):
    """The durable run record carries an operator stop request."""


class Worker:
    def __init__(self, service: ExperimentService, run_id: str, attempt: int):
        self.service = service
        self.run_id = run_id
        self.attempt = attempt
        self.directory = service.run_dir(run_id)
        self.log = self.directory / f"attempt-{attempt}.log"
        self.deadline = 0.0
        self.identity: dict | None = None

    def update(self, **values) -> dict:
        with self.service.run_lock(self.run_id):
            state = self.service.store.read(self.run_id)
            if state["attempt"] != self.attempt:
                raise ValueError("experiment_attempt_changed")
            state.update(values)
            self.service._save(state)
            return state

    def check_budget(self) -> None:
        if self.service.store.read(self.run_id)["stop_requested"]:
            raise StopRequested()
        if time.monotonic() >= self.deadline:
            raise TimeoutError("experiment_time_limit")

    def quiescent(self) -> bool:
        return self.identity is None or not group_alive(self.identity["process_group"])

    def execute(self, command: list[str], gpu_fd: int) -> None:
        self.check_budget()
        child = subprocess.Popen(
            command,
            cwd=REPO,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(gpu_fd,),
        )
        identity = process_identity(child.pid)
        self.identity = identity
        try:
            if identity is None:
                child.wait(timeout=1)
                raise RuntimeError("experiment_child_start_unconfirmed")
            if child.stdout is None:
                raise RuntimeError("experiment_child_pipe_missing")
            os.set_blocking(child.stdout.fileno(), False)
            self.update(child=identity)
            while child.poll() is None:
                _drain(child, self.log)
                self.check_budget()
                time.sleep(0.1)
            _drain(child, self.log)
            if not self.quiescent():
                raise RuntimeError("experiment_child_group_active")
            if child.returncode:
                raise RuntimeError("experiment_child_failed")
        finally:
            if identity is not None and (child.poll() is None or not self.quiescent()):
                _terminate(child, identity, self.log)
            if child.stdout is not None:
                child.stdout.close()
            if self.quiescent():
                self.update(child=None)

    def prepare_gpu(self, lease: RuntimeLease, *, offline: bool) -> None:
        """Unload models before CUDA starts and retain the lease for the whole job."""
        capability = lease.training_cleanup_capability()
        try:
            port = self._local_api_port()
            if offline:
                # An older API may be serving before it has claimed the ledger.
                # Only use the standalone release path when the API is absent.
                with probe_socket() as probe:
                    probe.settimeout(1)
                    if probe.connect_ex(("127.0.0.1", port)) == 0:
                        raise ValueError("API listener has no host ownership")
                receipt = asyncio.run(
                    release_all_runtime_models(
                        LlmServerController(SETTINGS), training_capability=capability
                    )
                )
            else:
                with httpx.Client(timeout=120, trust_env=False) as client:
                    response = client.post(
                        f"http://127.0.0.1:{port}/api/v1/system/models/release",
                        headers={TRAINING_CLEANUP_HEADER: capability},
                    )
                    response.raise_for_status()
                    receipt = response.json()
            if (
                not isinstance(receipt, dict)
                or receipt.get("released") is not True
                or receipt.get("training_lease_verified") is not True
            ):
                raise ValueError("incomplete model release")
        except (HTTPException, httpx.HTTPError, OSError, ValueError) as exc:
            raise ValueError("experiment_gpu_release_failed") from exc
        atomic_json(self.directory / f"gpu-release-{self.attempt}.json", receipt)

    @staticmethod
    def _local_api_port() -> int:
        values = dotenv_values(_settings_env_file())
        port: str | int | None = os.environ.get("PORT") or values.get("PORT")
        if not port:
            proxy = os.environ.get("API_PROXY_TARGET") or values.get("API_PROXY_TARGET")
            port = httpx.URL(proxy).port if proxy else None
        defaults = {"dev": 8000, "preprod": 8100, "prod": 8200}
        result = int(port or defaults.get(SETTINGS.ENVIRONMENT_ROLE, 8000))
        if not 1 <= result <= 65535:
            raise ValueError("invalid local API port")
        return result

    def _space(self, profile: Profile) -> None:
        volumes = [self.directory]
        if profile.backing_volume is not None:
            volumes.append(resolve_input(self.service.root, profile.backing_volume))
        for volume in volumes:
            stats = os.statvfs(volume)
            if stats.f_bavail * stats.f_frsize < profile.min_free_bytes:
                raise ValueError("experiment_disk_headroom")

    def pipeline(self, state: dict, manifest: dict, gpu_fd: int) -> None:
        profile = Profile.model_validate(manifest["profile"])
        check_inputs(self.service.root, profile)
        self._space(profile)

        def path(value: str) -> str:
            return str(resolve_input(self.service.root, value))

        snapshot = path(profile.snapshot)
        venv = path(profile.training_venv)
        train = path(profile.train)
        dev = Path(path(profile.dev))
        validate_dev_cases(rows(dev))
        training = self.directory / "training"
        recipe = self.directory / "recipe.json"
        if state["mode"] != "evaluate":
            self.update(stage="preflight")
            preflight = self.directory / f"preflight-{self.attempt}"
            self.execute(
                [
                    "bash",
                    str(RUNNER),
                    snapshot,
                    train,
                    str(preflight),
                    venv,
                    "preflight",
                    str(recipe),
                ],
                gpu_fd,
            )
            self._space(profile)
            self.update(stage="train")
            self.execute(
                [
                    "bash",
                    str(RUNNER),
                    snapshot,
                    train,
                    str(training),
                    venv,
                    state["mode"],
                    str(recipe),
                ],
                gpu_fd,
            )
        checkpoint = self.service._checkpoint(self.run_id)
        if checkpoint is None:
            raise ValueError("experiment_checkpoint_unavailable")
        checkpoint_path, evidence = checkpoint
        if (
            state["mode"] != "evaluate"
            and evidence["step"] != manifest["recipe"]["steps"]
        ):
            raise ValueError("experiment_training_incomplete")
        self.update(
            stage="generate",
            checkpoint_step=evidence["step"],
            checkpoint_sha256=evidence["sha256"],
        )
        generation = self.directory / f"evaluation-{self.attempt}"
        self._space(profile)
        self.execute(
            [
                "bash",
                str(EVALUATOR),
                snapshot,
                str(dev),
                str(generation),
                venv,
                "--resume-partial",
                "base",
                f"{checkpoint_path.name}={checkpoint_path}",
            ],
            gpu_fd,
        )
        check_inputs(self.service.root, profile)
        atomic_json(
            generation / "generation-seal.json",
            {
                name: digest(generation / name)
                for name in (
                    "blind.jsonl",
                    "unblind.json",
                    "raw.jsonl",
                    "manifest.json",
                )
            },
        )
        self.check_budget()

    def run(self) -> None:
        with self.service.run_lock(self.run_id):
            state = self.service.store.read(self.run_id)
            if (
                state["attempt"] != self.attempt
                or state["status"] != "queued"
                or state["supervisor"] != process_identity(os.getpid())
            ):
                return
        remaining = state["max_seconds"] - max(
            0, time.time() - state["attempt_started_at"]
        )
        self.deadline = time.monotonic() + remaining
        terminal, error = "failed", None
        try:
            self.check_budget()
            manifest = self.service._manifest(self.run_id)
            if stable_hash(manifest) != state["manifest_sha256"]:
                raise ValueError("experiment_manifest_changed")
            from .profiles import read_json

            if read_json(self.directory / "recipe.json") != manifest["recipe"]:
                raise ValueError("experiment_recipe_changed")
            host = get_runtime_admission()
            host.database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            gpu_lock = host.database.parent / "academy-experiments.gpu.lock"
            with file_lock(gpu_lock, blocking=False) as gpu_fd:
                if not host.enabled:
                    raise ValueError("experiment_gpu_admission_disabled")
                admission = RuntimeAdmission.for_training_worker(host.database)
                offline = admission.claim_offline_host()
                lease = admission.acquire(
                    owner=ACADEMY_TRAINING_OWNER,
                    run_id=self.run_id,
                    engine="omni-training",
                    model=manifest["profile"]["model"],
                )
                training_started = False
                try:
                    self.update(stage="release_gpu")
                    self.prepare_gpu(lease, offline=offline)
                    self.check_budget()
                    with lease.operation(
                        kind="lifecycle", confirm_quiescent=self.quiescent
                    ):
                        self.update(status="running")
                        training_started = True
                        self.pipeline(state, manifest, gpu_fd)
                finally:
                    if self.quiescent():
                        try:
                            atomic_json(
                                self.directory / f"gpu-after-{self.attempt}.json",
                                memory_snapshot(),
                            )
                        finally:
                            if not lease.release():
                                if training_started:
                                    raise ValueError("experiment_gpu_recovery_required")
                                lease.defer_training_release()
            with self.service.run_lock(self.run_id):
                current = self.service.store.read(self.run_id)
                self.check_budget()
                calibration = manifest["calibration"]
                if calibration is not None:
                    generation, dev = self.service._review_inputs(current)
                    judgments = calibrated_judgments(
                        calibration, review_data(generation, dev)
                    )
                    self.service._commit(current, judgments)
                    terminal = "succeeded"
                else:
                    terminal = "awaiting_review"
        except StopRequested:
            terminal = "stopped"
        except TimeoutError:
            terminal, error = "timed_out", "experiment_time_limit"
        except BlockingIOError:
            error = "experiment_gpu_busy"
        except HTTPException as exc:
            error = getattr(exc, "code", "experiment_admission_failed")
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            RuntimeError,
        ) as exc:
            code = str(exc)
            error = (
                code
                if code.startswith("experiment_") and code.isidentifier()
                else "experiment_stage_failed"
            )
            from venom_core.services.remote_training.supervisor import _append

            _append(self.log, f"\n{type(exc).__name__}: {exc}\n".encode())
        self.update(
            status=terminal,
            stage="score"
            if terminal == "awaiting_review"
            else (
                "done"
                if terminal == "succeeded"
                else self.service.store.read(self.run_id)["stage"]
            ),
            error=error,
            elapsed_seconds=state["elapsed_before"]
            + max(0, time.time() - state["attempt_started_at"]),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("attempt", type=int)
    args = parser.parse_args()
    Worker(ExperimentService(args.root), args.run_id, args.attempt).run()


if __name__ == "__main__":
    main()
