"""Account-level billing and daily model aggregates, without generation records."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Iterator
from uuid import uuid4

import httpx
from pydantic import AwareDatetime, BaseModel, Field

from venom_core.services import openrouter_runtime as runtime

BASE = "https://openrouter.ai/api/v1"
REFRESH_SECONDS = 300
ANALYTICS_SECONDS = 3600
Usd = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Finite = Annotated[Decimal, Field(allow_inf_nan=False)]


class BillingError(ValueError):
    pass


class Account(BaseModel):
    total_credits: Usd
    total_usage: Usd


class KeyUsage(BaseModel):
    usage: Usd
    usage_daily: Usd | None = None
    usage_weekly: Usd | None = None
    usage_monthly: Usd | None = None
    limit: Usd | None = None
    limit_remaining: Finite | None = None


class ModelUsage(BaseModel):
    usd: Usd = Decimal(0)
    requests: Annotated[int, Field(ge=0, strict=True)] = 0


class Cache(BaseModel):
    account: Account | None = None
    key: KeyUsage | None = None
    account_at: AwareDatetime | None = None
    key_at: AwareDatetime | None = None
    attempted_at: AwareDatetime | None = None
    analytics_at: AwareDatetime | None = None
    analytics_attempted_at: AwareDatetime | None = None
    errors: dict[str, str] = Field(default_factory=dict)
    source: str | None = None
    days: dict[str, dict[str, ModelUsage]] = Field(default_factory=dict)


class Store:
    """SQLite leases and atomic payload replacement also work on Windows."""

    def __init__(self, root: Path, namespace: str):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path, self.namespace = root / "billing.sqlite", namespace
        with self.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS billing (namespace TEXT PRIMARY KEY, payload TEXT NOT NULL DEFAULT '{}', owner TEXT, lease REAL NOT NULL DEFAULT 0)"
            )
        self.path.chmod(0o600)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def load(self) -> Cache:
        with self.connection() as db:
            row = db.execute(
                "SELECT payload FROM billing WHERE namespace=?", (self.namespace,)
            ).fetchone()
        if not row:
            return Cache()
        try:
            return Cache.model_validate_json(row[0])
        except ValueError:
            return Cache(errors={"account": "cache_invalid", "models": "cache_invalid"})

    def claim(self, current: float) -> str | None:
        owner = uuid4().hex
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO billing(namespace) VALUES (?)", (self.namespace,)
            )
            count = db.execute(
                "UPDATE billing SET owner=?, lease=? WHERE namespace=? AND lease<=?",
                (owner, current + 120, self.namespace, current),
            ).rowcount
        return owner if count else None

    def save(self, cache: Cache, owner: str) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE billing SET payload=?, owner=NULL, lease=0 WHERE namespace=? AND owner=?",
                (cache.model_dump_json(), self.namespace, owner),
            )

    def release(self, owner: str) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE billing SET owner=NULL, lease=0 WHERE namespace=? AND owner=?",
                (self.namespace, owner),
            )


def _management_credential() -> str:
    key = runtime.SETTINGS.OPENROUTER_MANAGEMENT_API_KEY.get_secret_value()
    if key:
        return key
    name = runtime.SETTINGS.OPENROUTER_MANAGEMENT_CREDENTIAL_FILE
    if not name:
        return ""
    try:
        path = Path(name)
        if os.name != "nt" and path.stat().st_mode & 0o077:
            return ""
        return path.read_text().strip()
    except OSError:
        return ""


def _iso(current: datetime) -> str:
    return current.astimezone(timezone.utc).date().isoformat()


def _text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _fresh(value: datetime | None, current: datetime, seconds: int) -> bool:
    return bool(value and 0 <= (current - value).total_seconds() < seconds)


def _aggregate(
    rows: list[dict], start: date, end: date, *, analytics: bool
) -> dict[str, dict[str, ModelUsage]]:
    days: dict[str, dict[str, ModelUsage]] = {
        (start + timedelta(days=offset)).isoformat(): {}
        for offset in range((end - start).days + 1)
    }
    for row in rows:
        day = str(row.get("date__day" if analytics else "date", ""))[:10]
        date.fromisoformat(day)
        if day not in days:
            raise BillingError("invalid_response")
        model = row.get("model")
        if not isinstance(model, str) or not model or len(model) > 300:
            raise BillingError("invalid_response")
        value = ModelUsage.model_validate(
            {
                "usd": row.get("total_usage" if analytics else "usage"),
                "requests": row.get("request_count" if analytics else "requests"),
            }
        )
        old = days[day].setdefault(model, ModelUsage())
        old.usd += value.usd
        old.requests += value.requests
    return days


def _summarize(
    days: dict[str, dict[str, ModelUsage]], start: date, end: date
) -> tuple[list[dict], int]:
    models: dict[str, ModelUsage] = {}
    covered = 0
    for day, values in days.items():
        if not start.isoformat() <= day <= end.isoformat():
            continue
        covered += 1
        for name, value in values.items():
            old = models.setdefault(name, ModelUsage())
            old.usd += value.usd
            old.requests += value.requests
    total = sum((v.usd for v in models.values()), Decimal(0))
    result: list[dict[str, Any]] = [
        {
            "model": key,
            "usd": str(value.usd),
            "requests": value.requests,
            "share_percent": str(value.usd * 100 / total if total else Decimal(0)),
        }
        for key, value in models.items()
    ]
    result.sort(key=lambda row: (-Decimal(row["usd"]), row["model"]))
    return result, covered


class OpenRouterBilling:
    def __init__(
        self,
        *,
        root: Path | None = None,
        credential: str | None = None,
        management: str | None = None,
        client_factory: Any = httpx.Client,
        clock: Any = None,
    ):
        self.key = runtime.credential() if credential is None else credential
        self.management = _management_credential() if management is None else management
        namespace = hashlib.sha256(
            (self.key + "\0" + self.management).encode()
        ).hexdigest()
        self.store = Store(root or runtime._STATE, namespace)
        self.client_factory = client_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _request(
        self, client: Any, path: str, key: str, payload: dict | None = None
    ) -> Any:
        if not key:
            raise BillingError("missing_credentials")
        method = "GET" if payload is None else "POST"
        try:
            response = client.request(
                method,
                BASE + path,
                headers={"Authorization": "Bearer " + key},
                json=payload,
            )
            if response.status_code == 403:
                raise BillingError("management_required")
            if response.status_code != 200:
                raise BillingError("provider_unavailable")
            data = response.json()
            if not isinstance(data, dict) or "data" not in data:
                raise BillingError("invalid_response")
            return data["data"]
        except (httpx.HTTPError, json.JSONDecodeError):
            raise BillingError("provider_unavailable") from None

    def _numbers(self, cache: Cache, client: Any, current: datetime) -> None:
        for name, path, key, schema in (
            ("account", "/credits", self.management or self.key, Account),
            ("key", "/key", self.key, KeyUsage),
        ):
            try:
                value = schema.model_validate(self._request(client, path, key))
                setattr(cache, name, value)
                setattr(cache, name + "_at", current)
                cache.errors.pop(name, None)
            except ValueError as exc:
                cache.errors[name] = (
                    str(exc) if isinstance(exc, BillingError) else "invalid_response"
                )

    def _analytics(self, client: Any, start: date, end: date) -> tuple[dict, str]:
        key = self.management or self.key
        try:
            meta = self._request(client, "/analytics/meta", key)
            metrics = {m["name"] for m in meta["metrics"]}
            dimensions = {d["name"] for d in meta["dimensions"]}
            if (
                not {"total_usage", "request_count"} <= metrics
                or "model" not in dimensions
            ):
                raise BillingError("analytics_unsupported")
            payload = {
                "metrics": ["total_usage", "request_count"],
                "dimensions": ["model"],
                "granularity": "day",
                "time_range": {
                    "start": start.isoformat() + "T00:00:00Z",
                    "end": (end + timedelta(days=1)).isoformat() + "T00:00:00Z",
                },
                "limit": 10000,
            }
            result = self._request(client, "/analytics/query", key, payload)
            if result.get("metadata", {}).get("truncated") is not False:
                raise BillingError("analytics_truncated")
            return _aggregate(result["data"], start, end, analytics=True), "analytics"
        except BillingError as exc:
            if str(exc) != "analytics_unsupported":
                raise
        # Legacy account activity contains completed UTC days only.
        rows = self._request(client, "/activity", key)
        return _aggregate(
            rows, start, end - timedelta(days=1), analytics=False
        ), "activity"

    def _sync(self, cache: Cache, client: Any, current: datetime) -> None:
        cache.attempted_at = current
        self._numbers(cache, client, current)
        if _fresh(cache.analytics_attempted_at, current, ANALYTICS_SECONDS):
            return
        cache.analytics_attempted_at = current
        try:
            end = current.astimezone(timezone.utc).date()
            days, source = self._analytics(client, end - timedelta(days=30), end)
            cache.days.update(days)
            cache.source, cache.analytics_at = source, current
            cache.errors.pop("models", None)
        except (ValueError, KeyError, TypeError) as exc:
            cache.errors["models"] = (
                str(exc) if isinstance(exc, BillingError) else "invalid_response"
            )

    def sync(self) -> None:
        current = self.clock()
        cache = self.store.load()
        if _fresh(cache.attempted_at, current, REFRESH_SECONDS):
            return
        owner = self.store.claim(current.timestamp())
        if owner is None:
            return
        try:
            cache = self.store.load()
            if _fresh(cache.attempted_at, current, REFRESH_SECONDS):
                return
            with self.client_factory(timeout=15, follow_redirects=False) as client:
                self._sync(cache, client, current)
            self.store.save(cache, owner)
        finally:
            self.store.release(owner)

    def view(
        self, period: str = "30d", start: date | None = None, end: date | None = None
    ) -> dict[str, Any]:
        cache, current = self.store.load(), self.clock()
        today = current.astimezone(timezone.utc).date()
        last = end or today
        first = start or today - timedelta(days=29)
        if start is None:
            if period == "7d":
                first = today - timedelta(days=6)
            elif period == "month":
                first = today.replace(day=1)
            elif period == "all" and cache.days:
                first = date.fromisoformat(min(cache.days))
        if first > last or last > today:
            raise BillingError("invalid_window")
        rows, covered = _summarize(cache.days, first, last)
        return {
            "configured": bool(self.key or self.management),
            "enabled": runtime.is_enabled() and runtime.cloud_allowed(),
            "account": cache.account.model_dump(mode="json") if cache.account else None,
            "available_usd": _text(
                cache.account.total_credits - cache.account.total_usage
            )
            if cache.account
            else None,
            "key": cache.key.model_dump(mode="json") if cache.key else None,
            "account_observed_at": cache.account_at,
            "models_observed_at": cache.analytics_at,
            "errors": cache.errors,
            "stale": not _fresh(cache.attempted_at, current, REFRESH_SECONDS * 2),
            "models_stale": not _fresh(
                cache.analytics_at, current, ANALYTICS_SECONDS * 2
            ),
            "source": cache.source,
            "scope": "account",
            "period": period,
            "from_utc": first.isoformat(),
            "to_utc": last.isoformat(),
            "covered_days": covered,
            "expected_days": (last - first).days + 1,
            "models": rows,
            "period_usd": str(sum((Decimal(row["usd"]) for row in rows), Decimal(0)))
            if covered
            else None,
        }
