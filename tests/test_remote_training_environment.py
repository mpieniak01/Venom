"""Control-layer readiness is separate from training/CUDA qualification."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from venom_core.services.remote_training import remote_env


@pytest.fixture
def declared(tmp_path, monkeypatch):
    (tmp_path / remote_env.CONTROL_REQUIREMENTS).write_text(
        "fastapi==0.136.3 \\\n    --hash=sha256:" + "a" * 64 + "\n"
    )
    monkeypatch.setattr(remote_env.platform, "python_version", lambda: "3.14.8")
    monkeypatch.setattr(remote_env.platform, "system", lambda: "Linux")
    monkeypatch.setattr(remote_env.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        remote_env.importlib.metadata, "version", lambda name: "0.136.3"
    )
    monkeypatch.setattr(remote_env.importlib, "import_module", lambda name: None)
    monkeypatch.setattr(
        remote_env.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0, "", ""),
    )
    return tmp_path


def test_declared_control_pins_are_checked_without_model_imports(declared):
    result = remote_env.inspect_control(declared)
    assert result["ok"]
    assert result["versions"] == {"fastapi": "0.136.3"}
    assert result["pip_check"]["exit_code"] == 0
    assert not result["model_loaded"]
    assert all(
        not name.startswith(("torch", "transformers")) for name in result["imports"]
    )


@pytest.mark.parametrize("problem", ["version", "package", "import", "pip", "python"])
def test_control_failures_block_readiness(declared, monkeypatch, problem):
    if problem == "version":
        monkeypatch.setattr(
            remote_env.importlib.metadata, "version", lambda name: "other"
        )
    elif problem == "package":

        def missing(name):
            raise remote_env.importlib.metadata.PackageNotFoundError(name)

        monkeypatch.setattr(remote_env.importlib.metadata, "version", missing)
    elif problem == "import":

        def missing_module(name):
            raise ImportError("do-not-report-SECRET")

        monkeypatch.setattr(remote_env.importlib, "import_module", missing_module)
    elif problem == "pip":
        monkeypatch.setattr(
            remote_env.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(a, 1, "secret", ""),
        )
    else:
        monkeypatch.setattr(remote_env.platform, "python_version", lambda: "3.12.0")
    result = remote_env.inspect_control(declared)
    assert not result["ok"]
    assert result["errors"]
    assert "SECRET" not in json.dumps(result)
    assert "secret" not in json.dumps(result)


def test_fresh_worker_probe_has_explicit_interpreter_and_isolated_env(
    tmp_path, monkeypatch
):
    desired = {"ok": True, "imports": {}, "model_loaded": False}
    run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(desired), ""))
    monkeypatch.setattr(remote_env.subprocess, "run", run)
    result = remote_env.check_control_environment(tmp_path, Path(sys.executable))
    assert result == desired
    args, kwargs = run.call_args
    assert args[0][0] == sys.executable
    assert kwargs["env"]["ENV_FILE"] == "/dev/null"
    assert kwargs["env"]["PYTHONPATH"] == str(tmp_path.resolve())
    assert "pip" not in args[0]


@pytest.mark.parametrize(
    "output,code", [("not-json", 0), ("[]", 0), ('{"ok":false}', 1)]
)
def test_broken_worker_probe_is_not_readiness(tmp_path, monkeypatch, output, code):
    monkeypatch.setattr(
        remote_env.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, code, output, ""),
    )
    assert not remote_env.check_control_environment(tmp_path, Path(sys.executable))[
        "ok"
    ]


def test_missing_control_declaration_is_explicit(tmp_path):
    with pytest.raises(ValueError, match="requirements_missing"):
        remote_env.required_versions(tmp_path)
    (tmp_path / remote_env.CONTROL_REQUIREMENTS).write_text("# no packages\n")
    with pytest.raises(ValueError, match="requirements_empty"):
        remote_env.required_versions(tmp_path)


def test_runtime_receipt_rejects_other_source_root(tmp_path):
    result = remote_env.runtime_receipt(tmp_path)
    assert not result["ok"]
    assert result["errors"] == ["code_root_mismatch"]


def test_runtime_receipt_checks_actual_training_versions(monkeypatch):
    root = Path(remote_env.__file__).resolve().parents[3]
    fake_base = {"ok": True, "errors": [], "versions": {}, "model_loaded": False}
    monkeypatch.setattr(
        remote_env,
        "inspect_control",
        lambda code_root: dict(fake_base, errors=[], versions={}),
    )
    metadata = json.loads(
        (
            root / "requirements/locks/granite-operator-training-linux-py314.json"
        ).read_text()
    )
    expected = {name: value["version"] for name, value in metadata["artifacts"].items()}
    monkeypatch.setattr(
        remote_env.importlib.metadata, "version", lambda name: expected[name]
    )
    result = remote_env.runtime_receipt(root)
    assert result["ok"]
    assert result["versions"] == expected
    assert len(result["training_lock_sha256"]) == 64
    assert len(result["control_requirements_sha256"]) == 64
    monkeypatch.setattr(
        remote_env.importlib.metadata, "version", lambda name: "incorrect"
    )
    result = remote_env.runtime_receipt(root)
    assert not result["ok"]
    assert any(
        value.startswith("training_package_version_mismatch:")
        for value in result["errors"]
    )


def test_runtime_receipt_reports_missing_training_package(monkeypatch):
    root = Path(remote_env.__file__).resolve().parents[3]
    monkeypatch.setattr(
        remote_env,
        "inspect_control",
        lambda code_root: {"ok": True, "errors": [], "versions": {}},
    )

    def missing(name):
        raise remote_env.importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(remote_env.importlib.metadata, "version", missing)
    result = remote_env.runtime_receipt(root)
    assert not result["ok"]
    assert any(
        value.startswith("missing_training_package:") for value in result["errors"]
    )


@pytest.mark.parametrize(
    "raw",
    [
        "/etc/passwd",
        "/proc/self/environ",
        "/tmp/../outside",
        "/tmp/.ssh/key",
        "/tmp/.env",
    ],
)
def test_operator_paths_reject_unsafe_inputs_before_filesystem_access(monkeypatch, raw):
    from venom_core.services.remote_training.paths import operator_path

    with monkeypatch.context() as guard:
        guard.setattr(
            Path,
            "resolve",
            lambda *a, **kw: pytest.fail("unsafe input reached filesystem resolution"),
        )
        with pytest.raises(ValueError, match="remote_training_operator_path"):
            operator_path(raw)


def test_operator_paths_reject_symlink_escape_and_preserve_venv_python(tmp_path):
    import sys

    from venom_core.services.remote_training.paths import operator_path, python_path

    link = tmp_path / "input"
    link.symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="symlink"):
        operator_path(link)
    with pytest.raises(ValueError, match="outside_roots"):
        operator_path(link, allow_symlinks=True)
    python = tmp_path / "venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    assert python_path(python) == python.absolute()
    with pytest.raises(ValueError, match="python_path"):
        python_path(tmp_path / "sh")


def test_control_probe_rejects_arbitrary_program_before_spawn(tmp_path, monkeypatch):
    run = Mock()
    monkeypatch.setattr(remote_env.subprocess, "run", run)
    with pytest.raises(ValueError, match="python_path"):
        remote_env.check_control_environment(tmp_path, tmp_path / "sh")
    run.assert_not_called()


def test_python_named_payload_is_not_an_approved_interpreter(tmp_path):
    from venom_core.services.remote_training.paths import python_path

    executable = tmp_path / "bin/python"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    with pytest.raises(ValueError, match="runtime_untrusted"):
        python_path(executable)


def test_control_report_uses_validated_output_file(tmp_path, monkeypatch, capsys):
    output = tmp_path / "reports/qualified.json"
    monkeypatch.setattr(
        remote_env, "check_control_environment", lambda *a: {"ok": True}
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["remote_env", "--code-root", str(tmp_path), "--output", str(output)],
    )
    assert remote_env.main() == 0
    assert json.loads(output.read_text()) == {"ok": True}
