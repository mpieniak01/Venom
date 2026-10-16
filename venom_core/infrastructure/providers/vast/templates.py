"""Allowlisted template metadata; executable payloads and credentials never leave the adapter."""

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
# Read dangerous configuration only to fingerprint it, never return its contents.
TEMPLATE_COLUMNS = (*TEMPLATE_FIELDS, "env", "onstart", "args_str", "extra_filters")


def template_snapshot(row: dict[str, Any]) -> dict:
    result = project(row, TEMPLATE_FIELDS)
    result.update(
        has_environment=bool(row.get("env")),
        has_startup=bool(row.get("onstart")),
        has_arguments=bool(row.get("args_str")),
        configuration_sha256=digest({key: row.get(key) for key in TEMPLATE_COLUMNS}),
        constraints_policy="replaced_by_workload_profile",
    )
    return result
