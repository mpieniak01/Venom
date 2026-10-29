"""Provider contracts use synthetic data and never rent resources."""

import json
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
    empty_key = SecretStr("")
    with pytest.raises(VastError, match="vast.missing_key"):
        VastClient(empty_key)


def test_object_and_invalid_wire_shapes():
    api, _ = client([(200, [])])
    with pytest.raises(VastError, match="vast.invalid_response"):
        api.account()
    api, _ = client([(200, "invalid")])
    with pytest.raises(VastError, match="vast.invalid_response"):
        api.account()
    api, _ = client([(200, {})])
    with pytest.raises(VastError):
        api.instances()
    api, _ = client([(200, {})])
    with pytest.raises(VastError):
        api.offers(150)


def test_instance_and_mutations_and_volumes():
    api, transport = client(
        [
            (
                200,
                {
                    "instances": {
                        "id": 88,
                        "actual_status": "running",
                        "onstart": "secret",
                    }
                },
            ),
            (200, {"success": True}),
            (200, {"success": True}),
            (200, {"volumes": [{"id": 7, "status": "active", "private": "secret"}]}),
            (
                200,
                {
                    "results": [
                        {"source": "instance-88", "amount": 1, "items": [{"amount": 1}]}
                    ]
                },
            ),
        ]
    )
    assert api.instance(88) == {"id": 88, "actual_status": "running"}
    api.set_state(88, "stopped")
    api.destroy(88)
    assert api.volumes() == [{"id": 7, "status": "active"}]
    assert api.charges(1, 2) == [{"source": "instance-88", "amount": 1}]
    assert json.loads(transport.calls[-1][2]["params"]["select_filters"])["day"] == {
        "gte": 1,
        "lte": 2,
    }
    with pytest.raises(VastError):
        api.charges(2, 1)
    with pytest.raises(VastError):
        api.set_state(88, "bad")
    with pytest.raises(VastError):
        api._request("GET", "//foreign.test")


def test_ssh_response_uses_public_key():
    from venom_core.infrastructure.providers.vast.client import ssh_fingerprint

    public = "ssh-ed25519 YWJjZA== fixture"
    api, _ = client(
        [(200, [{"public_key": public, "private_key": "private", "deleted_at": None}])]
    )
    assert api.ssh_fingerprints() == [ssh_fingerprint(public)]
    for value in ["bad", "ssh-ed25519 @@@"]:
        with pytest.raises(VastError):
            ssh_fingerprint(value)
    api, _ = client([(200, {})])
    with pytest.raises(VastError):
        api.ssh_fingerprints()


def test_retry_exhaustion_and_ambiguous_mutation():
    api, transport = client([(503, {})] * 3)
    with pytest.raises(VastError):
        api.account()
    assert len(transport.calls) == 3
    api, transport = client([(503, {})])
    with pytest.raises(VastError) as exc:
        api.create(12, {})
    assert exc.value.ambiguous
    assert len(transport.calls) == 1


def test_missing_rate_and_local_filters(profile, offer):
    from venom_core.services.vast_environments.assessment import search_filters

    assert quote({}, profile).hourly_usd is None
    missing = {k: v for k, v in offer.items() if k not in {"cpu_arch", "id"}}
    assert assess(missing, profile).status == "unknown"
    changed = profile.model_copy(update={"countries": ["PL"], "gpu_names": ["GB10"]})
    assert search_filters(changed)["geolocation"] == {"in": ["PL"]}
    assert "country" in assess({**offer, "geolocation": "Spain, ES"}, changed).reasons
    assert "country" in assess(offer, changed).unknown
    assert (
        "country" not in assess({**offer, "geolocation": "Poland, PL"}, changed).unknown
    )
    raw = {**offer, "reliability2": 0.999}
    del raw["reliability"]
    assert assess(raw, profile).status == "eligible"


@pytest.mark.parametrize(
    "updates",
    [
        {"image": "invalid@sha256:" + "z" * 64},
        {"image": "-bad@sha256:" + "a" * 64},
        {"image": "REPLACE_WITH_IMAGE@sha256:" + "0" * 64},
        {"model": "bad model"},
        {"model_digest": "-bad"},
    ],
)
def test_profile_validators(profile, updates):
    invalid_profile_data = {**profile.model_dump(), **updates}
    with pytest.raises(ValidationError):
        WorkloadProfile.model_validate(invalid_profile_data)


def test_host_billing_rejection_is_explicit():
    api, _ = client(
        [(200, {"success": False, "msg": "Host users do not have instance charges"})]
    )
    with pytest.raises(VastError, match="vast.charges_unavailable_for_host"):
        api.charges(1, 2)


