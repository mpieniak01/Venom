"""Persistent fixed-matrix training campaigns driven by the experiment service."""

from __future__ import annotations

import math
import os
import re
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from typing import Protocol

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.remote_training.lifecycle import (
    atomic_json,
    file_lock,
    identity_alive,
    process_identity,
)
from venom_core.services.remote_training.paths import data_directory, operator_path

from .campaign_schema import CampaignSpec
from .retention import (
    ExperimentArtifacts,
    Retention,
    file_fingerprint,
    fingerprint,
    read_object,
)

_CAMPAIGN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
_ACTIVE = frozenset({"running", "awaiting_review", "stopping", "interrupted"})
_RUN_ACTIVE = frozenset({"queued", "running", "stopping"})
_RUN_FINISHED = frozenset({"succeeded", "failed", "stopped", "timed_out"})


class CampaignExperiments(ExperimentArtifacts, Protocol):
    root: Path

    def validate(self, profile_id: str, recipe: dict | None = None) -> dict: ...

    def profiles(self) -> list[dict]: ...

    def free_storage_bytes(self, profile_id: str) -> int: ...

    def status(self, run_id: str) -> dict: ...

    def start(
        self,
        profile_id: str,
        run_id: str,
        recipe: dict | None = None,
        *,
        max_seconds: int | None = None,
        campaign_id: str | None = None,
        expected_identity: str | None = None,
        review_mode: str | None = None,
    ) -> dict: ...

    def stop(self, run_id: str, *, campaign_id: str | None = None) -> dict: ...

    def resume(
        self,
        run_id: str,
        *,
        max_seconds: int | None = None,
        campaign_id: str | None = None,
    ) -> dict: ...

    def evaluate(
        self,
        run_id: str,
        *,
        max_seconds: int | None = None,
        campaign_id: str | None = None,
    ) -> dict: ...

    def report(self, run_id: str) -> dict: ...


def _has_work(run: dict) -> bool:
    return run["status"] in _RUN_ACTIVE or run.get("resources_active") is True


def _run_id(campaign_id: str, index: int) -> str:
    return f"campaign-{campaign_id}-{index + 1:02d}"


def _workload(value: dict) -> dict:
    workload = value["workload"]
    if any(
        type(workload.get(key)) is not int or workload[key] <= 0
        for key in ("updates", "tokens")
    ):
        raise ValueError("campaign_workload_invalid")
    return {key: workload[key] for key in ("updates", "tokens")}


def _plan(spec: CampaignSpec, experiments: CampaignExperiments) -> dict:
    variants: list[dict] = []
    identity = None
    seen: set[str] = set()
    for index, overrides in enumerate(spec.variants):
        validated = experiments.validate(spec.profile_id, overrides)
        if spec.review_mode == "automatic" and not validated["automatic_review"]:
            raise ValueError("campaign_evaluator_not_qualified")
        if identity is not None and identity != validated["identity"]:
            raise ValueError("campaign_profile_changed")
        identity = validated["identity"]
        recipe = validated["recipe"]
        recipe_hash = fingerprint(recipe)
        if recipe_hash in seen:
            raise ValueError("campaign_duplicate_variant")
        seen.add(recipe_hash)
        variants.append(
            {
                "run_id": _run_id(spec.campaign_id, index),
                "recipe": recipe,
                "workload": _workload(validated),
            }
        )
    budget = spec.budget
    if sum(v["workload"]["updates"] for v in variants) > budget.max_updates:
        raise ValueError("campaign_update_budget_exceeded")
    if sum(v["workload"]["tokens"] for v in variants) > budget.max_tokens:
        raise ValueError("campaign_token_budget_exceeded")
    payload = {
        **spec.model_dump(),
        "profile_identity": identity,
        "variants": variants,
    }
    return {**payload, "plan_sha256": fingerprint(payload)}


def _initial_state(plan: dict) -> dict:
    return {
        "campaign_id": plan["campaign_id"],
        "plan": plan,
        "status": "planned",
        "trial_index": 0,
        "trials": [
            {"run_id": item["run_id"], "status": "pending"} for item in plan["variants"]
        ],
        "selected_run_id": None,
        "started_at": None,
        "elapsed_seconds": 0.0,
        "used_updates": 0,
        "used_tokens": 0,
        "retries": 0,
        "artifact_bytes": 0,
        "termination": None,
        "worker": None,
        "error": None,
    }


