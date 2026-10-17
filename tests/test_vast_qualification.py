"""Observed stack qualification and persistent history; never accesses hardware."""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from tests.test_vast_operations import service as source_service
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.runtime_contracts import (
    RuntimeRequirements,
)
from venom_core.services.vast_environments.gpu_probe import (
    CUDA_SCRIPT,
    REMOTE_SCRIPT,
    probe_gpu,
)
from venom_core.services.vast_environments.history import entries, lookup, remember
from venom_core.services.vast_environments.qualification import qualify
from venom_core.services.vast_environments.store import Journal


@pytest.fixture
def service(tmp_path):
    return source_service.__wrapped__(tmp_path)


def gpu():
    return {
        "status": "passed",
        "reason": "kernel_verified",
        "gpu_name": "GB10",
        "compute_cap": 1210,
        "driver_version": "580.29.04",
        "driver_cuda": "13.0",
        "engine_kernel": "passed",
        "packages": {"torch": "2.8.0", "vllm": "0.30.0"},
    }


def inspection():
    return {"reasons": [], "unknown": [], "facts": {}}


def test_probe_is_bounded_and_serializes_constant_script(service):
    _, plan, _ = service
    compile(CUDA_SCRIPT, "<cuda>", "exec")
    compile(REMOTE_SCRIPT, "<remote>", "exec")
    with patch(
        "venom_core.services.vast_environments.gpu_probe.subprocess.run",
        return_value=Mock(returncode=0, stdout=json.dumps(gpu())),
    ) as run:
        assert (
            probe_gpu(plan, {"ssh_host": "example.test", "ssh_port": 22})["status"]
            == "passed"
        )
    assert run.call_args.kwargs["timeout"] == 40
    script = run.call_args.kwargs["input"]
    compile(script, "<generated>", "exec")
    assert "timeout=25" in script
    assert "pip install" not in script
    assert "apt-get" not in script


@pytest.mark.parametrize(
    "result",
    [
        Mock(returncode=1, stdout="bad"),
        Mock(returncode=0, stdout="[]"),
        Mock(returncode=0, stdout='{"status":"invented"}'),
        Mock(returncode=0, stdout="x" * 65537),
    ],
)
def test_probe_rejects_invalid_transport(service, result):
    _, plan, _ = service
    with (
        patch(
            "venom_core.services.vast_environments.gpu_probe.subprocess.run",
            return_value=result,
        ),
        pytest.raises(VastError),
    ):
        probe_gpu(plan, {"ssh_host": "example.test", "ssh_port": 22})


def test_probe_timeout(service):
    _, plan, _ = service
    with (
        patch(
            "venom_core.services.vast_environments.gpu_probe.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ssh", 40),
        ),
        pytest.raises(VastError, match="gpu_probe_transport"),
    ):
        probe_gpu(plan, {"ssh_host": "example.test", "ssh_port": 22})


def test_suitable_stack_and_version_requirements(service):
    _, plan, _ = service
    plan.profile.mode = "pytorch"
    plan.profile.runtime = RuntimeRequirements(
        min_cuda="12.9",
        min_driver="580.1",
        min_engine_version="2.8",
        compute_capabilities=[1210],
    )
    result = qualify(plan, inspection(), gpu())
    assert result["status"] == "suitable"
    probe = {
        **gpu(),
        "driver_version": "570.1",
        "driver_cuda": "12.8",
        "compute_cap": 1200,
    }
    result = qualify(plan, inspection(), probe)
    assert result["status"] == "unsuitable"
    assert set(result["reasons"]) == {
        "driver_version",
        "driver_cuda",
        "compute_capability",
    }


def test_ollama_offload_and_loaded_model_are_explicit(service):
    _, plan, _ = service
    plan.profile.mode = "ollama"
    engine = {"loaded_model": {"digest": plan.profile.model_digest}}
    result = qualify(
        plan,
        inspection(),
        {**gpu(), "ollama_processor": {"gpu_percent": 100, "cpu_percent": 0}},
        engine,
    )
    assert result["status"] == "suitable"
    assert qualify(plan, inspection(), gpu(), engine)["status"] == "inconclusive"
    probe = {**gpu(), "ollama_processor": {"gpu_percent": 70, "cpu_percent": 30}}
    assert qualify(plan, inspection(), probe, engine)["status"] == "unsuitable"
    plan.profile.runtime.allow_cpu_offload = True
    assert qualify(plan, inspection(), probe, engine)["status"] == "suitable"


