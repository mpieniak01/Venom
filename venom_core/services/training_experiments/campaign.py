"""Persistent fixed-matrix training campaigns driven by the experiment service."""

from __future__ import annotations

import math
import os
import re
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from itertools import product
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

from . import optuna_backend, quality_guard, quality_native
from .adapters import verify_adapter_entry
from .campaign_schema import CampaignSpec
from .checkpoint_evaluation import validate_steps
from .profiles import digest, stable_hash
from .retention import (
    ExperimentArtifacts,
    Retention,
    file_fingerprint,
    fingerprint,
    read_object,
)

_CAMPAIGN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
_ACTIVE = frozenset(
    {"running", "awaiting_review", "stopping", "interrupted", "qualifying"}
)
_RUN_ACTIVE = frozenset({"queued", "running", "stopping"})
_RUN_FINISHED = frozenset({"succeeded", "failed", "stopped", "timed_out"})


class CampaignExperiments(ExperimentArtifacts, Protocol):
    root: Path

    def validate(self, profile_id: str, recipe: dict | None = None) -> dict: ...

    def profiles(self) -> list[dict]: ...

    def free_storage_bytes(self, profile_id: str) -> int: ...

    def run_dir(self, run_id: str) -> Path: ...

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
        expected_initial_adapter: dict | None = None,
        checkpoint_steps: list[int] | None = None,
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

    def checkpoint_report(self, run_id: str, step: int) -> tuple[dict, str]: ...


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


def _is_optuna(plan: dict) -> bool:
    return plan.get("strategy") == "optuna"


def _validate_trial(
    spec: CampaignSpec, experiments: CampaignExperiments, recipe: dict | None
) -> dict:
    validated = experiments.validate(spec.profile_id, recipe)
    if recipe and "train_sha256" in recipe:
        if recipe["train_sha256"] != validated["recipe"].get("train_sha256"):
            raise ValueError("campaign_quality_training_identity_changed")
    if spec.review_mode == "automatic" and not validated["automatic_review"]:
        raise ValueError("campaign_evaluator_not_qualified")
    return validated


def _fixed_variants(
    spec: CampaignSpec, experiments: CampaignExperiments
) -> tuple[str, list[dict]]:
    variants: list[dict] = []
    identity = None
    seen: set[str] = set()
    for index, overrides in enumerate(spec.variants):
        validated = _validate_trial(spec, experiments, overrides)
        if identity is not None and identity != validated["identity"]:
            raise ValueError("campaign_profile_changed")
        identity = validated["identity"]
        recipe = validated["recipe"]
        if spec.checkpoint_steps is not None:
            validate_steps(spec.checkpoint_steps, recipe)
        audit = validated.get("data_audit")
        adapter = validated.get("initial_adapter")
        initialization = {"initial_adapter": adapter} if adapter is not None else {}
        recipe_hash = fingerprint((recipe, initialization))
        if recipe_hash in seen:
            raise ValueError("campaign_duplicate_variant")
        seen.add(recipe_hash)
        variants.append(
            {
                "run_id": _run_id(spec.campaign_id, index),
                "recipe": recipe,
                "workload": _workload(validated),
                **initialization,
                **({"data_audit": audit} if audit is not None else {}),
            }
        )
    if identity is None:
        raise ValueError("campaign_fixed_variants_required")
    return identity, variants


def _optimization_plan(
    spec: CampaignSpec, experiments: CampaignExperiments
) -> tuple[str, list[dict], dict]:
    space = optuna_backend.validate_search_space(
        {
            name: bounds.model_dump(exclude_none=True)
            for name, bounds in (spec.search_space or {}).items()
        }
    )
    version = optuna_backend.require_optuna()
    base = _validate_trial(spec, experiments, None)
    workload = _workload(base)
    audit = base.get("data_audit")
    for values in product(*[(item["low"], item["high"]) for item in space.values()]):
        recipe = dict(zip(space, values, strict=True))
        corner = _validate_trial(spec, experiments, recipe)
        if corner["identity"] != base["identity"]:
            raise ValueError("campaign_profile_changed")
        if corner.get("data_audit") != audit:
            raise ValueError("experiment_data_audit_changed")
        for metric, amount in _workload(corner).items():
            workload[metric] = max(workload[metric], amount)
    variants = [
        {
            "run_id": _run_id(spec.campaign_id, index),
            "recipe": base["recipe"],
            "workload": workload,
            **({"data_audit": audit} if audit is not None else {}),
        }
        for index in range(spec.budget.max_trials)
    ]
    return (
        base["identity"],
        variants,
        {
            "strategy": "optuna",
            "search_space": space,
            "sampler_seed": spec.sampler_seed,
            "optuna_version": version,
        },
    )


def _plan_audit(variants: list[dict]) -> dict | None:
    audit = variants[0].get("data_audit")
    if any(variant.get("data_audit") != audit for variant in variants):
        raise ValueError("experiment_data_audit_changed")
    return audit


def _freeze_extension(spec: CampaignSpec, variants: list[dict]) -> dict | None:
    if spec.extension is None:
        return None
    frozen = spec.extension.model_dump()
    if not spec.extension.repeat_best_recipe:
        frozen.pop("repeat_best_recipe")
        return frozen
    parents = [variant.get("initial_adapter") for variant in variants]
    if parents[0] is None or any(parent != parents[0] for parent in parents):
        raise ValueError("campaign_repeat_parent_changed")
    initial = spec.extension.initial_trials
    repeats = variants[initial:]
    mapping = {}
    excluded = {"seed", "max_supervised_tokens"}
    for source in variants[:initial]:
        recipe = source["recipe"]
        comparable = {
            key: value for key, value in recipe.items() if key not in excluded
        }
        matches = [
            candidate
            for candidate in repeats
            if candidate["recipe"].get("seed") != recipe.get("seed")
            and {
                key: value
                for key, value in candidate["recipe"].items()
                if key not in excluded
            }
            == comparable
        ]
        if len(matches) != 1:
            raise ValueError("campaign_repeat_recipe_mismatch")
        mapping[source["run_id"]] = matches[0]["run_id"]
    if len(set(mapping.values())) != initial:
        raise ValueError("campaign_repeat_recipe_mismatch")
    return {**frozen, "repeat_variants": mapping}


def _bounded_workload(
    variants: list[dict],
    extension: dict | None,
    metric: str,
    *,
    start: int = 0,
    skipped: set[int] | None = None,
) -> int:
    """Reserve the initial block plus at most one pre-frozen repeat alternative."""
    total, alternatives = 0, []
    for index, variant in enumerate(variants[start:], start=start):
        if skipped and index in skipped:
            continue
        amount = variant["workload"][metric]
        if (
            extension
            and extension.get("repeat_best_recipe")
            and index >= extension["initial_trials"]
        ):
            alternatives.append(amount)
        else:
            total += amount
    return total + max(alternatives, default=0)


def _freeze_plan_quality_policy(
    spec: CampaignSpec,
    experiments: CampaignExperiments,
    variants: list[dict],
    payload: dict,
) -> None:
    if spec.quality_policy is None:
        return
    context = quality_native.profile_context(
        experiments,
        spec.profile_id,
        spec.review_mode,
        include_runtime=spec.quality_policy.source_record_id is not None,
    )
    if "checkpoint_evaluation_identity" in payload:
        context["identity"] = payload["checkpoint_evaluation_identity"]
    if spec.quality_policy.parent_reference_record_id is not None:
        parents = [variant.get("initial_adapter") for variant in variants]
        if (
            not parents
            or parents[0] is None
            or any(parent != parents[0] for parent in parents)
        ):
            raise ValueError("campaign_quality_parent_adapter_required")
        context["initial_adapter_sha256"] = parents[0]["weights_sha256"]
    payload["quality_policy"] = quality_guard.freeze_policy(
        spec.quality_policy.model_dump(
            exclude={"protect_parent_full_pass"}
            if not spec.quality_policy.protect_parent_full_pass
            else set()
        ),
        context,
        lambda record_id: quality_native.get_record(experiments, record_id),
    )


