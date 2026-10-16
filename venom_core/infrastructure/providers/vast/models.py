"""Versioned contracts. Provider secrets never enter exported models."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now() -> datetime:
    return datetime.now(timezone.utc)


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def amount(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class WorkloadProfile(Contract):
    name: str = Field(min_length=1, max_length=80)
    mode: Literal["inspect", "ollama"] = "inspect"
    cpu_arch: Literal["amd64", "arm64"]
    image: str
    model: str = ""
    model_digest: str = ""
    disk_gb: int = Field(default=150, ge=16, le=10000)
    min_free_disk_bytes: int = Field(default=10_000_000_000, ge=0)
    min_gpu_ram_mb: int = Field(default=24000, ge=0)
    min_cpu_ram_mb: int = Field(default=32000, ge=0)
    min_cpu_cores: float = Field(default=4, gt=0)
    min_reliability: float = Field(default=0.98, ge=0, le=1)
    min_disk_mb_s: float = Field(default=0, ge=0)
    min_download_mb_s: float = Field(default=0, ge=0)
    min_gpu_fraction: float = Field(default=1, gt=0, le=1)
    countries: list[str] = Field(default_factory=list)
    gpu_names: list[str] = Field(default_factory=list)
    duration_minutes: int = Field(default=30, ge=1, le=1440)
    download_gb: Decimal = Field(default=Decimal("0"), ge=0)
    upload_gb: Decimal = Field(default=Decimal("0"), ge=0)
    context_tokens: int = Field(default=16384, ge=512, le=131072)
    output_tokens: int = Field(default=128, ge=8, le=512)

    @field_validator("image")
    @classmethod
    def pinned_image(cls, value: str) -> str:
        name, separator, sha = value.partition("@sha256:")
        if not separator or not name or len(sha) != 64:
            raise ValueError("vast.image_digest_required")
        if any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("vast.image_digest_required")
        if (
            any(c.isspace() for c in name)
            or name.startswith("-")
            or "REPLACE" in name
            or sha == "0" * 64
        ):
            raise ValueError("vast.invalid_image")
        return value

    @field_validator("model", "model_digest")
    @classmethod
    def safe_model(cls, value: str) -> str:
        if any(c.isspace() for c in value) or value.startswith("-"):
            raise ValueError("vast.invalid_model")
        return value


# Only these scalar fields may leave the provider boundary.
OFFER_FIELDS = (
    "id",
    "ask_contract_id",
    "machine_id",
    "host_id",
    "gpu_name",
    "cpu_arch",
    "cpu_ram",
    "gpu_ram",
    "num_gpus",
    "gpu_frac",
    "cpu_cores_effective",
    "reliability",
    "reliability2",
    "verification",
    "rentable",
    "rented",
    "duration",
    "disk_space",
    "disk_bw",
    "inet_down",
    "inet_up",
    "direct_port_count",
    "geolocation",
    "dph_base",
    "dph_total",
    "storage_cost",
    "storage_total_cost",
    "inet_down_cost",
    "inet_up_cost",
    "internet_down_cost_per_tb",
    "internet_up_cost_per_tb",
    "dlperf",
    "cuda_max_good",
    "driver_version",
    "os_version",
)
INSTANCE_FIELDS = (
    "id",
    "label",
    "actual_status",
    "intended_status",
    "ssh_host",
    "ssh_port",
    "image_uuid",
    "image_runtype",
    "start_date",
    "disk_space",
    "gpu_name",
    "cpu_arch",
    "cpu_ram",
    "gpu_ram",
    "dph_total",
    "host_id",
    "machine_id",
)


def project(data: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {
        key: data[key]
        for key in fields
        if key in data and isinstance(data[key], (str, int, float, bool, type(None)))
    }


def offer_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    result = project(data, OFFER_FIELDS)
    search = data.get("search")
    if isinstance(search, dict):
        result["search"] = project(search, ("totalHour", "gpuCostPerHour", "diskHour"))
    return result


class CostQuote(Contract):
    currency: Literal["USD"] = "USD"
    kind: Literal["quote"] = "quote"
    observed_at: datetime = Field(default_factory=now)
    hourly_usd: Decimal | None
    storage_hourly_usd: Decimal | None
    transfer_usd: Decimal | None
    total_usd: Decimal | None
    samples_minutes_usd: dict[str, Decimal | None]
    rates: dict[str, Any]
    unknown: list[str]
    source: str = "Vast search quote for allocated_storage; disk included in total"


class OfferAssessment(Contract):
    offer: dict[str, Any]
    observed_at: datetime = Field(default_factory=now)
    status: Literal["eligible", "ineligible", "unknown"]
    reasons: list[str]
    unknown: list[str]
    quote: CostQuote
    performance: Literal["unknown"] = "unknown"


class EnvironmentPlan(Contract):
    schema_version: Literal[1] = 1
    plan_id: str
    profile: WorkloadProfile
    assessment: OfferAssessment
    expires_at: datetime
    max_hourly_usd: Decimal = Field(gt=0)
    max_total_usd: Decimal = Field(gt=0)
    finish_policy: Literal["manual", "stop", "destroy"] = "manual"
    ssh_identity_file: str
    ssh_known_hosts: str
    ssh_fingerprint: str
    startup_sha256: str
    checksum: str = ""

    def calculate_checksum(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"checksum"}))


class EnvironmentRecord(Contract):
    schema_version: Literal[1] = 1
    plan_id: str
    state: str = "planned"
    instance_id: int | None = None
    observed_at: datetime = Field(default_factory=now)
    submitted_at: datetime | None = None
    instance: dict[str, Any] = Field(default_factory=dict)
    pending_action: Literal["start", "stop", "destroy"] | None = None
    ssh_state: str = "unknown"
    runtime_state: str = "unknown"
    reports: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, str]] = Field(default_factory=list)
