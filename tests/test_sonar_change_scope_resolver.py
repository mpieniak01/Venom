from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "resolve_sonar_new_code_tests.py"
    )
    spec = importlib.util.spec_from_file_location(
        "resolve_sonar_new_code_tests", script_path
    )
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_is_light_test_detects_blocked_markers(tmp_path):
    module = _load_module()
    test_file = tmp_path / "test_blocked.py"
    test_file.write_text(
        "@pytest.mark.integration\ndef test_x():\n    pass\n", encoding="utf-8"
    )
    assert module._is_light_test(str(test_file)) is False


def test_is_light_test_accepts_plain_unit_test(tmp_path):
    module = _load_module()
    test_file = tmp_path / "test_plain.py"
    test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    assert module._is_light_test(str(test_file)) is True


def test_resolve_tests_includes_groups_and_changed_items(monkeypatch, tmp_path):
    module = _load_module()

    baseline = tmp_path / "ci-lite.txt"
    new_code = tmp_path / "sonar-new-code.txt"
    baseline.write_text("tests/test_base.py\n", encoding="utf-8")
    new_code.write_text("tests/test_new.py\n", encoding="utf-8")

    files = [
        "tests/test_base.py",
        "tests/test_new.py",
        "tests/test_changed.py",
        "tests/test_related.py",
        "tests/test_integration.py",
    ]

    monkeypatch.setattr(
        module,
        "git_changed_files",
        lambda _base: [
            "tests/test_changed.py",
            "venom_core/core/model_registry_clients.py",
        ],
    )
    monkeypatch.setattr(module, "all_test_files", lambda: sorted(files))
    monkeypatch.setattr(
        module,
        "related_tests_for_modules",
        lambda _changed, _tests: {"tests/test_related.py", "tests/test_integration.py"},
    )
    monkeypatch.setattr(
        module,
        "is_light_test",
        lambda path: path != "tests/test_integration.py",
    )

    resolved = module.resolve_tests(
        baseline_group=baseline,
        new_code_group=new_code,
        include_baseline=True,
        diff_base="origin/main",
    )

    assert "tests/test_base.py" in resolved
    assert "tests/test_new.py" in resolved
    assert "tests/test_changed.py" in resolved
    assert "tests/test_related.py" in resolved
    assert "tests/test_integration.py" not in resolved


def test_collect_changed_tests_supports_nested_tests_paths():
    module = _load_module()
    changed = [
        "tests/api/test_queue.py",
        "tests/test_root.py",
        "tests/api/not_a_test.py",
    ]
    assert module.collect_changed_tests(changed) == {
        "tests/api/test_queue.py",
        "tests/test_root.py",
    }


def test_resolve_candidates_from_changed_files_returns_sorted_light_unique(
    monkeypatch,
):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "all_test_files",
        lambda: ["tests/test_a.py", "tests/test_b.py"],
    )
    monkeypatch.setattr(
        module,
        "collect_changed_tests",
        lambda _changed: {"tests/test_b.py", "tests/test_a.py"},
    )
    monkeypatch.setattr(
        module,
        "related_tests_for_modules",
        lambda _changed, _tests: {"tests/test_a.py", "tests/test_c.py"},
    )
    monkeypatch.setattr(
        module,
        "is_light_test",
        lambda path: path != "tests/test_c.py",
    )

    resolved = module.resolve_candidates_from_changed_files(
        ["venom_core/core/file.py", "tests/api/test_any.py"]
    )
    assert resolved == ["tests/test_a.py", "tests/test_b.py"]


def test_resolve_tests_applies_time_budget(monkeypatch, tmp_path):
    module = _load_module()
    baseline = tmp_path / "ci-lite.txt"
    new_code = tmp_path / "sonar-new-code.txt"
    baseline.write_text("tests/test_fast.py\n", encoding="utf-8")
    new_code.write_text("tests/test_slow.py\n", encoding="utf-8")

    monkeypatch.setattr(module, "git_changed_files", lambda _base: [])
    monkeypatch.setattr(
        module,
        "all_test_files",
        lambda: ["tests/test_fast.py", "tests/test_slow.py"],
    )
    monkeypatch.setattr(module, "related_tests_for_modules", lambda *_args: set())
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(
        module,
        "load_junit_timings",
        lambda _xml: {"tests/test_fast.py": 1.0, "tests/test_slow.py": 120.0},
    )

    resolved = module.resolve_tests(
        baseline_group=baseline,
        new_code_group=new_code,
        include_baseline=True,
        diff_base="origin/main",
        time_budget_sec=10.0,
        timings_junit_xml="irrelevant.xml",
    )
    assert resolved == ["tests/test_fast.py"]


