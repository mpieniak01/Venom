"""Summarize sealed development evidence by skill, difficulty and family."""

from __future__ import annotations

from collections import defaultdict
from math import sqrt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .quality_schema import MAX_QUALITY_CASES, CaseId, Digest, EvidenceLabel
from .retention import fingerprint

Level = Literal["P1", "P2", "P3"]
Area = Literal[
    "conversation", "sources", "tools", "action_arguments", "state", "result"
]
_AREAS = {
    "chat": ("conversation", "sources", "tools"),
    "decision": ("action_arguments", "state", "result"),
}
_LEVELS = ("P1", "P2", "P3")
_METRICS = {"usable": False, "passed": False, "critical": True}


class DiagnosticCase(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    area: Area
    level: Level
    family: EvidenceLabel


class DiagnosticMatrix(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal[1] = 1
    role: Literal["chat", "decision"]
    dataset_sha256: Digest
    protocol_sha256: Digest
    min_families: int = Field(default=6, ge=1, le=MAX_QUALITY_CASES)
    cases: dict[CaseId, DiagnosticCase] = Field(
        min_length=1, max_length=MAX_QUALITY_CASES
    )


def _flag(values: list[bool | None], decisive: bool) -> bool | None:
    if decisive in values:
        return decisive
    return None if None in values else not decisive


def _interval(passed: int, known: int) -> list[float] | None:
    if not known:
        return None
    z = 1.959963984540054
    ratio = passed / known
    denominator = 1 + z**2 / known
    center = (ratio + z**2 / (2 * known)) / denominator
    margin = z * sqrt((ratio * (1 - ratio) + z**2 / (4 * known)) / known) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _metric(families: dict[str, list[dict]], metric: str, decisive: bool) -> dict:
    paired = {}
    for family, rows in families.items():
        paired[family] = tuple(
            _flag([row[arm].get(metric) for row in rows], decisive)
            for arm in ("base", "candidate")
        )
    result = {}
    for index, arm in enumerate(("base", "candidate")):
        values = [pair[index] for pair in paired.values()]
        true_count = values.count(True)
        known = len(values) - values.count(None)
        result[arm] = {
            "true": true_count,
            "known": known,
            "interval_95": _interval(true_count, known),
        }
    return {
        **result,
        "changed_to_true": sorted(
            f for f, pair in paired.items() if pair == (False, True)
        ),
        "changed_to_false": sorted(
            f for f, pair in paired.items() if pair == (True, False)
        ),
    }


def diagnose(record: dict, matrix: DiagnosticMatrix) -> dict:
    """Use family as the observation unit, keeping incomplete evidence visible."""
    if record["split"] != "dev":
        raise ValueError("diagnostic_dev_required")
    identity = record["identity"]
    if (identity["dataset_sha256"], identity["protocol_sha256"]) != (
        matrix.dataset_sha256,
        matrix.protocol_sha256,
    ):
        raise ValueError("diagnostic_identity_mismatch")
    if record["cases"].keys() != matrix.cases.keys():
        raise ValueError("diagnostic_case_coverage")
    areas = _AREAS[matrix.role]
    grouped: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for case_id, label in matrix.cases.items():
        if label.area not in areas:
            raise ValueError("diagnostic_area_outside_role")
        grouped[label.area, label.level][label.family].append(record["cases"][case_id])

    cells = []
    for area in areas:
        for level in _LEVELS:
            families = grouped[area, level]
            metrics = {
                metric: _metric(families, metric, decisive)
                for metric, decisive in _METRICS.items()
            }
            complete = all(
                metric[arm]["known"] == len(families)
                for metric in metrics.values()
                for arm in ("base", "candidate")
            )
            cells.append(
                {
                    "area": area,
                    "level": level,
                    "families": len(families),
                    "cases": sum(map(len, families.values())),
                    "status": (
                        "measured"
                        if complete and len(families) >= matrix.min_families
                        else "REVIEW"
                    ),
                    **metrics,
                }
            )
    return {
        "identity": identity,
        "result_sha256": record["result_sha256"],
        "matrix_sha256": fingerprint(matrix.model_dump(mode="json")),
        "role": matrix.role,
        "min_families": matrix.min_families,
        "cells": cells,
    }