def _plan(spec: CampaignSpec, experiments: CampaignExperiments) -> dict:
    extra: dict = {}
    if spec.strategy == "optuna":
        identity, variants, extra = _optimization_plan(spec, experiments)
    else:
        identity, variants = _fixed_variants(spec, experiments)
    audit = _plan_audit(variants)
    if audit is not None:
        extra["data_audit"] = audit
        for variant in variants:
            variant.pop("data_audit")
    if spec.checkpoint_steps is not None:
        extra["checkpoint_steps"] = spec.checkpoint_steps
        extra["checkpoint_evaluation_identity"] = (
            quality_native.frozen_evaluation_identity(
                experiments, spec.profile_id, spec.review_mode
            )
        )
    extension = _freeze_extension(spec, variants)
    budget = spec.budget
    if _bounded_workload(variants, extension, "updates") > budget.max_updates:
        raise ValueError("campaign_update_budget_exceeded")
    if _bounded_workload(variants, extension, "tokens") > budget.max_tokens:
        raise ValueError("campaign_token_budget_exceeded")
    payload = {
        **spec.model_dump(
            exclude={
                "strategy",
                "search_space",
                "sampler_seed",
                "quality_policy",
                "checkpoint_steps",
                "extension",
                "final_qualification",
            }
        ),
        **extra,
        "profile_identity": identity,
        "variants": variants,
    }
    if not spec.selection.protect_parent_full_pass:
        payload["selection"].pop("protect_parent_full_pass")
    if extension is not None:
        payload["extension"] = extension
    _freeze_plan_quality_policy(spec, experiments, variants, payload)
    if spec.final_qualification is not None:
        from .local_campaign_final import freeze_inputs

        payload["final_qualification"] = freeze_inputs(
            experiments.root, payload, spec.final_qualification.model_dump()
        )
    return {**payload, "plan_sha256": fingerprint(payload)}


