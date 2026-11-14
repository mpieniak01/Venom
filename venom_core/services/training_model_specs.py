"""Read-only, code-backed training contracts for the current model candidates."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from scripts.academy.omni_pl_chat_recipe import DEFAULT_RECIPE, LANGUAGE_TARGET_MODULES
from venom_core.services.gemma4_operator.profile import E4B_MODEL
from venom_core.services.gemma4_operator.profile import MODEL as GEMMA_12B
from venom_core.services.gemma4_operator.profile import (
    PINNED_REVISIONS,
    loader_for_model,
)
from venom_core.services.gemma4_operator.training import (
    GemmaTrainingRecipe,
    dependency_spec,
    resource_recommendations,
    target_modules_for,
)
from venom_core.services.training_experiments.profiles import MODEL as OMNI_MODEL


def model_training_specs() -> list[dict[str, Any]]:
    """Expose implementation defaults and qualification boundaries without loading weights."""
    omni = {
        "model": OMNI_MODEL,
        "path": "academy_omni_experiment",
        "status": "local_gpu_executor_available",
        "loader": "AutoModelForMultimodalLM",
        "revision": "snapshot_manifest_pinned",
        "modality": "text_only_lora_on_multimodal_base",
        "target_modules": list(LANGUAGE_TARGET_MODULES),
        "target_families": list(LANGUAGE_TARGET_MODULES),
        "target_policy": "explicit_profile_selection_language_model_only",
        "legacy_recipe_default": list(DEFAULT_RECIPE["target_modules"]),
        "recipe_defaults": {
            key: DEFAULT_RECIPE[key]
            for key in (
                "rank",
                "alpha",
                "dropout",
                "learning_rate",
                "max_tokens",
                "microbatch",
                "gradient_accumulation_steps",
                "steps",
                "loss_mode",
                "gradient_checkpointing",
            )
        },
        "data_contract": "reviewed_pl_chat_jsonl_selected_assistant_turns",
        "runtime": "local_cuda_bf16_no_cpu_fallback",
        "gpu_memory": "measured_by_preflight_no_fixed_minimum",
        "qualification": "snapshot_data_masks_targets_and_gpu_preflight_per_run",
    }
    gemma: list[dict[str, Any]] = []
    for model in (E4B_MODEL, GEMMA_12B):
        recipe = GemmaTrainingRecipe(model=model, revision=PINNED_REVISIONS[model])
        gemma.append(
            {
                "model": model,
                "path": "remote_gemma4_operator",
                "status": (
                    "trained_candidate_below_acceptance"
                    if model == E4B_MODEL
                    else "remote_gpu_smoke_required"
                ),
                "loader": loader_for_model(model),
                "revision": PINNED_REVISIONS[model],
                "modality": "text_only_lora_or_qlora",
                "target_modules": target_modules_for(model),
                "target_families": ["q_proj", "k_proj", "v_proj", "o_proj"],
                "target_policy": "fixed_text_attention_qkvo",
                "recipe_defaults": {
                    key: asdict(recipe)[key]
                    for key in (
                        "context",
                        "rank",
                        "alpha",
                        "dropout",
                        "learning_rate",
                        "accumulation",
                        "quantization",
                        "gradient_checkpointing",
                        "row_order",
                    )
                },
                "data_contract": "native_tokenized_selected_assistant_turn_masks",
                "runtime": dependency_spec(model),
                "gpu_memory": resource_recommendations(model),
                "qualification": "pinned_snapshot_native_masks_remote_smoke_resume_reload_adapter_effect",
            }
        )
    return [omni, *gemma]
