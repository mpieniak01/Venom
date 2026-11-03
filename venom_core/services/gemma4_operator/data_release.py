"""Freeze CPU material exports without leaking the evaluation reserve to training."""

from __future__ import annotations

from typing import Any

from .material import digest, prepare_material
from .profile import GemmaProfile


def build_release(splits: dict[str, Any], profile: GemmaProfile) -> dict[str, Any]:
    """Bind canonical material to Gemma metadata; remote masks are still required."""
    if not isinstance(splits, dict) or not {"train", "validation"} <= set(splits):
        raise ValueError("gemma_release_train_and_validation_required")
    prepared = prepare_material(splits)
    manifest = prepared["manifest"]
    training_records = {
        name: prepared["records"][name] for name in ("train", "validation")
    }
    reserve = manifest["splits"].get("holdout")
    result = {
        "schema_version": 1,
        "kind": "gemma4_material_release",
        "status": "CPU_PREPARED",
        "model_profile": profile.identity(),
        "source_material_sha256": manifest["source_sha256"],
        "prepared_material_sha256": manifest["prepared_material_sha256"],
        "training_payload": {
            "records": training_records,
            "records_sha256": digest(training_records),
            "splits": {
                name: manifest["splits"][name] for name in ("train", "validation")
            },
        },
        "evaluation_reserve": {
            "present": reserve is not None,
            "records": reserve["records"] if reserve else 0,
            "records_sha256": reserve["records_sha256"] if reserve else None,
            "qualification": "declared_reserve_not_final_benchmark",
            "included_in_training_payload": False,
        },
        "tokenization_status": "pending_remote_qualification",
        "training_ready": False,
        "training_started": False,
        "adapter_activation_authorized": False,
        "remote_requirements": [
            "tokenizer_and_selected_turn_masks",
            "loader_and_native_tool_cycle",
            "baseline_before_training",
            "qualified_gemma_training_worker",
        ],
    }
    result["release_sha256"] = digest(result)
    return result
