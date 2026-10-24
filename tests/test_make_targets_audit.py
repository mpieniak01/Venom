from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "dev" / "make_targets_audit.py"
    spec = importlib.util.spec_from_file_location("make_targets_audit", script_path)
    assert spec is not None
    assert spec.loader is not None
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


def test_prepush_gate_isolates_git_context_before_running_tests(tmp_path: Path):
    source = Path(__file__).resolve().parents[1]
    local_names = set(
        subprocess.check_output(
            ["git", "rev-parse", "--local-env-vars"], cwd=source, text=True
        ).splitlines()
    )
    environment = {
        key: value for key, value in os.environ.items() if key not in local_names
    }
    repository = tmp_path / "release"
    repository.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=repository,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    git("init", "--template=", "-b", "main")
    git("config", "user.email", "fixture@example.com")
    git("config", "user.name", "Fixture")
    (repository / "README").write_text("base\n")
    git("add", "README")
    git("commit", "-m", "base")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    (repository / "venom_core").mkdir()
    (repository / "venom_core" / "fixture.py").write_text("value = 1\n")
    git("add", "venom_core")
    git("commit", "-m", "change")
    scripts = repository / "scripts"
    scripts.mkdir()
    script = scripts / "prepush_quality_gate.sh"
    shutil.copyfile(source / "scripts/prepush_quality_gate.sh", script)
    binary = tmp_path / "bin"
    binary.mkdir()
    observed = tmp_path / "observed.json"
    make = binary / "make"
    make.write_text(
        f"#!{sys.executable}\nimport json, os\n"
        f"open({str(observed)!r}, 'w').write(json.dumps(sorted(k for k in os.environ if k.startswith('GIT_'))))\n"
    )
    make.chmod(0o700)
    alternate = tmp_path / "alternate-index"
    shutil.copyfile(repository / ".git/index", alternate)
    before = alternate.read_bytes()
    environment.update(
        GIT_INDEX_FILE=str(alternate),
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0="core.hooksPath",
        GIT_CONFIG_VALUE_0="/dev/null",
        PATH=str(binary) + os.pathsep + environment["PATH"],
    )
    result = subprocess.run(
        ["bash", str(script)],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not local_names.intersection(json.loads(observed.read_text()))
    assert alternate.read_bytes() == before
