from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "check_new_code_coverage.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_new_code_coverage", script_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_git_diff_falls_back_when_origin_main_is_missing(monkeypatch):
    module = _load_module()
    calls: list[str] = []

    def _fake_run(diff_base: str, scope: str):
        calls.append(diff_base)
        if diff_base == "origin/main":
            return 128, "", "bad revision 'origin/main...HEAD'"
        if diff_base == "main":
            return 0, "ok-diff", ""
        return 128, "", "bad revision"

    monkeypatch.setattr(module, "_run_git_diff_once", _fake_run)

    out = module._run_git_diff("origin/main", "venom_core")

    assert out == "ok-diff"
    assert calls[:2] == ["origin/main", "main"]


def test_run_git_diff_raises_after_all_candidates_fail(monkeypatch):
    module = _load_module()

    def _always_fail(diff_base: str, scope: str):
        return 128, "", f"bad revision: {diff_base}"

    monkeypatch.setattr(module, "_run_git_diff_once", _always_fail)

    try:
        module._run_git_diff("origin/main", "venom_core")
    except RuntimeError as exc:
        msg = str(exc)
    else:
        raise AssertionError("Expected RuntimeError")

    assert "origin/main" in msg
    assert "main" in msg
    assert "HEAD~1" in msg
