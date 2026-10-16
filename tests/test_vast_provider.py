"""Provider contracts use synthetic data and never rent resources."""

from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from venom_core.infrastructure.providers.vast.client import VastClient, VastError
from venom_core.infrastructure.providers.vast.models import WorkloadProfile, amount
from venom_core.services.vast_environments.assessment import assess, quote


@pytest.fixture
def profile():
    return WorkloadProfile(
        name="fixture", cpu_arch="arm64", image="image@sha256:" + "a" * 64
    )


@pytest.fixture
def offer():
    return {
        "id": 12,
        "host_id": 3,
        "machine_id": 4,
        "cpu_arch": "arm64",
        "num_gpus": 1,
        "gpu_frac": 1,
        "rentable": True,
        "rented": False,
        "verification": "verified",
        "cpu_ram": 128000,
        "gpu_ram": 119000,
        "cpu_cores_effective": 20,
        "reliability": 0.999,
        "disk_space": 250,
        "duration": 10000,
        "direct_port_count": 10,
        "search": {"totalHour": "0.4", "diskHour": "0.02"},
    }


class Transport:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(
            reply[0], json=reply[1], request=httpx.Request(method, url)
        )

    def close(self):
        self.closed = True


def client(replies):
    transport = Transport(replies)
    return VastClient(SecretStr("fake-key"), transport, sleep=lambda _: None), transport


def test_quote_includes_disk_once(profile, offer):
    result = quote(offer, profile)
    assert result.hourly_usd == Decimal("0.4")
    assert result.storage_hourly_usd == Decimal("0.02")
    assert result.total_usd == Decimal("0.2")
    assert result.samples_minutes_usd["60"] == Decimal("0.4")


def test_assessment(profile, offer):
    assert assess(offer, profile).status == "eligible"
    assert assess({**offer, "cpu_arch": "amd64"}, profile).status == "ineligible"
    assert assess({**offer, "disk_space": 32}, profile).reasons == ["disk_space"]
    incomplete = {k: v for k, v in offer.items() if k != "gpu_ram"}
    assert assess(incomplete, profile).status == "unknown"
    assert assess(offer, profile).performance == "unknown"


def test_unknown_transfer_unit(profile, offer):
    changed = profile.model_copy(update={"download_gb": Decimal("20")})
    assert quote(offer, changed).total_usd is None
    result = quote({**offer, "internet_down_cost_per_tb": "2"}, changed)
    assert result.transfer_usd == Decimal("0.04")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-2", None, "no"])
def test_invalid_money(value):
    assert amount(value) is None


def test_pinned_images(profile):
    assert profile.disk_gb == 150
    with pytest.raises(ValidationError):
        WorkloadProfile(name="bad", cpu_arch="amd64", image="image:latest")


def test_account_allowlist():
    api, _ = client(
        [(200, {"credit": 9.52, "balance": 0, "email": "private", "ssh_key": "secret"})]
    )
    assert api.account() == {"credit": 9.52, "balance": 0}
    api.close()


@pytest.mark.parametrize("status", [401, 403, 404, 410, 302])
def test_http_errors(status):
    api, transport = client([(status, {"error": "secret"})])
    with pytest.raises(VastError) as exc:
        api.account()
    assert exc.value.status == status
    assert "secret" not in str(exc.value)
    assert len(transport.calls) == 1


def test_bounded_retries_and_rejection():
    api, transport = client([(429, "too fast"), (503, {}), (200, {"credit": 1})])
    assert api.account() == {"credit": 1}
    assert len(transport.calls) == 3
    assert all(x[2]["disable_retry"] for x in transport.calls)
    api, _ = client([(200, {"success": False, "msg": "private"})])
    with pytest.raises(VastError, match="vast.provider_rejected"):
        api.account()


def test_create_timeout_never_retried():
    api, transport = client([httpx.ReadTimeout("sensitive")])
    with pytest.raises(VastError) as exc:
        api.create(12, {"image": "test"})
    assert exc.value.ambiguous
    assert len(transport.calls) == 1


def test_create_success_and_no_id():
    api, _ = client([(200, {"new_contract": 88})])
    assert api.create(12, {}) == 88
    api, _ = client([(200, {"success": True})])
    with pytest.raises(VastError) as exc:
        api.create(12, {})
    assert exc.value.ambiguous


def test_paginate_and_sanitize():
    api, transport = client(
        [
            (
                200,
                {
                    "instances": [{"id": 1, "jupyter_token": "secret"}],
                    "next_token": "next",
                },
            ),
            (200, {"instances": [{"id": 2}], "next_token": None}),
        ]
    )
    assert api.instances() == [{"id": 1}, {"id": 2}]
    assert transport.calls[1][2]["params"]["after_token"] == "next"


def test_repeated_pagination():
    api, _ = client([(200, {"instances": [], "next_token": "x"})] * 2)
    with pytest.raises(VastError, match="vast.pagination_invalid"):
        api.instances()


def test_offer_query_and_sanitize(profile, offer):
    api, transport = client([(200, {"offers": [{**offer, "extra_env": "secret"}]})])
    rows = api.offers(profile.disk_gb)
    assert "extra_env" not in rows[0]
    assert transport.calls[0][2]["json"]["allocated_storage"] == 150
    assert transport.calls[0][2]["json"]["type"] == "ondemand"


def test_missing_key():
    with pytest.raises(VastError, match="vast.missing_key"):
        VastClient(SecretStr(""))
