"""Persistent controller for a text campaign on a prepared Vast environment."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import time
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.services.remote_training.bundles import MAX_BYTES
from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path
from venom_core.services.remote_training.transport import TransportError

from .campaign import CampaignService
from .campaign_schema import CampaignId, CampaignSpec, Digest
from .remote_text_evidence import artifact_path, summarize, sync_run
from .remote_text_qualification import read_qualification
from .retention import fingerprint, read_object

_TERMINAL = frozenset({"succeeded", "timed_out", "stopped", "blocked", "failed"})
_ERRORS = (OSError, RuntimeError, ValueError, KeyError, TypeError)
_RECOVERY_LIMIT = 3
_WATCHDOG_MAX_AGE = 60
_CAMPAIGN_ID = TypeAdapter(CampaignId)


class RemoteTextSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    campaign: CampaignSpec
    environment_plan_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
    max_cost_microusd: Annotated[int, Field(ge=1, le=1_000_000_000)]
    final_test_sha256: Digest | None = None
    final_calibration_sha256: Digest | None = None

    @model_validator(mode="after")
    def validate_final_test(self) -> RemoteTextSpec:
        if (self.final_test_sha256 is None) != (self.final_calibration_sha256 is None):
            raise ValueError("campaign_remote_final_test_pins_required")
        return self


class Rental(Protocol):
    def validate(
        self,
        plan_id: str,
        max_seconds: int,
        max_cost_microusd: int,
        *,
        campaign_id: str,
    ) -> dict: ...

    def acquire(self, plan_id: str, *, campaign_id: str) -> dict: ...

    def cleanup(self, plan_id: str, *, campaign_id: str) -> dict: ...

    def cost(self, plan_id: str, *, campaign_id: str) -> dict: ...


class Host(Protocol):
    def plan(
        self, spec: dict, *, expected_profile_identity: str | None = None
    ) -> dict: ...

    def start(
        self,
        campaign_id: str,
        plan_sha256: str,
        *,
        cutoff_at: float,
    ) -> dict: ...

    def resume(self, campaign_id: str) -> dict: ...

    def stop(self, campaign_id: str) -> dict: ...

    def status(self, campaign_id: str) -> dict: ...

    def fetch(
        self,
        campaign_id: str,
        run_id: str,
        destination: Path,
        max_bytes: int,
        *,
        timeout: int | None = None,
    ) -> dict: ...


def _remote_spec(spec: RemoteTextSpec) -> CampaignSpec:
    campaign = spec.campaign
    if campaign.review_mode != "automatic":
        raise ValueError("campaign_remote_automatic_review_required")
    if campaign.retention != "keep_all":
        raise ValueError("campaign_remote_evidence_retention_required")
    parents = [variant.get("initial_adapter_id") for variant in campaign.variants]
    if parents and any(parent != parents[0] for parent in parents):
        raise ValueError("campaign_remote_mixed_parents")
    return campaign


class RemoteTextService:
    """The controller owns billing lifetime; the remote Academy owns training."""

    def __init__(
        self,
        local: CampaignService,
        rental: Rental,
        host: Callable[[str, str, dict], Host],
        *,
        clock: Callable[[], float] = time,
    ):
        self.local = local
        self.root = operator_path(local.experiments.root / "remote-text")
        self.rental = rental
        self.host = host
        self.clock = clock

    def directory(self, campaign_id: str) -> Path:
        return operator_path(self.root / _CAMPAIGN_ID.validate_python(campaign_id))

    def status(self, campaign_id: str) -> dict:
        directory = self.directory(campaign_id)
        state = read_object(directory / "state.json")
        if (directory / "stop.json").exists():
            state["stop_requested"] = True
        if state["status"] == "completed":
            self._show_qualification(directory, state)
        return state

    def _show_qualification(self, directory: Path, state: dict) -> None:
        request = state["plan"]["request"]
        final_test = request.get("final_test_sha256")
        if not final_test or state["remote"] is None:
            return
        try:
            decision = read_qualification(
                directory / "evidence",
                state["remote"],
                state["evidence"],
                academy_root=self.local.experiments.root,
                final_test_sha256=final_test,
                final_calibration_sha256=request["final_calibration_sha256"],
            )
        except (OSError, ValueError, KeyError, TypeError):
            state["qualification_status"] = "evidence_invalid"
            return
        if decision is None:
            return
        state["qualification_status"] = decision["status"]
        if decision["qualified"] is not None:
            state["result"] = {
                **state["result"],
                "outcome": "QUALIFIED",
                "best_qualified": decision["qualified"],
            }

    def list(self) -> list[dict]:
        result = []
        for path in sorted(self.root.glob("*/state.json")):
            try:
                result.append(self.status(path.parent.name))
            except FileNotFoundError:
                continue
        return result

    def _quote(self, spec: RemoteTextSpec, seconds: int) -> dict:
        try:
            quote = self.rental.validate(
                spec.environment_plan_id,
                seconds,
                spec.max_cost_microusd,
                campaign_id=spec.campaign.campaign_id,
            )
        except VastError as exc:
            if exc.code == "vast.text_budget_exceeded":
                raise ValueError("campaign_remote_cost_budget_exceeded") from exc
            raise
        if spec.campaign.budget.max_artifact_bytes > min(
            quote["max_upload_bytes"], MAX_BYTES
        ):
            raise ValueError("campaign_remote_transfer_budget_exceeded")
        return quote

    def plan(self, spec: RemoteTextSpec) -> dict:
        ensure_data_mutation_allowed("academy_campaign_remote_plan")
        campaign = _remote_spec(spec)
        local_plan = self.local.validate(campaign)
        request = spec.model_dump(
            exclude={"campaign": {"extension"}} if campaign.extension is None else None
        )
        expected = {
            "request": request,
            "remote_plan_sha256": local_plan["plan_sha256"],
            "profile_identity": local_plan["profile_identity"],
        }
        plan_hash = fingerprint(expected)
        quote = self._quote(spec, campaign.budget.max_seconds)
        reserve = quote["cleanup_reserve_seconds"]
        if campaign.budget.trial_seconds + reserve > campaign.budget.max_seconds:
            raise ValueError("campaign_remote_trial_exceeds_work_window")
        directory = self.directory(campaign.campaign_id)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with file_lock(self.root / ".catalog.lock"):
            directory.mkdir(mode=0o700, exist_ok=True)
            path = directory / "state.json"
            if path.exists():
                state = self.status(campaign.campaign_id)
                if state["plan_sha256"] != plan_hash:
                    raise ValueError("campaign_plan_conflict")
                return state
            state = {
                "campaign_id": campaign.campaign_id,
                "status": "planned",
                "plan_sha256": plan_hash,
                "plan": expected,
                "quote": quote,
                "cleanup": {"state": "not_started"},
                "stop_requested": False,
                "recovery_attempts": 0,
                "started_at": None,
                "deadline_at": None,
                "search_cutoff_at": None,
                "last_sync_at": None,
                "remote": None,
                "evidence": {},
                "result": None,
                "error": None,
            }
            atomic_json(path, state)
            return state

    def heartbeat(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_json(self.root / "supervisor.json", {"updated_at": self.clock()})

    def _require_supervisor(self) -> None:
        try:
            heartbeat = read_object(self.root / "supervisor.json")["updated_at"]
        except FileNotFoundError:
            raise ValueError("campaign_remote_supervisor_unavailable") from None
        if not 0 <= self.clock() - heartbeat <= _WATCHDOG_MAX_AGE:
            raise ValueError("campaign_remote_supervisor_unavailable")

    def start(self, campaign_id: str, plan_sha256: str) -> dict:
        ensure_data_mutation_allowed("academy_campaign_remote_start")
        directory = self.directory(campaign_id)
        with (
            file_lock(self.root / ".catalog.lock"),
            file_lock(directory / ".state.lock"),
        ):
            state = self.status(campaign_id)
            if state["plan_sha256"] != plan_sha256:
                raise ValueError("campaign_plan_changed")
            if state["status"] != "planned":
                return state
            self._require_supervisor()
            if any(
                other["campaign_id"] != campaign_id
                and other["status"]
                in {"queued", "running", "finalizing", "cleanup_pending"}
                for other in self.list()
            ):
                raise ValueError("campaign_remote_already_active")
            spec = RemoteTextSpec.model_validate(state["plan"]["request"])
            seconds = spec.campaign.budget.max_seconds
            quote = self._quote(spec, seconds)
            if (
                self.local.validate(spec.campaign)["plan_sha256"]
                != state["plan"]["remote_plan_sha256"]
            ):
                raise ValueError("campaign_plan_changed")
            started = self.clock()
            state.update(
                status="queued",
                quote=quote,
                started_at=started,
                deadline_at=started + seconds,
                search_cutoff_at=started + seconds - quote["cleanup_reserve_seconds"],
                cleanup={"state": "pending"},
            )
            atomic_json(directory / "state.json", state)
            return state

    def stop(self, campaign_id: str) -> dict:
        ensure_data_mutation_allowed("academy_campaign_remote_stop")
        directory = self.directory(campaign_id)
        with file_lock(directory / ".stop.lock"):
            state = self.status(campaign_id)
            if state["status"] in {"queued", "running", "finalizing"}:
                state["stop_requested"] = True
                atomic_json(directory / "stop.json", {"requested_at": self.clock()})
            return state

    def _start_host(self, host: Host, state: dict, spec: RemoteTextSpec) -> dict:
        expected = state["plan"]
        planned = host.plan(
            spec.campaign.model_dump(),
            expected_profile_identity=expected["profile_identity"],
        )
        if planned["plan"]["plan_sha256"] != expected["remote_plan_sha256"]:
            raise ValueError("campaign_remote_plan_mismatch")
        if (
            planned["status"] != "planned"
            and planned.get("cutoff_at") != state["search_cutoff_at"]
        ):
            raise ValueError("campaign_remote_host_identity_mismatch")
        if self.clock() >= state["search_cutoff_at"]:
            raise ValueError("campaign_remote_start_window_expired")
        return host.start(
            spec.campaign.campaign_id,
            expected["remote_plan_sha256"],
            cutoff_at=state["search_cutoff_at"],
        )

    def _sync(
        self, host: Host, directory: Path, state: dict, spec: RemoteTextSpec
    ) -> None:
        remote = state["remote"]
        receipts = state["evidence"]
        remaining = spec.campaign.budget.max_artifact_bytes - sum(
            entry["archive_bytes"] for entry in receipts.values()
        )
        for trial in remote["trials"]:
            run_id = trial["run_id"]
            if trial.get("result_sha256") and run_id not in receipts:
                timeout = min(120, int(state["deadline_at"] - self.clock()))
                if remaining <= 0 or timeout < 1:
                    break
                receipt = sync_run(
                    host,
                    remote,
                    run_id,
                    directory / "evidence",
                    remaining,
                    timeout=timeout,
                )
                receipts[run_id] = receipt
                remaining -= receipt["archive_bytes"]
                atomic_json(directory / "state.json", state)
        state["result"] = summarize(remote, receipts)

    def _observe(self, state: dict, remote: dict) -> None:
        if (
            remote.get("campaign_id") != state["campaign_id"]
            or remote.get("plan", {}).get("plan_sha256")
            != state["plan"]["remote_plan_sha256"]
            or remote.get("cutoff_at") != state["search_cutoff_at"]
            or not isinstance(remote.get("status"), str)
            or not isinstance(remote.get("trials"), list)
        ):
            raise ValueError("campaign_remote_host_identity_mismatch")
        state.update(
            remote=remote, last_sync_at=self.clock(), status="running", error=None
        )

    def _execute(self, directory: Path, state: dict, spec: RemoteTextSpec) -> None:
        campaign_id = state["campaign_id"]
        plan_id = spec.environment_plan_id
        if state["stop_requested"] or self.clock() >= state["search_cutoff_at"]:
            state["status"] = "finalizing"
            return
        endpoint = self.rental.acquire(plan_id, campaign_id=campaign_id)
        host = self.host(plan_id, campaign_id, endpoint)
        remote = (
            host.status(campaign_id)
            if state["remote"] is not None
            else self._start_host(host, state, spec)
        )
        if (
            remote["status"] == "interrupted"
            and state["recovery_attempts"] < _RECOVERY_LIMIT
        ):
            self._observe(state, remote)
            state["recovery_attempts"] += 1
            atomic_json(directory / "state.json", state)
            remote = host.resume(campaign_id)
        self._observe(state, remote)
        self._sync(host, directory, state, spec)
        if remote["status"] in _TERMINAL | {"awaiting_review", "interrupted"}:
            state["status"] = "finalizing"

    def _finalize(self, directory: Path, state: dict, spec: RemoteTextSpec) -> None:
        campaign_id = state["campaign_id"]
        plan_id = spec.environment_plan_id
        # A lost start reply can leave a host campaign even before its first heartbeat.
        if self.clock() < state["deadline_at"]:
            try:
                endpoint = self.rental.acquire(plan_id, campaign_id=campaign_id)
                host = self.host(plan_id, campaign_id, endpoint)
                remote = host.status(campaign_id)
                self._observe(state, remote)
                if remote["status"] not in _TERMINAL:
                    remote = host.stop(campaign_id)
                    self._observe(state, remote)
                self._sync(host, directory, state, spec)
                if remote["status"] not in _TERMINAL:
                    state["status"] = "finalizing"
                    return
            except TransportError as exc:
                state["error"] = "campaign_remote_final_sync_unavailable"
                if (
                    exc.code != "remote_text_not_found"
                    and self.clock() < state["deadline_at"]
                ):
                    state["status"] = "finalizing"
                    return
            except (OSError, RuntimeError):
                state["error"] = "campaign_remote_final_sync_unavailable"
                if self.clock() < state["deadline_at"]:
                    state["status"] = "finalizing"
                    return
            except (ValueError, KeyError, TypeError):
                state["error"] = "campaign_remote_final_evidence_invalid"
        state["status"] = "cleanup_pending"
        if state["result"] is None:
            state["result"] = summarize(state["remote"] or {}, state["evidence"])
        atomic_json(directory / "state.json", state)

    def _cleanup(self, state: dict, spec: RemoteTextSpec) -> None:
        campaign_id = state["campaign_id"]
        plan_id = spec.environment_plan_id
        state["cleanup"] = self.rental.cleanup(plan_id, campaign_id=campaign_id)
        if state["cleanup"]["state"] not in {"destroyed", "stopped"}:
            return
        state["status"] = "completed"
        state["finished_at"] = self.clock()
        try:
            state["cost"] = self.rental.cost(plan_id, campaign_id=campaign_id)
        except _ERRORS:
            state["cost"] = None

    def tick(self, campaign_id: str) -> dict:
        """Run one recoverable transition from the independent supervisor."""
        ensure_data_mutation_allowed("academy_campaign_remote_tick")
        directory = self.directory(campaign_id)
        with file_lock(directory / ".state.lock"):
            state = self.status(campaign_id)
            if state["status"] in {"planned", "completed"}:
                return state
            spec = RemoteTextSpec.model_validate(state["plan"]["request"])
            try:
                if state["status"] in {"queued", "running"}:
                    self._execute(directory, state, spec)
            except _ERRORS as exc:
                state["error"] = (
                    str(exc)
                    if str(exc).startswith("campaign_remote_")
                    and str(exc).isidentifier()
                    else "campaign_remote_poll_unavailable"
                )
                if (
                    isinstance(exc, (ValueError, KeyError, TypeError))
                    or isinstance(exc, TransportError)
                    and not exc.retryable
                    or self.clock() >= state["search_cutoff_at"]
                ):
                    state["status"] = "finalizing"
            if state["status"] == "finalizing":
                self._finalize(directory, state, spec)
            if state["status"] == "cleanup_pending":
                try:
                    self._cleanup(state, spec)
                except _ERRORS:
                    state["error"] = "campaign_remote_cleanup_unavailable"
            atomic_json(directory / "state.json", state)
            return state

    def evidence_archive(self, campaign_id: str, run_id: str) -> Path:
        state = self.status(campaign_id)
        if run_id not in state["evidence"]:
            raise FileNotFoundError(run_id)
        return artifact_path(self.directory(campaign_id) / "evidence", run_id)


def remote_text_service() -> RemoteTextService:
    from .operator import campaign_service
    from .remote_text_host import RemoteTextHost
    from .remote_text_vast import VastTextRental

    rental = VastTextRental.from_settings()

    def host(plan_id: str, campaign_id: str, endpoint: dict) -> Host:
        return RemoteTextHost(
            rental.ssh_prefix(plan_id, campaign_id=campaign_id),
            endpoint["python"],
            endpoint["repo"],
            endpoint["root"],
            request_timeout=15,
            expected_commit=endpoint["commit"],
        )

    return RemoteTextService(campaign_service(), rental, host)
