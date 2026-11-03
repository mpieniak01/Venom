"""Pure Gemma SFT recipes and integrity checks; GPU execution stays in its worker."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from venom_core.services.granite_operator.contract import (
    TrainingProfile,
    file_digest,
    inside,
)
from venom_core.services.remote_training.paths import operator_path

from .material import digest
from .profile import MODEL, PINNED_REVISIONS, GemmaProfile, loader_for_model

REVISION = "43c9d014b231474fa7212dbb48a762566c2b255d"
TARGET_MODULES = (
    r"model\.language_model\.layers\.\d+\.self_attn\.(q_proj|k_proj|v_proj|o_proj)"
)
LOCK = "requirements/locks/granite-operator-training-linux-py314.txt"
VERSIONS = {
    "torch": "2.13.0",
    "transformers": "5.17.0",
    "peft": "0.21.2",
    "bitsandbytes": "0.50.2",
}
CHECKPOINT_RECEIPT = "receipt.json"
STAGES = frozenset({"preflight", "smoke", "smoke-resume", "train", "resume", "seal"})


def _validate_numbers(learning_rate: float, dropout: float) -> None:
    if (
        type(learning_rate) not in {int, float}
        or not math.isfinite(learning_rate)
        or not 0 < learning_rate <= 0.001
    ):
        raise ValueError("gemma_training_learning_rate_invalid")
    if (
        type(dropout) not in {int, float}
        or not math.isfinite(dropout)
        or not 0 <= dropout < 1
    ):
        raise ValueError("gemma_training_dropout_invalid")


@dataclass(frozen=True)
class GemmaTrainingRecipe(TrainingProfile):
    """One text-only experiment, with an explicit independent update budget.

    Shared optimizer, sampler and checkpoint code is reused from the native
    trainer. Its historical Granite 125-update result is not a Gemma schedule.
    """

    model: str = MODEL
    revision: str = REVISION
    context: int = 4096
    learning_rate: float = 0.00005
    row_order: str = "family_epoch_v1"

    def validate(self) -> None:
        if (
            self.model not in PINNED_REVISIONS
            or self.revision != PINNED_REVISIONS[self.model]
        ):
            raise ValueError("gemma_training_base_mismatch")
        if self.quantization not in {"bf16", "nf4"}:
            raise ValueError("gemma_training_precision_invalid")
        if self.row_order != "family_epoch_v1":
            raise ValueError("gemma_training_row_order_invalid")
        for name, maximum in (
            ("context", 4096),
            ("rank", 64),
            ("alpha", 256),
            ("accumulation", 32),
            ("seed", 2**31 - 1),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("gemma_training_integer_invalid:" + name)
        _validate_numbers(self.learning_rate, self.dropout)
        if type(self.gradient_checkpointing) is not bool:
            raise ValueError("gemma_training_checkpointing_invalid")

    @classmethod
    def for_profile(
        cls, profile: GemmaProfile, **parameters: Any
    ) -> GemmaTrainingRecipe:
        profile.validate()
        recipe = cls(
            model=profile.model,
            revision=profile.revision,
            context=profile.context,
            **parameters,
        )
        recipe.validate_profile(profile)
        return recipe

    def identity(self) -> dict[str, Any]:
        result = super().identity()
        result.update(
            loader=loader_for_model(self.model),
            target_modules=target_modules_for(self.model),
            modality="text",
        )
        return result

    def validate_profile(self, profile: GemmaProfile) -> None:
        self.validate()
        profile.validate()
        if (
            profile.model != self.model
            or profile.revision != self.revision
            or profile.context != self.context
            or profile.enable_thinking
        ):
            raise ValueError("gemma_training_profile_mismatch")


def target_modules_for(model: str) -> str:
    """Both actual architectures are qualified against this text-only path."""
    loader_for_model(model)
    return TARGET_MODULES


def dependency_spec(model: str = MODEL) -> dict[str, Any]:
    """Reuse a real hash-locked Linux ABI; Gemma GPU support needs live smoke."""
    return {
        "python": "3.14.8",
        "platform": "Linux",
        "machine": "x86_64",
        "lock": LOCK,
        "versions": dict(VERSIONS),
        "loader": loader_for_model(model),
        "trust_remote_code": False,
        "gpu_required": True,
        "cpu_fallback": False,
        "disk_offload": False,
        "install": ["python", "-m", "pip", "install", "--require-hashes", "-r", LOCK],
        "qualification": "remote_smoke_required",
    }


def inspect_dependencies() -> dict[str, Any]:
    """Inspect installed metadata without importing Torch or loading any model."""
    errors = []
    versions = {}
    if platform.python_version() != "3.14.8":
        errors.append("python_version_mismatch")
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        errors.append("platform_mismatch")
    for name, desired in VERSIONS.items():
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append("package_missing:" + name)
            continue
        if versions[name] != desired:
            errors.append("package_version_mismatch:" + name)
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "versions": versions,
        "model_loaded": False,
        "gpu_qualified": False,
    }


def read_json(path: str | Path) -> dict[str, Any]:
    target = operator_path(path)
    if target.suffix != ".json" or not target.is_file():
        raise ValueError("gemma_training_json_required")
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("gemma_training_object_required")
    return value


def verified_checkpoint(path: str | Path, fingerprint: str) -> dict[str, Any]:
    """Verify the complete sealed file set before PEFT or torch reads state."""
    checkpoint = operator_path(path)
    receipt = read_json(checkpoint / CHECKPOINT_RECEIPT)
    files = receipt.get("files")
    if receipt.get("fingerprint") != fingerprint or not isinstance(files, dict):
        raise ValueError("gemma_checkpoint_identity_mismatch")
    mandatory = {
        "adapter_config.json",
        "adapter_model.safetensors",
        "training-state.pt",
    }
    if not mandatory.issubset(files) or CHECKPOINT_RECEIPT in files:
        raise ValueError("gemma_checkpoint_files_missing")
    actual = {p.name for p in checkpoint.iterdir() if p.name != CHECKPOINT_RECEIPT}
    if set(files) != actual:
        raise ValueError("gemma_checkpoint_file_set_changed")
    for name, checksum in files.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("gemma_checkpoint_file_invalid")
        artifact = operator_path(inside(checkpoint, name))
        if not isinstance(checksum, str) or file_digest(artifact) != checksum:
            raise ValueError("gemma_checkpoint_hash_mismatch")
    step = receipt.get("step")
    if type(step) is not int or step < 1:
        raise ValueError("gemma_checkpoint_step_invalid")
    return receipt


def snapshot_weights(snapshot: Path) -> list[Path]:
    """Reject incomplete sharded bases before any GPU allocation or qualification."""
    weights = sorted(snapshot.glob("*.safetensors"))
    if not weights or any(path.is_symlink() or not path.is_file() for path in weights):
        raise ValueError("gemma_training_weights_missing")
    index = snapshot / "model.safetensors.index.json"
    if index.exists():
        document = read_json(index)
        mapping = document.get("weight_map")
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("gemma_training_weights_index_invalid")
        declared = set(mapping.values())
        if any(
            not isinstance(name, str) or Path(name).name != name for name in declared
        ) or declared != {path.name for path in weights}:
            raise ValueError("gemma_training_weights_incomplete")
    elif [path.name for path in weights] != ["model.safetensors"]:
        raise ValueError("gemma_training_weights_index_missing")
    return weights


def execution_identity(
    profile: GemmaProfile,
    recipe: GemmaTrainingRecipe,
    encoded_release: dict[str, Any],
    snapshot: Path,
) -> dict[str, Any]:
    """Bind exact source, metadata, weights, labels and installed dependencies."""
    recipe.validate_profile(profile)
    profile.validate_snapshot(snapshot)
    weights = snapshot_weights(snapshot)
    sources = list(Path(__file__).parent.glob("*.py"))
    common = Path(__file__).parents[1] / "granite_operator"
    sources += [
        common / name
        for name in ("engine.py", "encoding.py", "sampling.py", "contract.py")
    ]
    root = Path(__file__).resolve().parents[3]
    index = snapshot / "model.safetensors.index.json"
    return {
        "schema_version": 1,
        "model_profile": profile.identity(),
        "recipe": recipe.identity(),
        "encoded_release_sha256": encoded_release["encoded_release_sha256"],
        "weights": {p.name: file_digest(p) for p in weights},
        "weights_index": file_digest(index) if index.is_file() else None,
        "generation_config_sha256": (
            file_digest(snapshot / "generation_config.json")
            if (snapshot / "generation_config.json").is_file()
            else None
        ),
        "sources": {str(p.relative_to(root)): file_digest(p) for p in sorted(sources)},
        "dependency_lock": file_digest(root / LOCK),
        "environment": inspect_dependencies(),
    }


def _metrics_file_hash(document: dict) -> str:
    serialized = (
        json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def _combined_checks(first: dict, resumed: dict) -> dict:
    first_checks, resumed_checks = first.get("checks"), resumed.get("checks")
    if not isinstance(first_checks, dict) or not isinstance(resumed_checks, dict):
        raise ValueError("gemma_training_smoke_checks_invalid")
    combined = dict(resumed_checks)
    for name in ("mask", "updated_adapter", "frozen_base"):
        combined[name] = (
            resumed_checks.get(name) is True and first_checks.get(name) is True
        )
    return combined


def _valid_smoke_progress(metrics: dict) -> bool:
    names = ("initial_step", "global_step", "additional_updates")
    if any(type(metrics.get(name)) is not int for name in names):
        return False
    return (
        metrics["initial_step"] >= 0
        and 1 <= metrics["additional_updates"] <= 16
        and metrics["global_step"]
        == metrics["initial_step"] + metrics["additional_updates"]
    )


def _qualified_metrics(receipt: dict, fingerprint: str) -> None:
    metrics = receipt.get("smoke_metrics")
    artifacts = receipt.get("artifacts")
    if (
        not isinstance(metrics, dict)
        or not isinstance(artifacts, dict)
        or not artifacts
    ):
        raise ValueError("gemma_training_smoke_artifacts_required")
    first, resumed = metrics.get("first"), metrics.get("resumed")
    if not isinstance(first, dict) or not isinstance(resumed, dict):
        raise ValueError("gemma_training_smoke_metrics_required")
    if (
        first.get("stage") != "smoke"
        or resumed.get("stage") != "smoke-resume"
        or first.get("fingerprint") != fingerprint
        or resumed.get("fingerprint") != fingerprint
        or first.get("global_step") != resumed.get("initial_step")
        or first.get("initial_step") != 0
    ):
        raise ValueError("gemma_training_smoke_stages_invalid")
    if (
        not _valid_smoke_progress(first)
        or not _valid_smoke_progress(resumed)
        or receipt.get("checks") != _combined_checks(first, resumed)
    ):
        raise ValueError("gemma_training_smoke_checks_inconsistent")
    for observed in (first, resumed):
        if _metrics_file_hash(observed) not in artifacts.values():
            raise ValueError("gemma_training_smoke_metrics_unsealed")
    evidence = first.get("mask_evidence")
    if (
        not isinstance(evidence, dict)
        or evidence != resumed.get("mask_evidence")
        or evidence.get("basis") != "validated_native_token_spans"
        or not isinstance(evidence.get("encoded_release_sha256"), str)
        or re.fullmatch(r"[a-f0-9]{64}", evidence["encoded_release_sha256"]) is None
    ):
        raise ValueError("gemma_training_mask_evidence_missing")


def require_qualification(document: dict[str, Any], fingerprint: str) -> None:
    """A smoke receipt has scoped evidence, never model activation permission."""
    if (
        not isinstance(fingerprint, str)
        or re.fullmatch(r"[a-f0-9]{64}", fingerprint) is None
    ):
        raise ValueError("gemma_training_remote_smoke_required")
    checks = document.get("checks")
    required = {
        "mask",
        "frozen_base",
        "updated_adapter",
        "reload",
        "resume",
        "adapter_effect",
        "context_backward",
    }
    if (
        document.get("kind") != "gemma4_training_qualification"
        or document.get("status") != "PASS"
        or document.get("fingerprint") != fingerprint
        or not isinstance(checks, dict)
        or any(checks.get(name) is not True for name in required)
    ):
        raise ValueError("gemma_training_remote_smoke_required")
    _qualified_metrics(document, fingerprint)


def validate_request(request: dict[str, Any]) -> tuple[str, int]:
    """Stages are atomic; training always receives an explicit additional budget."""
    stage = request.get("stage")
    if (
        type(request.get("schema_version")) is not int
        or request["schema_version"] != 1
        or stage not in STAGES
    ):
        raise ValueError("gemma_training_stage_invalid")
    updates = request.get("updates", 0)
    if type(updates) is not int or not 0 <= updates <= 1000:
        raise ValueError("gemma_training_updates_invalid")
    if stage in {"smoke", "smoke-resume"} and not 1 <= updates <= 16:
        raise ValueError("gemma_training_smoke_budget_invalid")
    if stage in {"train", "resume"} and updates < 1:
        raise ValueError("gemma_training_explicit_budget_required")
    if stage in {"preflight", "seal"} and updates != 0:
        raise ValueError("gemma_training_nontraining_stage_budget")
    resumed = stage in {"smoke-resume", "resume", "seal"}
    if bool(request.get("checkpoint")) != resumed:
        raise ValueError("gemma_training_checkpoint_stage_mismatch")
    return stage, updates


def identity_fingerprint(identity: dict[str, Any], hardware: dict[str, Any]) -> str:
    return digest({"identity": identity, "hardware": hardware})


def qualification(metrics: dict, first: dict, artifacts: dict) -> dict:
    """Merge two independent smoke stages without claiming tool-loop qualification."""
    checks = _combined_checks(first, metrics)
    if first["fingerprint"] != metrics["fingerprint"]:
        raise ValueError("gemma_training_smoke_identity_changed")
    receipt = {
        "kind": "gemma4_training_qualification",
        "status": "PASS",
        "fingerprint": metrics["fingerprint"],
        "checks": checks,
        "artifacts": artifacts,
        "smoke_metrics": {"first": first, "resumed": metrics},
        "checkpoint": metrics["checkpoint"],
        "activation_allowed": False,
        "tool_loop_qualified": False,
    }
    try:
        require_qualification(receipt, metrics["fingerprint"])
    except ValueError:
        receipt["status"] = "FAIL"
    return receipt


def resource_recommendations(model: str = MODEL) -> dict[str, Any]:
    """Recommendations are preparation estimates, never GPU-fit evidence."""
    loader_for_model(model)
    shared = (
        {"gpu_memory_gb": 48, "ram_gb": 64}
        if model == MODEL
        else {"gpu_memory_gb": 32, "ram_gb": 48}
    )
    return {
        "shared_lora_qlora": {
            **shared,
            "disk_gb": 100,
            "qualification": "remote_smoke_required",
        },
        "qlora_candidate": {
            "gpu_memory_gb": 24,
            "ram_gb": 64,
            "disk_gb": 100,
            "qualification": "fit_unproven_remote_smoke_required",
        },
        "full_sft": "not_implemented",
        "budget_basis": "explicit_updates_and_measured_target_tokens",
        "historical_125_updates_transferred": False,
    }


def recipe_from_identity(document: dict[str, Any]) -> GemmaTrainingRecipe:
    """Reject extra identity values rather than silently discarding metadata."""
    from dataclasses import fields

    names = {field.name for field in fields(GemmaTrainingRecipe)}
    recipe = GemmaTrainingRecipe(
        **{name: value for name, value in document.items() if name in names}
    )
    if document != recipe.identity():
        raise ValueError("gemma_training_coordinator_profile_mismatch")
    return recipe


def remote_preflight(
    host: dict,
    input_root: Path,
    identity: dict,
) -> tuple[GemmaTrainingRecipe, dict]:
    """Model-specific hook for the existing remote coordinator; no GPU use."""
    from venom_core.services.remote_training.host import (
        code_identity,
        dependencies_identity,
        tokenizer_identity,
    )

    from .encoding import validate_encoded_release

    source = Path(host["code_root"]).resolve()
    if Path(__file__).resolve().parents[3] != source:
        raise ValueError("remote_training_imported_code_mismatch")
    input_root = operator_path(input_root)
    recipe = recipe_from_identity(read_json(input_root / "profile.json"))
    document = read_json(input_root / "data-manifest.json")
    profile = GemmaProfile(**document["model_profile"])
    recipe.validate_profile(profile)
    validate_encoded_release(document, profile)
    snapshot = operator_path(host["snapshot"])
    if snapshot.name != recipe.revision:
        raise ValueError("gemma_training_snapshot_revision_mismatch")
    profile.validate_snapshot(snapshot)
    snapshot_weights(snapshot)
    tokenizer_sha, template_sha = tokenizer_identity(snapshot)
    actual = {
        "model": recipe.model,
        "revision": recipe.revision,
        "tokenizer_sha256": tokenizer_sha,
        "template_sha256": template_sha,
        "profile_sha256": digest(recipe.identity()),
        "data_sha256": digest(document),
        "code_sha256": code_identity(source, model=recipe.model),
        "dependencies_sha256": dependencies_identity(source, model=recipe.model),
        "encoding_sha256": document["encoded_release_sha256"],
    }
    if any(identity.get(key) != value for key, value in actual.items()):
        raise ValueError("remote_training_identity_mismatch")
    return recipe, document
