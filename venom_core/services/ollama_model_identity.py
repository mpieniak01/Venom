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
SALUKI_GGUF = (
    "hf.co/ConwayResearch/Underdog-Saluki-27B-1.0:Underdog-Saluki-27B-1.0-IQ2-mix.gguf"
)
SALUKI_ALIAS = "saluki:latest"
QWEN_ALIAS = "qwen3.5:latest"
QWEN_EXPLICIT = "qwen3.5:9b"
ALIAS_TARGETS = {
    LATEST_GEMMA_TAG: frozenset(EXPLICIT_GEMMA_TAGS),
    SALUKI_ALIAS: frozenset({SALUKI_GGUF}),
    QWEN_ALIAS: frozenset({QWEN_EXPLICIT}),
}
EXPLICIT_OPERATOR_TAGS = frozenset(EXPLICIT_GEMMA_TAGS) | {SALUKI_GGUF, QWEN_EXPLICIT}
UNRESOLVED_MESSAGES = {
    LATEST_GEMMA_TAG: UNRESOLVED_GEMMA_SELECTION,
    SALUKI_ALIAS: "Saluki preset metadata is incomplete. Refresh the runtime catalog or choose the explicit "
    "Underdog Saluki 27B 1.0 IQ2-mix GGUF source.",
    QWEN_ALIAS: "Model identity metadata is incomplete. Refresh the runtime catalog or choose an explicit model tag.",
}
UNRESOLVED_CODES = {
    LATEST_GEMMA_TAG: "gemma4_variant_unresolved",
    SALUKI_ALIAS: "ollama_source_unresolved",
    QWEN_ALIAS: "ollama_identity_unresolved",
}
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


def _matching_metadata(
    first: dict[str, Any], second: dict[str, Any], alias: str
) -> bool:
    left, right = _details(first), _details(second)
    keys = ("family", "format", "parameter_size", "quantization_level")
    return (
        left.get("format") == "gguf"
        and (alias != LATEST_GEMMA_TAG or left.get("family") == "gemma4")
        and all(isinstance(left.get(key), str) and left[key] for key in keys)
        and all(left[key] == right.get(key) for key in keys)
    )


def ollama_display_name(name: str, quantization: str | None = None) -> str:
    if name in ALIAS_TARGETS:
        return name + " (unresolved variant)"
    if name == SALUKI_GGUF:
        return "Underdog Saluki 27B 1.0 IQ2-mix GGUF"
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


def _retain_proven_alias(row: dict[str, Any], alias: str) -> None:
    evidence = row.get("ollama_alias_evidence")
    latest = evidence.get(alias) if isinstance(evidence, dict) else None
    proved = (
        row.get("name") in ALIAS_TARGETS[alias]
        and isinstance(latest, dict)
        and _digest(row) is not None
        and _digest(row) == _digest(latest)
        and _matching_metadata(row, latest, alias)
    )
    row["aliases"] = [item for item in _aliases(row) if item != alias or proved]


def _clear_alias_evidence(row: dict[str, Any], alias: str) -> None:
    row["aliases"] = [item for item in _aliases(row) if item != alias]
    evidence = row.get("ollama_alias_evidence")
    if isinstance(evidence, dict):
        evidence.pop(alias, None)


def _remember_alias_evidence(
    canonical: dict[str, Any], alias: str, latest: dict[str, Any]
) -> None:
    canonical["aliases"] = sorted(set(_aliases(canonical)) | {alias})
    evidence = canonical.get("ollama_alias_evidence")
    if not isinstance(evidence, dict):
        evidence = {}
        canonical["ollama_alias_evidence"] = evidence
    evidence[alias] = {
        "digest": _digest(latest),
        "details": copy.deepcopy(_details(latest)),
    }