def _initial_state(plan: dict) -> dict:
    return {
        "campaign_id": plan["campaign_id"],
        **(
            {
                "phase": "trials",
                "qualification_status": "pending",
                "qualification_attempts": 0,
            }
            if plan.get("final_qualification")
            else {}
        ),
        "plan": plan,
        "status": "planned",
        "trial_index": 0,
        "trials": [
            {"run_id": item["run_id"], "status": "pending"} for item in plan["variants"]
        ],
        "selected_run_id": None,
        **({"selected_checkpoint_step": None} if "checkpoint_steps" in plan else {}),
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


def _current_variant(state: dict) -> dict:
    return state["plan"]["variants"][state["trial_index"]]


def _actual_recipe(state: dict, trial: dict) -> dict:
    return trial.get("recipe", _current_variant(state)["recipe"])


def _parent_metrics(item: dict, guard: dict) -> None:
    parent = guard.get("parent_delta")
    if parent is not None:
        for key in ("usable_delta", "critical_delta"):
            item[f"m0_{key}"] = item[key]
            item[key] = parent[key]


def _passes_selection(row: dict, selection: dict) -> bool:
    if (
        row.get("critical_delta") is None
        or row["usable_delta"] < selection["min_usable_delta"]
        or row["critical_delta"] > selection["max_critical_delta"]
    ):
        return False
    if selection.get("protect_parent_full_pass"):
        full = (
            row.get("quality_guard", {}).get("parent_delta", {}).get("full_pass_delta")
        )
        return full is not None and full > 0 and full >= selection["min_usable_delta"]
    return True


def _selection_key(row: dict) -> tuple[float, float, float]:
    return (
        row["usable_delta"],
        -row["critical_delta"],
        row.get("quality_guard", {})
        .get("parent_delta", {})
        .get("full_pass_delta", 0.0),
    )


def _rank(state: dict) -> None:
    if "checkpoint_steps" in state["plan"]:
        _rank_checkpoints(state)
        return
    selection = state["plan"]["selection"]
    guarded = state["plan"].get("quality_policy") is not None
    if guarded and state.get("quality_policy_error"):
        state["selected_run_id"] = None
        return
    candidates = [
        trial
        for trial in state["trials"]
        if trial.get("result_sha256")
        and (not guarded or trial.get("quality_guard", {}).get("status") == "passed")
        and _passes_selection(trial, selection)
    ]
    winner = max(
        candidates,
        key=_selection_key,
        default=None,
    )
    state["selected_run_id"] = winner["run_id"] if winner else None


def _rank_checkpoints(state: dict) -> None:
    if state.get("quality_policy_error"):
        state["selected_run_id"] = state["selected_checkpoint_step"] = None
        return
    qualified = (
        (trial["run_id"], item)
        for trial in state["trials"]
        if trial["status"] == "succeeded"
        for item in trial.get("checkpoint_evaluations", ())
        if item.get("qualified") is True
    )
    run_id, winner = max(
        qualified,
        key=lambda choice: (*_selection_key(choice[1]), -choice[1]["step"]),
        default=(None, None),
    )
    state["selected_run_id"] = run_id
    state["selected_checkpoint_step"] = winner["step"] if winner else None


def _extension_decision(state: dict, policy: dict) -> dict:
    selected = state["selected_run_id"]
    step = state.get("selected_checkpoint_step")
    winner: dict = next(
        (
            trial
            for trial in state["trials"][: state["trial_index"]]
            if trial["run_id"] == selected
        ),
        {},
    )
    if step is not None:
        winner = next(
            (
                row
                for row in winner.get("checkpoint_evaluations", ())
                if row["step"] == step
            ),
            {},
        )
    gain = winner.get("usable_delta")
    approved = (
        gain is not None
        and gain >= policy["min_usable_delta"]
        and _passes_selection(winner, state["plan"]["selection"])
    )
    return {
        "status": "approved" if approved else "skipped",
        "run_id": selected,
        "checkpoint_step": step,
        "usable_delta": gain,
        "result_sha256": winner.get("result_sha256"),
        **(
            {
                "full_pass_delta": winner.get("quality_guard", {})
                .get("parent_delta", {})
                .get("full_pass_delta")
            }
            if state["plan"]["selection"].get("protect_parent_full_pass")
            else {}
        ),
    }


def _allow_extension(state: dict) -> bool:
    policy = state["plan"].get("extension")
    if policy is None or state["trial_index"] != policy["initial_trials"]:
        return True
    if "extension_decision" not in state:
        if state["selected_run_id"] is None:
            _rank(state)
        state["extension_decision"] = _extension_decision(state, policy)
    decision = state["extension_decision"]
    if decision["status"] == "approved" and policy.get("repeat_best_recipe"):
        repeated = policy["repeat_variants"][decision["run_id"]]
        if decision.get("repeat_run_id", repeated) != repeated:
            raise ValueError("campaign_repeat_selection_changed")
        decision["repeat_run_id"] = repeated
        for trial in state["trials"][policy["initial_trials"] :]:
            if trial["run_id"] != repeated:
                trial.update(status="skipped", error="campaign_repeat_not_selected")
    return decision["status"] == "approved"


def _repeat_candidates(state: dict, trial: dict) -> list[dict]:
    rows = (
        trial.get("checkpoint_evaluations", [])
        if "checkpoint_steps" in state["plan"]
        else [trial]
    )
    policy = state["plan"]["extension"]
    return [
        item
        for item in rows
        if trial["status"] == "succeeded"
        and item.get("result_sha256")
        and item.get("quality_guard", {}).get("status") == "passed"
        and (
            state["plan"].get("conversation_review") is None
            or item.get("conversation_review_status") == "pass"
        )
        and _passes_selection(item, state["plan"]["selection"])
        and item["usable_delta"] >= policy["min_usable_delta"]
    ]


def development_complete(state: dict) -> bool:
    """A missing candidate is a quality decision only with complete development."""
    trials = [trial for trial in state["trials"] if trial["status"] != "skipped"]
    if not trials or state.get("quality_policy_error"):
        return False
    steps = state["plan"].get("checkpoint_steps")
    guarded = state["plan"].get("quality_policy") is not None
    for trial in trials:
        if trial["status"] != "succeeded":
            return False
        rows = trial.get("checkpoint_evaluations", []) if steps is not None else [trial]
        if steps is not None and (
            len(rows) != len(steps) or {row.get("step") for row in rows} != set(steps)
        ):
            return False
        if any(
            row.get("status") != "succeeded"
            or not row.get("result_sha256")
            or guarded
            and row.get("quality_guard", {}).get("status") not in {"passed", "rejected"}
            for row in rows
        ):
            return False
    return True


def _confirm_repeat(state: dict) -> None:
    policy = state["plan"].get("extension", {})
    if not policy.get("repeat_best_recipe") or state["status"] not in {
        "succeeded",
        "timed_out",
        "stopped",
        "blocked",
        "awaiting_review",
    }:
        return
    decision = state.get("extension_decision", {})
    repeat_id = decision.get("repeat_run_id")
    repeat: dict = next(
        (trial for trial in state["trials"] if trial["run_id"] == repeat_id), {}
    )
    confirmation = {
        "status": "incomplete",
        "reason": "campaign_repeat_not_confirmed",
        "source_run_id": decision.get("run_id"),
        "source_checkpoint_step": decision.get("checkpoint_step"),
        "source_result_sha256": decision.get("result_sha256"),
        "repeat_run_id": repeat_id,
    }
    # Interrupted execution is not evidence of poor model quality.
    eligible = _repeat_candidates_for_step(state, repeat, decision)
    if _repeat_review_pending(state, repeat, decision) and _can_select_repeat(state):
        _wait_for_repeat_review(state, confirmation)
    elif _can_select_repeat(state) and eligible:
        _confirm_repeat_success(state, decision, repeat, eligible, confirmation)
    else:
        _record_repeat_failure(state, decision, repeat, confirmation)
    state["repeat_confirmation"] = confirmation


def _repeat_candidates_for_step(
    state: dict, repeat: dict, decision: dict
) -> list[dict]:
    if not repeat:
        return []
    step = decision.get("checkpoint_step")
    return [
        item for item in _repeat_candidates(state, repeat) if item.get("step") == step
    ]


def _repeat_review_pending(state: dict, repeat: dict, decision: dict) -> bool:
    if not state["plan"].get("conversation_review"):
        return False
    source_id = decision.get("run_id")
    step = decision.get("checkpoint_step")
    source: dict = next(
        (trial for trial in state["trials"] if trial["run_id"] == source_id), {}
    )
    return any(
        row.get("conversation_review_status") == "pending"
        for trial in (source, repeat)
        for row in trial.get("checkpoint_evaluations", ())
        if row.get("step") == step
    )


def _can_select_repeat(state: dict) -> bool:
    return state["status"] not in {"stopped", "blocked"}


def _wait_for_repeat_review(state: dict, confirmation: dict) -> None:
    confirmation.update(status="pending_review", reason="pending_conversation_review")
    state["selected_run_id"] = None
    if "selected_checkpoint_step" in state:
        state["selected_checkpoint_step"] = None


def _record_repeat_failure(
    state: dict, decision: dict, repeat: dict, confirmation: dict
) -> None:
    completed = _repeat_step_complete(repeat, decision.get("checkpoint_step")) or (
        decision.get("status") == "skipped" and state["status"] == "succeeded"
    )
    if not development_complete(state):
        confirmation["reason"] = "campaign_development_incomplete"
    elif completed and _can_select_repeat(state):
        confirmation.update(
            status="failed_quality", reason="campaign_repeat_failed_quality"
        )
    state["selected_run_id"] = None
    if "selected_checkpoint_step" in state:
        state["selected_checkpoint_step"] = None


def _repeat_step_complete(trial: dict, step: int | None) -> bool:
    rows = trial.get("checkpoint_evaluations", []) if step is not None else [trial]
    return trial.get("status") == "succeeded" and any(
        item.get("step") == step
        and item.get("status") == "succeeded"
        and item.get("result_sha256")
        for item in rows
    )


def _confirm_repeat_success(
    state: dict,
    decision: dict,
    repeat: dict,
    eligible: list[dict],
    confirmation: dict,
) -> None:
    best = max(eligible, key=lambda item: (*_selection_key(item), -item.get("step", 0)))
    confirmation.update(
        status="passed",
        reason=None,
        repeat_checkpoint_step=best.get("step"),
        repeat_result_sha256=best["result_sha256"],
        usable_delta=best["usable_delta"],
        full_pass_delta=best["quality_guard"]
        .get("parent_delta", {})
        .get("full_pass_delta"),
    )
    source = next(
        trial for trial in state["trials"] if trial["run_id"] == decision["run_id"]
    )
    source_rows = {item.get("step"): item for item in _repeat_candidates(state, source)}
    repeat_rows = {item.get("step"): item for item in _repeat_candidates(state, repeat)}
    common = source_rows.keys() & repeat_rows.keys()
    pair = [
        (run_id, rows[step])
        for run_id, rows in (
            (source["run_id"], source_rows),
            (repeat["run_id"], repeat_rows),
        )
        for step in common
    ]
    run_id, winner = max(
        pair, key=lambda choice: (*_selection_key(choice[1]), -choice[1].get("step", 0))
    )
    step = winner.get("step")
    confirmation.update(
        finalist_run_id=run_id,
        finalist_checkpoint_step=step,
        paired_source_result_sha256=source_rows[step]["result_sha256"],
        paired_repeat_result_sha256=repeat_rows[step]["result_sha256"],
    )
    state["selected_run_id"] = run_id
    if "selected_checkpoint_step" in state:
        state["selected_checkpoint_step"] = step


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


def _reassessing_quality(state: dict) -> bool:
    index = state["trial_index"]
    if index >= len(state["trials"]):
        return False
    trial = state["trials"][index]
    return (
        trial["status"] == "succeeded"
        and trial.get("quality_guard", {}).get("status") == "blocked"
    )


def _block_missing_quality(state: dict, trial: dict) -> bool:
    reason = state.get("quality_policy_error")
    guard = trial.get("quality_guard", {})
    if reason is None and guard.get("status") == "blocked":
        reason = guard["reasons"][0]["code"]
    if reason is None:
        return False
    state.update(status="blocked", error=reason)
    return True


def _quality_error(exc: Exception) -> str:
    code = str(exc)
    if re.fullmatch(r"campaign_quality_[a-z0-9_]+", code):
        return code
    if re.fullmatch(r"conversation_review_[a-z0-9_]+", code):
        return f"campaign_quality_{code}"
    return "campaign_quality_evidence_unavailable"


def _check_suggestion(space: dict, params: dict) -> None:
    if not isinstance(params, dict) or params.keys() != space.keys():
        raise ValueError("campaign_optuna_suggestion_invalid")
    for name, value in params.items():
        allowed = (int,) if name in {"rank", "alpha"} else (int, float)
        if (
            type(value) not in allowed
            or not space[name]["low"] <= value <= space[name]["high"]
        ):
            raise ValueError("campaign_optuna_suggestion_invalid")


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

    def validate(self, spec: CampaignSpec) -> dict:
        return _plan(spec, self.experiments)

    def plan(self, spec: CampaignSpec) -> dict:
        ensure_data_mutation_allowed("academy_campaign_plan")
        plan = self.validate(spec)
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
        self._review_selection(state)
        self._review_repeat_confirmation(state)
        if state["plan"].get("final_qualification"):
            from .local_campaign_final import observe

            observe(self.experiments.root, state)
        return state

    def _review_selection(self, state: dict) -> None:
        self._refresh_pending_conversation_reviews(state)
        self._verify_selected_quality(state)

    def _refresh_pending_conversation_reviews(self, state: dict) -> None:
        config = state["plan"].get("conversation_review")
        if config is None:
            return
        from .conversation_review import checkpoint_review_id

        pending = [
            (trial, row)
            for trial in state["trials"]
            if trial["status"] == "succeeded"
            for row in trial.get("checkpoint_evaluations", ())
            if row.get("conversation_review_status") == "pending"
            and (
                self.directory(state["campaign_id"])
                / "conversation-reviews"
                / checkpoint_review_id(
                    config["receipt_id_prefix"], trial["run_id"], row["step"]
                )
                / "receipt.json"
            ).is_file()
        ]
        pending_by_trial: dict[str, tuple[dict, set[int]]] = {}
        for trial, row in pending:
            if trial["run_id"] not in pending_by_trial:
                pending_by_trial[trial["run_id"]] = (trial, set())
            pending_by_trial[trial["run_id"]][1].add(row["step"])
        for trial, steps in pending_by_trial.values():
            self._record_checkpoint_results(
                state,
                trial,
                state["plan"].get("quality_policy"),
                steps=steps,
            )
        if pending:
            _rank(state)

    def _verify_selected_quality(self, state: dict) -> None:
        requires_verification = (
            state["plan"].get("quality_policy") or "checkpoint_steps" in state["plan"]
        )
        if not requires_verification or not state["selected_run_id"]:
            return
        try:
            self._verify_quality_policy(state["plan"])
            winner = next(
                trial
                for trial in state["trials"]
                if trial["run_id"] == state["selected_run_id"]
            )
            self._verify_quality_winner(state, winner)
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
            self._invalidate_quality_selection(state, exc)

    @staticmethod
    def _invalidate_quality_selection(state: dict, error: Exception) -> None:
        state["selected_run_id"] = None
        if "selected_checkpoint_step" in state:
            state["selected_checkpoint_step"] = None
        if state["plan"].get("conversation_review") is not None:
            state.update(
                status="blocked",
                phase="complete",
                qualification_status="incomplete",
                quality_policy_error="campaign_quality_conversation_review_changed",
                error="campaign_quality_conversation_review_changed",
                worker=None,
            )
        else:
            state["quality_policy_error"] = _quality_error(error)

    def _review_repeat_confirmation(self, state: dict) -> None:
        confirmation = state.get("repeat_confirmation", {})
        if confirmation.get("status") == "pending_review":
            _confirm_repeat(state)
            confirmation = state.get("repeat_confirmation", {})
        if confirmation.get("status") != "passed":
            return
        try:
            self._verify_repeat_confirmation(state, confirmation)
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            confirmation.update(
                status="incomplete", reason="campaign_repeat_confirmation_changed"
            )
            state["selected_run_id"] = None
            if "selected_checkpoint_step" in state:
                state["selected_checkpoint_step"] = None

    def _verify_repeat_confirmation(self, state: dict, confirmation: dict) -> None:
        if (
            state["selected_run_id"] != confirmation["finalist_run_id"]
            or state.get("selected_checkpoint_step")
            != confirmation["finalist_checkpoint_step"]
        ):
            raise ValueError("campaign_repeat_confirmation_changed")
        for prefix in ("source", "repeat"):
            self._verify_repeat_confirmation_run(state, confirmation, prefix)

    def _verify_repeat_confirmation_run(
        self, state: dict, confirmation: dict, prefix: str
    ) -> None:
        run_id = confirmation[f"{prefix}_run_id"]
        trial = next(item for item in state["trials"] if item["run_id"] == run_id)
        paired_results = (
            (
                confirmation[f"{prefix}_checkpoint_step"],
                confirmation[f"{prefix}_result_sha256"],
            ),
            (
                confirmation["finalist_checkpoint_step"],
                confirmation[f"paired_{prefix}_result_sha256"],
            ),
        )
        for step, checksum in paired_results:
            item = self._repeat_confirmation_item(trial, step)
            if item["result_sha256"] != checksum:
                raise ValueError("campaign_repeat_confirmation_changed")
            self._verify_quality_winner(
                {**state, "selected_checkpoint_step": step}, trial
            )

    @staticmethod
    def _repeat_confirmation_item(trial: dict, step: int | None) -> dict:
        if step is None:
            return trial
        return next(
            row for row in trial["checkpoint_evaluations"] if row["step"] == step
        )

    def report(self, campaign_id: str) -> dict:
        return self.status(campaign_id)

    def evaluations(self, state: dict) -> dict[str, dict]:
        """Expose aggregate evidence for the exact results recorded by this campaign."""
        evaluations = {}
        for trial in state["trials"]:
            expected = trial.get("result_sha256")
            if not expected:
                continue
            run_id = trial["run_id"]
            try:
                report, observed = self._read_evaluation(
                    run_id, state["plan"]["profile_identity"]
                )
                if observed != expected:
                    continue
                evidence = (
                    self._checkpoint_evidence(state, trial)
                    if "checkpoint_steps" in state["plan"]
                    else self._evaluation_totals(report)
                )
                if evidence is not None:
                    evaluations[run_id] = evidence
            except (OSError, ValueError, TypeError, KeyError, StopIteration):
                # Missing or stale evidence remains unavailable in the comparison.
                continue
        return evaluations

    @staticmethod
    def _evaluation_totals(report: dict) -> dict:
        totals = report["summaries"]
        return {
            "base": totals["base"]["total"],
            "candidate": totals["candidate"]["total"],
            "adapter_available": any(
                artifact.get("available") is True for artifact in report["artifacts"]
            ),
        }

    def _checkpoint_evidence(self, state: dict, trial: dict) -> dict | None:
        checkpoints = self._checkpoint_evaluations(trial)
        if not checkpoints:
            return None
        step = (
            state.get("selected_checkpoint_step")
            if trial["run_id"] == state.get("selected_run_id")
            else checkpoints[-1]["step"]
        )
        anchor = next(item for item in checkpoints if item["step"] == step)
        return {**anchor, "checkpoints": checkpoints}

    def _checkpoint_evaluations(self, trial: dict) -> Sequence[dict]:
        checkpoint_rows = []
        run_id = trial["run_id"]
        with self.experiments.run_lock(run_id):
            for item in trial.get("checkpoint_evaluations", ()):
                step = item["step"]
                report, result_sha = self.experiments.checkpoint_report(run_id, step)
                if result_sha != item.get("result_sha256"):
                    raise ValueError("campaign_quality_result_changed")
                checkpoint_rows.append(
                    {"step": step, **self._evaluation_totals(report)}
                )
        return checkpoint_rows

    def start(
        self, campaign_id: str, plan_sha256: str, *, cutoff_at: float | None = None
    ) -> dict:
        return self._activate(campaign_id, plan_sha256=plan_sha256, cutoff_at=cutoff_at)

    def resume(self, campaign_id: str) -> dict:
        return self._activate(campaign_id)

    def _activate(
        self,
        campaign_id: str,
        *,
        plan_sha256: str | None = None,
        cutoff_at: float | None = None,
    ) -> dict:
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
                    if state.get("cutoff_at") != cutoff_at:
                        raise ValueError("campaign_execution_cutoff_changed")
                    return state
                if cutoff_at is not None:
                    if not math.isfinite(cutoff_at) or cutoff_at <= self._clock():
                        raise ValueError("campaign_execution_cutoff_expired")
                    state["cutoff_at"] = cutoff_at
            if state["status"] == "planned" and plan_sha256 is None:
                raise ValueError("campaign_plan_not_approved")
            if state.get("phase") == "complete":
                raise ValueError("campaign_resume_unavailable")
            if state["status"] not in _ACTIVE | {"planned", "stopped", "blocked"}:
                raise ValueError("campaign_resume_unavailable")
            if state["status"] in _ACTIVE and identity_alive(state["worker"]):
                return state
            self._ensure_single_campaign(campaign_id)
            if state.get("phase") == "qualification":
                state["status"] = "qualifying"
            elif state["status"] != "stopping":
                if state["plan"].get("final_qualification"):
                    from .local_campaign_final import pin_inputs

                    pin_inputs(self.experiments.root, state)
                self._prepare_activation(state)
            if state["started_at"] is None:
                state["started_at"] = self._clock()
                if state["plan"].get("final_qualification"):
                    deadline = (
                        state["started_at"] + state["plan"]["budget"]["max_seconds"]
                    )
                    state["deadline_at"] = min(
                        deadline, state.get("cutoff_at", deadline)
                    )
            self._start_worker(directory, state)
            return state

    def _prepare_activation(self, state: dict) -> None:
        plan = state["plan"]
        if plan["plan_sha256"] != fingerprint(
            {key: value for key, value in plan.items() if key != "plan_sha256"}
        ):
            raise ValueError("campaign_plan_changed")
        self._verify_activation_inputs(plan, first_start=state["status"] == "planned")
        state.pop("quality_policy_error", None)
        optimized = _is_optuna(plan)
        if optimized and optuna_backend.require_optuna() != plan["optuna_version"]:
            raise ValueError("campaign_optuna_version_changed")
        state["status"] = "running"
        self._elapsed(state)
        expired = self._campaign_seconds_left(state) <= 0
        if (
            expired
            and not optimized
            and not _reassessing_quality(state)
            and not plan.get("final_qualification")
        ):
            raise ValueError("campaign_time_budget_exhausted")
        state["error"] = None
        state["termination"] = "timed_out" if expired else None
        if expired:
            state["status"] = "stopping"

    def _verify_activation_inputs(self, plan: dict, *, first_start: bool) -> None:
        warm_variants = [
            variant for variant in plan["variants"] if "initial_adapter" in variant
        ]
        if (
            plan.get("data_audit")
            or "checkpoint_steps" in plan
            or (first_start and warm_variants)
        ):
            self._profile(plan)
            self._verify_checkpoint_protocol(plan)
            if plan.get("data_audit"):
                self._verify_data_audit(plan)
        else:
            self._verify_quality_policy(plan)
        if first_start:
            for variant in warm_variants:
                verify_adapter_entry(
                    self.experiments.root, variant["initial_adapter"], variant["recipe"]
                )

    def _ensure_single_campaign(self, campaign_id: str) -> None:
        for other in self.list():
            if other["campaign_id"] == campaign_id:
                continue
            if other["status"] in _ACTIVE and not self._only_final_review(other):
                raise ValueError("campaign_already_active")
            if other["status"] == "blocked" and other["trial_index"] < len(
                other["trials"]
            ):
                run = self._run(other, other["trials"][other["trial_index"]])
                if run and _has_work(run):
                    raise ValueError("campaign_already_active")

    def _only_final_review(self, state: dict) -> bool:
        """A final manual review can finish without starting another GPU trial."""
        index = state["trial_index"]
        if (
            state["status"] != "awaiting_review"
            or state["plan"]["review_mode"] != "manual"
            or index != len(state["trials"]) - 1
        ):
            return False
        run = self._run(state, state["trials"][index])
        return bool(
            run
            and run["status"] in {"awaiting_review", "succeeded"}
            and not _has_work(run)
        )

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
            if (
                state["status"] in _ACTIVE | {"blocked"}
                and state.get("phase") != "complete"
            ):
                state["termination"] = "stopped"
                state["status"] = "stopping"
                if not identity_alive(state["worker"]):
                    self._start_worker(directory, state)
                else:
                    self._save(directory, state)
            return state

    def _elapsed(self, state: dict) -> None:
        if state["started_at"] is not None and (
            state["status"] in _ACTIVE or state.get("phase") == "qualification"
        ):
            state["elapsed_seconds"] = max(
                state["elapsed_seconds"], self._clock() - state["started_at"]
            )

    def _verify_quality_policy(self, plan: dict) -> None:
        policy = plan.get("quality_policy")
        if policy is None:
            return
        try:
            quality_guard.verify_policy(
                policy,
                lambda record_id: quality_native.get_record(
                    self.experiments, record_id
                ),
            )
            context = quality_native.profile_context(
                self.experiments,
                plan["profile_id"],
                plan["review_mode"],
                include_runtime=policy.get("source_record") is not None,
            )
            if policy.get("parent_cases") is not None:
                context["initial_adapter_sha256"] = plan["variants"][0][
                    "initial_adapter"
                ]["weights_sha256"]
            quality_guard.verify_context(policy, context)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(_quality_error(exc)) from exc

    def _verify_data_audit(self, plan: dict) -> None:
        # In a bound plan every variant was checked against the same length limit.
        audit = self.experiments.validate(
            plan["profile_id"], plan["variants"][0]["recipe"]
        )
        if audit.get("data_audit") != plan["data_audit"]:
            raise ValueError("experiment_data_audit_changed")

    def _verify_checkpoint_protocol(self, plan: dict) -> None:
        expected = plan.get("checkpoint_evaluation_identity")
        if (
            expected is not None
            and quality_native.frozen_evaluation_identity(
                self.experiments, plan["profile_id"], plan["review_mode"]
            )
            != expected
        ):
            raise ValueError("campaign_checkpoint_protocol_changed")

    def _profile(self, plan: dict) -> None:
        self._verify_quality_policy(plan)
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
            or (_is_optuna(state["plan"]) and "recipe" not in trial)
            or run.get("recipe") != _actual_recipe(state, trial)
            or run.get("initial_adapter")
            != _current_variant(state).get("initial_adapter")
            or run.get("data_audit") != state["plan"].get("data_audit")
            or run.get("checkpoint_steps") != state["plan"].get("checkpoint_steps")
        ):
            raise ValueError("campaign_trial_conflict")
        return run

    def _artifact_budget(self, state: dict) -> bool:
        state["artifact_bytes"] = sum(
            _tree_bytes(self.experiments.run_dir(trial["run_id"]))
            for trial in state["trials"]
            if trial["status"] != "pending" or trial.get("intent")
        )
        if state["plan"].get("final_qualification"):
            state["artifact_bytes"] += _tree_bytes(
                self.experiments.root
                / "local-text-qualification"
                / state["campaign_id"]
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
                self._campaign_seconds_left(state),
            )
        )

    def _campaign_seconds_left(self, state: dict) -> float:
        remaining = state["plan"]["budget"]["max_seconds"] - state["elapsed_seconds"]
        if state.get("deadline_at") is not None:
            return (
                state["deadline_at"]
                - self._clock()
                - state["plan"]["final_qualification"]["reserve_seconds"]
            )
        cutoff = state.get("cutoff_at")
        return (
            min(remaining, cutoff - self._clock()) if cutoff is not None else remaining
        )

    def _reserve(
        self, directory: Path, state: dict, trial: dict, action: str, attempt: int
    ) -> None:
        workload = trial.get("workload", _current_variant(state)["workload"])
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
        self._verify_checkpoint_protocol(state["plan"])
        if not self._artifact_budget(state):
            raise ValueError("campaign_storage_budget_exhausted")
        run_id = trial["run_id"]
        if action == "start":
            adapter = _current_variant(state).get("initial_adapter")
            recipe = _actual_recipe(state, trial)
            if adapter is not None:
                recipe = {**recipe, "initial_adapter_id": adapter["adapter_id"]}
            return self.experiments.start(
                state["plan"]["profile_id"],
                run_id,
                recipe,
                campaign_id=state["campaign_id"],
                expected_identity=state["plan"]["profile_identity"],
                review_mode=state["plan"]["review_mode"],
                max_seconds=remaining,
                expected_initial_adapter=adapter,
                **(
                    {"checkpoint_steps": state["plan"]["checkpoint_steps"]}
                    if "checkpoint_steps" in state["plan"]
                    else {}
                ),
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

    def _terminate(self, directory: Path, state: dict, run: dict | None) -> None:
        if run and _has_work(run):
            run = self.experiments.stop(run["run_id"], campaign_id=state["campaign_id"])
            if _has_work(run):
                state["status"] = "stopping"
                return
        if state["termination"] == "timed_out" and not self._settle_timeout(
            directory, state, run
        ):
            return
        state["status"] = state["termination"]
        state["termination"] = None

    def _settle_timeout(self, directory: Path, state: dict, run: dict | None) -> bool:
        plan = state["plan"]
        optimized = _is_optuna(plan)
        reviewed = run and run["status"] == "succeeded"
        if not optimized and not reviewed:
            return True
        index = state["trial_index"]
        trial = state["trials"][index]
        if optimized:
            if "optuna_trial_number" not in trial:
                assignment = optuna_backend.assigned(directory, plan, index)
                if assignment is not None:
                    trial["optuna_trial_number"] = self._suggestion_number(
                        assignment, index
                    )
            if "optuna_trial_number" in trial:
                return self._record_timeout(directory, state, trial, run)
        else:
            return self._record_timeout(directory, state, trial, run)
        return True

    def _record_timeout(
        self, directory: Path, state: dict, trial: dict, run: dict | None
    ) -> bool:
        if run and run["status"] == "succeeded":
            self._record_result(state, trial, run["run_id"])
            trial["status"] = "succeeded"
            _rank(state)
        elif "result_sha256" not in trial and trial["status"] != "skipped":
            trial.update(status="timed_out", error="campaign_time_budget_exhausted")
        self._save(directory, state)
        if _block_missing_quality(state, trial):
            return False
        self._tell_optuna(directory, state, trial)
        return True

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
        if _block_missing_quality(state, trial):
            return
        self._tell_optuna(directory, state, trial)
        self._verify_quality_retention(state)
        retention = Retention(self.experiments, directory)
        plan = retention.plan(state)
        if plan["files"]:
            receipt = retention.apply(state, plan["plan_sha256"])
            self._record_retention(state, receipt)
        self._next_slot(state)
        self._artifact_budget(state)

    @staticmethod
    def _next_slot(state: dict) -> None:
        state["trial_index"] += 1
        state["status"] = (
            "succeeded" if state["trial_index"] == len(state["trials"]) else "running"
        )

    def _read_evaluation(self, run_id: str, profile_identity: str) -> tuple[dict, str]:
        with self.experiments.run_lock(run_id):
            run_dir = self.experiments.run_dir(run_id)
            report = self.experiments.report(run_id)
            if report.get("profile_identity") != profile_identity:
                raise ValueError("campaign_evaluation_identity_changed")
            result_sha256 = file_fingerprint(run_dir / "result.json")
            if (
                read_object(run_dir / "result-seal.json").get("result_sha256")
                != result_sha256
            ):
                raise ValueError("campaign_evaluation_seal_changed")
        return report, result_sha256

    def _record_result(self, state: dict, trial: dict, run_id: str) -> None:
        report, result_sha256 = self._read_evaluation(
            run_id, state["plan"]["profile_identity"]
        )
        trial.update(_deltas(report))
        trial["result_sha256"] = result_sha256
        policy = state["plan"].get("quality_policy")
        if "checkpoint_steps" in state["plan"]:
            self._record_checkpoint_results(state, trial, policy)
        elif policy is not None:
            self._record_quality_decision(state, trial, policy)

    def _assess_checkpoint(
        self, state: dict, run_id: str, step: int, policy: dict | None
    ) -> dict:
        expected = state["plan"]["checkpoint_evaluation_identity"]
        with self.experiments.run_lock(run_id):
            report, checksum = self.experiments.checkpoint_report(run_id, step)
            record = quality_native.native_record(self.experiments, run_id, step)
        if record["identity"] != expected or record["source"]["sha256"] != checksum:
            raise ValueError("campaign_quality_identity_changed")
        metrics = _deltas(report)
        selection = state["plan"]["selection"]
        item = {
            "step": step,
            "status": "succeeded",
            "result_sha256": checksum,
            "summaries": report["summaries"],
            **metrics,
            "qualified": _passes_selection(metrics, selection),
        }
        if policy is not None:
            guard, _ = quality_guard.evaluate(
                policy, record, expected["protocol_sha256"]
            )
            _parent_metrics(item, guard)
            item["quality_guard"] = guard
            item["qualified"] = (
                _passes_selection(item, selection) and guard["status"] == "passed"
            )
        review_config = state["plan"].get("conversation_review")
        if review_config is not None:
            from .conversation_review import (
                MissingConversationReview,
                checkpoint_review_id,
                verify_review,
            )

            try:
                receipt, binding = self._verify_conversation_checkpoint_review(
                    state,
                    run_id,
                    step,
                    checksum,
                    record,
                    review_config,
                    verify_review,
                    checkpoint_review_id,
                )
                item["conversation_review_binding"] = binding
            except MissingConversationReview as exc:
                item["qualified"] = False
                item["conversation_review_status"] = "pending"
                item["conversation_review_reason"] = "receipt_missing"
                item["conversation_review_id"] = exc.review_id
                item["conversation_review_binding"] = exc.binding
            except (OSError, ValueError, KeyError, TypeError) as exc:
                item["qualified"] = False
                item["conversation_review_status"] = "blocked"
                item["conversation_review_reason"] = _quality_error(exc)
            else:
                item["conversation_review_status"] = receipt["status"].lower()
                item["conversation_review_reason"] = (
                    None if receipt["status"] == "PASS" else "score_stop"
                )
                item["conversation_review_sha256"] = stable_hash(receipt)
                item["qualified"] = item["qualified"] and receipt["status"] == "PASS"
        return item

    def _verify_conversation_checkpoint_review(
        self,
        state: dict,
        run_id: str,
        step: int,
        result_sha256: str,
        record: dict,
        config: dict,
        verify_review_fn: Callable,
        review_id_fn: Callable,
    ) -> tuple[dict, dict]:
        plan = state["plan"]
        parent_id = plan["quality_policy"]["parent_reference_record_id"]
        parent = quality_native.get_record(self.experiments, parent_id)
        initial = plan["variants"][0].get("initial_adapter")
        if not isinstance(initial, dict):
            raise ValueError("conversation_review_parent_adapter_missing")
        checkpoint_dir = (
            self.experiments.run_dir(run_id) / "training" / f"checkpoint-{step}"
        )
        config_path = checkpoint_dir / "adapter_config.json"
        candidate_identity = {
            "model": record["identity"]["model"],
            "weights_sha256": record["candidate_sha256"],
            "config_sha256": digest(config_path),
            "snapshot_sha256": record["identity"]["base_sha256"],
        }
        p13_identity = {
            name: initial[name]
            for name in ("model", "weights_sha256", "config_sha256", "snapshot_sha256")
        }
        if (
            parent["split"] != "dev"
            or parent["candidate_sha256"] != p13_identity["weights_sha256"]
            or parent.get("candidate_config_sha256") != p13_identity["config_sha256"]
            or parent["identity"]["model"] != p13_identity["model"]
            or parent["identity"]["base_sha256"] != p13_identity["snapshot_sha256"]
            or parent["identity"]["dataset_sha256"]
            != record["identity"]["dataset_sha256"]
            or parent["identity"]["protocol_sha256"]
            != record["identity"]["protocol_sha256"]
        ):
            raise ValueError("conversation_review_parent_reference_mismatch")
        binding = {
            "campaign_id": plan["campaign_id"],
            "plan_sha256": plan["plan_sha256"],
            "profile_identity": plan["profile_identity"],
            "run_id": run_id,
            "step": step,
            "checkpoint_result_sha256": result_sha256,
            "p13_record_id": parent_id,
            "p13_record_sha256": parent["source"]["sha256"],
            "p13_identity": p13_identity,
            "candidate_identity": candidate_identity,
            "panel_sha256": config["panel_sha256"],
            "development_identity": record["identity"],
        }
        review_id = review_id_fn(config["receipt_id_prefix"], run_id, step)
        try:
            receipt = verify_review_fn(
                self.directory(state["campaign_id"]),
                review_id,
                binding,
                require_pass=False,
            )
        except FileNotFoundError as exc:
            from .conversation_review import MissingConversationReview

            raise MissingConversationReview(review_id, binding) from exc
        if receipt["panel_sha256"] != config["panel_sha256"]:
            raise ValueError("conversation_review_panel_hash_mismatch")
        return receipt, binding

    def _record_checkpoint_results(
        self,
        state: dict,
        trial: dict,
        policy: dict | None,
        *,
        steps: set[int] | None = None,
    ) -> None:
        try:
            self._verify_quality_policy(state["plan"])
            evaluated = [
                self._assess_checkpoint(state, trial["run_id"], step, policy)
                for step in (
                    sorted(steps)
                    if steps is not None
                    else state["plan"]["checkpoint_steps"]
                )
            ]
            if steps is None:
                trial["checkpoint_evaluations"] = evaluated
            else:
                by_step = {
                    row["step"]: row for row in trial.get("checkpoint_evaluations", ())
                }
                by_step.update({row["step"]: row for row in evaluated})
                trial["checkpoint_evaluations"] = [
                    by_step[step]
                    for step in state["plan"]["checkpoint_steps"]
                    if step in by_step
                ]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            reason = _quality_error(exc)
            state["quality_policy_error"] = reason
            state["selected_run_id"] = state["selected_checkpoint_step"] = None
            trial["quality_guard"] = quality_guard.blocked(reason)
            return
        state.pop("quality_policy_error", None)
        trial.pop("quality_guard", None)

    def _record_quality_decision(self, state: dict, trial: dict, policy: dict) -> None:
        try:
            self._verify_quality_policy(state["plan"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            reason = _quality_error(exc)
            state["quality_policy_error"] = reason
            trial["quality_guard"] = quality_guard.blocked(reason)
            return
        state.pop("quality_policy_error", None)
        try:
            decision, protocol = self._evaluate_quality(state, trial, policy)
            state["quality_protocol_sha256"] = protocol
        except (OSError, ValueError, KeyError, TypeError) as exc:
            decision = quality_guard.blocked(_quality_error(exc))
        trial["quality_guard"] = decision
        _parent_metrics(trial, decision)

    def _evaluate_quality(
        self, state: dict, trial: dict, policy: dict
    ) -> tuple[dict, str]:
        with self.experiments.run_lock(trial["run_id"]):
            record = quality_native.native_record(self.experiments, trial["run_id"])
            if record["source"]["sha256"] != trial["result_sha256"]:
                raise ValueError("campaign_quality_result_changed")
        return quality_guard.evaluate(
            policy, record, state.get("quality_protocol_sha256")
        )

    def _verify_quality_winner(self, state: dict, trial: dict) -> None:
        if "checkpoint_steps" in state["plan"]:
            step = state["selected_checkpoint_step"]
            observed = self._assess_checkpoint(
                state, trial["run_id"], step, state["plan"].get("quality_policy")
            )
            expected = next(
                item for item in trial["checkpoint_evaluations"] if item["step"] == step
            )
            if observed != expected or not observed["qualified"]:
                raise ValueError("campaign_quality_result_changed")
            return
        decision, _ = self._evaluate_quality(
            state, trial, state["plan"]["quality_policy"]
        )
        if decision != trial.get("quality_guard") or decision["status"] != "passed":
            raise ValueError("campaign_quality_result_changed")

    def _retry(self, state: dict, run: dict) -> str | None:
        retriable = {"failed", "stopped"}
        if "checkpoint_steps" in state["plan"]:
            retriable.add("timed_out")
        if run["status"] not in retriable:
            return None
        if state["retries"] >= state["plan"]["budget"]["max_retries"]:
            return None
        if run["stage"] in {"generate", "score"} and run["evaluation_available"]:
            return "evaluate"
        if run["stage"] == "train" and run["resume_available"]:
            plan = state["plan"]
            skipped = {
                index
                for index, trial in enumerate(state["trials"])
                if trial["status"] == "skipped"
            }
            if all(
                state[f"used_{key}"]
                + _bounded_workload(
                    plan["variants"],
                    plan.get("extension"),
                    key,
                    start=state["trial_index"],
                    skipped=skipped,
                )
                <= plan["budget"][f"max_{key}"]
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
            self._terminate(directory, state, run)
            return True
        if remaining < 1:
            stopped = self.experiments.stop(
                run["run_id"], campaign_id=state["campaign_id"]
            )
            if not _has_work(stopped):
                if stopped["status"] != "succeeded":
                    stopped = {**stopped, "status": "timed_out"}
                self._finish_trial(directory, state, trial, stopped)
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
        if self._campaign_seconds_left(state) <= 0:
            state["termination"] = "timed_out"
        if state["termination"]:
            self._terminate(directory, state, run)
            return True
        if not _allow_extension(state):
            for pending in state["trials"][state["trial_index"] :]:
                pending["status"] = "skipped"
            state.update(trial_index=len(state["trials"]), status="succeeded")
            return True
        if run is None:
            return self._check_pending_trial(directory, state, trial, remaining)
        return _has_work(run) and self._monitor(directory, state, trial, run, remaining)

    def _check_pending_trial(
        self, directory: Path, state: dict, trial: dict, remaining: int
    ) -> bool:
        if state["plan"].get("extension", {}).get("repeat_best_recipe"):
            if trial["status"] == "skipped":
                self._next_slot(state)
                return True
            self._verify_repeat_winner(state)
        if (
            state.get("cutoff_at") is not None
            and trial.get("intent") is None
            and remaining < state["plan"]["budget"]["trial_seconds"]
        ):
            state["termination"] = "timed_out"
            self._terminate(directory, state, None)
            return True
        if remaining < 1:
            state["termination"] = "timed_out"
            self._terminate(directory, state, None)
            return True
        return False

    def _verify_repeat_winner(self, state: dict) -> None:
        decision = state.get("extension_decision")
        if decision is None or decision["status"] != "approved":
            return
        source = next(
            trial for trial in state["trials"] if trial["run_id"] == decision["run_id"]
        )
        self._verify_quality_winner(
            {**state, "selected_checkpoint_step": decision["checkpoint_step"]},
            source,
        )

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
            self._prepare_trial(directory, state, trial)
            return
        trial.update(
            {
                key: run.get(key)
                for key in ("status", "stage", "attempt", "error", "resume_available")
            }
        )
        if "checkpoint_evaluations" in run:
            trial.setdefault("checkpoint_evaluations", run["checkpoint_evaluations"])
            if run["status"] != "succeeded":
                trial["checkpoint_evaluations"] = run["checkpoint_evaluations"]
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

    def _prepare_trial(self, directory: Path, state: dict, trial: dict) -> None:
        if trial["status"] == "skipped" and _is_optuna(state["plan"]):
            self._skip_duplicate(directory, state, trial)
            return
        if trial["status"] != "pending" or "started_at" in trial:
            raise ValueError("campaign_trial_missing")
        self._verify_quality_policy(state["plan"])
        if _is_optuna(state["plan"]) and "recipe" not in trial:
            self._suggest(directory, state, trial)
            if trial["status"] == "skipped":
                self._skip_duplicate(directory, state, trial)
                return
        self._reserve(directory, state, trial, "start", 0)

    @staticmethod
    def _suggestion_number(suggestion: dict, index: int) -> int:
        number = suggestion["trial_number"]
        if type(number) is not int or number != index:
            raise ValueError("campaign_optuna_suggestion_invalid")
        return number

    def _suggest(self, directory: Path, state: dict, trial: dict) -> None:
        plan = state["plan"]
        self._profile(plan)
        if not self._artifact_budget(state):
            raise ValueError("campaign_storage_budget_exhausted")
        index = state["trial_index"]
        suggestion = optuna_backend.ask(directory, plan, index)
        number = self._suggestion_number(suggestion, index)
        params = suggestion["params"]
        previous = state["trials"][:index]
        trial.update(optuna_trial_number=number, optuna_trial_state="RUNNING")
        _check_suggestion(plan["search_space"], params)
        base = _current_variant(state)
        validated = self.experiments.validate(
            plan["profile_id"], {**base["recipe"], **params}
        )
        if validated["identity"] != plan["profile_identity"]:
            raise ValueError("campaign_profile_changed")
        if plan["review_mode"] == "automatic" and not validated["automatic_review"]:
            raise ValueError("campaign_evaluator_not_qualified")
        workload = _workload(validated)
        if any(workload[key] > base["workload"][key] for key in workload):
            raise ValueError("campaign_optuna_workload_exceeded")
        recipe = validated["recipe"]
        trial.update(recipe=recipe, workload=workload)
        if any(other.get("recipe") == recipe for other in previous):
            trial.update(status="skipped", error="campaign_duplicate_suggestion")

    def _skip_duplicate(self, directory: Path, state: dict, trial: dict) -> None:
        self._save(directory, state)
        self._tell_optuna(directory, state, trial)
        self._next_slot(state)

    @staticmethod
    def _tell_optuna(directory: Path, state: dict, trial: dict) -> None:
        if not _is_optuna(state["plan"]):
            return
        number = trial["optuna_trial_number"]
        guard = trial.get("quality_guard", {})
        if (
            "result_sha256" in trial
            and guard.get("status") != "blocked"
            and trial.get("critical_delta") is not None
        ):
            selection = state["plan"]["selection"]
            constraints = [
                trial["critical_delta"] - selection["max_critical_delta"],
                selection["min_usable_delta"] - trial["usable_delta"],
            ]
            if guard.get("status") == "rejected":
                constraints[0] = max(constraints[0], 1.0)
            optuna_backend.tell(
                directory,
                state["plan"],
                number,
                "COMPLETE",
                trial["usable_delta"],
                constraints=constraints,
            )
            trial.update(
                optuna_trial_state="COMPLETE", gate_passed=max(constraints) <= 0
            )
        else:
            optuna_backend.tell(directory, state["plan"], number, "FAIL")
            trial["optuna_trial_state"] = "FAIL"

    def advance(self, campaign_id: str) -> dict:
        """Advance one durable transition. Called by the detached supervisor."""
        ensure_data_mutation_allowed("academy_campaign_advance")
        directory = self.directory(campaign_id)
        state = self._state(directory)
        if state.get("phase") == "qualification":
            return self._advance_qualification(campaign_id, directory, state)
        if self._awaiting_conversation_review(state):
            return self._advance_conversation_review(directory)
        return self._advance_active(directory)

    def _advance_qualification(
        self, campaign_id: str, directory: Path, state: dict
    ) -> dict:
        if state["plan"].get("conversation_review") is not None:
            with file_lock(directory / ".state.lock"):
                state = self._state(directory)
                self._review_selection(state)
                if state.get("phase") != "qualification":
                    self._save(directory, state)
                    return state
        from .local_campaign_final import advance

        return advance(self, campaign_id)

    @staticmethod
    def _awaiting_conversation_review(state: dict) -> bool:
        return (
            state.get("phase") == "trials"
            and state.get("status") == "awaiting_review"
            and state["plan"].get("conversation_review") is not None
        )

    def _advance_conversation_review(self, directory: Path) -> dict:
        with file_lock(directory / ".state.lock"):
            state = self._state(directory)
            self._review_selection(state)
            review_changed = (
                state.get("error") == "campaign_quality_conversation_review_changed"
            )
            if not review_changed:
                state["status"] = state.get("training_status", "succeeded")
                if state["plan"].get("final_qualification"):
                    from .local_campaign_final import transition

                    transition(state, service=self)
                else:
                    state["status"] = "succeeded"
            if state["status"] not in _ACTIVE:
                state["worker"] = None
            self._save(directory, state)
            return state

    def _advance_active(self, directory: Path) -> dict:
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
                if code.startswith("campaign_quality_"):
                    state.update(
                        selected_run_id=None, quality_policy_error=_quality_error(exc)
                    )
                state["error"] = (
                    code
                    if re.fullmatch(
                        r"(?:campaign_|experiment_initial_adapter_|experiment_data_audit_)[a-z0-9_]+",
                        code,
                    )
                    else "campaign_stage_failed"
                )
            _confirm_repeat(state)
            if state["plan"].get("final_qualification"):
                from .local_campaign_final import transition

                transition(state, service=self)
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
            state = self._state(directory)
            self._verify_quality_retention(state)
            return Retention(self.experiments, directory).plan(state)

    def _verify_quality_retention(self, state: dict) -> None:
        self._verify_quality_policy(state["plan"])
        if state["selected_run_id"] and (
            state["plan"].get("quality_policy") or "checkpoint_steps" in state["plan"]
        ):
            winner = next(
                (
                    trial
                    for trial in state["trials"]
                    if trial["run_id"] == state["selected_run_id"]
                ),
                None,
            )
            if winner is None:
                raise ValueError("campaign_quality_result_changed")
            self._verify_quality_winner(state, winner)

    def retention_apply(self, campaign_id: str, plan_sha256: str) -> dict:
        ensure_data_mutation_allowed("academy_campaign_retention")
        directory = self.directory(campaign_id)
        with file_lock(directory / ".state.lock"):
            state = self._state(directory)
            if state["status"] in _ACTIVE:
                raise ValueError("campaign_retention_while_active")
            self._verify_quality_retention(state)
            receipt = Retention(self.experiments, directory).apply(state, plan_sha256)
            self._record_retention(state, receipt)
            self._artifact_budget(state)
            self._save(directory, state)
            return receipt
