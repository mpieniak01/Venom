"""Pin and collect holdout inputs from an existing local Academy campaign."""

from pathlib import Path
from time import monotonic
from typing import BinaryIO, cast

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path

from .campaign import CampaignService
from .profiles import read_json
from .remote_text_evidence import _ARCHIVE, _run_directory, _sha, export_run, sync_run
from .service import ExperimentService


def _directory(academy_root: Path, campaign: CampaignService, campaign_id: str) -> Path:
    name = campaign.directory(campaign_id).name
    return operator_path(academy_root / "local-text-qualification" / name)


def _plan_identity(state: dict) -> dict:
    plan = state["plan"]
    return {
        "source": "local",
        "campaign_id": state["campaign_id"],
        "plan_sha256": _sha(plan["plan_sha256"]),
        "profile_identity": _sha(plan["profile_identity"]),
    }


def pin_local(
    academy_root: Path,
    campaign_id: str,
    *,
    final_test_sha256: str,
    final_calibration_sha256: str,
) -> dict:
    """Bind both hashes before the local campaign starts, allowing identical retries."""
    ensure_data_mutation_allowed("academy_local_text_qualification_pin")
    campaign = CampaignService(ExperimentService(academy_root))
    with file_lock(campaign.directory(campaign_id) / ".state.lock"):
        state = campaign.status(campaign_id)
        return pin_state(
            academy_root,
            state,
            final_test_sha256=final_test_sha256,
            final_calibration_sha256=final_calibration_sha256,
        )


def pin_state(
    academy_root: Path,
    state: dict,
    *,
    final_test_sha256: str,
    final_calibration_sha256: str,
) -> dict:
    """Persist pre-start pins under the caller's campaign state lock."""
    campaign = CampaignService(ExperimentService(academy_root))
    directory = _directory(academy_root, campaign, state["campaign_id"])
    pins = {
        "final_test_sha256": _sha(final_test_sha256),
        "final_calibration_sha256": _sha(final_calibration_sha256),
    }
    expected = {**_plan_identity(state), "pins": pins}
    location = operator_path(directory / "holdout-pins.json")
    if location.exists():
        if read_json(location) != expected:
            raise ValueError("remote_text_final_local_pins_changed")
    elif state["status"] == "planned" and state["started_at"] is None:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_json(location, expected)
    else:
        raise ValueError("remote_text_final_local_pins_required_before_start")
    return expected


class _LimitedWriter:
    def __init__(self, stream: BinaryIO, max_bytes: int, timeout: int | None) -> None:
        self.stream = stream
        self.limit = max_bytes
        self.deadline = None if timeout is None else monotonic() + timeout

    def write(self, chunk: bytes) -> int:
        if self.deadline is not None and monotonic() >= self.deadline:
            raise TimeoutError("remote_text_evidence_fetch_timeout")
        if len(chunk) > self.limit:
            raise ValueError("remote_text_evidence_size_invalid")
        written = self.stream.write(chunk)
        self.limit -= written
        return written


class _LocalEvidence:
    def __init__(self, campaign: CampaignService) -> None:
        self.campaign = campaign

    def fetch(
        self,
        campaign_id: str,
        run_id: str,
        destination: Path,
        max_bytes: int,
        *,
        timeout: int | None = None,
    ) -> dict:
        with destination.open("xb") as stream:
            # tarfile's sequential export only calls write on this bounded sink.
            export_run(
                self.campaign,
                campaign_id,
                run_id,
                cast(BinaryIO, _LimitedWriter(stream, max_bytes, timeout)),
            )
        return {}


def _export_budget(
    campaign: CampaignService, state: dict, evidence: Path, run_id: str
) -> int:
    if not campaign._artifact_budget(state):
        raise ValueError("campaign_storage_budget_exhausted")
    budget = state["plan"]["budget"]
    archive = operator_path(_run_directory(evidence, run_id) / _ARCHIVE)
    archived_bytes = archive.stat().st_size if archive.exists() else 0
    # Keep space for the receipt written alongside the bounded archive.
    metadata_reserve = 64 * 1024
    available = min(
        budget["max_artifact_bytes"] - state["artifact_bytes"],
        campaign.experiments.free_storage_bytes(state["plan"]["profile_id"])
        - budget["min_free_bytes"],
    )
    limit = available + archived_bytes - metadata_reserve
    if limit <= 0:
        raise ValueError("campaign_storage_budget_exhausted")
    return min(limit, budget["max_artifact_bytes"])


def collect_local(
    academy_root: Path, campaign_id: str, *, timeout: int | None = None
) -> tuple[Path, dict, dict, dict[str, str]]:
    """Export and verify exactly the finalist of a completed local CampaignService."""
    ensure_data_mutation_allowed("academy_local_text_qualification_collect")
    campaign = CampaignService(ExperimentService(academy_root))
    directory = _directory(academy_root, campaign, campaign_id)
    location = operator_path(directory / "holdout-pins.json")
    if not location.is_file():
        raise ValueError("remote_text_final_local_pins_required_before_start")
    record = read_json(location)
    state = campaign.status(campaign_id)
    if state.get("phase") in {"qualification", "complete"}:
        state = {**state, "status": state["training_status"]}
    if state["status"] not in {"succeeded", "timed_out", "stopped"}:
        raise ValueError("remote_text_final_campaign_not_finished")
    if {key: value for key, value in record.items() if key != "pins"} != _plan_identity(
        state
    ):
        raise ValueError("remote_text_final_local_pins_changed")
    pins = {
        name: _sha(record["pins"][name])
        for name in ("final_test_sha256", "final_calibration_sha256")
    }
    run_id = state.get("selected_run_id")
    if not isinstance(run_id, str):
        raise ValueError("remote_text_final_candidate_missing")
    evidence = directory / "evidence"
    max_bytes = state["plan"]["budget"]["max_artifact_bytes"]
    if state["plan"].get("final_qualification"):
        max_bytes = _export_budget(campaign, state, evidence, run_id)
    receipt = sync_run(
        _LocalEvidence(campaign),
        state,
        run_id,
        evidence,
        max_bytes,
        timeout=timeout,
    )
    return evidence, state, {run_id: receipt}, pins
