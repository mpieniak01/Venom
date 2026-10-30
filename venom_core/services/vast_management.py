"""Operator-ordered rental -> provision -> metadata readiness -> chat attachment.

No startup work, generation or test zero. Paid create is never retried. The existing
lifecycle journal remains authoritative for rental identity and ambiguous outcomes.
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterator
from uuid import uuid4

import httpx

from venom_core.infrastructure.providers.vast.client import VastClient, VastError
from venom_core.infrastructure.providers.vast.models import (
    EnvironmentRecord,
    OfferAssessment,
    amount,
    now,
)
from venom_core.services import vast_management_config as configuration
from venom_core.services.vast_environments.account_billing import (
    AccountBilling,
    instance_summary,
)
from venom_core.services.vast_environments.lifecycle import Environments
from venom_core.services.vast_environments.operations import workload
from venom_core.services.vast_environments.store import Journal

MANAGEMENT_DISABLED = "vast.management_disabled"
MANAGEMENT_SUFFIX = ".management.json"
PLAN_SUFFIX = ".plan.json"
OPERATION_LOCKS = "management-locks"
SSH_RETRY_ERRORS = {"vast.ssh_failed", "vast.invalid_ssh_host", "vast.invalid_ssh_port"}
ATTACH_RETRY_ERRORS = {
    "vast.management_model_not_ready",
    "vast.chat_probe_failed",
    "vast.tunnel_failed",
}

ACTIVE = {"queued", "creating", "waiting", "provisioning", "connecting"}
ERRORS = (VastError, OSError, ValueError, httpx.HTTPError)


def _billing_summary(record: EnvironmentRecord) -> dict[str, Any]:
    costs = record.reports.get("costs")
    if isinstance(costs, dict):
        reported = costs.get("provider_reported")
        billed = (
            amount(reported.get("usd"))
            if isinstance(reported, dict) and costs.get("currency") == "USD"
            else None
        )
        if billed is not None and isinstance(reported, dict):
            unknown = reported.get("unknown_amounts", 0)
            status = "reported" if unknown == 0 else "partial"
            return {"billing_status": status, "billed_usd": str(billed)}
        if costs.get("status") == "unavailable":
            return {"billing_status": "unavailable", "billed_usd": None}
    status = "unverified"
    if (
        record.state == "planned"
        and record.submitted_at is None
        and record.instance_id is None
    ):
        status = "not_applicable"
    return {"billing_status": status, "billed_usd": None}


def _selectable_offers(rows: list[OfferAssessment]) -> list[OfferAssessment]:
    eligible = [
        row
        for row in rows
        if row.status == "eligible"
        and type(row.offer.get("id")) is int
        and row.offer["id"] > 0
        and all(
            value is not None and value.is_finite() and value >= 0
            for value in (row.quote.hourly_usd, row.quote.total_usd)
        )
    ]
    return sorted(
        eligible,
        key=lambda row: (row.quote.hourly_usd or Decimal(0), row.offer["id"]),
    )[:100]


class VastManagement:
    def __init__(
        self,
        settings: Any,
        connection: Any,
        *,
        journal: Journal | None = None,
        client_factory: Any = VastClient,
        launch: Any = None,
        enabled: Any = None,
        selection: Any = None,
        sleep: Any = time.sleep,
    ):
        self.settings, self.connection = settings, connection
        self.journal = journal or connection.journal
        self.client_factory = client_factory
        self.launch = launch or self._launch
        self.is_enabled = enabled or (lambda: True)
        self.selection = selection or (lambda: None)
        self.sleep = sleep
        self.owner = uuid4().hex
        self._guard = threading.RLock()

    @property
    def billing(self) -> AccountBilling:
        return AccountBilling(self.journal, self.settings.VAST_API_KEY)

    @staticmethod
    def _launch(action: Any, plan_id: str) -> None:
        threading.Thread(
            target=action,
            args=(plan_id,),
            daemon=True,
            name="vast-order-" + plan_id[:8],
        ).start()

    @contextmanager
    def _service(
        self, *, check_enabled: bool = True, api_key: Any = None
    ) -> Iterator[Environments]:
        if check_enabled and not self.is_enabled():
            raise VastError(MANAGEMENT_DISABLED)
        client = self.client_factory(
            self.settings.VAST_API_KEY if api_key is None else api_key
        )
        try:
            yield Environments(client, self.journal)
        finally:
            client.close()

    def _job(self, plan_id: str) -> dict[str, Any]:
        path = self.journal.path(plan_id, MANAGEMENT_SUFFIX)
        try:
            value = json.loads(path.read_text())
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict):
            raise VastError("vast.management_journal_invalid")
        return value

    def _save(self, plan_id: str, **values: Any) -> None:
        with self._guard:
            job = {**self._job(plan_id), **values, "updated_at": now().isoformat()}
            self.journal.write(self.journal.path(plan_id, MANAGEMENT_SUFFIX), job)

    def row(self, plan_id: str, billing: dict | None = None) -> dict[str, Any]:
        plan, record = self.journal.plan(plan_id), self.journal.record(plan_id)
        job = self._job(plan_id)
        phase = job.get("phase", record.state)
        error = job.get("error")
        if phase in ACTIVE and job.get("owner") != self.owner:
            phase, error = "interrupted", "vast.management_interrupted"
        state = self.connection.status(refresh=False)
        connected = bool(
            state.get("available")
            and state.get("plan_id") == plan_id
            and any(
                m.get("name") == plan.profile.model
                and m.get("digest") == plan.profile.model_digest
                for m in state.get("models", [])
            )
        )
        if phase == "ready" and not connected:
            phase, error = "interrupted", "vast.chat_attach_required"
        return {
            "plan_id": plan_id,
            "model": plan.profile.model,
            "state": record.state,
            "phase": phase,
            "instance_id": record.instance_id,
            "hourly_usd": str(plan.assessment.quote.hourly_usd)
            if plan.assessment.quote.hourly_usd is not None
            else None,
            "total_usd": str(plan.assessment.quote.total_usd)
            if plan.assessment.quote.total_usd is not None
            else None,
            "duration_minutes": plan.profile.duration_minutes,
            "expires_at": plan.expires_at.isoformat(),
            "connected": connected,
            "error": error,
            **_billing_summary(record),
            **instance_summary(
                billing if billing is not None else self.billing.snapshot(),
                record.instance_id,
            ),
            "billing_possible": bool(
                record.submitted_at and record.state != "destroyed"
            ),
        }

    def _overview_entry(
        self, plan_id: str, *, historical: bool, billing: dict
    ) -> dict[str, Any]:
        try:
            if not historical and self._job(plan_id).get("phase") in {
                "stop_requested",
                "destroy_requested",
            }:
                return self.refresh(plan_id)
            entry = self.row(plan_id, billing)
            if historical:
                entry["phase"] = entry["state"]
            return entry
        except ERRORS:
            # A damaged entry cannot invalidate the independent current profile.
            return {
                "plan_id": plan_id,
                "model": "—",
                "state": "unknown",
                "phase": "error",
                "instance_id": None,
                "hourly_usd": None,
                "total_usd": None,
                "duration_minutes": 0,
                "expires_at": None,
                "connected": False,
                "error": "vast.management_journal_invalid",
                "billing_status": "unverified",
                "billed_usd": None,
                "billing_possible": True,
            }

    def overview(self) -> dict[str, Any]:
        model, duration, reason = None, 60, None
        try:
            value = configuration.profile(self.settings)
            model, duration = value.model, value.duration_minutes
            configuration.ssh_paths()
            key = self.settings.VAST_API_KEY
            if not (
                key.get_secret_value() if hasattr(key, "get_secret_value") else key
            ):
                raise VastError("vast.missing_api_key")
        except ERRORS as error:
            reason = "vast.management_profile_invalid"
            if isinstance(error, VastError):
                reason = error.code
        billing = self.billing.snapshot()
        rows: list[dict[str, Any]] = []
        history: list[dict[str, Any]] = []
        paths = sorted(
            self.journal.root.glob("*" + PLAN_SUFFIX),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in paths[:100]:
            # Keep CLI attempts visible as history, never as managed live orders.
            historical = not path.with_name(
                path.name.replace(PLAN_SUFFIX, MANAGEMENT_SUFFIX)
            ).exists()
            destination = history if historical else rows
            plan_id = path.name.removesuffix(PLAN_SUFFIX)
            destination.append(
                self._overview_entry(plan_id, historical=historical, billing=billing)
            )
        return {
            "configured": reason is None,
            "enabled": self.is_enabled(),
            "model": model,
            "duration_minutes": duration,
            "reason": reason,
            "environments": rows,
            "history": history,
            "billing": {
                key: value for key, value in billing.items() if key != "instances"
            },
        }

    def sync_billing(self, reconcile: bool = False) -> dict[str, Any]:
        key = self.settings.VAST_API_KEY
        billing = AccountBilling(self.journal, key)
        with self._service(api_key=key) as service:
            result = billing.sync(service.client, reconcile=reconcile)
        return {key: value for key, value in result.items() if key != "instances"}

    def search(self, duration: int) -> dict[str, Any]:
        profile = configuration.profile(self.settings, duration)
        with self._service() as service:
            rows = service.search(profile)
        return {
            "model": profile.model,
            "duration_minutes": duration,
            "offers": [
                {
                    "offer_id": row.offer.get("id"),
                    "gpu_name": row.offer.get("gpu_name", ""),
                    "country": row.host.country_code,
                    "gpu_ram_mb": row.offer.get("gpu_ram"),
                    "hourly_usd": str(row.quote.hourly_usd)
                    if row.quote.hourly_usd is not None
                    else None,
                    "total_usd": str(row.quote.total_usd)
                    if row.quote.total_usd is not None
                    else None,
                    "status": row.status,
                    "reasons": row.reasons + row.unknown,
                }
                for row in _selectable_offers(rows)
            ],
        }

    def plan(
        self, offer_id: int, duration: int, hourly: Decimal, total: Decimal
    ) -> dict[str, Any]:
        profile = configuration.profile(self.settings, duration)
        identity, known = configuration.ssh_paths()
        with self._service() as service:
            value = service.plan(profile, offer_id, hourly, total, identity, known)
        self._save(value.plan_id, phase="planned", authorized=False)
        return self.row(value.plan_id)

    def _target_allowed(self, plan_id: str) -> None:
        selected = self.selection()
        if selected and not str(selected.get("target_id", "")).startswith(
            "ollama@vast:" + plan_id + ":"
        ):
            raise VastError("vast.management_target_selected")
        state = self.connection.status(refresh=False)
        if state.get("available") and state.get("plan_id") != plan_id:
            raise VastError("vast.management_target_connected")

    def order(self, plan_id: str, accept_new_host_key: bool) -> dict[str, Any]:
        with self._guard, self.journal.lock("0" * 32):
            if not self.is_enabled():
                raise VastError(MANAGEMENT_DISABLED)
            plan = self.journal.plan(plan_id)
            job = self._job(plan_id)
            if job.get("authorized"):
                return self.row(plan_id)
            if (
                job.get("phase") != "planned"
                or self.journal.record(plan_id).state != "planned"
            ):
                raise VastError("vast.management_plan_required")
            if plan.expires_at <= now():
                raise VastError("vast.plan_expired")
            self._target_allowed(plan_id)
            for path in self.journal.root.glob("*.management.json"):
                other = path.name.removesuffix(MANAGEMENT_SUFFIX)
                if other == plan_id:
                    continue
                previous = self._job(other)
                record = self.journal.record(other)
                if previous.get("authorized") and (
                    previous.get("phase") in ACTIVE
                    or (
                        record.submitted_at
                        and record.state not in {"destroyed", "failed"}
                    )
                ):
                    raise VastError("vast.management_existing_order")
            self._save(
                plan_id,
                phase="queued",
                authorized=True,
                owner=self.owner,
                accept_new_host_key=accept_new_host_key,
                error=None,
            )
            try:
                self.launch(self._run, plan_id)
            except RuntimeError:
                self._save(
                    plan_id, phase="error", error="vast.management_worker_failed"
                )
                raise VastError("vast.management_worker_failed") from None
        return self.row(plan_id)

    def _await_ssh(self, service: Environments, plan_id: str, accept_new: bool) -> None:
        for attempt in range(12):
            if not self.is_enabled():
                raise VastError(MANAGEMENT_DISABLED)
            try:
                workload(service, plan_id, "inspect", accept_new)
                return
            except VastError as error:
                if error.code not in SSH_RETRY_ERRORS or attempt == 11:
                    raise
                self.sleep(5)

    def _attach(self, plan_id: str) -> None:
        if not self.is_enabled():
            raise VastError(MANAGEMENT_DISABLED)
        self._target_allowed(plan_id)
        plan = self.journal.plan(plan_id)
        record = self.journal.record(plan_id)
        if record.pending_action or record.state != "running":
            raise VastError("vast.chat_instance_unavailable")
        state = self.connection.status(refresh=False)
        if state.get("plan_id") != plan_id or not state.get("available"):
            state = self.connection.attach(
                plan_id, expected_model=(plan.profile.model, plan.profile.model_digest)
            )
        else:
            state = self.connection.status(refresh=True)
        if not state.get("available") or not any(
            m.get("name") == plan.profile.model
            and m.get("digest") == plan.profile.model_digest
            for m in state.get("models", [])
        ):
            self.connection.detach(expected_plan_id=plan_id)
            raise VastError("vast.management_model_not_ready")

    def _run(self, plan_id: str) -> None:
        # A concurrent short refresh must not discard the only scheduled worker.
        # HTTP handlers remain non-blocking; only the background worker waits.
        with Journal(self.journal.root / OPERATION_LOCKS).lock(plan_id, blocking=True):
            self._run_owned(plan_id)

    def _run_owned(self, plan_id: str) -> None:
        if self._job(plan_id).get("phase") != "queued":
            return
        try:
            with self._service() as service:
                self._save(plan_id, phase="creating")
                service.create(plan_id)
                self._save(plan_id, phase="waiting")
                record = service.wait(plan_id, timeout_seconds=600)
                if record.state != "running":
                    raise VastError("vast.management_not_running")
                job = self._job(plan_id)
                self._await_ssh(service, plan_id, job["accept_new_host_key"])
                self._save(plan_id, phase="provisioning")
                workload(service, plan_id, "provision", job["accept_new_host_key"])
                self._save(plan_id, phase="connecting", provisioned=True)
                for attempt in range(12):
                    try:
                        self._attach(plan_id)
                        break
                    except VastError as error:
                        if error.code not in ATTACH_RETRY_ERRORS or attempt == 11:
                            raise
                        self.sleep(5)
                self._save(plan_id, phase="ready", error=None)
        except ERRORS as error:
            self._save(
                plan_id,
                phase="error",
                error=error.code
                if isinstance(error, VastError)
                else "vast.management_failed",
            )

    def refresh(self, plan_id: str) -> dict[str, Any]:
        with Journal(self.journal.root / OPERATION_LOCKS).lock(plan_id):
            return self._refresh_owned(plan_id)

    def _refresh_owned(self, plan_id: str) -> dict[str, Any]:
        job = self._job(plan_id)
        if job.get("phase") in ACTIVE and job.get("owner") == self.owner:
            return self.row(plan_id)
        try:
            with self._service(check_enabled=False) as service:
                record = service.reconcile(plan_id)
            if record.pending_action or record.state in {"stopped", "destroyed"}:
                state = self.connection.status(refresh=False)
                if state.get("plan_id") == plan_id:
                    self.connection.detach(expected_plan_id=plan_id)
            if record.pending_action:
                self._save(
                    plan_id, phase=record.pending_action + "_requested", error=None
                )
            elif record.state in {"stopped", "destroyed"}:
                self._save(plan_id, phase=record.state, error=None)
            elif (
                record.state == "running"
                and job.get("authorized")
                and job.get("provisioned")
            ):
                self._attach(plan_id)
                self._save(plan_id, phase="ready", owner=self.owner, error=None)
        except ERRORS as error:
            self._save(
                plan_id,
                phase="error",
                error=error.code
                if isinstance(error, VastError)
                else "vast.management_failed",
            )
        return self.row(plan_id)

    def change(self, plan_id: str, action: str) -> dict[str, Any]:
        with Journal(self.journal.root / OPERATION_LOCKS).lock(plan_id):
            return self._change_owned(plan_id, action)

    def _change_owned(self, plan_id: str, action: str) -> dict[str, Any]:
        if action not in {"stop", "destroy"}:
            raise VastError("vast.invalid_action")
        job = self._job(plan_id)
        record = self.journal.record(plan_id)
        if record.pending_action == action or record.pending_action == "destroy":
            return self.row(plan_id)
        if (
            action == "destroy"
            and job.get("authorized")
            and record.submitted_at is None
        ):
            record.state = "cancelled"
            self.journal.save_record(record)
            self._save(plan_id, phase="cancelled", authorized=False, error=None)
            return self.row(plan_id)
        if job.get("phase") in ACTIVE and job.get("owner") == self.owner:
            raise VastError("vast.management_busy")
        state = self.connection.status(refresh=False)
        if state.get("plan_id") == plan_id:
            self.connection.detach(expected_plan_id=plan_id)
        with self._service(check_enabled=False) as service:
            if action == "destroy":
                service.export(plan_id)
            service.change(plan_id, "destroy" if action == "destroy" else "stop")
        self._save(plan_id, phase=action + "_requested", error=None)
        return self.row(plan_id)


_manager: VastManagement | None = None
_SINGLETON = threading.Lock()


def manager() -> VastManagement:
    global _manager
    with _SINGLETON:
        if _manager is None:
            from venom_core.config import SETTINGS
            from venom_core.services import remote_provider_control, vast_chat_runtime

            _manager = VastManagement(
                SETTINGS,
                vast_chat_runtime.connection(),
                enabled=lambda: remote_provider_control.enabled("vast_ollama"),
                selection=vast_chat_runtime.selection,
            )
        return _manager
