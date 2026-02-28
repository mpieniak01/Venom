from __future__ import annotations

import importlib.util
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
    assert spec and spec.loader
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
    assert resolved == ["tests/test_ok.py"]


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
    assert resolved == ["tests/test_anchor.py"]