def test_resolve_tests_excludes_slow_fastlane(monkeypatch, tmp_path):
    module = _load_module()
    baseline = tmp_path / "ci-lite.txt"
    new_code = tmp_path / "sonar-new-code.txt"
    baseline.write_text("tests/test_core_nervous_system.py\n", encoding="utf-8")
    new_code.write_text("tests/test_ok.py\n", encoding="utf-8")

    monkeypatch.setattr(module, "git_changed_files", lambda _base: [])
    monkeypatch.setattr(
        module,
        "all_test_files",
        lambda: ["tests/test_core_nervous_system.py", "tests/test_ok.py"],
    )
    monkeypatch.setattr(module, "related_tests_for_modules", lambda *_args: set())
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)

    resolved = module.resolve_tests(
        baseline_group=baseline,
        new_code_group=new_code,
        include_baseline=True,
        diff_base="origin/main",
        exclude_slow_fastlane=True,
    )
    assert set(resolved) == {"tests/test_ok.py", "tests/test_core_nervous_system.py"}


def test_load_coverage_floor_targets_parses_file(tmp_path):
    module = _load_module()
    floor = tmp_path / "coverage-floor.txt"
    floor.write_text(
        "# comment\nvenom_core/a.py,40\nvenom_core/b.py:55\nvenom_core/c.py\n",
        encoding="utf-8",
    )
    assert module.load_coverage_floor_targets(floor) == [
        "venom_core/a.py",
        "venom_core/b.py",
        "venom_core/c.py",
    ]


def test_coverage_floor_anchor_tests_prefers_direct_module_test(monkeypatch):
    module = _load_module()
    tests = [
        "tests/test_alpha.py",
        "tests/test_beta.py",
        "tests/test_module_registry.py",
    ]
    monkeypatch.setattr(
        module,
        "load_coverage_floor_targets",
        lambda _path=module.DEFAULT_COVERAGE_FLOOR_FILE: [
            "venom_core/services/module_registry.py"
        ],
    )
    monkeypatch.setattr(
        module,
        "related_tests_for_modules",
        lambda _changed, _tests: {"tests/test_alpha.py", "tests/test_beta.py"},
    )
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    anchors = module.coverage_floor_anchor_tests(tests, {})
    assert anchors == {"tests/test_module_registry.py"}


def test_coverage_floor_anchor_tests_prefers_named_module_test(monkeypatch):
    module = _load_module()
    tests = [
        "tests/test_toolmaker_agent.py",
        "tests/test_agents_skill_manager_paths.py",
    ]
    monkeypatch.setattr(
        module,
        "load_coverage_floor_targets",
        lambda _path=module.DEFAULT_COVERAGE_FLOOR_FILE: [
            "venom_core/agents/toolmaker.py"
        ],
    )
    monkeypatch.setattr(
        module,
        "related_tests_for_modules",
        lambda _changed, _tests: {"tests/test_agents_skill_manager_paths.py"},
    )
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(module, "is_fast_safe_test", lambda _path: True)

    anchors = module.coverage_floor_anchor_tests(tests, {}, exclude_slow_fastlane=True)
    assert anchors == {"tests/test_toolmaker_agent.py"}


def test_resolve_tests_prioritizes_floor_anchors_under_budget(monkeypatch, tmp_path):
    module = _load_module()
    baseline = tmp_path / "ci-lite.txt"
    new_code = tmp_path / "sonar-new-code.txt"
    baseline.write_text("tests/test_baseline.py\n", encoding="utf-8")
    new_code.write_text("tests/test_regular.py\n", encoding="utf-8")

    monkeypatch.setattr(module, "git_changed_files", lambda _base: [])
    monkeypatch.setattr(
        module,
        "all_test_files",
        lambda: [
            "tests/test_anchor.py",
            "tests/test_baseline.py",
            "tests/test_regular.py",
        ],
    )
    monkeypatch.setattr(module, "related_tests_for_modules", lambda *_args: set())
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(module, "is_fast_safe_test", lambda _path: True)
    monkeypatch.setattr(
        module,
        "coverage_floor_anchor_tests",
        lambda _tests, _timings, **_kwargs: {"tests/test_anchor.py"},
    )
    monkeypatch.setattr(
        module,
        "load_junit_timings",
        lambda _xml: {
            "tests/test_anchor.py": 1.0,
            "tests/test_baseline.py": 120.0,
            "tests/test_regular.py": 120.0,
        },
    )

    resolved = module.resolve_tests(
        baseline_group=baseline,
        new_code_group=new_code,
        include_baseline=True,
        diff_base="origin/main",
        time_budget_sec=10.0,
        timings_junit_xml="irrelevant.xml",
    )
    assert resolved == ["tests/test_anchor.py", "tests/test_baseline.py"]


