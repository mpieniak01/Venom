"""Lightweight declared compatibility, separate from measured qualification."""

from typing import Any

from venom_core.infrastructure.providers.vast.models import WorkloadProfile, amount
from venom_core.infrastructure.providers.vast.runtime_contracts import version_parts
from venom_core.infrastructure.providers.vast.templates import template_constraints

VERSION_FIELDS = {"cuda_max_good", "driver_version"}
TEXT_FIELDS = {"cpu_arch", "gpu_arch", "gpu_name"}


def _value(key: str, value: Any):
    if key in VERSION_FIELDS:
        return version_parts(value)
    if key in TEXT_FIELDS:
        return value if isinstance(value, str) else None
    return amount(value)


def _matches(key: str, raw: Any, op: str, expected: Any) -> bool | None:
    actual = _value(key, raw)
    values = expected if isinstance(expected, list) else [expected]
    converted = [_value(key, value) for value in values]
    if actual is None or any(value is None for value in converted):
        return None
    target = converted[0]
    if op == "in":
        return actual in converted
    if op == "notin":
        return actual not in converted
    operators = {
        "eq": lambda: actual == target,
        "neq": lambda: actual != target,
        "gte": lambda: actual >= target,
        "gt": lambda: actual > target,
        "lte": lambda: actual <= target,
        "lt": lambda: actual < target,
    }
    return operators[op]()


def declared_compatibility(offer: dict, profile: WorkloadProfile) -> dict:
    runtime = profile.runtime
    failed, unknown, checks = [], list(runtime.unresolved_constraints), []
    requirements: dict[str, dict] = {}
    if runtime.acceleration == "cuda":
        requirements["gpu_arch"] = {"eq": "nvidia"}
    for key, value in [
        ("cuda_max_good", runtime.min_cuda),
        ("driver_version", runtime.min_driver),
    ]:
        if value:
            requirements[key] = {"gte": value}
    if runtime.image_min_cuda:
        existing = requirements.setdefault("cuda_max_good", {})
        previous = str(existing.get("gte", "0"))
        existing["gte"] = max(
            [previous, runtime.image_min_cuda], key=lambda x: version_parts(x) or ()
        )
    if runtime.compute_capabilities:
        requirements["compute_cap"] = {"in": runtime.compute_capabilities}
    template = template_constraints(runtime.template_constraints)
    unknown.extend(template["unresolved"])
    for source, rules in [
        ("profile", requirements),
        ("template", template["constraints"]),
    ]:
        for key, predicates in rules.items():
            for op, expected in predicates.items():
                match = _matches(key, offer.get(key), op, expected)
                reason = source + "." + key
                if match is False:
                    failed.append(reason)
                elif match is None:
                    unknown.append(reason)
                checks.append(
                    {
                        "source": source,
                        "field": key,
                        "operator": op,
                        "expected": expected,
                        "actual": offer.get(key),
                        "matches": match,
                    }
                )
    return {
        "status": "incompatible" if failed else "unknown" if unknown else "compatible",
        "reasons": sorted(set(failed)),
        "unknown": sorted(set(unknown)),
        "checks": checks,
        "evidence": "provider_and_profile_declared",
        "qualification": "not_tested",
    }


def runtime_filters(profile: WorkloadProfile) -> dict:
    runtime = profile.runtime
    result: dict[str, Any] = {}
    if runtime.acceleration == "cuda":
        result["gpu_arch"] = {"eq": "nvidia"}
    cuda = max(
        [runtime.min_cuda, runtime.image_min_cuda], key=lambda x: version_parts(x) or ()
    )
    if cuda:
        result["cuda_max_good"] = {"gte": cuda}
    if runtime.compute_capabilities:
        result["compute_cap"] = {"in": runtime.compute_capabilities}
    for key, rules in template_constraints(runtime.template_constraints)[
        "constraints"
    ].items():
        # Vast documents reliable driver equality only; enforce numeric version rules locally.
        if key != "driver_version":
            result.setdefault(key, rules)
    return result
