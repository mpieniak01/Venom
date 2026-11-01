"""Portable identity checks stay offline; a remote PASS is not a local reload."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from venom_core.services.granite_operator.contract import (
    MODEL,
    REVISION,
    TrainingProfile,
    digest,
    file_digest,
)
from venom_core.services.remote_training.host import (
    code_identity,
    dependencies_identity,
    tokenizer_identity,
)
from venom_core.services.remote_training.verification import (
    _receipt_matches,
    validate_local,
)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    snapshot = tmp_path / REVISION
    snapshot.mkdir()
    (snapshot / "tokenizer_config.json").write_text(
        json.dumps({"chat_template": "native"})
    )
    code = tmp_path / "code"
    package = code / "venom_core/services/granite_operator"
    package.mkdir(parents=True)
    (package / "engine.py").write_text("reviewed-code")
    lock = code / "requirements/locks/granite-operator-training-linux-py314.txt"
    lock.parent.mkdir(parents=True)
    lock.write_text("qualified-lock")
    (code / "requirements-remote-training-control.txt").write_text(
        "qualified-control-lock"
    )
    from venom_core.services.remote_training import verification

    monkeypatch.setattr(verification, "native_code_root", lambda: code)
    monkeypatch.setattr(
        verification, "_runtime", lambda _: {"ok": True, "model_loaded": False}
    )
    monkeypatch.setattr(verification, "_worker_runtime", lambda _: {"ok": True})
    document = {"license": "fixture-provenance"}
    (adapter / "data-manifest.json").write_text(json.dumps(document))
    profile = TrainingProfile()
    tokenizer_sha, template_sha = tokenizer_identity(snapshot)
    identity = {
        "model": MODEL,
        "revision": REVISION,
        "tokenizer_sha256": tokenizer_sha,
        "template_sha256": template_sha,
        "code_sha256": code_identity(code),
        "dependencies_sha256": dependencies_identity(code),
        "profile_sha256": digest(profile.identity()),
        "data_sha256": digest(document),
    }
    (adapter / "identity.json").write_text(json.dumps(identity))
    (adapter / "profile.json").write_text(json.dumps(profile.identity()))
    (adapter / "adapter_model.safetensors").write_bytes(b"fixture-no-model-loading")
    (adapter / "adapter_config.json").write_text(
        json.dumps(
            {
                "peft_type": "LORA",
                "task_type": "CAUSAL_LM",
                "r": profile.rank,
                "lora_alpha": profile.alpha,
                "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
                "base_model_name_or_path": MODEL,
            }
        )
    )
    host = {"snapshot": str(snapshot), "code_root": str(code)}
    return adapter, host, identity


def test_actual_local_identity_matches_without_loading_model(setup):
    adapter, host, expected = setup
    actual, profile = validate_local(adapter, host)
    assert actual == expected
    assert profile.model == MODEL


@pytest.mark.parametrize(
    "field",
    [
        "tokenizer_sha256",
        "template_sha256",
        "profile_sha256",
        "code_sha256",
        "dependencies_sha256",
        "data_sha256",
    ],
)
def test_changed_local_identity_rejects_foreign_artifact(setup, field):
    adapter, host, identity = setup
    identity[field] = "b" * 64
    (adapter / "identity.json").write_text(json.dumps(identity))
    with pytest.raises(ValueError, match="portable_identity"):
        validate_local(adapter, host)


@pytest.mark.parametrize(
    "key,value",
    [
        ("auto_mapping", {"parent_library": "untrusted"}),
        ("modules_to_save", ["arbitrary"]),
        ("target_modules", ["q_proj"]),
        ("r", 64),
        ("base_model_name_or_path", "other/model"),
        ("revision", "b" * 40),
    ],
)
def test_unsafe_or_different_adapter_config_is_rejected(setup, key, value):
    adapter, host, _ = setup
    path = adapter / "adapter_config.json"
    config = json.loads(path.read_text())
    config[key] = value
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="adapter_"):
        validate_local(adapter, host)


def test_symlink_adapter_and_missing_weights_rejected(setup, tmp_path):
    adapter, host, _ = setup
    link = tmp_path / "link"
    link.symlink_to(adapter, target_is_directory=True)
    with pytest.raises(ValueError, match="adapter_path"):
        validate_local(link, host)
    (adapter / "adapter_model.safetensors").unlink()
    with pytest.raises(ValueError, match="weights_missing"):
        validate_local(adapter, host)


def test_remote_pass_cannot_be_reused_as_fresh_local_receipt(setup):
    adapter, _, identity = setup
    expected_hash = file_digest(adapter / "adapter_model.safetensors")
    forged = {
        "status": "PASS",
        "runtime_verified": True,
        "identity_sha256": digest(identity),
        "adapter_sha256": expected_hash,
    }
    with pytest.raises(ValueError, match="fresh_local_reload"):
        _receipt_matches(forged, identity, expected_hash, "local-nonce")
    forged["nonce"] = "local-nonce"
    _receipt_matches(forged, identity, expected_hash, "local-nonce")
    with pytest.raises(ValueError, match="fresh_local_reload"):
        _receipt_matches(forged, identity, "b" * 64, "local-nonce")


@pytest.mark.parametrize("result", ["PASS", "bad-nonce", "exit-failure"])
def test_coordinator_spawns_fresh_process_and_releases_lease(
    setup, tmp_path, monkeypatch, result
):
    import contextlib

    from venom_core.services import runtime_admission
    from venom_core.services.granite_operator import cli
    from venom_core.services.remote_training import verification

    adapter, host, identity = setup
    host_root = tmp_path / "host"
    host_root.mkdir()
    host.update(
        schema_version=1,
        host_id="local-host",
        worker_python="/qualified/python",
        admission_db=str(host_root / "admission.sqlite"),
    )
    (host_root / "host.json").write_text(json.dumps(host))
    calls = []

    class Lease:
        def operation(self, **kwargs):
            return contextlib.nullcontext()

        def release(self):
            calls.append("released")

    class Admission:
        def __init__(self, *args, **kwargs):
            pass

        def acquire(self, **kwargs):
            assert kwargs["owner"] == "granite-training"
            return Lease()

    class Process:
        def __init__(self, argv, **kwargs):
            calls.append(argv)
            request = json.loads(Path(argv[-1]).read_text())
            receipt = {
                "status": "PASS",
                "runtime_verified": True,
                "identity_sha256": digest(identity),
                "adapter_sha256": file_digest(adapter / "adapter_model.safetensors"),
                "nonce": request["nonce"] if result != "bad-nonce" else "remote-nonce",
            }
            Path(request["output"]).write_text(json.dumps(receipt))

        def wait(self, timeout):
            return 23 if result == "exit-failure" else 0

        def poll(self):
            return 0

    monkeypatch.setattr(cli, "require_offline", lambda: None)
    monkeypatch.setattr(runtime_admission, "RuntimeAdmission", Admission)
    monkeypatch.setattr(verification.subprocess, "Popen", Process)
    if result == "PASS":
        receipt = verification.verify_local(adapter, host_root)
        assert receipt["runtime_verified"] is True
        assert "nonce" not in receipt
    else:
        with pytest.raises((RuntimeError, ValueError), match="reload"):
            verification.verify_local(adapter, host_root)
    assert calls[-1] == "released"
    assert calls[0][:5] == ["setpriv", "--pdeathsig", "TERM", "--", "/qualified/python"]
    assert calls[0][-3:-1] == [
        "venom_core.services.remote_training.verification",
        "--worker",
    ]


@pytest.mark.parametrize(
    "fault", [None, "nonfinite", "no-effect", "weights-changed", "wrong-abi"]
)
def test_fresh_worker_measures_reload_without_loading_optimizer_state(
    setup, tmp_path, monkeypatch, fault
):
    import sys
    from types import SimpleNamespace

    from venom_core.services.granite_operator import encoding, engine
    from venom_core.services.remote_training import verification

    adapter, host, identity = setup
    host_root = tmp_path / "host"
    host_root.mkdir()
    host.update(schema_version=1, host_id="local", worker_python=sys.executable)
    (host_root / "host.json").write_text(json.dumps(host))
    result_path = tmp_path / "receipt.json"
    request = {
        "host_root": str(host_root),
        "adapter_root": str(adapter),
        "identity_sha256": digest(identity),
        "adapter_sha256": file_digest(adapter / "adapter_model.safetensors"),
        "nonce": "fresh-local-nonce",
        "output": str(result_path),
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request))

    class Tensor:
        def __init__(self, value):
            self.value = value

        def __sub__(self, other):
            return Tensor(self.value - other.value)

        def abs(self):
            return Tensor(abs(self.value))

        def max(self):
            return self.value

    class Session:
        def __init__(self, *args):
            self.tokenizer = object()
            self.load_seconds = 0.25
            self.torch = SimpleNamespace(
                isfinite=lambda _: SimpleNamespace(all=lambda: fault != "nonfinite"),
                cuda=SimpleNamespace(get_device_name=lambda _: "fixture GPU"),
                __version__="test-version",
                version=SimpleNamespace(cuda="test-cuda"),
            )
            if fault == "weights-changed":
                (adapter / "adapter_model.safetensors").write_bytes(
                    b"changed-after-validation"
                )

        def probe(self, row, disable=False):
            return Tensor(0 if disable or fault == "no-effect" else 0.25)

    monkeypatch.setattr(engine, "require_owner", lambda: None)
    monkeypatch.setattr(engine, "Session", Session)
    monkeypatch.setattr(
        encoding, "encode", lambda *args: {"input_ids": [1, 2], "labels": [-100, 2]}
    )
    monkeypatch.setattr(
        verification.platform,
        "python_version",
        lambda: "3.12.3" if fault == "wrong-abi" else "3.14.8",
    )
    if fault:
        with pytest.raises((RuntimeError, ValueError)):
            verification.worker(request_path)
        assert not result_path.exists()
    else:
        verification.worker(request_path)
        receipt = json.loads(result_path.read_text())
        assert receipt["runtime_verified"] is True
        assert receipt["max_absolute_logit_difference"] == 0.25
        assert receipt["optimizer_resume_verified"] is False
        assert receipt["activation_authorized"] is False
        assert receipt["nonce"] == "fresh-local-nonce"


def test_identity_cannot_hash_another_checkout_than_the_imported_worker(
    setup, tmp_path, monkeypatch
):
    from venom_core.services.remote_training import verification

    adapter, host, _ = setup
    monkeypatch.setattr(
        verification, "native_code_root", lambda: tmp_path / "different-actual-import"
    )
    with pytest.raises(ValueError, match="imported_code_mismatch"):
        validate_local(adapter, host)


def test_local_reload_requires_actual_environment_qualification(
    setup, tmp_path, monkeypatch
):
    from venom_core.services.granite_operator import cli
    from venom_core.services.remote_training import verification

    adapter, host, _ = setup
    host_root = tmp_path / "host"
    host_root.mkdir()
    host.update(schema_version=1, host_id="local")
    (host_root / "host.json").write_text(json.dumps(host))
    monkeypatch.setattr(cli, "require_offline", lambda: None)
    monkeypatch.setattr(verification, "_worker_runtime", lambda _: {"ok": False})
    with pytest.raises(ValueError, match="environment_unqualified"):
        verification.verify_local(adapter, host_root)


def test_changed_data_provenance_fails_before_reload(setup):
    adapter, host, _ = setup
    (adapter / "data-manifest.json").write_text(json.dumps({"license": "changed"}))
    with pytest.raises(ValueError, match="portable_identity"):
        validate_local(adapter, host)


def test_worker_preflight_uses_configured_interpreter(tmp_path, monkeypatch):
    from venom_core.services.remote_training import remote_env, verification

    observed = []

    def probe(code_root, python):
        observed.append((code_root, python))
        return {"ok": True, "python": "3.14.8"}

    monkeypatch.setattr(remote_env, "check_control_environment", probe)
    host = {"code_root": str(tmp_path), "worker_python": "/qualified/model/python"}
    assert verification._worker_runtime(host)["ok"]
    assert observed == [(tmp_path, Path("/qualified/model/python"))]
