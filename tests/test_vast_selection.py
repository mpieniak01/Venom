"""Host selection uses explicit country, cost, bandwidth and reliability."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from tests.test_vast_operations import service as source_service
from venom_core.infrastructure.providers.vast.models import WorkloadProfile
from venom_core.services.vast_environments.assessment import assess, search_filters
from venom_core.services.vast_environments.cli import parser, workload_profile
from venom_core.services.vast_environments.selection import (
    country_code,
    host_signals,
    preferred_queries,
    provider_order,
    rank,
    reliability,
)


@pytest.fixture
def service(tmp_path):
    return source_service.__wrapped__(tmp_path)


def candidate(base, offer_id, country, price, down, up, quality):
    return {
        **base,
        "id": offer_id,
        "geolocation": "Location, " + country,
        "inet_down": down,
        "inet_up": up,
        "reliability": quality,
        "search": {"totalHour": str(price)},
    }


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("balanced", [2, 1, 3]),
        ("price", [1, 2, 3]),
        ("network", [2, 1, 3]),
        ("reliability", [2, 1, 3]),
    ],
)
def test_sort_with_poland_preference(service, mode, expected):
    _, plan, base = service
    profile = plan.profile.model_copy(update={"sort_by": mode})
    rows = [
        candidate(base, 1, "PL", "0.2", 500, 200, 0.995),
        candidate(base, 2, "PL", "0.3", 1500, 1000, 0.999),
        candidate(base, 3, "DE", "0.1", 2000, 2000, 1),
    ]
    assert [
        r.offer["id"] for r in rank([assess(r, profile) for r in rows], profile)
    ] == expected


def test_price_without_country_preference(service):
    _, plan, base = service
    profile = plan.profile.model_copy(
        update={"preferred_countries": [], "sort_by": "price"}
    )
    rows = [
        candidate(base, 1, "PL", "0.3", 1000, 500, 0.999),
        candidate(base, 2, "DE", "0.2", 1000, 500, 0.999),
    ]
    assert [
        x.offer["id"] for x in rank([assess(x, profile) for x in rows], profile)
    ] == [2, 1]


def test_network_ranking_uses_both_directions(service):
    _, plan, base = service
    profile = plan.profile.model_copy(update={"sort_by": "network"})
    rows = [
        candidate(base, 1, "PL", "0.2", 10000, 10, 0.999),
        candidate(base, 2, "PL", "0.3", 1000, 500, 0.999),
        candidate(base, 3, "PL", "0.1", 10000, None, 0.999),
    ]
    assert [
        x.offer["id"] for x in rank([assess(x, profile) for x in rows], profile)
    ] == [2, 1, 3]


def test_eligibility_overrides_country_and_price(service):
    _, plan, base = service
    foreign = candidate(base, 1, "DE", "0.3", 1000, 500, 0.999)
    bad = candidate(base, 2, "PL", "0.01", 1000, 500, 0.5)
    unknown = {**foreign, "id": 3, "cpu_arch": None, "geolocation": "Poland, PL"}
    ranked = rank(
        [assess(x, plan.profile) for x in [bad, unknown, foreign]], plan.profile
    )
    assert [x.status for x in ranked] == ["eligible", "unknown", "ineligible"]
    assert [x.offer["id"] for x in ranked] == [1, 3, 2]


def test_thresholds_and_missing_bandwidth(service):
    _, plan, base = service
    profile = plan.profile.model_copy(
        update={
            "min_download_mbps": 500,
            "min_upload_mbps": 200,
            "min_reliability": 0.99,
        }
    )
    row = candidate(base, 1, "PL", "0.3", 499, 199, 0.98)
    result = assess(row, profile)
    assert {"inet_down", "inet_up", "reliability"} <= set(result.reasons)
    row.update(inet_down=500, inet_up=200, reliability=0.99)
    assert assess(row, profile).status == "eligible"
    del row["inet_up"]
    assert "inet_up" in assess(row, profile).unknown
    filters = search_filters(profile)
    assert filters["inet_down"] == {"gte": 500}
    assert filters["inet_up"] == {"gte": 200}
    assert filters["reliability"] == {"gte": 0.99}


def test_missing_is_not_zero_and_no_reviews_are_invented(service):
    _, plan, base = service
    signals = host_signals(
        {**base, "reliability": None, "reliability2": 0.999, "country_code": "PL"},
        plan.profile,
    )
    assert signals.reliability_percent == Decimal("99.900")
    assert signals.download_mbps is None
    assert signals.user_reviews == "not_provided"
    assert signals.preferred_country
    assert host_signals({}, plan.profile).verified is None
    assert reliability({"reliability": 1.1}) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"geolocation": "Poland, PL"}, "PL"),
        ({"geolocation": "pl"}, "PL"),
        ({"country_code": "de", "geolocation": "Poland, PL"}, "DE"),
        ({"geolocation": "Poland"}, None),
        ({"country_code": "!!"}, None),
    ],
)
def test_country_parsing(raw, expected):
    assert country_code(raw) == expected


def test_country_filters_and_preferred_queries(service):
    _, plan, _ = service
    profile = plan.profile
    queries = preferred_queries(profile, search_filters(profile))
    assert len(queries) == 1 and queries[0]["geolocation"] == {"eq": "PL"}
    assert "geolocation" not in search_filters(profile)
    restricted = profile.model_copy(update={"countries": ["DE"]})
    assert preferred_queries(restricted, search_filters(restricted)) == []
    restricted = profile.model_copy(update={"countries": ["PL"]})
    assert preferred_queries(restricted, search_filters(restricted)) == []
    assert search_filters(restricted)["geolocation"] == {"in": ["PL"]}


def test_country_is_requested_even_if_global_top_100_omits_it(service):
    svc, plan, base = service
    global_rows = [
        candidate(base, i, "DE", "0.1", 1000, 500, 0.999) for i in range(100, 200)
    ]
    polish = candidate(base, 1, "PL", "0.4", 1000, 500, 0.999)
    svc.client.offers.side_effect = [global_rows, [polish]]
    results = svc.search(plan.profile)
    assert results[0].offer["id"] == 1
    assert len(results) == 101
    assert len(global_rows) == 100
    assert svc.client.offers.call_args_list[-1].args[1]["geolocation"] == {"eq": "PL"}


def test_candidate_deduplication_and_fallback(service):
    svc, plan, base = service
    foreign = candidate(base, 1, "DE", "0.2", 1000, 500, 0.999)
    polish = candidate(base, 2, "PL", "0.3", 1000, 500, 0.999)
    svc.client.offers.side_effect = [[foreign, polish], [polish]]
    assert [x.offer["id"] for x in svc.search(plan.profile)] == [2, 1]
    svc.client.offers.side_effect = [[foreign], []]
    assert svc.search(plan.profile)[0].offer["id"] == 1


@pytest.mark.parametrize("code", ["POL", "1P", "łł", ""])
def test_bad_country_validation(service, code):
    _, plan, _ = service
    with pytest.raises(ValidationError):
        WorkloadProfile.model_validate(
            {**plan.profile.model_dump(), "preferred_countries": [code]}
        )


def test_cli_overrides_are_validated_and_persistable(service, tmp_path):
    _, plan, _ = service
    path = tmp_path / "profile.json"
    path.write_text(plan.profile.model_dump_json())
    args = parser().parse_args(
        [
            "offers",
            "--profile",
            str(path),
            "--sort",
            "price",
            "--country",
            "pl",
            "--prefer-country",
            "pl",
            "--min-download-mbps",
            "500",
            "--min-upload-mbps",
            "200",
            "--min-reliability",
            "0.99",
        ]
    )
    profile = workload_profile(args)
    assert profile.sort_by == "price"
    assert profile.countries == ["PL"] and profile.preferred_countries == ["PL"]
    assert profile.min_download_mbps == 500 and profile.min_upload_mbps == 200
    assert profile.min_reliability == 0.99
    args = parser().parse_args(
        ["offers", "--profile", str(path), "--no-country-preference"]
    )
    assert workload_profile(args).preferred_countries == []
    args = parser().parse_args(
        ["offers", "--profile", str(path), "--min-upload-mbps", "-1"]
    )
    with pytest.raises(ValidationError):
        workload_profile(args)


def test_provider_sort_is_not_overwritten():
    from tests.test_vast_provider import client

    api, transport = client([(200, {"offers": []})])
    order = provider_order("network")
    assert api.offers(150, {"order": order}) == []
    assert transport.calls[0][2]["json"]["order"] == order
    api.close()


def test_saved_plan_rechecks_the_same_link_requirements(service):
    from pathlib import Path

    from venom_core.infrastructure.providers.vast.client import VastError

    svc, original, base = service
    profile = original.profile.model_copy(
        update={
            "countries": ["PL"],
            "min_download_mbps": 500,
            "min_upload_mbps": 200,
            "min_reliability": 0.99,
            "sort_by": "price",
        }
    )
    offer = candidate(base, 12, "PL", "0.4", 900, 900, 0.999)
    svc.client.offers.return_value = [offer]
    plan = svc.plan(
        profile,
        12,
        Decimal("0.5"),
        Decimal("1"),
        Path(original.ssh_identity_file),
        Path(original.ssh_known_hosts),
    )
    assert svc.journal.plan(plan.plan_id).profile == profile
    svc.client.offers.return_value = [{**offer, "inet_up": 100}]
    with pytest.raises(VastError, match="vast.offer_not_eligible"):
        svc.create(plan.plan_id)
    svc.client.create.assert_not_called()
