from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_new_code_coverage_gate.py"
    )
    spec = importlib.util.spec_from_file_location(
        "run_new_code_coverage_gate", script_path
    )
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ResolverStub:
    @staticmethod
    def all_test_files():
        return [
            "tests/test_service_monitor.py",
            "tests/test_core_nervous_system.py",
            "tests/test_foo.py",
        ]

    @staticmethod
    def related_tests_for_modules(changed_files, test_files):
        assert "venom_core/core/service_monitor.py" in changed_files
        return {"tests/test_service_monitor.py", "tests/test_core_nervous_system.py"}

    @staticmethod
    def is_light_test(path):
        return True

    @staticmethod
    def estimate_test_cost(path, timings):
        return timings.get(path, 10.0)


def test_fallback_candidates_skips_already_selected_and_respects_cost_order():
    module = _load_module()
    out = module._fallback_candidates(
        _ResolverStub(),
        uncovered_files=["venom_core/core/service_monitor.py"],
        already_selected={"tests/test_core_nervous_system.py"},
        timings={"tests/test_service_monitor.py": 1.0, "tests/test_foo.py": 2.0},
        max_count=5,
    )
    assert out == ["tests/test_service_monitor.py"]


def test_run_metacharacters_remain_literal_arguments(tmp_path):
    """Exercise this runner's real subprocess boundary without a shell."""
    module = _load_module()
    argv_file = tmp_path / "argv.json"
    marker = tmp_path / "injected"
    payload = f"scene; touch {marker}; # $(touch {marker})"
    executable = tmp_path / "coverage-gate-probe"
    executable.write_text(
        f"#!{sys.executable}\nimport json,sys\nfrom pathlib import Path\n"
        f"Path({str(argv_file)!r}).write_text(json.dumps(sys.argv[1:]))\n"
    )
    executable.chmod(0o700)
    module._run([str(executable), payload])
    assert json.loads(argv_file.read_text()) == [payload]
    assert not marker.exists()


def test_floor_only_failure_runs_fallback_and_keeps_both_junit_phases(
    monkeypatch, tmp_path, capsys
):
    """A passing diff must not conceal an under-covered floor or lose JUnit tests."""
    import xml.etree.ElementTree as ET

    module = _load_module()
    coverage = tmp_path / "coverage.xml"
    junit = tmp_path / "junit.xml"
    thresholds = tmp_path / "floors.txt"
    thresholds.write_text("venom_core/example.py,40\n", encoding="utf-8")
    phases = []

    def fake_pytest(**kwargs):
        phases.append(kwargs["tests"])
        rate = "0.2" if len(phases) == 1 else "0.8"
        coverage.write_text(
            "<coverage><packages><package><classes>"
            f'<class filename="example.py" line-rate="{rate}" />'
            "</classes></package></packages></coverage>",
            encoding="utf-8",
        )
        Path(kwargs["junit_xml"]).write_text(
            '<testsuites><testsuite name="pytest" tests="1">'
            f'<testcase classname="tests.test_sample" name="phase_{len(phases)}"/>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        return 1.0

    monkeypatch.setattr(module, "_run_pytest", fake_pytest)
    monkeypatch.setattr(
        module,
        "_resolve_tests_with_metadata",
        lambda *_args, **_kwargs: (["tests/test_base.py"], []),
    )
    monkeypatch.setattr(
        module,
        "_compute_uncovered_summary",
        lambda *_args, **_kwargs: {
            "pass": True,
            "total_coverable": 1,
            "rate_percent": 100.0,
            "required_percent": 80.0,
            "uncovered_files": [{"path": "venom_core/partially_covered.py"}],
        },
    )

    def fallback(_resolver, *, uncovered_files, floor_files, **_kwargs):
        assert uncovered_files == []
        assert floor_files == ["venom_core/example.py"]
        return ["tests/test_fallback.py"]

    monkeypatch.setattr(module, "_fallback_candidates", fallback)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "coverage-gate",
            "--baseline-group",
            "baseline",
            "--new-code-group",
            "new",
            "--mark-expr",
            "not performance",
            "--cov-target",
            "venom_core",
            "--coverage-xml",
            str(coverage),
            "--junit-xml",
            str(junit),
            "--floor-config",
            str(thresholds),
        ],
    )
    assert module.main() == 0
    assert phases == [["tests/test_base.py"], ["tests/test_fallback.py"]]
    assert [node.get("name") for node in ET.parse(junit).iter("testcase")] == [
        "phase_1",
        "phase_2",
    ]
    assert '"uncovered_floor_files": []' in capsys.readouterr().out