def test_template_and_history_boundary():
    api, wire = client(
        [
            (
                200,
                {
                    "templates": [
                        {
                            "hash_id": "abc",
                            "image": "ollama/ollama",
                            "env": "-e TOKEN=secret",
                            "onstart": "secret",
                            "docker_login_pass": "secret",
                            "extra_filters": {"gpu_ram": {"gte": 24000}},
                        }
                    ]
                },
            ),
            (
                200,
                {
                    "benchmarks": [
                        {
                            "machine_id": 42,
                            "score": 123,
                            "name": "fixture",
                            "private": "secret",
                        }
                    ]
                },
            ),
            (200, []),
        ]
    )
    template = api.templates("abc", True)[0]
    assert template["has_environment"]
    assert template["has_startup"]
    assert "secret" not in json.dumps(template)
    assert len(template["configuration_sha256"]) == 64
    filters = json.loads(wire.calls[0][2]["params"]["select_filters"])
    assert filters["hash_id"] == {"eq": "abc"}
    assert filters["recommended"] == {"eq": True}
    result = api.benchmarks(42)
    assert result["score_unit"] == "unknown"
    assert result["results"][0]["score"] == 123
    assert "private" not in result["results"][0]
    assert api.benchmarks(42)["status"] == "not_available"
    with pytest.raises(VastError):
        api.benchmarks(0)


@pytest.mark.parametrize("action", ["templates", "benchmarks"])
def test_catalog_invalid_shapes(action):
    api, _ = client([(200, {})])
    operation = getattr(api, action)
    arguments = [42] if action == "benchmarks" else []
    with pytest.raises(VastError, match="vast.invalid_response"):
        operation(*arguments)


def test_performance_fields(profile, offer):
    from venom_core.services.vast_environments.assessment import search_filters
    from venom_core.services.vast_environments.selection import provider_order, rank

    cfg = profile.model_copy(
        update={"min_dlperf": 20, "min_gpu_mem_bw_gb_s": 100, "sort_by": "performance"}
    )
    row = {**offer, "dlperf": 25, "gpu_mem_bw": 120, "total_flops": 29.5}
    out = assess(row, cfg)
    assert out.status == "eligible"
    assert out.host.dlperf_per_hourly_usd == Decimal("62.5")
    assert out.host.total_tflops == Decimal("29.5")
    assert out.host.gpu_memory_bandwidth_gb_s == Decimal("120")
    assert "dlperf" in assess(offer, cfg).unknown
    assert "gpu_mem_bw" in assess({**row, "gpu_mem_bw": 90}, cfg).reasons
    assert search_filters(cfg)["dlperf"] == {"gte": 20}
    assert search_filters(cfg)["gpu_mem_bw"] == {"gte": 100}
    rows = [
        out,
        assess({**row, "id": 13, "dlperf": 30, "search": {"totalHour": "1"}}, cfg),
    ]
    assert rank(rows, cfg)[0].offer["id"] == 13
    cfg = cfg.model_copy(update={"sort_by": "value"})
    assert rank(rows, cfg)[0].offer["id"] == 12
    assert provider_order("performance")[0] == ["dlperf", "desc"]
    assert provider_order("value")[0] == ["dlperf_per_dphtotal", "desc"]
    assert rank([assess(offer, profile), out], cfg)[0].host.dlperf is not None


def test_history_never_reports_other_machine_as_available():
    api, _ = client([(200, [{"machine_id": 2, "score": 50}])])
    assert api.benchmarks(1)["status"] == "not_available"
    api, _ = client([(200, [{"machine_id": 1}])])
    assert api.benchmarks(1)["score_status"] == "not_available"


def test_ssh_list_skips_only_invalid_rows():
    public = "ssh-ed25519 YWJjZA== fixture"
    api, _ = client(
        [
            (
                200,
                [
                    {"public_key": public},
                    {},
                    {"public_key": 1},
                    {"key": "invalid"},
                    {"key": public, "deleted_at": "yesterday"},
                    "invalid",
                ],
            )
        ]
    )
    from venom_core.infrastructure.providers.vast.client import ssh_fingerprint

    assert api.ssh_fingerprints() == [ssh_fingerprint(public)]


def test_absent_instance_is_distinct_from_invalid_response():
    api, _ = client([(200, {"instances": None})])
    with pytest.raises(VastError, match="vast.instance_not_found") as caught:
        api.instance(88)
    assert caught.value.status == 404
    for body in ({}, {"instances": []}, {"instances": {"id": 99}}):
        api, _ = client([(200, body)])
        with pytest.raises(VastError, match="vast.invalid_response"):
            api.instance(88)


def test_ram_baseline_uses_machine_fraction_not_card_vram(profile, offer):
    shared = {**offer, "cpu_ram": 128000, "gpu_frac": 0.125}
    result = assess(shared, profile)
    assert result.status == "ineligible"
    assert "cpu_ram" in result.reasons
    assert result.runtime["memory_allocation"]["baseline_ram_mb"] == "16000.000"
    assert result.offer["gpu_ram"] == offer["gpu_ram"]
    enough = assess({**shared, "cpu_ram": 512000}, profile)
    assert enough.status == "eligible"
    assert "gpu_frac" not in enough.reasons


def test_unknown_machine_fraction_does_not_claim_ram_baseline(profile, offer):
    row = {k: v for k, v in offer.items() if k != "gpu_frac"}
    result = assess(row, profile)
    assert "cpu_ram" in result.unknown
    assert result.runtime["memory_allocation"]["baseline_ram_mb"] is None
