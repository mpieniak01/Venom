"""Host-side operator handoff for a pending remote checkpoint review."""

from pathlib import Path

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.remote_training.lifecycle import file_lock, validate_run_id

from .campaign import CampaignService
from .conversation_blind import (
    _verify_blind_package,
    prepare_blind_package,
    publish_blind_package,
    register_blind_review,
)
from .profiles import load_profile, read_json, resolve_input


def _pending(service: CampaignService, state: dict, run_id: str, step: int) -> dict:
    validate_run_id(run_id)
    service._elapsed(state)
    if (
        not service._remote_conversation_review(state)
        or state["status"] != "awaiting_review"
        or service._campaign_seconds_left(state) <= 0
    ):
        raise ValueError("campaign_remote_review_unavailable")
    for trial in state["trials"]:
        if trial["run_id"] != run_id or trial["status"] != "succeeded":
            continue
        for review in trial.get("checkpoint_evaluations", ()):
            if (
                review["step"] == step
                and review.get("conversation_review_status") == "pending"
            ):
                return review
    raise ValueError("conversation_review_pending_checkpoint_required")


def prepare(
    service: CampaignService,
    campaign_id: str,
    run_id: str,
    step: int,
    panel_file: Path,
    parent_generation: Path,
) -> dict:
    ensure_data_mutation_allowed("academy_remote_conversation_prepare")
    directory = service.directory(campaign_id)
    state = service.status(campaign_id)
    pending = _pending(service, state, run_id, step)
    target = directory / "remote-review-packages" / pending["conversation_review_id"]
    if target.exists():
        _verify_blind_package(
            pending,
            read_json(target / "reviewer.json"),
            read_json(target / "private.json"),
        )
    else:
        root = service.experiments.root
        profile, identity = load_profile(root, state["plan"]["profile_id"])
        if identity != state["plan"]["profile_identity"]:
            raise ValueError("campaign_profile_changed")
        package, private = prepare_blind_package(
            pending,
            read_json(panel_file),
            resolve_input(root, profile.dev),
            parent_generation,
            service.experiments.run_dir(run_id) / "checkpoint-evaluations" / str(step),
        )
        publish_blind_package(target, package, private)
    return {
        "review_id": pending["conversation_review_id"],
        "reviewer": str(target / "reviewer.json"),
        "judgments_template": str(target / "judgments-template.json"),
    }


def submit(
    service: CampaignService,
    campaign_id: str,
    run_id: str,
    step: int,
    judgments: Path,
) -> dict:
    ensure_data_mutation_allowed("academy_remote_conversation_submit")
    directory = service.directory(campaign_id)
    submission = read_json(judgments)
    with file_lock(directory / ".state.lock"):
        state = service._state(directory)
        pending = _pending(service, state, run_id, step)
        target = (
            directory / "remote-review-packages" / pending["conversation_review_id"]
        )
        return register_blind_review(
            service.experiments.root, pending, target, submission
        )