def test_resolve_candidates_from_changed_files_respects_catalog(monkeypatch, tmp_path):
    module = _load_module()
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "path": "tests/test_memory_a.py",
                        "domain": "memory",
                        "allowed_lanes": ["new-code"],
                        "legacy_targeted": False,
                    },
                    {
                        "path": "tests/test_governance_b.py",
                        "domain": "governance",
                        "allowed_lanes": ["new-code"],
                        "legacy_targeted": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "all_test_files",
        lambda: ["tests/test_memory_a.py", "tests/test_governance_b.py"],
    )
    monkeypatch.setattr(
        module,
        "collect_changed_tests",
        lambda _changed: {"tests/test_memory_a.py", "tests/test_governance_b.py"},
    )
    monkeypatch.setattr(module, "related_tests_for_modules", lambda *_args: set())
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)

    resolved = module.resolve_candidates_from_changed_files(
        ["venom_core/memory/service.py"],
        catalog_path=catalog,
        required_lane="new-code",
    )
    assert resolved == ["tests/test_memory_a.py"]


def test_build_candidate_infos_keeps_floor_anchor_even_if_dynamic(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(module, "is_fast_safe_test", lambda _path: True)

    path = "tests/test_coder.py"
    infos = module._build_candidate_infos(
        baseline_items=[],
        new_code_items=[],
        changed_tests={path},
        direct_module_tests=set(),
        related_tests=set(),
        floor_anchors={path},
        timings={},
        exclude_slow_fastlane=False,
        changed_domains={"runtime"},
        catalog={
            path: {
                "path": path,
                "domain": "agents",
                "allowed_lanes": ["new-code"],
                "legacy_targeted": False,
            }
        },
        include_baseline=False,
    )
    assert [row.path for row in infos] == [path]


def test_resolve_tests_with_metadata_includes_domain_reason(monkeypatch, tmp_path):
    module = _load_module()
    baseline = tmp_path / "ci-lite.txt"
    new_code = tmp_path / "sonar-new-code.txt"
    catalog = tmp_path / "catalog.json"
    baseline.write_text("tests/test_base.py\n", encoding="utf-8")
    new_code.write_text("tests/test_new.py\n", encoding="utf-8")
    catalog.write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "path": "tests/test_base.py",
                        "domain": "workflow",
                        "allowed_lanes": ["ci-lite", "new-code"],
                        "legacy_targeted": False,
                    },
                    {
                        "path": "tests/test_new.py",
                        "domain": "workflow",
                        "allowed_lanes": ["new-code"],
                        "legacy_targeted": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "git_changed_files", lambda _base: [])
    monkeypatch.setattr(
        module, "all_test_files", lambda: ["tests/test_base.py", "tests/test_new.py"]
    )
    monkeypatch.setattr(module, "related_tests_for_modules", lambda *_args: set())
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(module, "is_fast_safe_test", lambda _path: True)

    selected, metadata = module.resolve_tests_with_metadata(
        baseline_group=baseline,
        new_code_group=new_code,
        include_baseline=True,
        diff_base="origin/main",
        catalog_path=catalog,
    )
    assert selected == ["tests/test_base.py", "tests/test_new.py"]
    by_path = {row["path"]: row for row in metadata}
    assert by_path["tests/test_base.py"]["domain"] == "workflow"
    assert by_path["tests/test_new.py"]["legacy_targeted"] is True
    assert "new_code_group" in by_path["tests/test_new.py"]["selection_reason"]


def test_context_builder_floor_uses_executing_test_even_when_mock_test_is_cheaper(
    monkeypatch,
):
    module = _load_module()
    target = "venom_core/core/orchestrator/task_pipeline/context_builder.py"
    real_test = "tests/test_runtime_registry_contracts.py"
    mock_test = "tests/test_orchestrator_decision_gates.py"
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(module, "is_fast_safe_test", lambda _path: True)
    monkeypatch.setattr(module, "related_tests_for_modules", lambda *_args: {mock_test})
    anchors = module.coverage_floor_anchor_tests(
        [mock_test, real_test],
        {mock_test: 0.1, real_test: 10},
        floor_targets=[target],
        exclude_slow_fastlane=True,
    )
    assert anchors == {real_test}


