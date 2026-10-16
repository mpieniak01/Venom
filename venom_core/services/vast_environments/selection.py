"""Explicit host preferences; no invented review score or measured latency."""

from decimal import Decimal
from typing import Any

from venom_core.infrastructure.providers.vast.models import (
    HostSignals,
    OfferAssessment,
    WorkloadProfile,
    amount,
)


def country_code(offer: dict) -> str | None:
    raw = str(offer.get("country_code") or "").strip().upper()
    if len(raw) == 2 and raw.isascii() and raw.isalpha():
        return raw
    raw = str(offer.get("geolocation") or "").rsplit(",", 1)[-1].strip().upper()
    return raw if len(raw) == 2 and raw.isascii() and raw.isalpha() else None


def reliability(offer: dict) -> Decimal | None:
    value = amount(offer.get("reliability"))
    if value is None:
        value = amount(offer.get("reliability2"))
    return value if value is not None and value <= 1 else None


def host_signals(offer: dict, profile: WorkloadProfile) -> HostSignals:
    country = country_code(offer)
    quality = reliability(offer)
    verification = offer.get("verification")
    dlperf = amount(offer.get("dlperf"))
    price = amount((offer.get("search") or {}).get("totalHour", offer.get("dph_total")))
    return HostSignals(
        dlperf=dlperf,
        total_tflops=amount(offer.get("total_flops")),
        gpu_memory_bandwidth_gb_s=amount(offer.get("gpu_mem_bw")),
        dlperf_per_hourly_usd=dlperf / price if dlperf is not None and price else None,
        country_code=country,
        preferred_country=country is not None
        and country in profile.preferred_countries,
        download_mbps=amount(offer.get("inet_down")),
        upload_mbps=amount(offer.get("inet_up")),
        reliability_percent=quality * 100 if quality is not None else None,
        verified=verification == "verified" if verification is not None else None,
    )


def provider_order(sort_by: str) -> list[list[str]]:
    orders = {
        "balanced": [
            ["reliability", "desc"],
            ["inet_down", "desc"],
            ["dph_total", "asc"],
        ],
        "performance": [["dlperf", "desc"], ["dph_total", "asc"]],
        "value": [["dlperf_per_dphtotal", "desc"], ["dph_total", "asc"]],
        "price": [["dph_total", "asc"], ["reliability", "desc"]],
        "network": [["inet_down", "desc"], ["inet_up", "desc"], ["dph_total", "asc"]],
        "reliability": [["reliability", "desc"], ["dph_total", "asc"]],
    }
    return orders[sort_by]


def preferred_queries(profile: WorkloadProfile, base: dict[str, Any]) -> list[dict]:
    # A global top 100 can omit every Polish offer. Request preferred countries
    # separately, then merge. Hard country restrictions are never widened.
    wanted = [
        code
        for code in profile.preferred_countries
        if not profile.countries or code in profile.countries
    ]
    return [
        {**base, "geolocation": {"eq": code}}
        for code in wanted
        if profile.countries != [code]
    ]


def rank(
    rows: list[OfferAssessment], profile: WorkloadProfile
) -> list[OfferAssessment]:
    infinity = Decimal("Infinity")

    def key(row: OfferAssessment):
        host = row.host
        code = host.country_code
        preference = (
            profile.preferred_countries.index(code)
            if code is not None and code in profile.preferred_countries
            else len(profile.preferred_countries)
        )
        total = row.quote.total_usd
        price = total if total is not None else infinity
        quality = (
            -host.reliability_percent
            if host.reliability_percent is not None
            else infinity
        )
        down, up = host.download_mbps, host.upload_mbps
        network = -min(down, up) if down is not None and up is not None else infinity
        performance = -host.dlperf if host.dlperf is not None else infinity
        value = (
            -host.dlperf_per_hourly_usd
            if host.dlperf_per_hourly_usd is not None
            else infinity
        )
        criteria = {
            "performance": (performance, price, quality),
            "value": (value, price, quality),
            "balanced": (quality, network, price),
            "price": (price, quality, network),
            "network": (network, quality, price),
            "reliability": (quality, price, network),
        }[profile.sort_by]
        status = {"eligible": 0, "unknown": 1, "ineligible": 2}[row.status]
        offer_id = amount(row.offer.get("id"))
        return (
            status,
            preference,
            *criteria,
            offer_id if offer_id is not None else infinity,
        )

    return sorted(rows, key=key)
