"""Versioned contracts. Provider secrets never enter exported models."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from venom_core.infrastructure.providers.vast.runtime_contracts import (
    RuntimeRequirements,
)


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
    runtime: RuntimeRequirements = Field(default_factory=RuntimeRequirements)
    mode: Literal["inspect", "ollama", "vllm", "pytorch"] = "inspect"
    cpu_arch: Literal["amd64", "arm64"]
    image: str
    model: str = ""
    model_digest: str = ""
    template_hash: str = Field(default="", max_length=128, pattern=r"^[a-zA-Z0-9_-]*$")
    template_configuration_sha256: str = Field(default="", pattern=r"^([a-f0-9]{64})?$")
    gpu_memory_utilization: float = Field(default=0.85, gt=0, le=0.95)
    max_parallel_requests: int = Field(default=4, ge=1, le=32)
    worker_packages: list[str] = Field(default_factory=list, max_length=8)
    worker_tasks: list[Literal["vision", "audio"]] = Field(default=["vision", "audio"])
    disk_gb: int = Field(default=150, ge=16, le=10000)
    min_free_disk_bytes: int = Field(default=10_000_000_000, ge=0)
    min_gpu_ram_mb: int = Field(default=24000, ge=0)
    min_cpu_ram_mb: int = Field(default=32000, ge=0)
    min_cpu_cores: float = Field(default=4, gt=0)
    min_reliability: float = Field(default=0.98, ge=0, le=1)
    min_disk_mb_s: float = Field(default=0, ge=0)
    min_download_mbps: float = Field(default=0, ge=0)
    min_upload_mbps: float = Field(default=0, ge=0)
    min_dlperf: float = Field(default=0, ge=0)
    min_gpu_mem_bw_gb_s: float = Field(default=0, ge=0)
    min_gpu_fraction: float = Field(
        default=0.001,
        gt=0,
        le=1,
        description="Minimum machine GPU allocation fraction, not per-card exclusivity",
    )
    countries: list[str] = Field(default_factory=list, max_length=50)
    preferred_countries: list[str] = Field(default_factory=lambda: ["PL"], max_length=8)
    sort_by: Literal[
        "balanced", "price", "network", "reliability", "performance", "value"
    ] = "balanced"
    gpu_names: list[str] = Field(default_factory=list)
    duration_minutes: int = Field(default=30, ge=1, le=1440)
    download_gb: Decimal = Field(default=Decimal("0"), ge=0)
    upload_gb: Decimal = Field(default=Decimal("0"), ge=0)
    context_tokens: int = Field(default=16384, ge=512, le=131072)
    output_tokens: int = Field(default=128, ge=8, le=512)

    @field_validator("worker_packages")
    @classmethod
    def pinned_worker_packages(cls, values: list[str]) -> list[str]:
        allowed = {"ultralytics", "transformers", "faster-whisper", "pillow"}
        for value in values:
            name, sep, version = value.partition("==")
            if (
                name not in allowed
                or not sep
                or not re.fullmatch(r"\d[\w.+-]{0,63}", version, flags=re.ASCII)
            ):
                raise ValueError("vast.pinned_worker_package_required")
        if len({value.split("==")[0] for value in values}) != len(values):
            raise ValueError("vast.duplicate_worker_package")
        return values

    @field_validator("countries", "preferred_countries")
    @classmethod
    def country_codes(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().upper() for value in values))
        if any(
            len(value) != 2 or not value.isascii() or not value.isalpha()
            for value in normalized
        ):
            raise ValueError("vast.invalid_country_code")
        return normalized

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
    "country_code",
    "dph_base",
    "dph_total",
    "storage_cost",
    "storage_total_cost",
    "inet_down_cost",
    "inet_up_cost",
    "internet_down_cost_per_tb",
    "internet_up_cost_per_tb",
    "total_flops",
    "dlperf_per_dphtotal",
    "flops_per_dphtotal",
    "gpu_mem_bw",
    "gpu_total_ram",
    "cpu_name",
    "cpu_ghz",
    "cpu_cores",
    "compute_cap",
    "pcie_bw",
    "pci_gen",
    "gpu_lanes",
    "bw_nvlink",
    "has_avx",
    "dlperf",
    "gpu_arch",
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
    "cpu_cores_effective",
    "gpu_frac",
    "mem_limit",
    "mem_usage",
    "vmem_usage",
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


class HostSignals(Contract):
    country_code: str | None = None
    preferred_country: bool = False
    download_mbps: Decimal | None = None
    upload_mbps: Decimal | None = None
    reliability_percent: Decimal | None = None
    verified: bool | None = None
    user_reviews: Literal["not_provided"] = "not_provided"
    dlperf: Decimal | None = None
    total_tflops: Decimal | None = None
    gpu_memory_bandwidth_gb_s: Decimal | None = None
    dlperf_per_hourly_usd: Decimal | None = None
    source: Literal["provider_declared"] = "provider_declared"


class OfferAssessment(Contract):
    offer: dict[str, Any]
    observed_at: datetime = Field(default_factory=now)
    status: Literal["eligible", "ineligible", "unknown"]
    reasons: list[str]
    unknown: list[str]
    quote: CostQuote
    performance: Literal["unknown"] = "unknown"
    host: HostSignals = Field(default_factory=HostSignals)
    runtime: dict[str, Any] = Field(default_factory=dict)
    history: dict[str, Any] = Field(default_factory=dict)


class EnvironmentPlan(Contract):
    schema_version: Literal[1, 2] = 2
    plan_id: str
    retest: bool = False
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

    @model_validator(mode="after")
    def legacy_defaults(self):
        if self.schema_version == 1 and (
            self.retest
            or self.profile.runtime != RuntimeRequirements()
            or self.assessment.runtime
            or self.assessment.history
        ):
            raise ValueError("vast.legacy_plan_runtime_changed")
        return self

    def calculate_checksum(self) -> str:
        data = self.model_dump(mode="json", exclude={"checksum"})
        if self.schema_version == 1:
            data.pop("retest", None)
            data["profile"].pop("runtime", None)
            data["assessment"].pop("runtime", None)
            data["assessment"].pop("history", None)
        return digest(data)


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
