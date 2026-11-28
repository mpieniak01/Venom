"""Host-side operator handoff for a pending remote checkpoint review."""

from pathlib import Path

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.remote_training.lifecycle import file_lock, validate_run_id

from .campaign import CampaignService
from .conversation_blind import (
    _verify_blind_package,
    prepare_blind_package,
    publish_blind_package,
    read_consumed_blind_review,
    register_blind_review,
    register_blind_review_batch,
)
from .conversation_review import checkpoint_review_id
from .profiles import load_profile, read_json, resolve_input


def _checkpoint(
    service: CampaignService,
    state: dict,
    run_id: str,
    step: int,
    *,
    allow_consumed: bool = False,
) -> dict:
    validate_run_id(run_id)
    if not service._remote_conversation_review(state):
        raise ValueError("campaign_remote_review_unavailable")
    review = next(
        (
            row
            for trial in state["trials"]
            if trial["run_id"] == run_id and trial["status"] == "succeeded"
            for row in trial.get("checkpoint_evaluations", ())
            if row["step"] == step
        ),
        None,
    )
    if allow_consumed and review and review.get("conversation_review_sha256"):
        prefix = state["plan"]["conversation_review"]["receipt_id_prefix"]
        return {
            **review,
            "conversation_review_id": checkpoint_review_id(prefix, run_id, step),
        }
    service._elapsed(state)
    if (
        state["status"] != "awaiting_review"
        or service._campaign_seconds_left(state) <= 0
    ):
        raise ValueError("campaign_remote_review_unavailable")
    if review and review.get("conversation_review_status") == "pending":
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
    pending = _checkpoint(service, state, run_id, step)
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
    template = target / "judgments-template.json"
    if not template.is_file():
        raise ValueError("conversation_review_judgments_template_missing")
    return {
        "review_id": pending["conversation_review_id"],
        "reviewer": str(target / "reviewer.json"),
        "judgments_template": str(template),
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
        checkpoint = _checkpoint(service, state, run_id, step, allow_consumed=True)
        target = (
            directory / "remote-review-packages" / checkpoint["conversation_review_id"]
        )
        if checkpoint.get("conversation_review_sha256"):
            return read_consumed_blind_review(directory, checkpoint, target, submission)
        if isinstance(submission, dict) and "batch" in submission:
            return register_blind_review_batch(
                service.experiments.root, checkpoint, target, submission
            )
        return register_blind_review(
            service.experiments.root, checkpoint, target, submission
        )
