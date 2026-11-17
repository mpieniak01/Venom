"""Pin and collect holdout inputs from an existing local Academy campaign."""

from pathlib import Path
from typing import BinaryIO, cast

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path

from .campaign import CampaignService
from .profiles import read_json
from .remote_text_evidence import _sha, export_run, sync_run
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
    directory = _directory(academy_root, campaign, campaign_id)
    pins = {
        "final_test_sha256": _sha(final_test_sha256),
        "final_calibration_sha256": _sha(final_calibration_sha256),
    }
    with file_lock(campaign.directory(campaign_id) / ".state.lock"):
        state = campaign.status(campaign_id)
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
    def __init__(self, stream: BinaryIO, max_bytes: int) -> None:
        self.stream = stream
        self.limit = max_bytes

    def write(self, chunk: bytes) -> int:
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
                cast(BinaryIO, _LimitedWriter(stream, max_bytes)),
            )
        return {}


def collect_local(
    academy_root: Path, campaign_id: str
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
    receipt = sync_run(
        _LocalEvidence(campaign),
        state,
        run_id,
        evidence,
        state["plan"]["budget"]["max_artifact_bytes"],
    )
    return evidence, state, {run_id: receipt}, pins
