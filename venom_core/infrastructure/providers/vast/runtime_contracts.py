"""Explicit runtime requirements; absent declarations remain unverified."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VERSION_PATTERN = r"\d{1,4}(?:\.\d{1,4}){0,3}"


def version_parts(value: Any) -> tuple[int, ...] | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).split("+", 1)[0]
    if not re.fullmatch(VERSION_PATTERN, text, flags=re.ASCII):
        return None
    parts = tuple(int(x) for x in text.split("."))
    return parts + (0,) * (4 - len(parts))


class RuntimeRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    acceleration: Literal["cuda", "cpu", "any"] = "cuda"
    min_cuda: str = ""
    min_driver: str = ""
    min_engine_version: str = ""
    compute_capabilities: list[int] = Field(default_factory=list, max_length=32)
    capabilities: list[Literal["json", "vision", "tools"]] = Field(default_factory=list)
    allow_cpu_offload: bool = False
    max_ttft_s: float | None = Field(default=None, gt=0)
    min_characters_s: float | None = Field(default=None, gt=0)
    image_cuda: str = ""
    image_min_cuda: str = ""
    image_metadata_source: Literal["operator", "registry_config_digest"] = "operator"
    template_constraints: dict[str, Any] = Field(default_factory=dict)
    unresolved_constraints: list[str] = Field(default_factory=list, max_length=64)

    @field_validator(
        "min_cuda", "min_driver", "min_engine_version", "image_cuda", "image_min_cuda"
    )
    @classmethod
    def valid_version(cls, value: str) -> str:
        if value and version_parts(value) is None:
            raise ValueError("vast.invalid_runtime_version")
        return value

    @field_validator("compute_capabilities")
    @classmethod
    def valid_compute(cls, values: list[int]) -> list[int]:
        if any(value < 100 or value > 9999 for value in values):
            raise ValueError("vast.invalid_compute_capability")
        return sorted(set(values))

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, values):
        return sorted(set(values))