def test_floor_fallback_breaks_equal_cost_ties_by_path(monkeypatch):
    module = _load_module()
    first = "tests/test_alpha.py"
    last = "tests/test_zeta.py"
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(
        module, "related_tests_for_modules", lambda *_args: [last, first]
    )
    assert module.coverage_floor_anchor_tests(
        [first, last], {}, floor_targets=["venom_core/example.py"]
    ) == {first}


def test_budget_and_max_tests_never_trim_baseline_or_changed_tests():
    module = _load_module()

    def candidate(path, rank, cost, *reasons):
        return module.CandidateInfo(path, rank, cost, "misc", False, reasons)

    baseline = candidate("tests/test_base.py", 2, 120, "baseline_group")
    changed = candidate("tests/test_changed.py", 0, 30, "changed_test")
    optional = candidate("tests/test_optional.py", 2, 1, "new_code_group")
    selected = module._apply_budget([changed, optional, baseline], 1, 1)
    assert [row.path for row in selected] == [changed.path, baseline.path]


def test_floor_anchor_is_independent_of_previous_junit_timings(monkeypatch):
    module = _load_module()
    first, second = "tests/test_alpha.py", "tests/test_zeta.py"
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(
        module, "related_tests_for_modules", lambda *_args: [first, second]
    )
    first_run = module.coverage_floor_anchor_tests(
        [first, second],
        {first: 1.0, second: 100.0},
        floor_targets=["venom_core/example.py"],
    )
    second_run = module.coverage_floor_anchor_tests(
        [first, second],
        {first: 100.0, second: 1.0},
        floor_targets=["venom_core/example.py"],
    )
    assert first_run == second_run


def test_skill_adapter_floor_uses_executing_test_not_mock(monkeypatch):
    module = _load_module()
    real = "tests/test_runtime_registry_translation_contracts.py"
    mock = "tests/test_runtime_policy_regression_contracts.py"
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(module, "is_fast_safe_test", lambda _path: True)
    monkeypatch.setattr(module, "related_tests_for_modules", lambda *_args: {mock})
    assert module.coverage_floor_anchor_tests(
        [real, mock],
        {real: 100.0, mock: 0.1},
        floor_targets=["venom_core/skills/mcp/skill_adapter.py"],
        exclude_slow_fastlane=True,
    ) == {real}


def test_live_test_markers_are_not_in_coverage_selection(tmp_path):
    module = _load_module()
    for marker in (
        "manual_llm",
        "requires_stack",
        "live_venom",
        "live_model",
        "unsafe_direct_runtime",
    ):
        path = tmp_path / f"test_{marker}.py"
        path.write_text(f"import pytest\n@pytest.mark.{marker}\ndef test_x(): pass\n")
        assert not module.is_light_test(str(path)), marker


def test_changed_test_survives_filename_and_domain_heuristics(monkeypatch):
    module = _load_module()
    changed = "tests/test_simulated_integration.py"
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(module, "is_fast_safe_test", lambda _path: False)
    infos = module._build_candidate_infos(
        baseline_items=[],
        new_code_items=[],
        changed_tests={changed},
        direct_module_tests=set(),
        related_tests=set(),
        floor_anchors=set(),
        timings={},
        exclude_slow_fastlane=True,
        changed_domains={"runtime"},
        catalog={changed: {"domain": "skills", "allowed_lanes": ["new-code"]}},
        include_baseline=True,
    )
    assert [item.path for item in infos] == [changed]


def test_required_candidates_survive_cross_domain_related_filter(monkeypatch):
    """Baseline and required anchors must never be discarded as unrelated."""
    module = _load_module()
    baseline = "tests/test_agents_skill_manager_paths.py"
    changed = "tests/test_changed.py"
    direct = "tests/test_direct.py"
    floor = "tests/test_floor.py"
    unrelated = "tests/test_optional_related.py"
    paths = {baseline, changed, direct, floor, unrelated}
    monkeypatch.setattr(module, "is_light_test", lambda _path: True)
    monkeypatch.setattr(module, "is_fast_safe_test", lambda _path: False)
    catalog = {
        path: {"domain": "agents", "allowed_lanes": ["new-code", "ci-lite"]}
        for path in paths
    }

    infos = module._build_candidate_infos(
        baseline_items=[baseline],
        new_code_items=[],
        changed_tests={changed},
        direct_module_tests={direct},
        related_tests=paths,
        floor_anchors={floor},
        timings={},
        exclude_slow_fastlane=True,
        changed_domains={"runtime"},
        catalog=catalog,
        include_baseline=True,
    )
    assert {item.path for item in infos} == {baseline, changed, direct, floor}
    baseline_info = next(item for item in infos if item.path == baseline)
    assert "baseline_group" in baseline_info.selection_reason
    assert "related_module" in baseline_info.selection_reason
