"""Plan and journal disposal of sealed checkpoint files owned by a campaign."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

from venom_core.services.remote_training.lifecycle import atomic_json
from venom_core.services.remote_training.paths import data_directory, operator_path

_CHECKPOINT = re.compile(r"checkpoint-[1-9][0-9]*\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_BINARY_FILES = (
    "adapter_model.safetensors",
    "optimizer.pt",
    "rng_state.pth",
    "scheduler.pt",
    "training_args.bin",
)
_JSON_LIMIT = 16 * 1024 * 1024


class ExperimentArtifacts(Protocol):
    def run_dir(self, run_id: str) -> Path: ...

    def run_lock(self, run_id: str) -> AbstractContextManager[Any]: ...

    def list_runs(self) -> list[dict[str, Any]]: ...

    def status(self, run_id: str) -> dict[str, Any]: ...

    def report(self, run_id: str) -> dict[str, Any]: ...


def read_object(path: Path) -> dict[str, Any]:
    with data_directory(path.parent) as directory_fd:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
        )
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > _JSON_LIMIT:
                raise ValueError("campaign_state_invalid")
            raw = stream.read(_JSON_LIMIT + 1)
    if len(raw) > _JSON_LIMIT:
        raise ValueError("campaign_state_invalid")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("campaign_state_invalid")
    return value


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def file_fingerprint(path: Path) -> str:
    with data_directory(path.parent) as directory_fd:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
        )
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("campaign_artifact_file_unmanaged")
            return hashlib.file_digest(stream, "sha256").hexdigest()


def protected_runs(experiments: ExperimentArtifacts) -> set[str]:
    runs = []
    for view in experiments.list_runs():
        run_dir = experiments.run_dir(view["run_id"])
        state = read_object(run_dir / "state.json")
        try:
            manifest = read_object(run_dir / "manifest.json")
        except FileNotFoundError:
            manifest = {}
        runs.append({**manifest, **state, "run_id": view["run_id"]})
    protected = {
        run["run_id"]
        for run in runs
        if any(run.get(flag) for flag in ("active", "pinned", "protected"))
    }
    protected.update(
        run["parent_run_id"]
        for run in runs
        if isinstance(run.get("parent_run_id"), str)
    )
    return protected


def _verify_run(experiments: ExperimentArtifacts, campaign: dict, trial: dict) -> Path:
    run_dir = experiments.run_dir(trial["run_id"])
    state = read_object(run_dir / "state.json")
    view = experiments.status(trial["run_id"])
    if (
        state.get("campaign_id") != campaign["campaign_id"]
        or view.get("status") != "succeeded"
        or view.get("resources_active") is True
        or any(state.get(flag) for flag in ("active", "pinned", "protected"))
    ):
        raise ValueError("campaign_artifact_run_unavailable")
    seal = read_object(run_dir / "result-seal.json")
    if (
        seal.get("result_sha256") != trial["result_sha256"]
        or file_fingerprint(run_dir / "result.json") != trial["result_sha256"]
    ):
        raise ValueError("campaign_artifact_result_changed")
    return run_dir


def _candidate_files(run_dir: Path, run_id: str) -> Iterator[dict]:
    training = operator_path(run_dir / "training")
    if not training.is_dir():
        return
    for checkpoint in sorted(training.iterdir()):
        if _CHECKPOINT.fullmatch(checkpoint.name) is None:
            continue
        checkpoint = operator_path(checkpoint)
        hashes = read_object(checkpoint / "hashes.json")
        for name in _BINARY_FILES:
            path = checkpoint / name
            digest = hashes.get(name)
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ValueError("campaign_artifact_checkpoint_invalid")
            try:
                info = path.lstat()
            except FileNotFoundError:
                # A previous completed receipt may have removed these files.
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("campaign_artifact_file_unmanaged")
            if file_fingerprint(path) != digest:
                raise ValueError("campaign_artifact_file_changed")
            yield {
                "run_id": run_id,
                "path": str(path.relative_to(run_dir)),
                "size_bytes": info.st_size,
                "sha256": digest,
            }


class Retention:
    def __init__(self, experiments: ExperimentArtifacts, directory: Path):
        self.experiments = experiments
        self.directory = directory

    def _eligible(self, state: dict) -> dict[str, dict]:
        winner = state["selected_run_id"]
        if state["plan"]["retention"] != "discard_rejected" or winner is None:
            return {}
        artifacts = self.experiments.report(winner).get("artifacts", ())
        if not any(artifact.get("available") is True for artifact in artifacts):
            # Retain alternatives if the current winner can no longer be loaded.
            return {}
        protected = protected_runs(self.experiments)
        protected.add(winner)
        return {
            trial["run_id"]: trial
            for trial in state["trials"]
            if (
                trial["status"] == "succeeded"
                and trial.get("result_sha256")
                and trial["run_id"] not in protected
                and (
                    not state["plan"].get("quality_policy")
                    or trial.get("quality_guard", {}).get("status")
                    in {"passed", "rejected"}
                )
            )
        }

    def _plan(self, state: dict) -> dict:
        files = []
        for run_id, trial in self._eligible(state).items():
            with self.experiments.run_lock(run_id):
                run_dir = _verify_run(self.experiments, state, trial)
                files.extend(_candidate_files(run_dir, run_id))
        payload = {
            "campaign_id": state["campaign_id"],
            "selected_run_id": state["selected_run_id"],
            "files": files,
            "bytes": sum(file["size_bytes"] for file in files),
        }
        return {**payload, "plan_sha256": fingerprint(payload)}

    def plan(self, state: dict) -> dict:
        pending = self.directory / "retention-pending.json"
        try:
            return read_object(pending)["plan"]
        except FileNotFoundError:
            return self._plan(state)

    def apply(self, state: dict, plan_sha256: str) -> dict:
        if _DIGEST.fullmatch(plan_sha256) is None:
            raise ValueError("campaign_retention_plan_invalid")
        completed = self.directory / f"retention-{plan_sha256}.json"
        pending = self.directory / "retention-pending.json"
        try:
            receipt = read_object(completed)
        except FileNotFoundError:
            receipt = self._apply(state, plan_sha256, pending, completed)
        if pending.exists():
            journal = read_object(pending)
            if journal["plan"]["plan_sha256"] == plan_sha256:
                pending.unlink()
        return receipt

    def _apply(
        self, state: dict, plan_sha256: str, pending: Path, completed: Path
    ) -> dict:
        try:
            journal = read_object(pending)
            recovering = True
        except FileNotFoundError:
            plan = self._plan(state)
            if plan["plan_sha256"] != plan_sha256:
                raise ValueError("campaign_retention_plan_changed")
            journal = {"plan": plan, "files": []}
            atomic_json(pending, journal)
            recovering = False
        plan = journal["plan"]
        if (
            plan["plan_sha256"] != plan_sha256
            or fingerprint({k: v for k, v in plan.items() if k != "plan_sha256"})
            != plan_sha256
            or plan["selected_run_id"] != state["selected_run_id"]
        ):
            raise ValueError("campaign_retention_plan_changed")
        eligible = self._eligible(state)
        done = {(file["run_id"], file["path"]) for file in journal["files"]}
        if any(
            file["run_id"] not in eligible
            for file in plan["files"]
            if (file["run_id"], file["path"]) not in done
        ):
            raise ValueError("campaign_retention_protection_changed")
        remaining: dict[str, list[dict]] = {}
        for file in plan["files"]:
            run_id = file["run_id"]
            if (run_id, file["path"]) not in done:
                remaining.setdefault(run_id, []).append(file)
        for run_id, files in remaining.items():
            if run_id in protected_runs(self.experiments):
                raise ValueError("campaign_retention_protection_changed")
            with self.experiments.run_lock(run_id):
                run_dir = _verify_run(self.experiments, state, eligible[run_id])
                for file in files:
                    outcome = _remove_file(run_dir, file, allow_absent=recovering)
                    journal["files"].append({**file, "outcome": outcome})
                    atomic_json(pending, journal)
        receipt = {
            **journal,
            "status": "completed",
            "removed_bytes": sum(
                file["size_bytes"]
                for file in journal["files"]
                if file["outcome"] == "removed"
            ),
        }
        atomic_json(completed, receipt)
        return receipt


def _remove_file(run_dir: Path, file: dict, *, allow_absent: bool) -> str:
    parts = Path(file["path"]).parts
    if (
        len(parts) != 3
        or parts[0] != "training"
        or _CHECKPOINT.fullmatch(parts[1]) is None
        or parts[2] not in _BINARY_FILES
    ):
        raise ValueError("campaign_artifact_file_unmanaged")
    checkpoint = run_dir / parts[0] / parts[1]
    name = parts[2]
    with data_directory(checkpoint) as directory_fd:
        try:
            fd = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
            )
        except FileNotFoundError:
            if allow_absent:
                return "absent_on_recovery"
            raise
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_size != file["size_bytes"]
                or hashlib.file_digest(stream, "sha256").hexdigest() != file["sha256"]
            ):
                raise ValueError("campaign_artifact_file_changed")
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
                current.st_dev,
                current.st_ino,
                current.st_size,
                current.st_mtime_ns,
            ) or current.st_nlink != 1:
                raise ValueError("campaign_artifact_file_changed")
            os.unlink(name, dir_fd=directory_fd)
            os.fsync(directory_fd)
    return "removed"
