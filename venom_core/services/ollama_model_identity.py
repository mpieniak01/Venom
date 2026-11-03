"""Explicit Ollama variant identities from observed tags, never latest-name guesses."""

from __future__ import annotations

import copy
import re
from typing import Any

EXPLICIT_GEMMA_TAGS = {
    "gemma4:e4b": "Gemma4 E4B IT",
    "gemma4:12b-it-q4_K_M": "Gemma4 12B IT",
}
LATEST_GEMMA_TAG = "gemma4:latest"
UNRESOLVED_GEMMA_SELECTION = (
    "Gemma4 latest has no verified variant identity. Choose gemma4:e4b "
    "or gemma4:12b-it-q4_K_M explicitly."
)
_SHA256 = re.compile(r"[a-f0-9]{64}")


def _digest(model: dict[str, Any]) -> str | None:
    value = model.get("digest")
    if not isinstance(value, str):
        return None
    value = value.removeprefix("sha256:")
    return value if _SHA256.fullmatch(value) else None


def _details(model: dict[str, Any]) -> dict[str, Any]:
    value = model.get("details")
    return value if isinstance(value, dict) else {}


def _matching_metadata(first: dict[str, Any], second: dict[str, Any]) -> bool:
    left, right = _details(first), _details(second)
    keys = ("family", "format", "parameter_size", "quantization_level")
    return (
        left.get("family") == "gemma4"
        and all(isinstance(left.get(key), str) and left[key] for key in keys)
        and all(left[key] == right.get(key) for key in keys)
    )


def ollama_display_name(name: str, quantization: str | None = None) -> str:
    if name == LATEST_GEMMA_TAG:
        return "gemma4:latest (unresolved variant)"
    base = EXPLICIT_GEMMA_TAGS.get(name)
    if base is None:
        return name
    precision = quantization or ("Q4_K_M" if name.endswith("-q4_K_M") else "")
    return f"{base} {precision}".strip()


def _aliases(model: dict[str, Any]) -> list[str]:
    aliases = model.get("aliases")
    return (
        [item for item in aliases if isinstance(item, str)]
        if isinstance(aliases, list)
        else []
    )


def _retain_proven_alias(row: dict[str, Any]) -> None:
    evidence = row.get("ollama_alias_evidence")
    latest = evidence.get(LATEST_GEMMA_TAG) if isinstance(evidence, dict) else None
    proved = (
        isinstance(latest, dict)
        and _digest(row) is not None
        and _digest(row) == _digest(latest)
        and _matching_metadata(row, latest)
    )
    row["aliases"] = [
        alias for alias in _aliases(row) if alias != LATEST_GEMMA_TAG or proved
    ]


def _prefer_verified_explicit_tag(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = next((row for row in rows if row.get("name") == LATEST_GEMMA_TAG), None)
    if latest is None:
        for row in rows:
            _retain_proven_alias(row)
        return rows
    for row in rows:
        row["aliases"] = [alias for alias in _aliases(row) if alias != LATEST_GEMMA_TAG]
        row.pop("ollama_alias_evidence", None)
    if _digest(latest) is None:
        return rows
    matches = [
        row
        for row in rows
        if row.get("name") in EXPLICIT_GEMMA_TAGS
        and _digest(row) == _digest(latest)
        and _matching_metadata(row, latest)
    ]
    if len(matches) != 1:
        return rows
    canonical = matches[0]
    canonical["aliases"] = sorted(set(_aliases(canonical)) | {LATEST_GEMMA_TAG})
    canonical["ollama_alias_evidence"] = {
        LATEST_GEMMA_TAG: {
            "digest": _digest(latest),
            "details": copy.deepcopy(_details(latest)),
        }
    }
    return [row for row in rows if row.get("name") != LATEST_GEMMA_TAG]


def canonical_ollama_entries(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide only a proven duplicate moving Gemma tag, preserving explicit variants.

    Each digest addresses the complete Ollama manifest; matching tag metadata
    supplies the model family and precision. A missing or ambiguous proof keeps
    latest visible under its original name. No other model family is normalized.
    """
    rows = _prefer_verified_explicit_tag(copy.deepcopy(models))
    for row in rows:
        if row.get("name") == LATEST_GEMMA_TAG:
            row["activation_supported"] = False
            row["selection_supported"] = False
            row["selection_block_reason"] = UNRESOLVED_GEMMA_SELECTION
            row["selection_block_code"] = "gemma4_variant_unresolved"
        details = _details(row)
        precision = details.get("quantization_level") or row.get("quantization")
        row["display_name"] = ollama_display_name(
            str(row.get("name", "")), precision if isinstance(precision, str) else None
        )
    return rows


def resolve_ollama_model_name(
    name: str, models: list[dict[str, Any]], *, require_explicit: bool = False
) -> str:
    """Resolve a legacy latest request only from a unique observed duplicate proof."""
    if name != LATEST_GEMMA_TAG:
        if require_explicit and name.casefold() == LATEST_GEMMA_TAG:
            raise ValueError(UNRESOLVED_GEMMA_SELECTION)
        return name
    entries = [
        row
        for row in models
        if row.get("provider") == "ollama" or row.get("runtime_id") == "ollama"
    ]
    proven = [
        str(row["name"])
        for row in canonical_ollama_entries(entries)
        if row.get("name") in EXPLICIT_GEMMA_TAGS and LATEST_GEMMA_TAG in _aliases(row)
    ]
    if len(proven) == 1:
        return proven[0]
    if require_explicit:
        raise ValueError(UNRESOLVED_GEMMA_SELECTION)
    return name
