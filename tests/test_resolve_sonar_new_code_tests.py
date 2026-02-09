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
