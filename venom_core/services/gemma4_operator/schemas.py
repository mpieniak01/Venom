"""Shared offline reference policy for material and native tool validation."""

from __future__ import annotations

from typing import Any

REFERENCE_KEYS = frozenset({"$ref", "$dynamicRef", "$recursiveRef"})


def check_schema_references(value: Any, *, error_prefix: str, depth: int = 0) -> None:
    """Allow local fragments/anchors only; never permit remote schema fetches."""
    if depth > 32:
        raise ValueError(error_prefix + "schema_depth_exceeded")
    if isinstance(value, dict):
        for key, item in value.items():
            if key in REFERENCE_KEYS and (
                not isinstance(item, str) or not item.startswith("#")
            ):
                raise ValueError(error_prefix + "external_schema_reference")
            check_schema_references(item, error_prefix=error_prefix, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            check_schema_references(item, error_prefix=error_prefix, depth=depth + 1)