def _rank(state: dict) -> None:
    selection = state["plan"]["selection"]
    candidates = [
        trial
        for trial in state["trials"]
        if trial.get("result_sha256")
        and trial["usable_delta"] >= selection["min_usable_delta"]
        and trial["critical_delta"] <= selection["max_critical_delta"]
    ]
    winner = max(
        candidates,
        key=lambda row: (row["usable_delta"], -row["critical_delta"]),
        default=None,
    )
    state["selected_run_id"] = winner["run_id"] if winner else None


def _deltas(report: dict) -> dict:
    totals = [report["summaries"][label]["total"] for label in ("base", "candidate")]
    n = totals[0]["n"]
    if type(n) is not int or n < 1:
        raise ValueError("campaign_evaluation_invalid")
    for item in totals:
        if item["n"] != n or any(
            type(item.get(key)) is not int or not 0 <= item[key] <= n
            for key in ("usable", "critical")
        ):
            raise ValueError("campaign_evaluation_invalid")
    return {
        f"{key}_delta": (totals[1][key] - totals[0][key]) / n
        for key in ("usable", "critical")
    }


def _tree_bytes(directory: Path) -> int:
    size = 0
    for root, _dirs, files in os.walk(directory, followlinks=False):
        for name in files:
            try:
                info = (Path(root) / name).lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                size += info.st_size
    return size


