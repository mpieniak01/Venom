"""Allowlisted template metadata; executable payloads and credentials never leave the adapter."""

import json
import re
from typing import Any

from venom_core.infrastructure.providers.vast.models import digest, project

TEMPLATE_FIELDS = (
    "id",
    "hash_id",
    "name",
    "image",
    "tag",
    "recommended_disk_space",
    "recommended",
    "use_ssh",
    "runtype",
    "count_created",
)
# Only effective configuration affects the fingerprint. Popularity/name changes
# must not invalidate a reviewed plan.
CONFIGURATION_FIELDS = (
    "image",
    "tag",
    "recommended_disk_space",
    "use_ssh",
    "runtype",
    "env",
    "onstart",
    "args_str",
    "extra_filters",
)
# Read dangerous configuration only to fingerprint it, never return its contents.
TEMPLATE_COLUMNS = (*TEMPLATE_FIELDS, "env", "onstart", "args_str", "extra_filters")


def template_snapshot(row: dict[str, Any]) -> dict:
    result = project(row, TEMPLATE_FIELDS)
    result.update(
        has_environment=bool(row.get("env")),
        has_startup=bool(row.get("onstart")),
        has_arguments=bool(row.get("args_str")),
        configuration_sha256=digest(
            {key: row.get(key) for key in CONFIGURATION_FIELDS}
        ),
        constraints_policy="reviewed_runtime_constraints",
        runtime_constraints=template_constraints(row.get("extra_filters")),
    )
    return result


CONSTRAINT_FIELDS = {
    "cpu_arch",
    "gpu_arch",
    "gpu_name",
    "cuda_max_good",
    "driver_version",
    "compute_cap",
    "num_gpus",
    "gpu_ram",
    "cpu_ram",
    "gpu_frac",
    "cpu_cores_effective",
    "disk_space",
    "disk_bw",
    "inet_down",
    "inet_up",
}
CONSTRAINT_OPS = {"eq", "neq", "gte", "gt", "lte", "lt", "in", "notin"}


def _safe_value(value: Any) -> bool:
    if type(value) in {int, float}:
        return len(str(value)) <= 32
    return isinstance(value, str) and bool(
        re.fullmatch(r"[A-Za-z0-9_. +:-]{1,80}", value, flags=re.ASCII)
    )


def template_constraints(value: Any) -> dict:
    if value is None or value == "" or value == {}:
        return {"constraints": {}, "unresolved": []}
    if isinstance(value, str):
        if len(value) > 8192:
            return {"constraints": {}, "unresolved": ["extra_filters"]}
        try:
            value = json.loads(value)
        except ValueError:
            return {"constraints": {}, "unresolved": ["extra_filters"]}
    if not isinstance(value, dict) or len(value) > 64:
        return {"constraints": {}, "unresolved": ["extra_filters"]}
    known, unresolved = {}, []
    for key, rules in value.items():
        label = key if re.fullmatch(r"[a-z_]{1,40}", str(key)) else "unknown_field"
        if key not in CONSTRAINT_FIELDS or not isinstance(rules, dict) or not rules:
            unresolved.append(label)
            continue
        accepted = {}
        for op, expected in rules.items():
            values = expected if isinstance(expected, list) else [expected]
            valid_shape = (
                isinstance(expected, list)
                if op in {"in", "notin"}
                else not isinstance(expected, list)
            )
            if (
                op not in CONSTRAINT_OPS
                or not valid_shape
                or not 1 <= len(values) <= 32
                or not all(_safe_value(x) for x in values)
            ):
                unresolved.append(label)
            else:
                accepted[op] = expected
        if accepted:
            known[key] = accepted
    return {"constraints": known, "unresolved": sorted(set(unresolved))}
