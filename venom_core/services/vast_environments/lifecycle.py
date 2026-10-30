"""One source of truth for rental intent, outcome and recovery."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

from venom_core.infrastructure.providers.vast.client import (
    MAX_OFFER_SEARCH_LIMIT,
    VastClient,
    VastError,
    ssh_fingerprint,
)
from venom_core.infrastructure.providers.vast.models import (
    EnvironmentPlan,
    EnvironmentRecord,
    OfferAssessment,
    WorkloadProfile,
    digest,
    now,
)
from venom_core.services.vast_environments.assessment import assess, search_filters
from venom_core.services.vast_environments.history import lookup, matching_rows
from venom_core.services.vast_environments.recipes import verify_template
from venom_core.services.vast_environments.selection import preferred_queries, rank
from venom_core.services.vast_environments.startup import ollama_environment, startup
from venom_core.services.vast_environments.store import Journal


class Environments:
    def __init__(self, client: VastClient, journal: Journal):
        self.client = client
        self.journal = journal

    def assess(
        self,
        profile: WorkloadProfile,
        offer: dict,
        retest: bool = False,
        *,
        history_rows: list[dict] | None = None,
    ) -> OfferAssessment:
        result = assess(offer, profile)
        result.history = lookup(self.journal, profile, result.offer, rows=history_rows)
        if result.history["excluded"] and not retest:
            result.status = "ineligible"
            result.reasons.append("qualification.previous_unsuitable")
        return result

    def search(
        self, profile: WorkloadProfile, retest: bool = False
    ) -> list[OfferAssessment]:
        filters = search_filters(profile)
        offers = list(
            self.client.offers(profile.disk_gb, filters, limit=MAX_OFFER_SEARCH_LIMIT)
        )
        for query in preferred_queries(profile, filters):
            offers.extend(
                self.client.offers(profile.disk_gb, query, limit=MAX_OFFER_SEARCH_LIMIT)
            )
        merged: dict[int | str, dict] = {}
        for row in offers:
            value = row.get("id")
            key = (
                value if type(value) is int and value > 0 else f"unknown-{len(merged)}"
            )
            merged[key] = row
        history_rows = matching_rows(self.journal, profile)
        return rank(
            [
                self.assess(profile, row, retest, history_rows=history_rows)
                for row in merged.values()
            ],
            profile,
        )

    def plan(
        self,
        profile: WorkloadProfile,
        offer_id: int,
        max_hourly: Decimal,
        max_total: Decimal,
        identity: Path,
        known_hosts: Path,
        finish_policy: Literal["manual", "stop", "destroy"] = "manual",
        retest: bool = False,
    ) -> EnvironmentPlan:
        verify_template(self.client, profile)
        offer = self._offer(profile, offer_id)
        assessment = self.assess(profile, offer, retest)
        if assessment.status != "eligible":
            raise VastError("vast.offer_not_eligible")
        plan_id = uuid4().hex
        plan = EnvironmentPlan(
            plan_id=plan_id,
            retest=retest,
            profile=profile,
            assessment=assessment,
            expires_at=now() + timedelta(minutes=10),
            max_hourly_usd=max_hourly,
            max_total_usd=max_total,
            finish_policy=finish_policy,
            ssh_identity_file=str(identity.expanduser().resolve()),
            ssh_known_hosts=str(known_hosts.expanduser().resolve()),
            ssh_fingerprint=ssh_fingerprint(
                Path(str(identity.expanduser()) + ".pub").read_text()
            ),
            startup_sha256=digest(startup(profile)),
        )
        self._limits(plan, assessment)
        plan.checksum = plan.calculate_checksum()
        self.journal.save_plan(plan)
        self._event(EnvironmentRecord(plan_id=plan_id), "planned")
        return plan

    def _offer(self, profile: WorkloadProfile, offer_id: int) -> dict:
        filters = {**search_filters(profile), "ask_contract_id": {"eq": offer_id}}
        offers = list(
            self.client.offers(profile.disk_gb, filters, limit=MAX_OFFER_SEARCH_LIMIT)
        )
        matching = [x for x in offers if x.get("id") == offer_id]
        if len(matching) != 1:
            raise VastError("vast.offer_expired")
        return matching[0]

    @staticmethod
    def _limits(plan, assessment) -> tuple[Decimal, Decimal]:
        cost = assessment.quote
        if (
            cost.hourly_usd is None
            or cost.total_usd is None
            or cost.hourly_usd > plan.max_hourly_usd
            or cost.total_usd > plan.max_total_usd
        ):
            raise VastError("vast.budget_exceeded")
        return cost.hourly_usd, cost.total_usd

    def _event(self, record: EnvironmentRecord, state: str) -> EnvironmentRecord:
        record.state = state
        record.observed_at = now()
        record.events.append({"state": state, "at": record.observed_at.isoformat()})
        self.journal.save_record(record)
        return record

    def create(self, plan_id: str) -> EnvironmentRecord:
        with self.journal.lock(plan_id):
            plan = self.journal.plan(plan_id)
            record = self.journal.record(plan_id)
            if record.state != "planned":
                raise VastError("vast.reconcile_required")
            if plan.expires_at < now():
                raise VastError("vast.plan_expired")
            verify_template(self.client, plan.profile)
            fresh = self.assess(
                plan.profile,
                self._offer(plan.profile, plan.assessment.offer["id"]),
                plan.retest,
            )
            if fresh.status != "eligible":
                raise VastError("vast.offer_not_eligible")
            for key in ("machine_id", "host_id"):
                if fresh.offer.get(key) != plan.assessment.offer.get(key):
                    raise VastError("vast.offer_changed")
            new_hourly, new_total = self._limits(plan, fresh)
            old_hourly, old_total = self._limits(plan, plan.assessment)
            if new_hourly > old_hourly or new_total > old_total:
                raise VastError("vast.price_changed")
            if digest(startup(plan.profile)) != plan.startup_sha256:
                raise VastError("vast.startup_changed")
            if plan.ssh_fingerprint not in self.client.ssh_fingerprints():
                raise VastError("vast.ssh_key_not_registered")
            record.submitted_at = now()
            self._event(record, "submitting")
            try:
                record.instance_id = self.client.create(
                    plan.assessment.offer["id"],
                    {
                        "image": plan.profile.image,
                        "disk": plan.profile.disk_gb,
                        "runtype": "ssh",
                        "target_state": "running",
                        "cancel_unavail": True,
                        "label": "venom-" + plan_id,
                        "onstart": startup(plan.profile),
                        **(
                            {"env": ollama_environment(plan.profile)}
                            if plan.profile.mode == "ollama"
                            else {}
                        ),
                    },
                )
            except VastError as exc:
                self._event(record, "outcome_unknown" if exc.ambiguous else "failed")
                raise
            return self._event(record, "created")

    def _recover(self, plan: EnvironmentPlan, record: EnvironmentRecord) -> bool:
        if record.state not in {"submitting", "outcome_unknown"}:
            return False
        matches = [
            row
            for row in self.client.instances()
            if row.get("label") == "venom-" + plan.plan_id
        ]
        if len(matches) != 1:
            self._event(record, "outcome_unknown")
            return False
        match = matches[0]
        if any(match.get(key) is None for key in ("host_id", "machine_id")):
            self._event(record, "outcome_unknown")
            return False
        if any(
            match[key] != plan.assessment.offer[key]
            for key in ("host_id", "machine_id")
        ):
            raise VastError("vast.recovery_mismatch")
        record.instance_id = match["id"]
        return True

    def reconcile(self, plan_id: str) -> EnvironmentRecord:
        with self.journal.lock(plan_id):
            plan = self.journal.plan(plan_id)
            record = self.journal.record(plan_id)
            if record.instance_id is None:
                self._recover(plan, record)
            if record.instance_id is None:
                return record
            try:
                instance = self.client.instance(record.instance_id)
            except VastError as exc:
                if exc.status in {404, 410} and record.pending_action == "destroy":
                    record.pending_action = None
                    return self._event(record, "destroyed")
                # Missing telemetry does not prove stopped/destroyed.
                self._event(record, "unknown")
                raise
            record.instance = instance
            state = instance.get("actual_status")
            if state is not None and not isinstance(state, str):
                self._event(record, "unknown")
                raise VastError("vast.instance_status_invalid")
            state = state or "unknown"
            target = {"start": "running", "stop": "stopped"}.get(
                record.pending_action or ""
            )
            if target == state:
                record.pending_action = None
            return self._event(record, state)

    def change(
        self, plan_id: str, action: Literal["start", "stop", "destroy"]
    ) -> EnvironmentRecord:
        if action not in {"start", "stop", "destroy"}:
            raise VastError("vast.invalid_action")
        with self.journal.lock(plan_id):
            self.journal.plan(plan_id)
            record = self.journal.record(plan_id)
            if record.instance_id is None or record.state == "destroyed":
                raise VastError("vast.instance_required")
            if (
                action == "destroy"
                and not self.journal.path(plan_id, ".export.json").exists()
            ):
                raise VastError("vast.export_required")
            record.pending_action = action
            self._event(record, action + "_requested")
            try:
                if action == "destroy":
                    self.client.destroy(record.instance_id)
                else:
                    self.client.set_state(
                        record.instance_id,
                        "running" if action == "start" else "stopped",
                    )
            except VastError:
                self._event(record, action + "_unknown")
                raise
            return record

    def export(self, plan_id: str) -> dict:
        with self.journal.lock(plan_id):
            data = {
                "plan": self.journal.plan(plan_id).model_dump(mode="json"),
                "record": self.journal.record(plan_id).model_dump(mode="json"),
                "exported_at": now().isoformat(),
            }
            self.journal.write(self.journal.path(plan_id, ".export.json"), data)
            return data

    def cleanup(self, plan_id: str) -> EnvironmentRecord:
        plan = self.journal.plan(plan_id)
        self.export(plan_id)
        if plan.finish_policy == "manual":
            raise VastError("vast.manual_cleanup_required")
        return self.change(plan_id, plan.finish_policy)

    def wait(
        self, plan_id: str, timeout_seconds: int = 120, sleep=None
    ) -> EnvironmentRecord:
        import time

        if not 1 <= timeout_seconds <= 600:
            raise VastError("vast.invalid_timeout")
        pause = sleep or time.sleep
        deadline = time.monotonic() + timeout_seconds
        for attempt in range(100):
            record = self.reconcile(plan_id)
            if record.state in {"running", "stopped", "destroyed", "failed", "error"}:
                return record
            if time.monotonic() >= deadline:
                break
            pause(min(2 + attempt, 10, max(0, deadline - time.monotonic())))
        return self.journal.record(plan_id)