def test_invalid_fallback_junit_preserves_original_report(tmp_path):
    import pytest

    module = _load_module()
    primary = tmp_path / "primary.xml"
    fallback = tmp_path / "fallback.xml"
    original = '<testsuites><testsuite name="pytest" tests="1"/></testsuites>'
    primary.write_text(original, encoding="utf-8")
    fallback.write_text("<invalid/>", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected JUnit root"):
        module._merge_junit_reports(str(primary), str(fallback))
    assert primary.read_text(encoding="utf-8") == original


def _load_manifest():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "sonar_report_manifest.py"
    )
    spec = importlib.util.spec_from_file_location("sonar_report_manifest", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sonar_reports_are_bound_to_checkout_and_contents(tmp_path):
    import pytest

    module = _load_manifest()
    (tmp_path / "python-coverage.xml").write_text(
        '<coverage><packages><package><classes><class filename="example.py"/>'
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )
    junit = tmp_path / "python-junit.xml"
    junit.write_text(
        '<testsuites><testsuite><testcase name="unit"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    sha = "a" * 40
    module.write_manifest(tmp_path, sha)
    module.verify_manifest(tmp_path, sha)
    with pytest.raises(ValueError, match="checkout revision"):
        module.verify_manifest(tmp_path, "b" * 40)
    junit.write_text(
        '<testsuites><testsuite><testcase name="other"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="reports differ"):
        module.verify_manifest(tmp_path, sha)


def test_sonar_manifest_rejects_empty_or_fully_skipped_runs(tmp_path):
    import pytest

    module = _load_manifest()
    (tmp_path / "python-coverage.xml").write_text(
        '<coverage><packages><package><classes><class filename="example.py"/>'
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )
    junit = tmp_path / "python-junit.xml"
    for content in (
        "<testsuites><testsuite/></testsuites>",
        "<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>",
    ):
        junit.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match="no executed tests"):
            module.write_manifest(tmp_path, "a" * 40)
    assert not (tmp_path / "report-manifest.json").exists()


def test_floor_candidate_precedes_more_than_twenty_cheaper_changed_candidates():
    module = _load_module()
    floor = "tests/test_floor.py"
    changed = [f"tests/test_changed_{i}.py" for i in range(30)]

    class Resolver:
        @staticmethod
        def all_test_files():
            return [floor, *changed]

        @staticmethod
        def related_tests_for_modules(paths, _tests):
            return {floor} if "venom_core/floor.py" in paths else set(changed)

        @staticmethod
        def is_light_test(_path):
            return True

        @staticmethod
        def estimate_test_cost(path, _timings):
            return 100.0 if path == floor else 1.0

    selected = module._fallback_candidates(
        Resolver(),
        floor_files=["venom_core/floor.py"],
        uncovered_files=["venom_core/changed.py"],
        already_selected=set(),
        timings={},
        max_count=20,
    )
    assert selected[0] == floor
    assert len(selected) == 20
    assert set(selected[1:]) <= set(changed)


def test_floor_reservations_cannot_be_cut_by_candidate_limit():
    module = _load_module()
    floors = [f"venom_core/floor_{i}.py" for i in range(25)]
    tests = [f"tests/test_floor_{i}.py" for i in range(25)]

    class Resolver:
        @staticmethod
        def all_test_files():
            return tests

        @staticmethod
        def related_tests_for_modules(paths, _tests):
            return {f"tests/test_{Path(path).stem}.py" for path in paths}

        @staticmethod
        def is_light_test(_path):
            return True

        @staticmethod
        def estimate_test_cost(_path, _timings):
            return 1.0

    selected = module._fallback_candidates(
        Resolver(),
        floor_files=floors,
        uncovered_files=[],
        already_selected=set(),
        timings={},
        max_count=20,
    )
    assert set(selected) == set(tests)


def test_fallback_respects_catalog_and_slow_policy_with_protected_floor():
    module = _load_module()
    protected = "tests/test_floor_integration.py"
    release = "tests/test_release_only.py"
    slow = "tests/test_slow_related.py"
    safe = "tests/test_safe_related.py"
    live = "tests/test_live_related.py"
    tests = [protected, release, slow, safe, live]

    class Resolver:
        @staticmethod
        def all_test_files():
            return tests

        @staticmethod
        def related_tests_for_modules(_paths, _tests):
            return set(tests)

        @staticmethod
        def is_light_test(path):
            return path != live

        @staticmethod
        def is_fast_safe_test(path):
            return path == safe

        @staticmethod
        def estimate_test_cost(path, _timings):
            return 0.1 if path == protected else 1.0

    catalog = {path: {"allowed_lanes": ["new-code"]} for path in tests}
    catalog[release] = {"allowed_lanes": ["release"]}
    selected = module._fallback_candidates(
        Resolver(),
        floor_files=["venom_core/floor_integration.py"],
        uncovered_files=["venom_core/changed.py"],
        already_selected=set(),
        timings={},
        max_count=20,
        catalog=catalog,
        include_baseline=True,
        exclude_slow_fastlane=True,
    )
    assert selected == [protected, safe]


def test_hosted_ci_dispatch_uses_full_report_only_on_main(tmp_path):
    """Exercise the actual workflow shell using a fake make, without running CI."""
    import os
    import subprocess

    import yaml

    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
    data = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    step = next(
        item["run"]
        for item in data["jobs"]["backend-lite"]["steps"]
        if item.get("name")
        == "Run backend coverage pipeline (PR fast gate / main full sonar report)"
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    make = binary / "make"
    make.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$RUN_CAPTURE"\n', encoding="utf-8"
    )
    make.chmod(0o700)
    cases = [
        ("push", "refs/heads/main", "", "sonar-reports-backend"),
        ("workflow_dispatch", "refs/heads/main", "", "sonar-reports-backend"),
        ("workflow_dispatch", "refs/heads/fix/coverage", "", "check-new-code-coverage"),
        ("workflow_dispatch", "refs/heads/main-extra", "", "check-new-code-coverage"),
        ("pull_request", "refs/pull/42/merge", "main", "check-new-code-coverage"),
    ]
    for index, (event, ref, base, expected) in enumerate(cases):
        case_dir = tmp_path / f"case-{index}"
        case_dir.mkdir()
        output = case_dir / "calls.txt"
        env = {
            **os.environ,
            "PATH": f"{binary}:{os.environ['PATH']}",
            "GITHUB_EVENT_NAME": event,
            "GITHUB_REF": ref,
            "GITHUB_BASE_REF": base,
            "BACKEND_LITE_PYTEST_WORKERS": "4",
            "RUN_CAPTURE": str(output),
        }
        result = subprocess.run(
            ["bash", "-e", "-c", step],
            cwd=case_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        calls = output.read_text(encoding="utf-8").splitlines()
        assert calls[0] == "audit-ci-lite"
        assert calls[1].split()[0] == expected
        if expected == "check-new-code-coverage":
            assert "NEW_CODE_DIFF_BASE=origin/main" in calls[1]
