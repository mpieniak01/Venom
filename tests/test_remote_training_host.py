"""Offline host preparation acceptance; no provider, installer or GPU calls."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

FILE = Path(__file__).resolve().parents[1] / "scripts/remote_training_host/prepare.py"
spec = importlib.util.spec_from_file_location("remote_host_prepare", FILE)
assert spec
assert spec.loader
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    code = tmp_path / "source"
    for name in (
        prepare.LOCK,
        prepare.CONTROL,
        "venom_core/services/remote_training/remote.py",
    ):
        path = code / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    snapshot = tmp_path / "models" / prepare.REVISION
    snapshot.mkdir(parents=True)
    for name in (
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "model.safetensors",
    ):
        (snapshot / name).write_text("{}")
    metadata = {"config.json": "fixture-hash", "tokenizer_config.json": "fixture-hash"}
    (snapshot / prepare.MODEL_RECEIPT).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model": prepare.MODEL,
                "revision": prepare.REVISION,
                "files": prepare.payload_hashes(snapshot),
                "native_snapshot_metadata": metadata,
            }
        )
    )
    venv = tmp_path / "model-venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("fixture")
    python = venv / "bin/python"
    python.write_text("fixture")
    python.chmod(0o700)
    args = prepare.parser().parse_args(
        [
            "--python",
            sys.executable,
            "--code-root",
            str(code),
            "--commit",
            "a" * 40,
            "--venv",
            str(venv),
            "--snapshot",
            str(snapshot),
            "--root",
            str(tmp_path / "host"),
            "--admission-db",
            str(tmp_path / "admission.sqlite3"),
            "--offline-model",
            "--apply",
        ]
    )
    commands = []

    def fake(command, **kwargs):
        commands.append(command)
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return args.commit
        if command[0] == "git":
            return ""
        if prepare.METADATA in command:
            return json.dumps(metadata)
        if prepare.DOWNLOAD in command:
            target = Path(command[-1])
            for name in (
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "model.safetensors",
            ):
                (target / name).write_text("{}")
            return ""
        if "platform.python_version()" in command[-1]:
            return prepare.PYTHON
        if command[1:4] == ["python", "find", "--managed-python"]:
            return sys.executable
        return ""

    monkeypatch.setattr(prepare, "run", fake)
    monkeypatch.setattr(prepare.platform, "system", lambda: "Linux")
    monkeypatch.setattr(prepare.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        prepare.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3)
    )
    return args, commands, fake


def test_plan_has_no_installs_downloads_or_filesystem_mutations(setup, monkeypatch):
    args, commands, _ = setup
    args.apply = False
    monkeypatch.setattr(
        prepare.subprocess, "run", lambda *_a, **_k: pytest.fail("process in dry plan")
    )
    result = prepare.plan(args)
    assert result["python_version"] == "3.14.8"
    assert result["requirements"] == [prepare.LOCK, prepare.CONTROL]
    assert not result["gpu_qualified"]
    assert not result["training_started"]
    assert not args.root.exists()
    assert not commands


def test_offline_prepare_is_separate_hash_pinned_and_rpc_importable(setup):
    args, commands, _ = setup
    result = prepare.apply(args)
    assert result["prepared"]
    assert not result["gpu_qualified"]
    install = next(c for c in commands if "--require-hashes" in c)
    assert str(args.code_root / prepare.LOCK) in install
    assert str(args.code_root / prepare.CONTROL) in install
    assert "--only-binary=:all:" in install
    assert not any(prepare.DOWNLOAD in c for c in commands)
    wrapper = args.root / "rpc-python"
    text = wrapper.read_text()
    assert str(args.venv / "bin/python") in text
    assert str(args.code_root) in text
    assert '"$@"' in text
    assert "ENV_FILE=/dev/null" in text
    assert "HF_HUB_OFFLINE=1" in text
    assert wrapper.stat().st_mode & 0o777 == 0o700


def test_download_uses_fixed_model_and_revision_and_no_credentials(setup, monkeypatch):
    args, commands, _ = setup
    args.offline_model = False
    shutil.rmtree(args.snapshot)
    monkeypatch.setenv("HF_TOKEN", "fixture-private-value")
    result = prepare.apply(args)
    download = next(c for c in commands if prepare.DOWNLOAD in c)
    assert download[-3:-1] == [prepare.MODEL, prepare.REVISION]
    assert Path(download[-1]).name == prepare.REVISION
    assert Path(download[-1]) != args.snapshot  # stage before atomic publication
    prepare.snapshot_ready(args.snapshot)
    assert "fixture-private-value" not in json.dumps(result) + json.dumps(commands)


def test_existing_uv_managed_runtime_install_and_new_venv(setup, tmp_path):
    args, commands, _ = setup
    uv = tmp_path / "uv"
    uv.write_text("fixture")
    uv.chmod(0o700)
    args.python, args.uv = None, uv
    (args.venv / "pyvenv.cfg").unlink()
    (args.venv / "bin/python").unlink()
    (args.venv / "bin").rmdir()
    args.venv.rmdir()
    prepare.apply(args)
    assert [str(uv), "python", "install", prepare.PYTHON] in commands
    assert any(c[1:4] == ["-I", "-m", "venv"] for c in commands)


def test_existing_host_configuration_is_idempotent_and_not_reinitialized(setup):
    args, commands, _ = setup
    args.root.mkdir()
    (args.root / "host.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "host_id": "fixture-host",
                "worker_python": str(args.venv / "bin/python"),
                "snapshot": str(args.snapshot),
                "admission_db": str(args.admission_db),
                "code_root": str(args.code_root),
            }
        )
    )
    prepare.apply(args)
    prepare.apply(args)
    assert not any("host-init" in c for c in commands)


@pytest.mark.parametrize(
    "case,error",
    [
        ("commit", "host_commit_mismatch"),
        ("dirty", "host_checkout_dirty"),
        ("python", "host_python_version_mismatch"),
        ("venv-version", "host_venv_version_mismatch"),
    ],
)
def test_rejects_wrong_checkout_or_python_before_install(
    setup, monkeypatch, case, error
):
    args, commands, fake = setup

    def changed(command, **kwargs):
        if case == "commit" and command[:3] == ["git", "rev-parse", "HEAD"]:
            return "b" * 40
        if case == "dirty" and command[:2] == ["git", "status"]:
            return " M unsafe.py"
        if "platform.python_version()" in command[-1]:
            if case == "python" or (
                case == "venv-version" and command[0] == str(args.venv / "bin/python")
            ):
                return "3.12.0"
        return fake(command, **kwargs)

    monkeypatch.setattr(prepare, "run", changed)
    with pytest.raises(ValueError, match=error):
        prepare.apply(args)
    assert not any("--require-hashes" in c for c in commands)


@pytest.mark.parametrize(
    "case,error",
    [
        ("overlap", "overlap"),
        ("revision", "revision_mismatch"),
        ("commit", "commit_invalid"),
        ("source", "source_missing"),
        ("python", "python_executable_invalid"),
        ("uv", "uv_executable_invalid"),
    ],
)
def test_plan_rejects_unsafe_configuration(setup, case, error):
    args, _, _ = setup
    if case == "overlap":
        args.venv = args.code_root / ".venv"
    elif case == "revision":
        args.snapshot = args.snapshot.parent / "main"
    elif case == "commit":
        args.commit = "main"
    elif case == "source":
        (args.code_root / prepare.CONTROL).unlink()
    elif case == "python":
        args.python = Path("/usr/bin/bash")
    else:
        args.uv, args.python = Path("/usr/bin/bash"), None
    with pytest.raises(ValueError, match=error):
        prepare.plan(args)


def test_refuses_existing_conflicting_host_before_install(setup):
    args, commands, _ = setup
    args.root.mkdir()
    (args.root / "host.json").write_text("{}")
    with pytest.raises(ValueError, match="configuration_conflict"):
        prepare.apply(args)
    assert not any("--require-hashes" in c for c in commands)


def test_refuses_active_native_training_lock(setup):
    args, commands, _ = setup
    with prepare.component_lock(args.root):
        with pytest.raises(ValueError, match="component_busy"):
            prepare.apply(args)
    assert not commands


def test_rejects_missing_shard_without_any_installs(setup):
    args, commands, _ = setup
    (args.snapshot / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"layer": "missing.safetensors"}})
    )
    with pytest.raises(ValueError, match="shard_missing"):
        prepare.apply(args)
    assert not any("--require-hashes" in c for c in commands)


def test_rejects_inadequate_disk_and_non_linux(setup, monkeypatch):
    args, _, _ = setup
    monkeypatch.setattr(prepare.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match="insufficient_disk"):
        prepare.apply(args)
    monkeypatch.setattr(prepare.platform, "system", lambda: "Windows")
    with pytest.raises(ValueError, match="platform_mismatch"):
        prepare.apply(args)


def test_error_output_hides_subprocess_stderr(setup, monkeypatch, capsys):
    args, _, _ = setup
    monkeypatch.setattr(
        prepare,
        "apply",
        lambda _: (_ for _ in ()).throw(RuntimeError("private-provider-value")),
    )
    monkeypatch.setattr(
        prepare, "parser", lambda: SimpleNamespace(parse_args=lambda _: args)
    )
    assert prepare.main([]) == 1
    output = capsys.readouterr().out
    assert "private-provider-value" not in output
    assert json.loads(output)["error"] == "host_preparation_failed"


def test_run_timeout_failure_and_environment_redaction(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONHOME", "unsafe")
    monkeypatch.setenv("PYTHONSTARTUP", "unsafe")
    monkeypatch.setenv("PYTHONPATH", "unsafe")
    env = prepare.environment(tmp_path)
    assert env["PYTHONPATH"] == str(tmp_path)
    assert "PYTHONHOME" not in env
    assert "PYTHONSTARTUP" not in env
    monkeypatch.setattr(
        prepare.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a, 1, "private-value", "private-value"
        ),
    )
    with pytest.raises(RuntimeError, match="^host_preparation_command_failed$"):
        prepare.run(["fixture"], cwd=tmp_path)
    monkeypatch.setattr(
        prepare.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, " ready \n", ""),
    )
    assert prepare.run(["fixture"], cwd=tmp_path) == "ready"


@pytest.mark.parametrize(
    "value", ["/etc/passwd", "/tmp/../secret", "/tmp/.ssh/key", "/tmp/bad\nname"]
)
def test_data_paths_reject_private_or_escaping_paths(value):
    with pytest.raises(ValueError):
        prepare.data_path(value)


def test_rejects_symlink_target_and_missing_executable(tmp_path):
    link = tmp_path / "alias"
    link.symlink_to(tmp_path / "target")
    with pytest.raises(ValueError, match="symlink"):
        prepare.data_path(link)
    with pytest.raises(ValueError, match="executable_missing"):
        prepare.executable(tmp_path / "missing")


@pytest.mark.parametrize(
    "change", ["extra", "corrupt", "wrong-model", "wrong-revision", "missing"]
)
def test_existing_snapshot_requires_pinned_provenance_before_install(setup, change):
    args, commands, _ = setup
    receipt = args.snapshot / prepare.MODEL_RECEIPT
    if change == "extra":
        (args.snapshot / "alien.safetensors").write_text("alien")
    elif change == "corrupt":
        (args.snapshot / "config.json").write_text("changed")
    elif change == "missing":
        receipt.unlink()
    else:
        value = json.loads(receipt.read_text())
        value["model" if change == "wrong-model" else "revision"] = "alien"
        receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="provenance"):
        prepare.apply(args)
    assert not any("--require-hashes" in c for c in commands)


def test_native_snapshot_metadata_rechecked_before_host_init(setup, monkeypatch):
    args, commands, fake = setup

    def changed(command, **kwargs):
        if prepare.METADATA in command:
            return json.dumps(
                {"config.json": "changed", "tokenizer_config.json": "changed"}
            )
        return fake(command, **kwargs)

    monkeypatch.setattr(prepare, "run", changed)
    with pytest.raises(ValueError, match="native_metadata_mismatch"):
        prepare.apply(args)
    assert not any("host-init" in c for c in commands)


def test_existing_online_snapshot_reuse_never_downloads_over_it(setup):
    args, commands, _ = setup
    args.offline_model = False
    prepare.apply(args)
    assert not any(prepare.DOWNLOAD in c for c in commands)


def test_payload_hashing_supports_bootstrap_python_without_file_digest(
    tmp_path, monkeypatch
):
    import hashlib

    monkeypatch.delattr(hashlib, "file_digest", raising=False)
    payload = b"blocks" * 300000
    (tmp_path / "model.safetensors").write_bytes(payload)
    assert prepare.payload_hashes(tmp_path) == {
        "model.safetensors": hashlib.sha256(payload).hexdigest()
    }
