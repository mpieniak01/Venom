from __future__ import annotations

import importlib.util
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
    assert spec and spec.loader
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
