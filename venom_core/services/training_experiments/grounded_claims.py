"""Validate frozen factual rubrics and grade explicit answer formatting."""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UNCERTAIN = "grounded_claims_unverifiable"

Alias = Annotated[str, Field(min_length=1, max_length=96)]
Aliases = Annotated[list[Alias], Field(min_length=1, max_length=16)]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class _Claim(_Strict):
    kind: Literal["value", "missing"]
    field_aliases: Aliases
    value_aliases: Aliases | None = None

    @model_validator(mode="after")
    def _shape(self) -> _Claim:
        if (self.kind == "value") != (self.value_aliases is not None):
            raise ValueError("grounded_claims_values_invalid")
        for alias in (*self.field_aliases, *(self.value_aliases or ())):
            if (
                not _normalize(alias)
                or len(alias.split()) > 10
                or re.search(r"[;\n]", alias)
            ):
                raise ValueError("grounded_claims_alias_invalid")
        return self


class _Rubric(_Strict):
    claims: Annotated[dict[str, _Claim], Field(min_length=1, max_length=16)]
    format: dict[str, Literal["bare_value", "labeled"]] = Field(
        default_factory=dict, max_length=16
    )

    @field_validator("claims")
    @classmethod
    def _unambiguous_aliases(cls, claims: dict[str, _Claim]) -> dict[str, _Claim]:
        observed: set[str] = set()
        for claim in claims.values():
            keys = {_normalize(alias) for alias in claim.field_aliases}
            if keys & observed:
                raise ValueError("grounded_claims_label_ambiguous")
            observed.update(keys)
        return claims


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def validate_claim_rubrics(specs: dict, cases: list[dict]) -> None:
    if specs.keys() != {case["record_id"] for case in cases}:
        raise ValueError("experiment_calibration_coverage")
    for case in cases:
        rubric = _Rubric.model_validate(specs[case["record_id"]])
        expected = {item["id"]: item["kind"] for item in case["criteria"]}
        observed = {key: "content" for key in rubric.claims}
        if rubric.format.keys() & observed.keys():
            raise ValueError("grounded_claims_criteria_invalid")
        observed.update({key: "format" for key in rubric.format})
        if observed != expected:
            raise ValueError("grounded_claims_criteria_invalid")


def format_grades(rubric: dict, response: str) -> dict[str, bool]:
    """Check a prescribed output form independently of semantic correctness."""
    spec = _Rubric.model_validate(rubric)
    clauses = [
        text for line in re.split(r"[;\n]", response) if (text := _normalize(line))
    ]
    fields = {
        alias
        for claim in spec.claims.values()
        for alias in map(_normalize, claim.field_aliases)
    }
    labeled = bool(clauses) and all(
        text.split(":", 1)[0].strip() in fields and ":" in text for text in clauses
    )
    values = {
        alias
        for claim in spec.claims.values()
        for alias in map(
            _normalize, claim.value_aliases or ("brak danych", "nie podano")
        )
    }
    bare = (
        len(clauses) == 1 and len(spec.claims) == 1 and clauses[0].rstrip(".") in values
    )
    return {
        key: bare if form == "bare_value" else labeled
        for key, form in spec.format.items()
    }
