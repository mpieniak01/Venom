"""Incremental provider billing uses doubles; never rents or generates."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import EnvironmentRecord
from venom_core.services.vast_environments.account_billing import (
    AccountBilling,
    instance_summary,
)
from venom_core.services.vast_environments.store import Journal


@pytest.fixture
def billing(tmp_path):
    current = [datetime(2026, 10, 30, 12, tzinfo=timezone.utc)]
    journal = Journal(tmp_path)
    journal.save_record(
        EnvironmentRecord(
            plan_id="a" * 32,
            instance_id=88,
            state="destroyed",
            submitted_at=current[0] - timedelta(days=1),
        )
    )
    client = Mock()
    client.account.return_value = {
        "credit": "8.9",
        "balance": 0,
        "api_key": "not public",
    }
    client.charges.return_value = [
        {"source": "instance-88", "amount": "0.4", "items": [{"amount": "0.4"}]},
        {"source": "volume-9", "amount": "0.1"},
    ]
    ledger = AccountBilling(journal, SecretStr("fake"), clock=lambda: current[0])
    return SimpleNamespace(
        ledger=ledger, journal=journal, client=client, current=current
    )


def test_backfill_totals_deleted_instances_and_atomic_idempotence(billing):
    b = billing
    assert b.ledger.snapshot()["status"] == "empty"
    result = b.ledger.sync(b.client)
    assert result["covered_days"] == 31
    assert result["total_usd"] == "15.5"
    assert result["managed_usd"] == "12.4"
    assert result["other_usd"] == "3.1"
    assert result["credit_usd"] == "8.9"
    assert instance_summary(result, 88)["billed_usd"] == "12.4"
    assert instance_summary(result, None) == {}
    assert instance_summary(result, 99) == {}
    b.ledger.sync(b.client)
    assert b.client.account.call_count == 1
    assert b.client.charges.call_count == 31
    # Cache survives a service restart and never adds repeated observations.
    restarted = AccountBilling(b.journal, SecretStr("fake"), clock=lambda: b.current[0])
    assert restarted.snapshot() == result
    b.current[0] += timedelta(minutes=6)
    assert restarted.sync(b.client)["total_usd"] == "15.5"
    assert b.client.charges.call_count == 33
    # Every interval is disjoint and ends at 23:59:59 UTC.
    start, end = b.client.charges.call_args.args
    assert end - start == 86399


def test_rollover_fetches_new_day_and_revises_recent_days(billing):
    b = billing
    b.ledger.sync(b.client)
    b.current[0] += timedelta(days=1)
    b.client.charges.return_value = [{"source": "instance-88", "amount": "0.5"}]
    result = b.ledger.sync(b.client)
    assert b.client.charges.call_count == 33
    assert Decimal(result["instances"]["88"]) == Decimal("12.6")
    assert result["from_utc"] == "2026-10-01"


def test_partial_unknown_is_not_a_complete_instance_total(billing):
    b = billing
    b.client.charges.return_value = [
        {"source": "instance-88", "amount": "0.1"},
        {"source": "instance-88", "amount": None},
    ]
    result = b.ledger.sync(b.client)
    assert result["status"] == "partial"
    assert result["instances"]["88"] is None
    assert instance_summary(result, 88) == {}
    b.current[0] += timedelta(minutes=6)
    b.client.charges.return_value = [{"source": "instance-88", "amount": "0"}]
    result = b.ledger.sync(b.client)
    assert instance_summary(result, 88)["billing_status"] == "reported"
    assert result["total_usd"] == "0"


@pytest.mark.parametrize(
    "error", [VastError("vast.http_error", 403), OSError(), ValueError()]
)
def test_failure_preserves_cached_costs_and_credit(billing, error):
    b = billing
    old = b.ledger.sync(b.client)
    b.current[0] += timedelta(minutes=6)
    b.client.account.side_effect = error
    b.client.charges.side_effect = error
    result = b.ledger.sync(b.client)
    assert result["status"] == "stale"
    assert result["credit_usd"] == old["credit_usd"]
    assert result["total_usd"] == old["total_usd"]
    assert result["error"] and result["account_error"]
    assert instance_summary(result, 88)["billing_status"] == "partial"
    assert b.client.charges.call_count == 32


def test_unavailable_account_and_invalid_numbers_do_not_fake_zero(billing):
    b = billing
    b.client.account.return_value = {"credit": "NaN"}
    b.client.charges.side_effect = VastError("vast.charges_unavailable_for_host", 200)
    result = b.ledger.sync(b.client)
    assert result["status"] == "unavailable"
    assert result["total_usd"] is None and result["credit_usd"] is None
    assert b.client.charges.call_count == 1


def test_cache_is_scoped_to_credential_and_corruption_can_recover(billing):
    b = billing
    b.ledger.sync(b.client)
    other = AccountBilling(
        b.journal, SecretStr("different"), clock=lambda: b.current[0]
    )
    assert other.snapshot()["credit_usd"] is None
    path = next(b.ledger.journal.root.glob("*.billing.json"))
    assert path.stat().st_mode & 0o777 == 0o600
    path.write_text("broken")
    assert b.ledger.snapshot()["error"] == "vast.billing_cache_invalid"
    assert b.ledger.sync(b.client)["status"] == "ready"


def test_explicit_reconciliation_reloads_archived_days(billing):
    b = billing
    b.ledger.sync(b.client)
    b.current[0] += timedelta(minutes=6)
    b.client.charges.return_value = [{"source": "instance-88", "amount": "0.2"}]
    result = b.ledger.sync(b.client, reconcile=True)
    assert result["total_usd"] == "6.2"
    assert b.client.charges.call_count == 62


def test_long_history_backfill_is_bounded_and_continues(billing):
    b = billing
    b.journal.save_record(
        EnvironmentRecord(
            plan_id="b" * 32,
            instance_id=99,
            submitted_at=b.current[0] - timedelta(days=65),
        )
    )
    (b.journal.root / ("c" * 32 + ".record.json")).write_text("broken")
    first = b.ledger.sync(b.client)
    assert first["expected_days"] == 66 and first["status"] == "partial"
    assert instance_summary(first, 88)["billing_status"] == "partial"
    for _ in range(3):
        b.current[0] += timedelta(minutes=6)
        result = b.ledger.sync(b.client)
    assert result["covered_days"] == 66 and result["status"] == "ready"
    b.current[0] += timedelta(minutes=6)
    assert b.ledger.sync(b.client, reconcile=True)["status"] == "partial"
    for _ in range(3):
        b.current[0] += timedelta(minutes=6)
        result = b.ledger.sync(b.client)
    assert result["status"] == "ready"


def test_cross_process_lock_returns_cache_without_request(billing):
    b = billing
    from venom_core.services.vast_environments.account_billing import CACHE_ID

    with b.ledger.journal.lock(CACHE_ID):
        assert b.ledger.sync(b.client)["status"] == "empty"
    b.client.account.assert_not_called()
    b.ledger.journal.lock = Mock(side_effect=VastError("vast.invalid_plan_id"))
    with pytest.raises(VastError, match="invalid_plan_id"):
        b.ledger.sync(b.client)
