"""Declared GPU constraints and legacy plans, without hardware or rental."""

import json

import pytest
from pydantic import ValidationError

from tests.test_vast_operations import service as source_service
from venom_core.infrastructure.providers.vast.models import EnvironmentPlan, digest
from venom_core.infrastructure.providers.vast.runtime_contracts import (
    RuntimeRequirements,
    version_parts,
)
from venom_core.infrastructure.providers.vast.templates import template_constraints
from venom_core.services.vast_environments.assessment import assess, search_filters


@pytest.fixture
def service(tmp_path):
    return source_service.__wrapped__(tmp_path)


def test_versions_are_components_not_floats():
    assert version_parts("12.10") > version_parts("12.9")
    assert version_parts("580.29.04") > version_parts("580.9")
    assert version_parts("2.8.0+cu129") == (2, 8, 0, 0)
    for value in [None, True, "v13", "１３.０", "13.0;id"]:
        assert version_parts(value) is None
    with pytest.raises(ValidationError):
        RuntimeRequirements(min_cuda="invalid")


def test_missing_cuda_is_a_diagnostic_candidate(service):
    _, plan, offer = service
    profile = plan.profile.model_copy(
        update={"runtime": RuntimeRequirements(min_cuda="13.0")}
    )
    result = assess(offer, profile)
    assert result.status == "eligible"
    assert result.runtime["status"] == "unknown"
    assert result.runtime["qualification"] == "not_tested"
    assert "profile.cuda_max_good" in result.runtime["unknown"]


def test_known_runtime_mismatch_and_exact_compute_capability(service):
    _, plan, base = service
    profile = plan.profile.model_copy(
        update={
            "runtime": RuntimeRequirements(
                min_cuda="12.10", min_driver="580.29.04", compute_capabilities=[1210]
            )
        }
    )
    offer = {
        **base,
        "gpu_arch": "nvidia",
        "cuda_max_good": "12.9",
        "driver_version": "580.9",
        "compute_cap": 1200,
    }
    result = assess(offer, profile)
    assert result.status == "ineligible"
    assert len(result.runtime["reasons"]) == 3
    offer.update(cuda_max_good="13.0", driver_version="590.1", compute_cap=1210)
    assert assess(offer, profile).runtime["status"] == "compatible"
    filters = search_filters(profile)
    assert filters["cuda_max_good"] == {"gte": "12.10"}
    assert filters["compute_cap"] == {"in": [1210]}


def test_template_constraints_are_bounded_and_do_not_export_unknown_payloads(service):
    _, plan, base = service
    raw = {
        "cuda_max_good": {"gte": "13.0"},
        "cpu_arch": {"in": ["arm64"]},
        "secret": {"eq": "do-not-export"},
    }
    parsed = template_constraints(json.dumps(raw))
    assert parsed["unresolved"] == ["secret"]
    assert "do-not-export" not in json.dumps(parsed)
    profile = plan.profile.model_copy(
        update={
            "runtime": RuntimeRequirements(
                template_constraints=parsed["constraints"],
                unresolved_constraints=parsed["unresolved"],
            )
        }
    )
    assert assess({**base, "cuda_max_good": "12.9"}, profile).status == "ineligible"
    assert assess({**base, "cuda_max_good": "13.0"}, profile).status == "eligible"
    for invalid in ["bad json", "x" * 9000, ["bad"]]:
        assert template_constraints(invalid)["unresolved"] == ["extra_filters"]


def test_legacy_plan_checksum_and_runtime_injection(service):
    _, plan, _ = service
    old = plan.model_dump(mode="json")
    old["schema_version"] = 1
    old["profile"].pop("runtime")
    old["assessment"].pop("runtime")
    old["assessment"].pop("history")
    old["checksum"] = digest({k: v for k, v in old.items() if k != "checksum"})
    parsed = EnvironmentPlan.model_validate(old)
    assert parsed.calculate_checksum() == old["checksum"]
    old["profile"]["runtime"] = {"min_cuda": "13.0"}
    with pytest.raises(ValidationError, match="legacy_plan_runtime_changed"):
        EnvironmentPlan.model_validate(old)
