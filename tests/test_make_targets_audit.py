from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "dev" / "make_targets_audit.py"
    spec = importlib.util.spec_from_file_location("make_targets_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_phony_multiline_collects_targets():
    module = _load_module()
    content = """
.PHONY: alpha beta \\
  gamma \\
  delta
target:
\t@echo ok
"""
    assert module.parse_phony(content) == {"alpha", "beta", "gamma", "delta"}


def test_cli_reports_missing_definition(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "make_targets_audit.py"
    makefile = tmp_path / "Makefile"
    modules = tmp_path / "make"
    modules.mkdir()

    makefile.write_text(
        ".PHONY: present missing\npresent:\n\t@echo ok\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--makefile",
            str(makefile),
            "--modules-dir",
            str(modules),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "phony_without_definition: 1" in result.stdout
    assert "missing" in result.stdout


def test_cli_reports_defined_target_not_in_phony(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "make_targets_audit.py"
    makefile = tmp_path / "Makefile"
    modules = tmp_path / "make"
    modules.mkdir()

    makefile.write_text(".PHONY: alpha\nalpha:\n\t@echo ok\n", encoding="utf-8")
    (modules / "extra.mk").write_text("beta:\n\t@echo ok\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--makefile",
            str(makefile),
            "--modules-dir",
            str(modules),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "definition_without_phony: 1" in result.stdout
    assert "beta" in result.stdout
