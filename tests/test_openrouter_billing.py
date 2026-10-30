"""Provider doubles only: aggregate billing never calls a completion endpoint."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from venom_core.api.routes import openrouter as routes
from venom_core.services import openrouter_billing as billing


@pytest.fixture
def state(tmp_path, monkeypatch):
    current = [datetime(2026, 10, 30, 12, tzinfo=timezone.utc)]
    calls = []
    responses = {
        "/credits": {"total_credits": 20, "total_usage": "10.45"},
        "/key": {
            "usage": "10.4",
            "usage_daily": "0",
            "usage_monthly": "0.01",
            "limit": 15,
            "limit_remaining": "4.6",
            "label": "private",
        },
        "/analytics/meta": {
            "metrics": [{"name": "total_usage"}, {"name": "request_count"}],
            "dimensions": [{"name": "model"}],
        },
        "/analytics/query": {
            "data": [
                {
                    "date__day": "2026-10-29T00:00:00Z",
                    "model": "vendor/a",
                    "total_usage": "0.1",
                    "request_count": 2,
                },
                {
                    "date__day": "2026-10-29T00:00:00Z",
                    "model": "vendor/a",
                    "total_usage": "0.2",
                    "request_count": 3,
                },
                {
                    "date__day": "2026-10-30T00:00:00Z",
                    "model": "vendor/b:free",
                    "total_usage": "0",
                    "request_count": 1,
                },
            ],
            "metadata": {"truncated": False},
        },
        "/activity": [
            {"date": "2026-10-29", "model": "vendor/a", "usage": "0.4", "requests": 2}
        ],
    }

    def send(request):
        calls.append(request)
        path = request.url.path.removeprefix("/api/v1")
        value = responses[path]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, int):
            return httpx.Response(value)
        return httpx.Response(200, json={"data": value})

    def factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(send), **kwargs)

    monkeypatch.setattr(billing.runtime, "is_enabled", lambda: True)
    monkeypatch.setattr(billing.runtime, "cloud_allowed", lambda: True)
    service = billing.OpenRouterBilling(
        root=tmp_path,
        credential="chat-secret",
        management="management-secret",
        client_factory=factory,
        clock=lambda: current[0],
    )
    return service, responses, calls, current


def test_account_and_model_aggregates_are_idempotent_and_persistent(state):
    service, responses, calls, current = state
    assert service.view()["available_usd"] is None
    assert calls == []
    service.sync()
    first = service.view()
    assert first["available_usd"] == "9.55"
    assert first["key"]["limit_remaining"] == "4.6"
    assert "label" not in first["key"]
    assert first["period_usd"] == "0.3"
    assert first["models"][0] == {
        "model": "vendor/a",
        "usd": "0.3",
        "requests": 5,
        "share_percent": "100",
    }
    assert first["models"][1]["usd"] == "0"
    assert first["covered_days"] == first["expected_days"] == 30
    assert all(r.url.host == "openrouter.ai" for r in calls)
    assert len(calls) == 4
    service.sync()
    assert len(calls) == 4
    assert service.view() == first
    other = billing.OpenRouterBilling(
        root=service.store.path.parent,
        credential="chat-secret",
        management="management-secret",
        clock=lambda: current[0],
    )
    assert other.view() == first
    assert service.store.path.stat().st_mode & 0o777 == 0o600
    assert calls[0].headers["Authorization"] == "Bearer management-secret"
    assert calls[1].headers["Authorization"] == "Bearer chat-secret"
    current[0] += timedelta(minutes=6)
    service.sync()
    assert len(calls) == 6  # Fresh account data, cached daily model aggregation.
    current[0] += timedelta(hours=1)
    responses["/analytics/query"]["data"][0]["total_usage"] = "0.15"
    service.sync()
    assert service.view()["period_usd"] == "0.35"  # Replaces daily snapshots.


def test_period_filters_and_retained_history(state):
    service, responses, calls, current = state
    service.sync()
    assert service.view("7d")["from_utc"] == "2026-10-24"
    assert service.view("month")["from_utc"] == "2026-10-01"
    assert service.view("all")["from_utc"] == "2026-09-30"
    assert service.view(start=datetime(2026, 10, 30).date())["period_usd"] == "0"
    current[0] += timedelta(days=20)
    responses["/analytics/query"]["data"] = []
    service.sync()
    assert service.view("all")["from_utc"] == "2026-09-30"
    # Old days outside the refreshed range survive even if a model is disconnected.
    result = service.view(
        start=datetime(2026, 9, 30).date(), end=datetime(2026, 10, 10).date()
    )
    assert result["period_usd"] == "0"
    assert (
        service.view(start=datetime(2026, 9, 1).date())["covered_days"]
        < service.view(start=datetime(2026, 9, 1).date())["expected_days"]
    )
    future = datetime(2027, 1, 1).date()
    with pytest.raises(billing.BillingError):
        service.view(end=future)


def test_permission_denial_is_cached_without_hiding_credit(state):
    service, responses, calls, current = state
    responses["/analytics/meta"] = 403
    service.sync()
    assert service.view()["errors"]["models"] == "management_required"
    assert service.view()["available_usd"] == "9.55"
    assert service.view()["period_usd"] is None
    current[0] += timedelta(minutes=6)
    service.sync()
    assert len(calls) == 5  # Denied analytics is not retried for an hour.
    assert all("completions" not in r.url.path for r in calls)


@pytest.mark.parametrize(
    "failure",
    [
        403,
        500,
        httpx.ConnectError("private details"),
        {"data": [], "metadata": {"truncated": True}},
        {"data": [{"model": "vendor/a"}], "metadata": {"truncated": False}},
    ],
)
def test_analytics_failure_retains_previous_totals(state, failure):
    service, responses, calls, current = state
    service.sync()
    current[0] += timedelta(hours=2)
    responses["/analytics/query"] = failure
    responses["/credits"] = 500
    service.sync()
    view = service.view()
    assert view["period_usd"] == "0.3"
    assert view["available_usd"] == "9.55"
    assert view["errors"]["models"]
    assert view["errors"]["account"] == "provider_unavailable"
    assert "private" not in str(view)


def test_activity_fallback_and_no_fake_current_day(state):
    service, responses, calls, current = state
    responses["/analytics/meta"] = {"metrics": [], "dimensions": []}
    service.sync()
    result = service.view()
    assert result["source"] == "activity"
    assert result["period_usd"] == "0.4"
    assert result["covered_days"] < result["expected_days"]


@pytest.mark.parametrize(
    "rows",
    [
        [{"date": "bad"}],
        [{"date": "2026-10-29", "model": None}],
        [{"date": "2020-01-01", "model": "a"}],
        [{"date": "2026-10-29", "model": "a", "usage": "NaN", "requests": 1}],
    ],
)
def test_malformed_daily_aggregates_fail_closed(rows):
    start = datetime(2026, 10, 1).date()
    end = datetime(2026, 10, 30).date()
    with pytest.raises(ValueError):
        billing._aggregate(rows, start, end, analytics=False)


def test_store_leases_and_credential_isolation(state):
    service, responses, calls, current = state
    lease = service.store.claim(current[0].timestamp())
    service.sync()
    assert calls == []
    service.store.release(lease)
    service.sync()
    other = billing.OpenRouterBilling(
        root=service.store.path.parent,
        credential="other",
        management="management-secret",
    )
    assert other.view()["account"] is None
    with service.store.connection() as db:
        db.execute(
            "UPDATE billing SET payload='bad' WHERE namespace=?",
            (service.store.namespace,),
        )
    assert service.view()["errors"]["account"] == "cache_invalid"
    service.sync()
    assert service.view()["available_usd"] == "9.55"


def test_missing_credentials_unknown_numbers_and_cache_staleness(state):
    service, responses, calls, current = state
    service.key = service.management = ""
    service.sync()
    assert not calls
    assert service.view()["errors"]["account"] == "missing_credentials"
    assert service.view()["key"] is None
    current[0] += timedelta(minutes=20)
    assert service.view()["stale"]
    responses["/credits"] = {"total_credits": "NaN", "total_usage": "0"}
    service.key = "chat"
    service.sync()
    assert service.view()["account"] is None


def test_management_credential_file_is_private(tmp_path, monkeypatch):
    settings = billing.runtime.SETTINGS
    monkeypatch.setattr(settings, "OPENROUTER_MANAGEMENT_API_KEY", SecretStr(""))
    monkeypatch.setattr(
        settings, "OPENROUTER_MANAGEMENT_CREDENTIAL_FILE", str(tmp_path / "missing")
    )
    assert billing._management_credential() == ""
    p = tmp_path / "key"
    p.write_text("secret")
    p.chmod(0o644)
    monkeypatch.setattr(settings, "OPENROUTER_MANAGEMENT_CREDENTIAL_FILE", str(p))
    assert billing._management_credential() == ""
    p.chmod(0o600)
    assert billing._management_credential() == "secret"
    monkeypatch.setattr(settings, "OPENROUTER_MANAGEMENT_API_KEY", SecretStr("direct"))
    assert billing._management_credential() == "direct"


def test_routes_only_sync_when_enabled_and_reject_cross_site(state, monkeypatch):
    service, responses, calls, current = state
    monkeypatch.setattr(billing, "OpenRouterBilling", lambda: service)
    monkeypatch.setattr(routes, "require_localhost_request", lambda r: None)
    # Both routers use the same strict local operator origin policy.
    from venom_core.api.routes import vast_environments

    monkeypatch.setattr(vast_environments, "require_localhost_request", lambda r: None)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/v1/openrouter/billing").status_code == 200
        assert not calls
        assert (
            client.post(
                "/api/v1/openrouter/billing/sync",
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert client.post("/api/v1/openrouter/billing/sync").status_code == 200
        assert (
            client.get("/api/v1/openrouter/billing?period=7d").json()["period_usd"]
            == "0.3"
        )
        assert (
            client.get("/api/v1/openrouter/billing?to_utc=2099-01-01").status_code
            == 422
        )
        assert (
            client.get("/api/v1/openrouter/billing?period=invalid").status_code == 422
        )
        monkeypatch.setattr(billing.runtime, "is_enabled", lambda: False)
        assert client.post("/api/v1/openrouter/billing/sync").status_code == 403
        assert client.get("/api/v1/openrouter/billing").json()["period_usd"] == "0.3"


def test_legacy_api_fallback_when_analytics_is_absent(state):
    service, responses, calls, current = state
    responses["/analytics/meta"] = 404
    service.sync()
    assert service.view()["source"] == "activity"
    assert service.view()["period_usd"] == "0.4"


def test_corrupt_provider_json_never_exposes_response_or_credentials(state):
    service, responses, calls, current = state

    def transport(request):
        return httpx.Response(200, text="private invalid json")

    service.client_factory = lambda **kwargs: httpx.Client(
        transport=httpx.MockTransport(transport), **kwargs
    )
    service.sync()
    view = service.view()
    assert view["errors"]["account"] == "provider_unavailable"
    assert "private" not in str(view)
    assert "secret" not in str(view)


def test_long_idle_invalid_cache_owner_and_unlimited_key(state):
    service, responses, calls, current = state
    responses["/key"] = {"usage": "0", "limit": None, "limit_remaining": None}
    service.sync()
    assert service.view()["key"]["limit"] is None
    lease = service.store.claim(current[0].timestamp())
    assert service.store.claim(current[0].timestamp()) is None
    current[0] += timedelta(seconds=121)
    new_owner = service.store.claim(current[0].timestamp())
    service.store.save(billing.Cache(), lease)
    assert service.view()["available_usd"] == "9.55"
    service.store.release(new_owner)
    current[0] += timedelta(days=100)
    assert service.view()["models_stale"]


@pytest.mark.parametrize(
    "path,bad",
    [
        ("/analytics/query", []),
        ("/analytics/query", {"metadata": None}),
        ("/analytics/query", {"metadata": {"truncated": False}, "data": [None]}),
        ("/analytics/query", {"metadata": {"truncated": False}, "data": {}}),
        ("/activity", {}),
        ("/activity", [None]),
    ],
)
def test_malformed_provider_shapes_are_cached_without_losing_totals(state, path, bad):
    service, responses, calls, current = state
    service.sync()
    previous = service.view()["models"]
    current[0] += timedelta(minutes=65)
    if path == "/activity":
        responses["/analytics/meta"] = 404
    responses[path] = bad
    service.sync()
    result = service.view()
    assert result["errors"]["models"] == "invalid_response"
    assert result["models"] == previous
    assert result["available_usd"] == "9.55"
    count = len(calls)
    service.sync()
    assert len(calls) == count


@pytest.mark.parametrize(
    "period,expected",
    [
        ("30d", "2026-08-12"),
        ("7d", "2026-09-04"),
        ("month", "2026-09-01"),
    ],
)
def test_historical_end_anchors_default_billing_period(state, period, expected):
    service, *_ = state
    end = datetime(2026, 9, 10).date()
    result = service.view(period, end=end)
    assert result["from_utc"] == expected
    assert result["to_utc"] == "2026-09-10"
    explicit = service.view(period, start=datetime(2026, 8, 1).date(), end=end)
    assert explicit["from_utc"] == "2026-08-01"


def test_all_period_before_retained_history_has_no_observed_cost(state):
    service, *_ = state
    service.sync()
    end = datetime(2026, 8, 10).date()
    result = service.view("all", end=end)
    assert result["from_utc"] == "2026-08-10"
    assert result["to_utc"] == "2026-08-10"
    assert result["models"] == []
    assert result["period_usd"] is None
    assert result["covered_days"] == 0
    assert result["expected_days"] == 1
    explicit = datetime(2026, 10, 1).date()
    with pytest.raises(billing.BillingError):
        service.view("all", start=explicit, end=end)
