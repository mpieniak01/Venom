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
    assert run.call_args.kwargs["timeout"] == 60
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


@pytest.mark.parametrize(
    "mode,runtime,probe,engine,expected",
    [
        ("inspect", {"acceleration": "any"}, {}, {}, "suitable"),
        ("inspect", {"acceleration": "cpu"}, {}, {}, "inconclusive"),
        (
            "ollama",
            {"acceleration": "cpu"},
            {"ollama_processor": {"cpu_percent": 100}},
            {},
            "suitable",
        ),
        ("ollama", {"acceleration": "cpu"}, {}, {}, "inconclusive"),
        ("pytorch", {}, {"status": "failed", "cuda_error": 209}, {}, "inconclusive"),
        (
            "pytorch",
            {},
            {"status": "failed", "cuda_error": 700, "engine_kernel": "failed"},
            {},
            "unsuitable",
        ),
        ("pytorch", {"min_driver": "999"}, gpu(), {}, "unsuitable"),
        ("pytorch", {"min_cuda": "999"}, {}, {}, "inconclusive"),
        ("pytorch", {"compute_capabilities": [1210]}, {}, {}, "inconclusive"),
        ("pytorch", {}, gpu(), {"readiness": "inconclusive"}, "inconclusive"),
    ],
)
def test_qualification_boundaries(service, mode, runtime, probe, engine, expected):
    _, plan, _ = service
    plan.profile.mode = mode
    plan.profile.runtime = RuntimeRequirements(**runtime)
    result = qualify(plan, inspection(), probe, engine)
    assert result["status"] == expected


def test_capacity_partial_suite_and_performance_phase(service):
    _, plan, _ = service
    plan.profile.mode = "pytorch"
    plan.profile.runtime = RuntimeRequirements(max_ttft_s=1, min_characters_s=1)
    assert (
        qualify(plan, inspection(), gpu(), evaluate_performance=False)["status"]
        == "suitable"
    )
    assert (
        qualify(plan, {"reasons": ["disk"], "unknown": ["cpu"]}, gpu())["status"]
        == "unsuitable"
    )
    assert (
        qualify(plan, inspection(), gpu(), benchmark={"status": "unsuitable"})["status"]
        == "unsuitable"
    )
    assert (
        qualify(plan, inspection(), gpu(), benchmark={"status": "inconclusive"})[
            "status"
        ]
        == "inconclusive"
    )
    result = qualify(
        plan,
        inspection(),
        gpu(),
        benchmark={
            "status": "suitable",
            "short_ttft_median_s": 0.1,
            "samples": [{"case": "short-0", "status": "ok", "characters_s": 10}],
        },
    )
    assert result["status"] == "suitable"


def test_history_transport_preserves_negative_successful_retest_supersedes(service):
    svc, plan, offer = service
    plan.profile.mode = "pytorch"
    offer.update(gpu_name="GB10", compute_cap=1210, driver_version="580.29.04")
    remember(
        svc.journal,
        plan,
        qualify(plan, inspection(), {**gpu(), "engine_kernel": "failed"}),
    )
    remember(
        svc.journal,
        plan,
        qualify(
            plan, inspection(), {**gpu(), "status": "error", "engine_kernel": None}
        ),
    )
    assert lookup(svc.journal, plan.profile, offer)["excluded"] is True
    assert (
        lookup(svc.journal, plan.profile, {**offer, "driver_version": "580.29.4"})[
            "excluded"
        ]
        is True
    )
    remember(svc.journal, plan, qualify(plan, inspection(), gpu()))
    assert lookup(svc.journal, plan.profile, offer)["excluded"] is False


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        '{"schema_version":2,"entries":{}}',
        '{"schema_version":1,"entries":{"x":{"status":"invalid"}}}',
    ],
)
def test_history_rejects_malformed_index(service, content):
    svc, _, _ = service
    (svc.journal.root / "qualifications.json").write_text(content)
    with pytest.raises(VastError, match="qualification_history_invalid"):
        entries(svc.journal)


def test_ready_and_runtime_only_qualification_do_not_erase_workload_failure(service):
    from venom_core.services.vast_environments.operations import _save_result

    svc, plan, offer = service
    context = {"gpu_name": "GB10", "compute_cap": 1210, "driver_version": "580.29.04"}
    offer.update(context)
    plan.assessment.offer.update(context)
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    failed = qualify(plan, inspection(), gpu(), benchmark={"status": "unsuitable"})
    _save_result(
        svc,
        plan.plan_id,
        "benchmark",
        {"status": "unsuitable", "qualification_report": failed},
    )
    assert lookup(svc.journal, plan.profile, offer)["excluded"] is True
    ready = qualify(plan, inspection(), gpu(), evaluate_performance=False)
    _save_result(
        svc, plan.plan_id, "ready", {"runtime": "ready", "qualification_report": ready}
    )
    assert len(entries(svc.journal)) == 1
    assert lookup(svc.journal, plan.profile, offer)["excluded"] is True
    runtime_only = qualify(plan, inspection(), gpu())
    _save_result(svc, plan.plan_id, "qualify", runtime_only)
    assert lookup(svc.journal, plan.profile, offer)["excluded"] is True
    complete = qualify(
        plan, inspection(), gpu(), benchmark={"status": "suitable", "samples": []}
    )
    _save_result(
        svc,
        plan.plan_id,
        "benchmark",
        {"status": "suitable", "qualification_report": complete},
    )
    assert lookup(svc.journal, plan.profile, offer)["excluded"] is False


@pytest.mark.parametrize(
    "code",
    [
        "vast.plan_busy",
        "vast.qualification_history_invalid",
        "vast.qualification_history_limit",
        "os_error",
    ],
)
def test_history_failure_keeps_operation_report_durable(service, code):
    from venom_core.services.vast_environments.operations import _save_result

    svc, plan, _ = service
    report = qualify(plan, inspection(), gpu())
    result = {
        "status": "suitable",
        "samples": [{"characters_s": 10}],
        "qualification_report": report,
    }

    def unavailable(*_):
        saved = svc.journal.record(plan.plan_id).reports["benchmark"]
        assert saved["samples"] == [{"characters_s": 10}]
        if code == "os_error":
            raise OSError("private path must not escape")
        raise VastError(code)

    with patch(
        "venom_core.services.vast_environments.operations.remember",
        side_effect=unavailable,
    ):
        _save_result(svc, plan.plan_id, "benchmark", result)
    saved = svc.journal.record(plan.plan_id).reports["benchmark"]
    assert saved["status"] == "suitable"
    assert saved["qualification_history"]["status"] == "error"
    assert saved["qualification_history"]["error"] == (
        "vast.qualification_history_write_failed" if code == "os_error" else code
    )
    assert "private path" not in json.dumps(saved)


def test_legacy_qualification_report_without_performance_flag_is_retained(service):
    from venom_core.services.vast_environments.operations import _save_result

    svc, plan, _ = service
    report = qualify(plan, inspection(), gpu())
    report.pop("performance_evaluated")
    _save_result(svc, plan.plan_id, "qualify", report)
    assert len(entries(svc.journal)) == 1