def test_performance_and_partial_suite_do_not_become_gpu_success(service):
    _, plan, _ = service
    plan.profile.mode = "pytorch"
    plan.profile.runtime = RuntimeRequirements(max_ttft_s=1, min_characters_s=20)
    result = qualify(plan, inspection(), gpu())
    assert result["status"] == "inconclusive"
    benchmark = {
        "status": "suitable",
        "short_ttft_median_s": 2,
        "samples": [{"case": "short-0", "status": "ok", "characters_s": 10}],
    }
    result = qualify(plan, inspection(), gpu(), benchmark=benchmark)
    assert result["status"] == "unsuitable"
    assert set(result["reasons"]) == {"characters_s", "ttft"}


def test_negative_history_exact_matching_retest_and_new_image(service):
    svc, plan, offer = service
    plan.profile.mode = "pytorch"
    plan.profile.model = "org/model"
    plan.profile.model_digest = "b" * 40
    offer.update(gpu_name="GB10", compute_cap=1210, driver_version="580.29.04")
    report = qualify(plan, inspection(), {**gpu(), "engine_kernel": "failed"})
    entry = remember(svc.journal, plan, report)
    assert lookup(svc.journal, plan.profile, offer)["excluded"] is True
    assert svc.assess(plan.profile, offer).status == "ineligible"
    assert svc.assess(plan.profile, offer, retest=True).status == "eligible"
    other = {**offer, "driver_version": "590.1"}
    assert lookup(svc.journal, plan.profile, other)["excluded"] is False
    changed = plan.profile.model_copy(update={"image": "test@sha256:" + "c" * 64})
    assert lookup(svc.journal, changed, offer)["status"] == "not_tested"
    reopened = Journal(svc.journal.root)
    assert entries(reopened)[0]["evidence_id"] == entry["evidence_id"]
    assert reopened.path(entry["evidence_id"], ".qualification.json").exists()


def test_inconclusive_transport_never_blacklists_template(service):
    svc, plan, offer = service
    result = qualify(plan, inspection(), {"status": "error", "reason": "probe_timeout"})
    assert result["status"] == "inconclusive"
    remember(svc.journal, plan, result)
    assert lookup(svc.journal, plan.profile, offer)["excluded"] is False
    path = svc.journal.root / "qualifications.json"
    path.write_text("bad json")
    with pytest.raises(VastError, match="qualification_history_invalid"):
        entries(svc.journal)


def test_qualify_operation_persists_and_offline_report_needs_no_cloud_key(
    service, capsys
):
    from venom_core.services.vast_environments.cli import main
    from venom_core.services.vast_environments.operations import workload

    svc, plan, _ = service
    svc.create(plan.plan_id)
    with (
        patch(
            "venom_core.services.vast_environments.operations.inspect",
            return_value=inspection(),
        ),
        patch(
            "venom_core.services.vast_environments.operations.probe_gpu",
            return_value=gpu(),
        ),
    ):
        result = workload(svc, plan.plan_id, "qualify")
    assert result["status"] == "suitable"
    assert result["qualification_history"]["status"] == "suitable"
    assert (
        main(
            [
                "--json",
                "--state-dir",
                str(svc.journal.root),
                "report",
                "--plan",
                plan.plan_id,
            ],
            client_factory=Mock(side_effect=AssertionError),
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["result"]["reports"]["qualify"]["status"] == "suitable"
    assert (
        main(
            ["--json", "--state-dir", str(svc.journal.root), "qualifications"],
            client_factory=Mock(side_effect=AssertionError),
        )
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)["result"]) == 1
    svc.export(plan.plan_id)
    svc.change(plan.plan_id, "destroy")
    assert entries(svc.journal)[0]["status"] == "suitable"
