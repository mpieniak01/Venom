"""Durable single-run control shared by the CLI, Academy and campaigns."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.academy.omni_pl_chat_scoring import aggregate
from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.remote_training.lifecycle import (
    atomic_json,
    file_lock,
    group_alive,
    identity_alive,
    process_identity,
)
from venom_core.services.remote_training.paths import operator_path

from .evidence import (
    historical_report,
    inspect_checkpoint,
    latest_checkpoint,
    review_data,
    sealed_report,
)
from .profiles import (
    Profile,
    check_inputs,
    digest,
    load_profile,
    read_json,
    recipe_for,
    resolve_input,
    stable_hash,
)
from .quality import QualityStore
from .store import RunStore

REPO = Path(__file__).resolve().parents[3]
GENERATION_SEAL = "generation-seal.json"
ACTIVE = frozenset({"queued", "running"})
RETRYABLE = frozenset({"failed", "stopped", "timed_out"})
PUBLIC = (
    "run_id",
    "profile_id",
    "profile_identity",
    "campaign_id",
    "status",
    "stage",
    "created_at",
    "updated_at",
    "attempt",
    "recipe",
    "checkpoint_step",
    "error",
    "elapsed_seconds",
    "report",
    "stop_requested",
)


def launch_worker(root: Path, run_id: str, attempt: int) -> dict:
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "venom_core.services.training_experiments.worker",
            str(root),
            run_id,
            str(attempt),
        ],
        cwd=REPO,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    identity = process_identity(child.pid)
    if identity is None:
        raise RuntimeError("experiment_worker_start_unconfirmed")
    return identity


class ExperimentService:
    def __init__(
        self,
        root: Path,
        *,
        launcher: Callable[[Path, str, int], dict] = launch_worker,
    ) -> None:
        self.store = RunStore(root)
        self.root = self.store.root
        self.launcher = launcher

    def run_dir(self, run_id: str) -> Path:
        return self.store.directory(run_id)

    def run_lock(self, run_id: str):
        return file_lock(operator_path(self.run_dir(run_id) / ".state.lock"))

    def _calibration(self, profile_id: str, profile: Profile) -> dict | None:
        if profile.calibration_sha256 is None:
            return None
        path = self.root / "profiles" / f"{profile_id}.calibration.json"
        if digest(path) != profile.calibration_sha256:
            raise ValueError("experiment_calibration_changed")
        calibration = read_json(path)
        if (
            calibration.get("schema_version") != 1
            or calibration.get("judge") != "exact-v1"
            or calibration.get("dev_sha256") != profile.dev_sha256
            or not isinstance(calibration.get("reviewer"), str)
            or not calibration["reviewer"].strip()
            or not isinstance(calibration.get("cases"), dict)
        ):
            raise ValueError("experiment_calibration_invalid")
        return calibration

    def _validated(
        self, profile_id: str, recipe: dict | None
    ) -> tuple[Profile, dict, dict | None]:
        profile, identity = load_profile(self.root, profile_id)
        parameters = recipe_for(profile, recipe)
        calibration = self._calibration(profile_id, profile)
        info = {
            "profile_id": profile_id,
            "identity": identity,
            "recipe": parameters,
            "automatic_review": calibration is not None,
            "workload": {
                "updates": parameters["steps"],
                "tokens": min(
                    parameters["steps"]
                    * parameters["max_tokens"]
                    * parameters["microbatch"]
                    * parameters["gradient_accumulation_steps"],
                    parameters.get("max_supervised_tokens") or sys.maxsize,
                ),
            },
        }
        return profile, info, calibration

    def profiles(self) -> list[dict]:
        result = []
        for path in sorted((self.root / "profiles").glob("*.json")):
            if "." in path.stem:
                continue
            try:
                profile, info, _ = self._validated(path.stem, None)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                continue
            result.append(
                {
                    "id": path.stem,
                    "label": profile.label,
                    "model": profile.model,
                    "dataset": profile.dataset,
                    **info,
                }
            )
        return result

    def validate(self, profile_id: str, recipe: dict | None = None) -> dict:
        profile, info, _ = self._validated(profile_id, recipe)
        check_inputs(self.root, profile)
        return info

    def _manifest(self, run_id: str) -> dict:
        return read_json(self.run_dir(run_id) / "manifest.json")

    def _checkpoint(self, run_id: str, *, resume: bool = False):
        return latest_checkpoint(self.run_dir(run_id) / "training", resume=resume)

    def _check_report(self, run_id: str) -> dict | None:
        directory = self.run_dir(run_id)
        seal_path = directory / "result-seal.json"
        if not seal_path.is_file():
            return None
        seal = read_json(seal_path)
        path = directory / "result.json"
        if digest(path) != seal["result_sha256"]:
            raise ValueError("experiment_result_changed")
        return read_json(path)

    @staticmethod
    def _orphaned(state: dict) -> bool:
        return state["status"] in ACTIVE and not identity_alive(state.get("supervisor"))

    @staticmethod
    def _child_alive(state: dict) -> bool:
        child = state.get("child")
        return bool(child and group_alive(child["process_group"]))

    def _external_review_fields(self, state: dict, status: str) -> dict:
        """Expose external dispositions alongside an outstanding native review."""
        if status != "awaiting_review":
            return {}
        run_id = state["run_id"]
        records, _ = QualityStore(self.root).list()
        links = [
            record
            for record in records
            if (record.get("reviewed_run") or {}).get("run_id") == run_id
            and record["outcome"] is not None
        ]
        if not links:
            return {}
        generation = self.run_dir(run_id) / f"evaluation-{state['attempt']}"
        try:
            seal = read_json(generation / GENERATION_SEAL)
            manifest = read_json(generation / "manifest.json")
            manifest_sha256 = seal["manifest.json"]
            files = ("blind.jsonl", "raw.jsonl", "unblind.json")
            if (
                any(digest(generation / name) != seal[name] for name in files)
                or digest(generation / "manifest.json") != manifest_sha256
                or any(manifest["outputs"][name] != seal[name] for name in files)
            ):
                return {}
            model = manifest["models"][f"checkpoint-{state['checkpoint_step']}"]
            checkpoint_sha256 = model["adapter_model.safetensors"]
        except (OSError, ValueError, KeyError, TypeError):
            return {}
        matches = [
            record
            for record in links
            if record["reviewed_run"]["generation_manifest_sha256"] == manifest_sha256
            and record["reviewed_run"]["checkpoint_sha256"]
            == checkpoint_sha256
            == state.get("checkpoint_sha256")
        ]
        if len(matches) != 1:
            return {}
        record = matches[0]
        return {
            "external_review": {
                "record_id": f"history:{record['record_id']}",
                "outcome": record["outcome"],
            }
        }

    def _view(self, state: dict) -> dict:
        run_id = state["run_id"]
        result = {key: state.get(key) for key in PUBLIC}
        if self._orphaned(state):
            result.update(status="failed", error="experiment_supervisor_exited")
        committed = self._check_report(run_id)
        if committed is not None and not self._child_alive(state):
            result.update(status="succeeded", stage="done", error=None)
            result["report"] = {"summaries": committed["summaries"]}
        can_retry = result["status"] in RETRYABLE and not self._child_alive(state)
        checkpoint = (
            self._checkpoint(run_id) if result["status"] not in ACTIVE else None
        )
        result["checkpoint_step"] = (
            checkpoint[1]["step"] if checkpoint else state.get("checkpoint_step")
        )
        result["resources_active"] = self._child_alive(state) or (
            state["status"] in ACTIVE and identity_alive(state.get("supervisor"))
        )
        resume_checkpoint = self._checkpoint(run_id, resume=True) if can_retry else None
        result["resume_available"] = bool(
            resume_checkpoint
            and resume_checkpoint[1]["step"] < state["recipe"]["steps"]
        )
        result["evaluation_available"] = bool(can_retry and checkpoint)
        operator_controls = state.get("campaign_id") is None
        result["actions"] = {
            "stop": operator_controls
            and result["status"] in ACTIVE | {"awaiting_review"},
            "resume": operator_controls and result["resume_available"],
            "evaluate": operator_controls and result["evaluation_available"],
            "review": result["status"] == "awaiting_review",
        }
        result.update(self._external_review_fields(state, result["status"]))
        if state["status"] in ACTIVE:
            result["elapsed_seconds"] = state["elapsed_before"] + max(
                0, time.time() - state["attempt_started_at"]
            )
        return result

    def status(self, run_id: str) -> dict:
        # State publication is atomic. Read-only callers never create a lock or index.
        return self._view(self.store.read(run_id))

    def list_runs(self) -> list[dict]:
        return [self.status(run_id) for run_id in self.store.ids()]

    def _save(self, state: dict) -> None:
        state["updated_at"] = time.time()
        self.store.save(state)

    def _enqueue(
        self,
        state: dict,
        *,
        stage: str,
        mode: str,
        max_seconds: int | None,
    ) -> dict:
        run_id = state["run_id"]
        profile = Profile.model_validate(self._manifest(run_id)["profile"])
        limit = (
            profile.max_seconds
            if max_seconds is None
            else min(max_seconds, profile.max_seconds)
        )
        if limit < 1:
            raise ValueError("experiment_budget_exhausted")
        state.update(
            status="queued",
            stage=stage,
            mode=mode,
            attempt=state["attempt"] + 1,
            attempt_started_at=time.time(),
            elapsed_before=state["elapsed_seconds"],
            max_seconds=limit,
            stop_requested=False,
            supervisor=None,
            child=None,
            error=None,
        )
        self._save(state)
        try:
            state["supervisor"] = self.launcher(self.root, run_id, state["attempt"])
        except (OSError, RuntimeError):
            state.update(status="failed", error="experiment_worker_launch_failed")
        self._save(state)
        return self._view(state)

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
    ) -> dict:
        ensure_data_mutation_allowed("academy_experiment_start")
        profile, info, calibration = self._validated(profile_id, recipe)
        if review_mode == "manual":
            calibration = None
        elif review_mode == "automatic" and calibration is None:
            raise ValueError("experiment_evaluator_unqualified")
        elif review_mode not in {None, "automatic"}:
            raise ValueError("experiment_review_mode_invalid")
        if expected_identity is not None and expected_identity != info["identity"]:
            raise ValueError("experiment_profile_changed")
        directory = self.run_dir(run_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "campaign_id": campaign_id,
            "profile_id": profile_id,
            "profile_identity": info["identity"],
            "profile": profile.model_dump(),
            "recipe": info["recipe"],
            "calibration": calibration,
        }
        with self.run_lock(run_id):
            if (directory / "manifest.json").exists():
                if self._manifest(run_id) != manifest:
                    raise ValueError("experiment_run_identity_conflict")
                if (directory / "state.json").exists():
                    return self.status(run_id)
            check_inputs(self.root, profile)
            atomic_json(directory / "manifest.json", manifest)
            atomic_json(directory / "recipe.json", info["recipe"])
            now = time.time()
            state = {
                "schema_version": 1,
                "run_id": run_id,
                "profile_id": profile_id,
                "profile_identity": info["identity"],
                "campaign_id": campaign_id,
                "manifest_sha256": stable_hash(manifest),
                "recipe": info["recipe"],
                "created_at": now,
                "attempt": 0,
                "elapsed_seconds": 0.0,
            }
            return self._enqueue(
                state, stage="train", mode="control", max_seconds=max_seconds
            )

    def _retry(
        self,
        run_id: str,
        *,
        stage: str,
        mode: str,
        max_seconds: int | None,
        campaign_id: str | None,
    ) -> dict:
        ensure_data_mutation_allowed("academy_experiment_retry")
        with self.run_lock(run_id):
            state = self.store.read(run_id)
            self._require_run_owner(state, campaign_id)
            view = self._view(state)
            if view["status"] not in RETRYABLE or self._child_alive(state):
                raise ValueError("experiment_retry_not_allowed")
            checkpoint = self._checkpoint(run_id, resume=mode == "resume")
            if checkpoint is None or (
                mode == "resume" and not view["resume_available"]
            ):
                raise ValueError("experiment_checkpoint_unavailable")
            profile = Profile.model_validate(self._manifest(run_id)["profile"])
            check_inputs(self.root, profile)
            if self._orphaned(state):
                state["elapsed_seconds"] = view["elapsed_seconds"]
            return self._enqueue(state, stage=stage, mode=mode, max_seconds=max_seconds)

    @staticmethod
    def _require_run_owner(state: dict, campaign_id: str | None) -> None:
        if state.get("campaign_id") != campaign_id:
            raise ValueError("experiment_campaign_controls_run")

    def resume(
        self,
        run_id: str,
        *,
        max_seconds: int | None = None,
        campaign_id: str | None = None,
    ) -> dict:
        return self._retry(
            run_id,
            stage="train",
            mode="resume",
            max_seconds=max_seconds,
            campaign_id=campaign_id,
        )

    def evaluate(
        self,
        run_id: str,
        *,
        max_seconds: int | None = None,
        campaign_id: str | None = None,
    ) -> dict:
        return self._retry(
            run_id,
            stage="generate",
            mode="evaluate",
            max_seconds=max_seconds,
            campaign_id=campaign_id,
        )

    def stop(self, run_id: str, *, campaign_id: str | None = None) -> dict:
        ensure_data_mutation_allowed("academy_experiment_stop")
        with self.run_lock(run_id):
            state = self.store.read(run_id)
            self._require_run_owner(state, campaign_id)
            if state["status"] in ACTIVE:
                state["stop_requested"] = True
            elif state["status"] == "awaiting_review":
                state.update(status="stopped", error="experiment_review_stopped")
            self._save(state)
            return self._view(state)

    def free_storage_bytes(self, profile_id: str) -> int:
        profile, _ = load_profile(self.root, profile_id)
        paths = [self.root]
        if profile.backing_volume is not None:
            paths.append(resolve_input(self.root, profile.backing_volume))
        return min(shutil.disk_usage(path).free for path in paths)

    def logs(self, run_id: str) -> dict:
        state = self.store.read(run_id)
        path = operator_path(self.run_dir(run_id) / f"attempt-{state['attempt']}.log")
        if not path.is_file():
            return {"logs": ""}
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 65536))
            return {"logs": stream.read(65536).decode("utf-8", errors="replace")}

    def _review_inputs(self, state: dict) -> tuple[Path, Path]:
        run_id = state["run_id"]
        profile = Profile.model_validate(self._manifest(run_id)["profile"])
        dev = resolve_input(self.root, profile.dev)
        generation = self.run_dir(run_id) / f"evaluation-{state['attempt']}"
        seal = read_json(generation / GENERATION_SEAL)
        if digest(dev) != profile.dev_sha256 or any(
            digest(generation / name) != seal[name]
            for name in ("blind.jsonl", "unblind.json")
        ):
            raise ValueError("experiment_evidence_changed")
        return generation, dev

    def review(self, run_id: str) -> dict:
        state = self.store.read(run_id)
        if state["status"] != "awaiting_review":
            raise ValueError("experiment_review_not_available")
        return review_data(*self._review_inputs(state))

    def _commit(self, state: dict, judgments: list[dict[str, Any]]) -> None:
        run_id = state["run_id"]
        directory = self.run_dir(run_id)
        generation, dev = self._review_inputs(state)
        checkpoint = inspect_checkpoint(
            directory / "training" / f"checkpoint-{state['checkpoint_step']}"
        )
        if checkpoint["sha256"] != state["checkpoint_sha256"]:
            raise ValueError("experiment_checkpoint_changed")
        bundle = review_data(generation, dev)
        aggregate(bundle["cases"], bundle["answers"], judgments)
        verdict_file = generation / "judgments.json"
        if verdict_file.exists():
            if read_json(verdict_file) != judgments:
                raise ValueError("experiment_judgments_sealed")
        else:
            atomic_json(verdict_file, judgments)
        result = sealed_report(generation, dev, judgments, checkpoint)
        result.update(
            run_id=run_id,
            profile_identity=state["profile_identity"],
            manifest_sha256=state["manifest_sha256"],
            dev_sha256=digest(dev),
            judgment_sha256=digest(verdict_file),
            generation_sha256=digest(generation / GENERATION_SEAL),
        )
        atomic_json(directory / "result.json", result)
        atomic_json(
            directory / "result-seal.json",
            {
                "result_sha256": digest(directory / "result.json"),
            },
        )
        state.update(status="succeeded", stage="done", error=None)
        self._save(state)

    def submit(self, run_id: str, judgments: list[dict]) -> dict:
        ensure_data_mutation_allowed("academy_experiment_submit")
        with self.run_lock(run_id):
            state = self.store.read(run_id)
            if self._check_report(run_id) is not None:
                return self._view(state)
            if state["status"] != "awaiting_review":
                raise ValueError("experiment_review_not_available")
            self._commit(state, judgments)
            return self._view(state)

    def import_results(self, run_id: str, source: Path) -> dict:
        ensure_data_mutation_allowed("academy_experiment_import")
        fingerprint = digest(source)
        result = historical_report(read_json(source), fingerprint)
        if digest(source) != fingerprint:
            raise ValueError("experiment_historical_source_changed")
        directory = self.run_dir(run_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.run_lock(run_id):
            if (directory / "manifest.json").exists():
                raise ValueError("experiment_run_identity_conflict")
            existing = self._check_report(run_id)
            if existing is not None and existing.get("source_sha256") != fingerprint:
                raise ValueError("experiment_run_identity_conflict")
            if existing is None:
                atomic_json(directory / "result.json", {**result, "run_id": run_id})
                atomic_json(
                    directory / "result-seal.json",
                    {"result_sha256": digest(directory / "result.json")},
                )
            if not (directory / "state.json").exists():
                now = time.time()
                self._save(
                    {
                        "schema_version": 1,
                        "run_id": run_id,
                        "profile_id": "historical",
                        "profile_identity": fingerprint,
                        "status": "succeeded",
                        "stage": "done",
                        "created_at": now,
                        "attempt": 0,
                        "recipe": {},
                        "elapsed_seconds": 0.0,
                        "checkpoint_step": result["checkpoint"]["step"],
                    }
                )
            return self.status(run_id)

    def report(self, run_id: str) -> dict:
        result = self._check_report(run_id)
        if result is None:
            raise FileNotFoundError("experiment_result_missing")
        if result.get("historical"):
            return result
        artifact = result["artifacts"][0]
        checkpoint = (
            self.run_dir(run_id) / "training" / f"checkpoint-{artifact['step']}"
        )
        try:
            artifact["available"] = (
                inspect_checkpoint(checkpoint)["sha256"] == artifact["sha256"]
            )
        except (OSError, ValueError, KeyError, TypeError):
            artifact["available"] = False
        return result
