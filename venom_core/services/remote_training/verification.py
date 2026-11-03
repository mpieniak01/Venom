"""Fresh local adapter reload; remote receipts never authorize activation or resume."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from venom_core.services.granite_operator.contract import (
    MODEL,
    REVISION,
    TrainingProfile,
    digest,
    file_digest,
)

from .bundles import validate_identity
from .host import (
    code_identity,
    dependencies_identity,
    is_gemma_model,
    load_host,
    tokenizer_identity,
)
from .lifecycle import atomic_json, file_lock
from .paths import operator_path

DATA_MANIFEST = "data-manifest.json"


def _metadata(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    limit = 64 * 1024**2 if name == DATA_MANIFEST else 8 * 1024**2
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("remote_training_local_metadata_invalid:" + name)
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("remote_training_local_metadata_invalid:" + name)
    return value


def native_code_root() -> Path:
    """Bind expected hashes to the actual imported Granite implementation."""
    from venom_core.services.granite_operator import contract

    return Path(contract.__file__).resolve().parents[3]


def execution_backend(model: str):
    """Select only an explicitly supported native loader and its shared lease."""
    if is_gemma_model(model):
        from venom_core.services.gemma4_operator.training_worker import (
            GemmaSession,
            require_owner,
        )

        return GemmaSession, require_owner, "gemma-training"
    if model != MODEL:
        raise ValueError("remote_training_model_unsupported")
    from venom_core.services.granite_operator.engine import Session, require_owner

    return Session, require_owner, "granite-training"


def _validate_gemma_base(adapter_root: Path, snapshot: Path, native, recipe) -> None:
    from venom_core.services.gemma4_operator.training import snapshot_weights

    environment = _metadata(adapter_root, "environment.json")
    recorded = environment.get("identity")
    if not isinstance(recorded, dict):
        raise ValueError("remote_training_native_training_identity_missing")
    actual = {path.name: file_digest(path) for path in snapshot_weights(snapshot)}
    if (
        recorded.get("weights") != actual
        or recorded.get("model_profile") != native.identity()
        or recorded.get("recipe") != recipe.identity()
    ):
        raise ValueError("remote_training_native_training_base_changed")
    index = snapshot / "model.safetensors.index.json"
    if recorded.get("weights_index") != (
        file_digest(index) if index.is_file() else None
    ):
        raise ValueError("remote_training_native_training_base_changed")
    generation = snapshot / "generation_config.json"
    if recorded.get("generation_config_sha256") != (
        file_digest(generation) if generation.is_file() else None
    ):
        raise ValueError("remote_training_native_generation_config_changed")


def _validate_gemma_local(
    adapter_root: Path, host: dict, identity: dict, profile_data: dict
):
    from venom_core.services.gemma4_operator.encoding import validate_encoded_release
    from venom_core.services.gemma4_operator.profile import GemmaProfile
    from venom_core.services.gemma4_operator.training import (
        recipe_from_identity,
        target_modules_for,
    )

    profile = recipe_from_identity(profile_data)
    document = _metadata(adapter_root, DATA_MANIFEST)
    native = GemmaProfile(**document["model_profile"])
    profile.validate_profile(native)
    validate_encoded_release(document, native)
    snapshot = operator_path(host["snapshot"])
    native.validate_snapshot(snapshot)
    _validate_gemma_base(adapter_root, snapshot, native, profile)
    if snapshot.name != profile.revision:
        raise ValueError("remote_training_local_snapshot_mismatch")
    code_root = Path(host["code_root"]).resolve()
    if code_root != native_code_root():
        raise ValueError("remote_training_local_imported_code_mismatch")
    tokenizer_sha, template_sha = tokenizer_identity(snapshot)
    expected = {
        "model": profile.model,
        "revision": profile.revision,
        "profile_sha256": digest(profile.identity()),
        "data_sha256": digest(document),
        "tokenizer_sha256": tokenizer_sha,
        "template_sha256": template_sha,
        "code_sha256": code_identity(code_root, model=profile.model),
        "dependencies_sha256": dependencies_identity(code_root, model=profile.model),
        "encoding_sha256": document["encoded_release_sha256"],
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("remote_training_local_portable_identity_mismatch")
    weights = adapter_root / "adapter_model.safetensors"
    if weights.is_symlink() or not weights.is_file() or weights.stat().st_size == 0:
        raise ValueError("remote_training_local_weights_missing")
    config = _metadata(adapter_root, "adapter_config.json")
    rejected = (
        "auto_mapping",
        "modules_to_save",
        "use_dora",
        "use_rslora",
        "loftq_config",
        "layer_replication",
        "alora_invocation_tokens",
        "target_parameters",
        "trainable_token_indices",
        "layers_to_transform",
        "layers_pattern",
    )
    if (
        config.get("peft_type") != "LORA"
        or config.get("task_type") != "CAUSAL_LM"
        or config.get("r") != profile.rank
        or config.get("lora_alpha") != profile.alpha
        or config.get("target_modules") != target_modules_for(profile.model)
        or config.get("bias") != "none"
        or config.get("lora_dropout") != profile.dropout
        or any(config.get(name) for name in rejected)
    ):
        raise ValueError("remote_training_local_adapter_configuration_mismatch")
    base = config.get("base_model_name_or_path", "")
    if base != profile.model and Path(base).name != profile.revision:
        raise ValueError("remote_training_local_adapter_base_mismatch")
    if config.get("revision") not in {None, profile.revision}:
        raise ValueError("remote_training_local_adapter_revision_mismatch")
    return identity, profile


def validate_local(adapter_root: Path, host: dict) -> tuple[dict, TrainingProfile]:
    """Compare actual local source/tokenizer and a constrained PEFT configuration."""
    if adapter_root.is_symlink() or not adapter_root.is_dir():
        raise ValueError("remote_training_local_adapter_path_invalid")
    identity = validate_identity(_metadata(adapter_root, "identity.json"))
    profile_data = _metadata(adapter_root, "profile.json")
    profile_data.pop("schema_version", None)
    if is_gemma_model(identity["model"]):
        return _validate_gemma_local(adapter_root, host, identity, profile_data)
    profile = TrainingProfile(**profile_data)
    profile.validate()
    if identity["model"] != MODEL or identity["revision"] != REVISION:
        raise ValueError("remote_training_local_base_mismatch")
    snapshot = Path(host["snapshot"])
    if snapshot.name != REVISION:
        raise ValueError("remote_training_local_snapshot_mismatch")
    tokenizer_sha, template_sha = tokenizer_identity(snapshot)
    code_root = Path(host["code_root"]).resolve()
    if code_root != native_code_root():
        raise ValueError("remote_training_local_imported_code_mismatch")
    expected = {
        "profile_sha256": digest(profile.identity()),
        "data_sha256": digest(_metadata(adapter_root, DATA_MANIFEST)),
        "tokenizer_sha256": tokenizer_sha,
        "template_sha256": template_sha,
        "code_sha256": code_identity(code_root),
        "dependencies_sha256": dependencies_identity(code_root),
    }
    if any(identity[key] != value for key, value in expected.items()):
        raise ValueError("remote_training_local_portable_identity_mismatch")
    weights = adapter_root / "adapter_model.safetensors"
    if weights.is_symlink() or not weights.is_file() or weights.stat().st_size == 0:
        raise ValueError("remote_training_local_weights_missing")
    config = _metadata(adapter_root, "adapter_config.json")
    if (
        config.get("peft_type") != "LORA"
        or config.get("task_type") != "CAUSAL_LM"
        or config.get("r") != profile.rank
        or config.get("lora_alpha") != profile.alpha
        or config.get("auto_mapping")
        or config.get("modules_to_save")
        or config.get("use_dora")
        or config.get("use_rslora")
        or config.get("loftq_config")
        or set(config.get("target_modules", []))
        != {"q_proj", "k_proj", "v_proj", "o_proj"}
    ):
        raise ValueError("remote_training_local_adapter_configuration_mismatch")
    base = config.get("base_model_name_or_path", "")
    if base != MODEL and Path(base).name != REVISION:
        raise ValueError("remote_training_local_adapter_base_mismatch")
    if config.get("revision") not in {None, REVISION}:
        raise ValueError("remote_training_local_adapter_revision_mismatch")
    return identity, profile


def _receipt_matches(
    receipt: dict, identity: dict, weights_hash: str, nonce: str
) -> None:
    if (
        receipt.get("status") != "PASS"
        or receipt.get("runtime_verified") is not True
        or receipt.get("identity_sha256") != digest(identity)
        or receipt.get("adapter_sha256") != weights_hash
        or receipt.get("nonce") != nonce
    ):
        raise ValueError("remote_training_fresh_local_reload_required")


def _runtime(code_root: Path) -> dict:
    from .remote_env import runtime_receipt

    return runtime_receipt(code_root)


def _worker_runtime(host: dict) -> dict:
    from .remote_env import check_control_environment

    return check_control_environment(
        Path(host["code_root"]), Path(host["worker_python"])
    )


def verify_local(adapter_root: Path, host_root: Path) -> dict:
    """Hold local GPU admission while a fixed fresh process reads safetensors only."""
    from venom_core.services.granite_operator.cli import require_offline
    from venom_core.services.runtime_admission import RuntimeAdmission

    adapter_root = Path(adapter_root).absolute()
    host_root = Path(host_root).resolve()
    host = load_host(host_root)
    identity, profile = validate_local(adapter_root, host)
    _, _, engine = execution_backend(profile.model)
    require_offline()
    if _worker_runtime(host).get("ok") is not True:
        raise ValueError("remote_training_local_environment_unqualified")
    weights_hash = file_digest(adapter_root / "adapter_model.safetensors")
    nonce = uuid.uuid4().hex
    directory = host_root / "local-verification" / nonce
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    request = {
        "adapter_root": str(adapter_root),
        "host_root": str(host_root),
        "identity_sha256": digest(identity),
        "adapter_sha256": weights_hash,
        "nonce": nonce,
        "output": str(directory / "receipt.json"),
    }
    request_path = directory / "request.json"
    atomic_json(request_path, request)
    process = None
    admission = RuntimeAdmission(Path(host["admission_db"]), enabled=True)
    with file_lock(host_root / "gpu.lock", blocking=False) as gpu_lock:
        lease = admission.acquire(
            owner=engine,
            run_id=nonce,
            engine=engine,
            model=identity["model"],
        )

        def quiescent():
            return process is None or process.poll() is not None

        try:
            with lease.operation(kind="lifecycle", confirm_quiescent=quiescent):
                environment = {
                    **os.environ,
                    "PYTHONPATH": host["code_root"],
                    "VENOM_GRANITE_ADMISSION_DB": host["admission_db"],
                    "VENOM_GRANITE_RUN_ID": nonce,
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "TOKENIZERS_PARALLELISM": "false",
                    "REMOTE_TRAINING_GPU_LOCK_FD": str(gpu_lock),
                }
                with (directory / "reload.log").open("wb") as log:
                    process = subprocess.Popen(
                        [
                            "setpriv",
                            "--pdeathsig",
                            "TERM",
                            "--",
                            host["worker_python"],
                            "-m",
                            "venom_core.services.remote_training.verification",
                            "--worker",
                            str(request_path),
                        ],
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        pass_fds=(gpu_lock,),
                    )
                    try:
                        code = process.wait(timeout=600)
                    except BaseException:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
                        raise
                if code != 0:
                    raise RuntimeError("remote_training_local_reload_failed")
                receipt = _metadata(directory, "receipt.json")
                _receipt_matches(receipt, identity, weights_hash, nonce)
                if (
                    file_digest(adapter_root / "adapter_model.safetensors")
                    != weights_hash
                ):
                    raise ValueError("remote_training_local_weights_changed")
                receipt.pop("nonce")
                return receipt
        finally:
            if quiescent():
                lease.release()


def worker(request_path: Path) -> None:
    """Only the live local coordinator may run a reload; no optimizer state loads."""
    request_path = operator_path(request_path)
    request = json.loads(request_path.read_text())
    host = load_host(operator_path(request["host_root"]))
    adapter_root = operator_path(request["adapter_root"])
    output_path = request_path.parent / "receipt.json"
    if Path(request["output"]).absolute() != output_path:
        raise ValueError("remote_training_local_output_path_mismatch")
    identity, profile = validate_local(adapter_root, host)
    session_type, owner_check, _ = execution_backend(profile.model)
    owner_check()
    if (
        Path(sys.executable).absolute() != Path(host["worker_python"]).absolute()
        or platform.python_version() != "3.14.8"
    ):
        raise ValueError("remote_training_local_qualified_interpreter_mismatch")
    if digest(identity) != request["identity_sha256"]:
        raise ValueError("remote_training_local_identity_changed")
    weights_hash = file_digest(adapter_root / "adapter_model.safetensors")
    if weights_hash != request["adapter_sha256"]:
        raise ValueError("remote_training_local_weights_changed")
    runtime = _runtime(Path(host["code_root"]))
    if runtime.get("ok") is not True:
        raise ValueError("remote_training_local_environment_unqualified")
    session = session_type(profile, Path(host["snapshot"]), adapter_root)
    encoded = _probe_row(adapter_root, profile, session.tokenizer)
    enabled = session.probe(encoded)
    disabled = session.probe(encoded, disable=True)
    torch = session.torch
    if not torch.isfinite(enabled).all() or not torch.isfinite(disabled).all():
        raise RuntimeError("remote_training_local_nonfinite_logits")
    difference = float((enabled - disabled).abs().max())
    if difference <= 1e-7:
        raise RuntimeError("remote_training_local_adapter_no_effect")
    if file_digest(adapter_root / "adapter_model.safetensors") != weights_hash:
        raise ValueError("remote_training_local_weights_changed")
    result = {
        "status": "PASS",
        "runtime_verified": True,
        "identity_sha256": digest(identity),
        "adapter_sha256": weights_hash,
        "nonce": request["nonce"],
        "max_absolute_logit_difference": difference,
        "gpu": torch.cuda.get_device_name(0),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "load_seconds": session.load_seconds,
        "test": "fresh_safetensors_reload_adapter_on_off",
        "environment": runtime,
        "activation_authorized": False,
        "optimizer_resume_verified": False,
        "gpu_required": True,
        "cpu_fallback": False,
    }
    atomic_json(output_path, result)


def _probe_row(adapter_root, profile, tokenizer):
    if is_gemma_model(profile.model):
        from venom_core.services.gemma4_operator.encoding import (
            validate_encoded_release,
        )
        from venom_core.services.gemma4_operator.profile import GemmaProfile

        document = _metadata(adapter_root, DATA_MANIFEST)
        native = GemmaProfile(**document["model_profile"])
        return validate_encoded_release(document, native)["validation"][0]
    row = {
        "tools": [],
        "messages": [
            {"role": "user", "content": "Reply with OK."},
            {"role": "assistant", "content": "OK"},
        ],
    }
    from venom_core.services.granite_operator.encoding import encode

    return encode(row, tokenizer, profile.context)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", required=True, type=operator_path)
    args = parser.parse_args()
    worker(args.worker)


if __name__ == "__main__":
    main()
