"""Gold solutions must reproduce fail → pass with actual Python processes."""

import subprocess
import sys

import pytest

from venom_core.services.maintenance_comparison.fixtures import (
    gold_files,
    repairs,
    visible_files,
)


@pytest.mark.parametrize("case", repairs(), ids=lambda case: case.id)
def test_controlled_fault_really_fails_then_gold_passes(tmp_path, case):
    def execute(files):
        for name, text in files.items():
            (tmp_path / name).write_text(text)
        oracle = tmp_path.parent / (tmp_path.name + "_oracle.py")
        oracle.write_text("from maintenance_fixture import *\n" + case.oracle + "\n")
        command = [
            sys.executable,
            "-B",
            "-c",
            "import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2]);runpy.run_path(sys.argv[3])['test_contract']()",
            str(tmp_path),
            str(oracle),
            str(tmp_path / "test_visible.py"),
        ]
        return subprocess.run(
            command, cwd=tmp_path, capture_output=True, text=True, timeout=10
        )

    broken = execute(visible_files(case))
    assert broken.returncode != 0
    fixed = execute(gold_files(case))
    assert fixed.returncode == 0, fixed.stderr
    assert len(repairs()) == 8