def _prefer_verified_explicit_tag(
    rows: list[dict[str, Any]], alias: str
) -> list[dict[str, Any]]:
    latest = next((row for row in rows if row.get("name") == alias), None)
    if latest is None:
        for row in rows:
            _retain_proven_alias(row, alias)
        return rows
    for row in rows:
        _clear_alias_evidence(row, alias)
    if _digest(latest) is None:
        return rows
    matches = [
        row
        for row in rows
        if row.get("name") in ALIAS_TARGETS[alias]
        and _digest(row) == _digest(latest)
        and _matching_metadata(row, latest, alias)
    ]
    if len(matches) != 1:
        return rows
    _remember_alias_evidence(matches[0], alias, latest)
    return [row for row in rows if row.get("name") != alias]


def _complete_observed_identity(row: dict[str, Any]) -> bool:
    details = _details(row)
    keys = ("family", "format", "parameter_size", "quantization_level")
    return _digest(row) is not None and all(
        isinstance(details.get(key), str) and details[key] for key in keys
    )


def _observed_display_name(row: dict[str, Any]) -> str:
    name = str(row.get("name", ""))
    if name in EXPLICIT_GEMMA_TAGS or name in {LATEST_GEMMA_TAG, SALUKI_GGUF}:
        return ollama_display_name(name, _details(row).get("quantization_level"))
    if not _complete_observed_identity(row):
        return ollama_display_name(name)
    details = _details(row)
    facts = " ".join(
        str(details[key]) for key in ("family", "parameter_size", "quantization_level")
    )
    parts = [name, facts]
    parent = details.get("parent_model")
    if isinstance(parent, str) and parent and parent != name:
        parts.append("← " + parent)
    parts.append("sha256:" + str(_digest(row))[:8])
    return " · ".join(parts)


def canonical_ollama_entries(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide only proven operator alias duplicates, preserving explicit variants.

    Each digest addresses the complete Ollama manifest; matching tag metadata
    supplies the model family and precision. A missing or ambiguous proof keeps
    latest visible under its original name. Unregistered aliases and providers are not normalized.
    """
    rows = copy.deepcopy(models)
    for alias in ALIAS_TARGETS:
        rows = _prefer_verified_explicit_tag(rows, alias)
    for row in rows:
        name = str(row.get("name", ""))
        if name in ALIAS_TARGETS:
            observed_preset = name != LATEST_GEMMA_TAG and _complete_observed_identity(
                row
            )
            row["activation_supported"] = observed_preset
            row["selection_supported"] = observed_preset
            if not observed_preset:
                row["selection_block_reason"] = UNRESOLVED_MESSAGES[name]
                row["selection_block_code"] = UNRESOLVED_CODES[name]
            else:
                row.pop("selection_block_reason", None)
                row.pop("selection_block_code", None)
        row["display_name"] = _observed_display_name(row)
    return rows


def _alias_selection(name: str, entries: list[dict[str, Any]]) -> str | None:
    proven = [
        str(row["name"])
        for row in canonical_ollama_entries(entries)
        if row.get("name") in ALIAS_TARGETS[name] and name in _aliases(row)
    ]
    if len(proven) == 1:
        return proven[0]
    observed = [
        row
        for row in entries
        if row.get("name") == name and _complete_observed_identity(row)
    ]
    if name != LATEST_GEMMA_TAG and len(observed) == 1:
        return name
    return None


def resolve_ollama_model_name(
    name: str, models: list[dict[str, Any]], *, require_explicit: bool = False
) -> str:
    """Resolve a legacy latest request only from a unique observed duplicate proof."""
    if name not in ALIAS_TARGETS:
        normalized = name.casefold()
        if require_explicit and normalized in ALIAS_TARGETS:
            raise ValueError(UNRESOLVED_MESSAGES[normalized])
        return name
    entries = [
        row
        for row in models
        if row.get("provider") == "ollama" or row.get("runtime_id") == "ollama"
    ]
    resolved = _alias_selection(name, entries)
    if resolved is not None:
        return resolved
    if require_explicit:
        raise ValueError(UNRESOLVED_MESSAGES[name])
    return name