class CampaignService:
    """Coordinate durable trial launches while ExperimentService owns each process."""

    def __init__(
        self,
        experiments: CampaignExperiments,
        *,
        launch: Callable[[str], dict | None] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.experiments = experiments
        self.root = operator_path(experiments.root / "campaigns")
        self._launch = launch or self._spawn
        self._clock = clock

    def directory(self, campaign_id: str) -> Path:
        if _CAMPAIGN_ID.fullmatch(campaign_id) is None:
            raise ValueError("campaign_id_invalid")
        return operator_path(self.root / campaign_id)

    @staticmethod
    def _state(directory: Path) -> dict:
        return read_object(directory / "state.json")

    @staticmethod
    def _save(directory: Path, state: dict) -> None:
        atomic_json(directory / "state.json", state)

    def plan(self, spec: CampaignSpec) -> dict:
        ensure_data_mutation_allowed("academy_campaign_plan")
        plan = _plan(spec, self.experiments)
        directory = self.directory(spec.campaign_id)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with file_lock(self.root / ".catalog.lock"):
            directory.mkdir(mode=0o700, exist_ok=True)
            try:
                current = self._state(directory)
            except FileNotFoundError:
                current = _initial_state(plan)
                self._save(directory, current)
            if current["plan"] != plan:
                raise ValueError("campaign_plan_conflict")
            return current

    def list(self) -> list[dict]:
        if not self.root.exists():
            return []
        result = []
        for directory in sorted(self.root.iterdir()):
            if _CAMPAIGN_ID.fullmatch(directory.name) is None:
                continue
            try:
                result.append(self.status(directory.name))
            except FileNotFoundError:
                # A plan being written has not yet been published.
                continue
        return result

    def status(self, campaign_id: str) -> dict:
        state = self._state(self.directory(campaign_id))
        if state["status"] in _ACTIVE and not identity_alive(state["worker"]):
            state["status"] = "interrupted"
        self._elapsed(state)
        return state

    def report(self, campaign_id: str) -> dict:
        return self.status(campaign_id)

    def start(self, campaign_id: str, plan_sha256: str) -> dict:
        return self._activate(campaign_id, plan_sha256=plan_sha256)

    def resume(self, campaign_id: str) -> dict:
        return self._activate(campaign_id)

    def _activate(self, campaign_id: str, *, plan_sha256: str | None = None) -> dict:
        ensure_data_mutation_allowed("academy_campaign_activate")
        directory = self.directory(campaign_id)
        with (
            file_lock(self.root / ".catalog.lock"),
            file_lock(directory / ".state.lock"),
        ):
            state = self._state(directory)
            if plan_sha256 is not None:
                if plan_sha256 != state["plan"]["plan_sha256"]:
                    raise ValueError("campaign_plan_changed")
                if state["status"] != "planned":
                    return state
            if state["status"] == "planned" and plan_sha256 is None:
                raise ValueError("campaign_plan_not_approved")
            if state["status"] not in _ACTIVE | {"planned", "stopped", "blocked"}:
                raise ValueError("campaign_resume_unavailable")
            if state["status"] in _ACTIVE and identity_alive(state["worker"]):
                return state
            self._ensure_single_campaign(campaign_id)
            if state["status"] != "stopping":
                state["status"] = "running"
                self._elapsed(state)
                if state["elapsed_seconds"] >= state["plan"]["budget"]["max_seconds"]:
                    raise ValueError("campaign_time_budget_exhausted")
                state["error"] = None
                state["termination"] = None
            if state["started_at"] is None:
                state["started_at"] = self._clock()
            self._start_worker(directory, state)
            return state

    def _ensure_single_campaign(self, campaign_id: str) -> None:
        for other in self.list():
            if other["campaign_id"] == campaign_id:
                continue
            if other["status"] in _ACTIVE:
                raise ValueError("campaign_already_active")
            if other["status"] == "blocked" and other["trial_index"] < len(
                other["trials"]
            ):
                run = self._run(other, other["trials"][other["trial_index"]])
                if run and _has_work(run):
                    raise ValueError("campaign_already_active")

    def _start_worker(self, directory: Path, state: dict) -> None:
        self._save(directory, state)
        try:
            state["worker"] = self._launch(state["campaign_id"])
        except OSError:
            state["status"] = "interrupted"
            state["error"] = "campaign_supervisor_launch_failed"
        self._save(directory, state)

    def _spawn(self, campaign_id: str) -> dict | None:
        repository = Path(__file__).resolve().parents[3]
        env = {**os.environ, "PYTHONPATH": str(repository)}
        directory = self.directory(campaign_id)
        with data_directory(directory) as directory_fd:
            fd = os.open(
                "supervisor.log",
                os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=directory_fd,
            )
        with os.fdopen(fd, "ab") as output:
            info = os.fstat(output.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OSError("campaign_supervisor_log_invalid")
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "venom_core.services.training_experiments.campaign_worker",
                    str(self.experiments.root),
                    campaign_id,
                ],
                cwd=repository,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
                env=env,
            )
        Thread(target=process.wait, daemon=True).start()
        return process_identity(process.pid)

    def stop(self, campaign_id: str) -> dict:
        ensure_data_mutation_allowed("academy_campaign_stop")
        directory = self.directory(campaign_id)
        with file_lock(directory / ".state.lock"):
            state = self._state(directory)
            if state["status"] in _ACTIVE | {"blocked"}:
                state["termination"] = "stopped"
                state["status"] = "stopping"
                if not identity_alive(state["worker"]):
                    self._start_worker(directory, state)
                else:
                    self._save(directory, state)
            return state

    def _elapsed(self, state: dict) -> None:
        if state["started_at"] is not None and state["status"] in _ACTIVE:
            state["elapsed_seconds"] = max(
                state["elapsed_seconds"], self._clock() - state["started_at"]
            )

    def _profile(self, plan: dict) -> None:
        for profile in self.experiments.profiles():
            if profile["id"] != plan["profile_id"]:
                continue
            if profile["identity"] != plan["profile_identity"]:
                break
            if plan["review_mode"] == "automatic" and not profile["automatic_review"]:
                raise ValueError("campaign_evaluator_not_qualified")
            return
        raise ValueError("campaign_profile_changed")

    def _run(self, state: dict, trial: dict) -> dict | None:
        try:
            run = self.experiments.status(trial["run_id"])
        except FileNotFoundError:
            return None
        if (
            run.get("campaign_id") != state["campaign_id"]
            or run.get("profile_id") != state["plan"]["profile_id"]
            or run.get("profile_identity") != state["plan"]["profile_identity"]
            or run.get("recipe")
            != state["plan"]["variants"][state["trial_index"]]["recipe"]
        ):
            raise ValueError("campaign_trial_conflict")
        return run

    def _artifact_budget(self, state: dict) -> bool:
        state["artifact_bytes"] = sum(
            _tree_bytes(self.experiments.run_dir(trial["run_id"]))
            for trial in state["trials"]
            if trial["status"] != "pending" or trial.get("intent")
        )
        budget = state["plan"]["budget"]
        return (
            state["artifact_bytes"] < budget["max_artifact_bytes"]
            and self.experiments.free_storage_bytes(state["plan"]["profile_id"])
            >= budget["min_free_bytes"]
        )

    def _remaining(self, state: dict, trial: dict) -> int:
        budget = state["plan"]["budget"]
        trial_elapsed = max(0.0, self._clock() - trial.get("started_at", self._clock()))
        trial["elapsed_seconds"] = max(trial.get("elapsed_seconds", 0.0), trial_elapsed)
        return math.floor(
            min(
                budget["trial_seconds"] - trial["elapsed_seconds"],
                budget["max_seconds"] - state["elapsed_seconds"],
            )
        )

    def _reserve(
        self, directory: Path, state: dict, trial: dict, action: str, attempt: int
    ) -> None:
        workload = state["plan"]["variants"][state["trial_index"]]["workload"]
        budget = state["plan"]["budget"]
        for metric in ("updates", "tokens"):
            charge = workload[metric] if action != "evaluate" else 0
            if state[f"used_{metric}"] + charge > budget[f"max_{metric}"]:
                raise ValueError("campaign_retry_workload_budget_exhausted")
        if action != "start":
            state["retries"] += 1
        for metric in ("updates", "tokens"):
            state[f"used_{metric}"] += workload[metric] if action != "evaluate" else 0
        trial.setdefault("started_at", self._clock())
        trial["intent"] = {"action": action, "attempt": attempt}
        self._save(directory, state)

    def _launch_trial(
        self, state: dict, trial: dict, run: dict | None, remaining: int
    ) -> dict:
        intent = trial["intent"]
        action = intent["action"]
        if run and (action == "start" or run["attempt"] > intent["attempt"]):
            # The previous coordinator already committed this launch.
            return run
        self._profile(state["plan"])
        if not self._artifact_budget(state):
            raise ValueError("campaign_storage_budget_exhausted")
        run_id = trial["run_id"]
        if action == "start":
            return self.experiments.start(
                state["plan"]["profile_id"],
                run_id,
                state["plan"]["variants"][state["trial_index"]]["recipe"],
                campaign_id=state["campaign_id"],
                expected_identity=state["plan"]["profile_identity"],
                review_mode=state["plan"]["review_mode"],
                max_seconds=remaining,
            )
        if run is None:
            raise ValueError("campaign_trial_missing")
        if action == "evaluate":
            return self.experiments.evaluate(
                run_id, max_seconds=remaining, campaign_id=state["campaign_id"]
            )
        return self.experiments.resume(
            run_id, max_seconds=remaining, campaign_id=state["campaign_id"]
        )

    def _terminate(self, state: dict, run: dict | None) -> None:
        if run and _has_work(run):
            stopped = self.experiments.stop(
                run["run_id"], campaign_id=state["campaign_id"]
            )
            if _has_work(stopped):
                state["status"] = "stopping"
                return
        state["status"] = state["termination"]
        state["termination"] = None

    def _finish_trial(
        self, directory: Path, state: dict, trial: dict, run: dict
    ) -> None:
        trial.update(
            {
                key: run.get(key)
                for key in ("status", "stage", "attempt", "error", "resume_available")
            }
        )
        trial.pop("intent", None)
        if run["status"] == "succeeded":
            self._record_result(state, trial, run["run_id"])
            _rank(state)
        # Persist the reviewed result and selection before touching a checkpoint.
        self._save(directory, state)
        retention = Retention(self.experiments, directory)
        plan = retention.plan(state)
        if plan["files"]:
            receipt = retention.apply(state, plan["plan_sha256"])
            self._record_retention(state, receipt)
        state["trial_index"] += 1
        state["status"] = (
            "succeeded" if state["trial_index"] == len(state["trials"]) else "running"
        )
        self._artifact_budget(state)

    def _record_result(self, state: dict, trial: dict, run_id: str) -> None:
        with self.experiments.run_lock(run_id):
            run_dir = self.experiments.run_dir(run_id)
            report = self.experiments.report(run_id)
            if report.get("profile_identity") != state["plan"]["profile_identity"]:
                raise ValueError("campaign_evaluation_identity_changed")
            result_sha256 = file_fingerprint(run_dir / "result.json")
            if (
                read_object(run_dir / "result-seal.json").get("result_sha256")
                != result_sha256
            ):
                raise ValueError("campaign_evaluation_seal_changed")
        trial.update(_deltas(report))
        trial["result_sha256"] = result_sha256

    def _retry(self, state: dict, run: dict) -> str | None:
        if run["status"] not in {"failed", "stopped"}:
            return None
        if state["retries"] >= state["plan"]["budget"]["max_retries"]:
            return None
        if run["stage"] in {"generate", "score"} and run["resume_available"]:
            return "evaluate"
        if run["stage"] == "train" and run["resume_available"]:
            pending = state["plan"]["variants"][state["trial_index"] :]
            if all(
                state[f"used_{key}"] + sum(item["workload"][key] for item in pending)
                <= state["plan"]["budget"][f"max_{key}"]
                for key in ("updates", "tokens")
            ):
                return "resume"
        return None

    def _monitor(
        self, directory: Path, state: dict, trial: dict, run: dict, remaining: int
    ) -> bool:
        if not self._artifact_budget(state):
            state["termination"] = "blocked"
            state["error"] = "campaign_storage_budget_exhausted"
            self._terminate(state, run)
            return True
        if remaining < 1:
            stopped = self.experiments.stop(
                run["run_id"], campaign_id=state["campaign_id"]
            )
            if not _has_work(stopped):
                self._finish_trial(
                    directory, state, trial, {**stopped, "status": "timed_out"}
                )
            return True
        if run["status"] not in _RUN_ACTIVE:
            # An orphaned child still owns runtime resources.
            state["status"] = "blocked"
            state["error"] = "campaign_trial_quiescence_unconfirmed"
            return True
        return False

    def _check_limits(
        self,
        directory: Path,
        state: dict,
        trial: dict,
        run: dict | None,
        remaining: int,
    ) -> bool:
        if state["elapsed_seconds"] >= state["plan"]["budget"]["max_seconds"]:
            state["termination"] = "timed_out"
        if state["termination"]:
            self._terminate(state, run)
            return True
        if run is None:
            if remaining < 1:
                state["status"] = "timed_out"
                return True
            return False
        return _has_work(run) and self._monitor(directory, state, trial, run, remaining)

    def _advance(self, directory: Path, state: dict) -> None:
        trial = state["trials"][state["trial_index"]]
        run = self._run(state, trial)
        remaining = self._remaining(state, trial)
        if self._check_limits(directory, state, trial, run, remaining):
            return
        if trial.get("intent") and remaining >= 1:
            run = self._launch_trial(state, trial, run, remaining)
            trial.pop("intent")
        if run is None:
            if trial["status"] != "pending" or "started_at" in trial:
                raise ValueError("campaign_trial_missing")
            self._reserve(directory, state, trial, "start", 0)
            return
        trial.update(
            {
                key: run.get(key)
                for key in ("status", "stage", "attempt", "error", "resume_available")
            }
        )
        if run["status"] == "awaiting_review":
            if remaining < 1:
                self._finish_trial(
                    directory, state, trial, {**run, "status": "timed_out"}
                )
            elif state["plan"]["review_mode"] == "automatic":
                state["status"] = "blocked"
                state["error"] = "campaign_automatic_evaluation_incomplete"
            else:
                state["status"] = "awaiting_review"
            return
        if run["status"] in _RUN_FINISHED:
            retry = self._retry(state, run) if remaining >= 1 else None
            if retry:
                self._reserve(directory, state, trial, retry, run["attempt"])
                state["status"] = "running"
            else:
                self._finish_trial(directory, state, trial, run)
            return
        if run["status"] not in _RUN_ACTIVE:
            raise ValueError("campaign_trial_state_unknown")
        state["status"] = "running"

    def advance(self, campaign_id: str) -> dict:
        """Advance one durable transition. Called by the detached supervisor."""
        ensure_data_mutation_allowed("academy_campaign_advance")
        directory = self.directory(campaign_id)
        with file_lock(directory / ".state.lock"):
            state = self._state(directory)
            if state["status"] not in _ACTIVE:
                return state
            self._elapsed(state)
            try:
                self._advance(directory, state)
            except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
                state["status"] = "blocked"
                code = str(exc)
                state["error"] = (
                    code
                    if re.fullmatch(r"campaign_[a-z0-9_]+", code)
                    else "campaign_stage_failed"
                )
            if state["status"] not in _ACTIVE:
                state["worker"] = None
            self._save(directory, state)
            return state

    @staticmethod
    def _record_retention(state: dict, receipt: dict) -> None:
        state["retention_receipt"] = {
            "plan_sha256": receipt["plan"]["plan_sha256"],
            "removed_bytes": receipt["removed_bytes"],
        }
        removed = {file["run_id"] for file in receipt["files"]}
        for trial in state["trials"]:
            if trial["run_id"] in removed:
                trial["resume_available"] = False

    def retention_plan(self, campaign_id: str) -> dict:
        directory = self.directory(campaign_id)
        with file_lock(directory / ".state.lock"):
            return Retention(self.experiments, directory).plan(self._state(directory))

    def retention_apply(self, campaign_id: str, plan_sha256: str) -> dict:
        ensure_data_mutation_allowed("academy_campaign_retention")
        directory = self.directory(campaign_id)
        with file_lock(directory / ".state.lock"):
            state = self._state(directory)
            if state["status"] in _ACTIVE:
                raise ValueError("campaign_retention_while_active")
            receipt = Retention(self.experiments, directory).apply(state, plan_sha256)
            self._record_retention(state, receipt)
            self._artifact_budget(state)
            self._save(directory, state)
            return receipt
