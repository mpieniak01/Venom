"""Decimal arithmetic, explicit UTC windows, no parent/child double counting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from venom_core.infrastructure.providers.vast.client import VastClient, VastError
from venom_core.infrastructure.providers.vast.models import (
    EnvironmentPlan,
    EnvironmentRecord,
    amount,
    now,
)


def _status(unavailable: str | None, total: Decimal | None) -> str:
    if unavailable:
        return "unavailable"
    return "provisional" if total is not None else "pending"


def _charges(
    client: VastClient, start: datetime, end: datetime
) -> tuple[list[dict], str | None]:
    unavailable = None
    try:
        rows = client.charges(int(start.timestamp()), int(end.timestamp()))
    except VastError as exc:
        if exc.code != "vast.charges_unavailable_for_host" and exc.status != 403:
            raise
        rows = []
        unavailable = exc.code
    return rows, unavailable


def _estimate(
    plan: EnvironmentPlan, record: EnvironmentRecord, start: datetime, end: datetime
) -> Decimal | None:
    reference = max(start, record.submitted_at or record.observed_at)
    # Quote-based exposure estimate: not a usage meter; stopped storage is separate.
    seconds = max(
        Decimal(0), Decimal(str((min(end, now()) - reference).total_seconds()))
    )
    hourly = plan.assessment.quote.hourly_usd
    estimate = None if hourly is None else hourly * seconds / Decimal(3600)
    transfer = plan.assessment.quote.transfer_usd
    if estimate is not None and transfer is not None:
        estimate += transfer
    return estimate


def costs(
    client: VastClient,
    plan: EnvironmentPlan,
    record: EnvironmentRecord,
    start: datetime,
    end: datetime,
) -> dict:
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise VastError("vast.invalid_window")
    if record.instance_id is None:
        raise VastError("vast.instance_required")
    rows, unavailable = _charges(client, start, end)
    attributed = [
        row for row in rows if row.get("source") == f"instance-{record.instance_id}"
    ]
    values = [amount(row.get("amount")) for row in attributed]
    known = [value for value in values if value is not None]
    total = sum(known, Decimal(0)) if known else None
    estimate = _estimate(plan, record, start, end)
    return {
        "currency": "USD",
        "instance_id": record.instance_id,
        "observed_at": now().isoformat(),
        "window_utc": [start.isoformat(), end.isoformat()],
        "status": _status(unavailable, total),
        "quote": plan.assessment.quote.model_dump(mode="json"),
        "estimate": {
            "usd": str(estimate) if estimate is not None else None,
            "kind": "quote_based_exposure_not_metered",
            "assumption": "Continuous quoted rate within requested window from submission; transfer budget included; stopped storage still billed.",
        },
        "provider_reported": {
            "usd": str(total) if total is not None else None,
            "source": "/api/v0/charges",
            "error": unavailable,
            "rows": attributed,
            "unknown_amounts": len(values) - len(known),
        },
        "unattributed_contracts": sorted(
            {str(row.get("source")) for row in rows if row not in attributed}
        ),
        "finalization": "unknown; retained journal permits later reconciliation",
    }
