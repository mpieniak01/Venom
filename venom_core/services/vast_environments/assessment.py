"""Assess declared capacity separately from measured workload suitability."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from venom_core.infrastructure.providers.vast.models import (
    CostQuote,
    OfferAssessment,
    WorkloadProfile,
    amount,
    offer_snapshot,
)
from venom_core.services.vast_environments.compatibility import (
    declared_compatibility,
    runtime_filters,
)
from venom_core.services.vast_environments.selection import (
    country_code,
    host_signals,
    provider_order,
    reliability,
)


def quote(offer: dict, profile: WorkloadProfile) -> CostQuote:
    search = offer.get("search") or {}
    hourly = amount(search.get("totalHour", offer.get("dph_total")))
    storage = amount(search.get("diskHour"))
    unknown = []
    transfer = Decimal(0)
    for direction, gb in (("down", profile.download_gb), ("up", profile.upload_gb)):
        rate = amount(offer.get(f"internet_{direction}_cost_per_tb"))
        if gb and rate is None:
            unknown.append(f"transfer_{direction}_unit")
        elif gb and rate is not None:
            transfer += gb * rate / Decimal(1000)
    if hourly is None:
        unknown.append("hourly_price")
    total_transfer = (
        None if unknown and any(x.startswith("transfer") for x in unknown) else transfer
    )

    def cost(minutes: int) -> Decimal | None:
        if hourly is None or total_transfer is None:
            return None
        return hourly * Decimal(minutes) / Decimal(60) + total_transfer

    return CostQuote(
        hourly_usd=hourly,
        storage_hourly_usd=storage,
        transfer_usd=total_transfer,
        total_usd=cost(profile.duration_minutes),
        samples_minutes_usd={str(m): cost(m) for m in (15, 30, 60)},
        rates={k: v for k, v in offer.items() if k.endswith(("_cost", "_per_tb"))},
        unknown=unknown,
    )


def _status(
    reasons: list[str], unknown: list[str]
) -> Literal["eligible", "ineligible", "unknown"]:
    if reasons:
        return "ineligible"
    if unknown:
        return "unknown"
    return "eligible"


def _check_expected(
    offer: dict, profile: WorkloadProfile, reasons: list[str], unknown: list[str]
) -> None:
    for key, expected in (
        ("cpu_arch", profile.cpu_arch),
        ("num_gpus", 1),
        ("rentable", True),
        ("rented", False),
        ("verification", "verified"),
    ):
        value = offer.get(key)
        if value is None:
            unknown.append(key)
        elif value != expected:
            reasons.append(key)


def _check_minimums(
    offer: dict, profile: WorkloadProfile, reasons: list[str], unknown: list[str]
) -> None:
    requirements = {
        "dlperf": profile.min_dlperf,
        "gpu_mem_bw": profile.min_gpu_mem_bw_gb_s,
        "cpu_ram": profile.min_cpu_ram_mb,
        "gpu_ram": profile.min_gpu_ram_mb,
        "cpu_cores_effective": profile.min_cpu_cores,
        "reliability": profile.min_reliability,
        "disk_space": profile.disk_gb,
        "duration": profile.duration_minutes * 60,
        "disk_bw": profile.min_disk_mb_s,
        "inet_down": profile.min_download_mbps,
        "inet_up": profile.min_upload_mbps,
        "direct_port_count": 1,
        "gpu_frac": profile.min_gpu_fraction,
    }
    for key, minimum in requirements.items():
        raw = reliability(offer) if key == "reliability" else offer.get(key)
        value = amount(raw)
        if value is None and minimum:
            unknown.append(key)
        if value is not None and value < Decimal(str(minimum)):
            reasons.append(key)


def _check_identity(
    offer: dict, profile: WorkloadProfile, reasons: list[str], unknown: list[str]
) -> None:
    if profile.gpu_names and offer.get("gpu_name") not in profile.gpu_names:
        reasons.append("gpu_name")
    if profile.countries:
        country = country_code(offer)
        if country is None:
            unknown.append("country")
        elif country not in profile.countries:
            reasons.append("country")
    for key in ("id", "machine_id", "host_id"):
        if type(offer.get(key)) is not int or offer[key] <= 0:
            unknown.append(key)


def assess(offer: dict[str, Any], profile: WorkloadProfile) -> OfferAssessment:
    reasons: list[str] = []
    unknown: list[str] = []
    _check_expected(offer, profile, reasons, unknown)
    _check_minimums(offer, profile, reasons, unknown)
    _check_identity(offer, profile, reasons, unknown)
    runtime = declared_compatibility(offer, profile)
    reasons.extend("runtime." + value for value in runtime["reasons"])
    cost = quote(offer, profile)
    unknown.extend(cost.unknown)
    return OfferAssessment(
        offer=offer_snapshot(offer),
        status=_status(reasons, unknown),
        reasons=reasons,
        unknown=unknown,
        quote=cost,
        host=host_signals(offer, profile),
        runtime=runtime,
    )


def search_filters(profile: WorkloadProfile) -> dict[str, Any]:
    result: dict[str, Any] = {
        "cpu_arch": {"eq": profile.cpu_arch},
        "verified": {"eq": True},
        "num_gpus": {"eq": 1},
        "order": provider_order(profile.sort_by),
        "reliability": {"gte": profile.min_reliability},
    }
    if profile.min_dlperf:
        result["dlperf"] = {"gte": profile.min_dlperf}
    if profile.min_gpu_mem_bw_gb_s:
        result["gpu_mem_bw"] = {"gte": profile.min_gpu_mem_bw_gb_s}
    if profile.min_download_mbps:
        result["inet_down"] = {"gte": profile.min_download_mbps}
    if profile.min_upload_mbps:
        result["inet_up"] = {"gte": profile.min_upload_mbps}
    if profile.countries:
        result["geolocation"] = {"in": profile.countries}
    if profile.gpu_names:
        result["gpu_name"] = {"in": profile.gpu_names}
    for key, value in runtime_filters(profile).items():
        result.setdefault(key, value)
    return result
