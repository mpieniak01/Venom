"""Persistent, credential-isolated daily provider charges; no rental operations."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Any

import httpx
from pydantic import AwareDatetime, BaseModel, Field

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import amount, now
from venom_core.services.vast_environments.store import Journal

Usd = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Finite = Annotated[Decimal, Field(allow_inf_nan=False)]
CACHE_ID = "b" * 32
REFRESH_SECONDS = 300
MAX_DAYS_PER_SYNC = 31
ERRORS = (VastError, OSError, ValueError, httpx.HTTPError)


class ChargeDay(BaseModel):
    total: Usd = Decimal(0)
    instances: dict[str, Usd | None] = Field(default_factory=dict)
    unknown_amounts: int = 0
    observed_at: AwareDatetime


class BillingCache(BaseModel):
    credit: Finite | None = None
    balance: Finite | None = None
    account_observed_at: AwareDatetime | None = None
    attempted_at: AwareDatetime | None = None
    error: str | None = None
    account_error: str | None = None
    reconcile_pending: list[str] = Field(default_factory=list)
    days: dict[str, ChargeDay] = Field(default_factory=dict)


def _error(exc: Exception) -> str:
    return exc.code if isinstance(exc, VastError) else "vast.billing_unavailable"


def _day(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _sum_rows(rows: list[dict], observed: datetime) -> ChargeDay:
    result = ChargeDay(observed_at=observed)
    for row in rows:
        value = amount(row.get("amount"))
        if value is None:
            result.unknown_amounts += 1
        else:
            result.total += value
        match = re.fullmatch(r"instance-([1-9][0-9]*)", str(row.get("source", "")))
        if not match:
            continue
        key = match[1]
        if key not in result.instances:
            result.instances[key] = Decimal(0)
        previous = result.instances[key]
        result.instances[key] = (
            None if value is None or previous is None else previous + value
        )
    return result


class AccountBilling:
    def __init__(self, journal: Journal, api_key: Any, clock=now):
        key = (
            api_key.get_secret_value()
            if hasattr(api_key, "get_secret_value")
            else api_key
        )
        self.configured = bool(key)
        namespace = hashlib.sha256(str(key or "").encode()).hexdigest()
        self.journal = Journal(journal.root / "billing" / namespace)
        self.source, self.clock = journal, clock

    def _load(self) -> BillingCache:
        path = self.journal.path(CACHE_ID, ".billing.json")
        if not path.exists():
            return BillingCache()
        return BillingCache.model_validate_json(path.read_text())

    def _records(self) -> list[Any]:
        records = []
        for path in self.source.root.glob("*.record.json"):
            try:
                records.append(
                    self.source.record(path.name.removesuffix(".record.json"))
                )
            except ERRORS:
                continue
        return records

    def _start(self, records: list[Any], current: datetime) -> datetime:
        dates = [current - timedelta(days=30)]
        dates.extend(r.submitted_at for r in records if r.submitted_at is not None)
        return _day(min(dates))

    def _snapshot(self, cache: BillingCache) -> dict[str, Any]:
        current = self.clock()
        records = self._records()
        start = self._start(records, current)
        today = _day(current)
        days = {
            key: value
            for key, value in cache.days.items()
            if start.date().isoformat() <= key <= today.date().isoformat()
        }
        instances: dict[str, Decimal | None] = {}
        for value in days.values():
            for key, usd in value.instances.items():
                old = instances.get(key, Decimal(0))
                instances[key] = None if old is None or usd is None else old + usd
        expected = (today - start).days + 1
        partial = (
            len(days) != expected
            or any(v.unknown_amounts for v in days.values())
            or bool(cache.reconcile_pending)
        )
        status = "partial" if partial else "ready"
        if cache.error:
            status = "stale" if days else "unavailable"
        if not days and not cache.attempted_at and not cache.error:
            status = "empty"
        managed_ids = {str(r.instance_id) for r in records if r.instance_id is not None}
        managed = sum(
            (
                usd
                for key, usd in instances.items()
                if key in managed_ids and usd is not None
            ),
            Decimal(0),
        )
        total = sum((value.total for value in days.values()), Decimal(0))
        return {
            "status": status,
            "error": cache.error,
            "account_error": cache.account_error,
            "credit_usd": str(cache.credit) if cache.credit is not None else None,
            "balance_usd": str(cache.balance) if cache.balance is not None else None,
            "account_observed_at": cache.account_observed_at.isoformat()
            if cache.account_observed_at
            else None,
            "observed_at": cache.attempted_at.isoformat()
            if cache.attempted_at
            else None,
            "from_utc": start.date().isoformat(),
            "to_utc": today.date().isoformat(),
            "total_usd": str(total) if days else None,
            "managed_usd": str(managed) if days else None,
            "other_usd": str(total - managed) if days else None,
            "covered_days": len(days),
            "expected_days": expected,
            "instances": {
                key: str(value) if value is not None else None
                for key, value in instances.items()
            },
            "complete": not partial and not cache.error,
        }

    def snapshot(self) -> dict[str, Any]:
        try:
            return self._snapshot(self._load())
        except ERRORS:
            return self._snapshot(BillingCache(error="vast.billing_cache_invalid"))

    def sync(self, client: Any, *, reconcile: bool = False) -> dict[str, Any]:
        try:
            with self.journal.lock(CACHE_ID):
                return self._sync_owned(client, reconcile)
        except VastError as exc:
            if exc.code != "vast.plan_busy":
                raise
            return self.snapshot()

    def _sync_owned(self, client: Any, reconcile: bool) -> dict[str, Any]:
        try:
            cache = self._load()
        except ERRORS:
            cache = BillingCache()
        current = self.clock()
        if (
            cache.attempted_at
            and (current - cache.attempted_at).total_seconds() < REFRESH_SECONDS
        ):
            return self._snapshot(cache)
        cache.attempted_at = current
        cache.error = None
        try:
            data = client.account()
            account = BillingCache(
                credit=data.get("credit"), balance=data.get("balance")
            )
            cache.credit, cache.balance = account.credit, account.balance
            cache.account_observed_at, cache.account_error = current, None
        except ERRORS as exc:
            cache.account_error = _error(exc)
        start, today = self._start(self._records(), current), _day(current)
        candidates = []
        cursor = today
        while cursor >= start:
            stored = cache.days.get(cursor.date().isoformat())
            if (
                reconcile
                or cursor.date().isoformat() in cache.reconcile_pending
                or stored is None
                or stored.unknown_amounts
                or cursor >= today - timedelta(days=1)
            ):
                candidates.append(cursor)
            cursor -= timedelta(days=1)
        if reconcile:
            cache.reconcile_pending = [value.date().isoformat() for value in candidates]
        for cursor in candidates[:MAX_DAYS_PER_SYNC]:
            try:
                rows = client.charges(
                    int(cursor.timestamp()),
                    int((cursor + timedelta(days=1)).timestamp()) - 1,
                )
                key = cursor.date().isoformat()
                cache.days[key] = _sum_rows(rows, current)
                if key in cache.reconcile_pending:
                    cache.reconcile_pending.remove(key)
            except ERRORS as exc:
                cache.error = _error(exc)
                break
        self.journal.write(
            self.journal.path(CACHE_ID, ".billing.json"), cache.model_dump(mode="json")
        )
        return self._snapshot(cache)


def instance_summary(snapshot: dict, instance_id: int | None) -> dict[str, Any]:
    if instance_id is None:
        return {}
    value = snapshot["instances"].get(str(instance_id))
    if value is None:
        return {}
    status = "reported" if snapshot["complete"] else "partial"
    return {
        "billed_usd": value,
        "billing_status": status,
        "billing_observed_at": snapshot["observed_at"],
    }
