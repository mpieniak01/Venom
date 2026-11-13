"""Validate the bounded Omni text LoRA recipe before allocating a GPU."""

import json
import math
import re
from pathlib import Path
from typing import Any

DEFAULT_RECIPE: dict[str, Any] = {
    "rank": 4,
    "alpha": 8,
    "dropout": 0.0,
    "target_modules": ["q_proj", "v_proj"],
    "loss_mode": "model_default",
    "gradient_checkpointing": False,
    "gpu_allocator_reserve_mib": 1000,
    "gpu_step_min_free_mib": 600,
    "steps": 8,
    "save_every": 2,
    "warmup_steps": 1,
    "learning_rate": 2e-4,
    "max_tokens": 1024,
    "microbatch": 1,
    "gradient_accumulation_steps": 1,
    "seed": 42,
    "lr_scheduler_type": "linear",
}
_INTEGER_LIMITS = {
    "rank": (1, 64),
    "alpha": (1, 256),
    "steps": (1, 10_000),
    "save_every": (1, 10_000),
    "warmup_steps": (0, 10_000),
    "max_tokens": (32, 4096),
    "microbatch": (1, 4),
    "gradient_accumulation_steps": (1, 32),
    "seed": (0, 2**32 - 1),
    "gpu_allocator_reserve_mib": (512, 4096),
    "gpu_step_min_free_mib": (256, 2048),
}
LANGUAGE_TARGET_MODULES = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "in_proj",
    "out_proj",
    "w1",
    "w2",
    "w3",
)
P13_LANGUAGE_SELECTOR = r"model\.language_model\..*\.(q_proj|k_proj|v_proj|o_proj|in_proj|out_proj|w1|w2|w3)"
_OPTIONAL = {"train_sha256", "max_supervised_tokens"}
_MAX_RECIPE_BYTES = 16 * 1024


def validate_target_modules(modules: object) -> list[str]:
    if (
        not isinstance(modules, list)
        or not 1 <= len(modules) <= len(LANGUAGE_TARGET_MODULES)
        or any(item not in LANGUAGE_TARGET_MODULES for item in modules)
        or len(set(modules)) != len(modules)
    ):
        raise ValueError(
            "target_modules must list distinct supported language projections"
        )
    return [module for module in LANGUAGE_TARGET_MODULES if module in modules]


def validate_recipe(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() - (
        DEFAULT_RECIPE.keys() | _OPTIONAL
    ):
        raise ValueError("expected a recipe object with supported fields")
    recipe = {**DEFAULT_RECIPE, **value}
    for key, (lower, upper) in _INTEGER_LIMITS.items():
        item = recipe[key]
        if type(item) is not int or not lower <= item <= upper:
            raise ValueError(f"{key} must be an integer in [{lower}, {upper}]")
    if (
        recipe["save_every"] > recipe["steps"]
        or recipe["warmup_steps"] >= recipe["steps"]
    ):
        raise ValueError("save interval and warmup must fit the optimizer step budget")
    if recipe["gpu_step_min_free_mib"] >= recipe["gpu_allocator_reserve_mib"]:
        raise ValueError("GPU step minimum must be below the allocator reserve")
    for key, lower, upper in (
        ("dropout", 0.0, 0.5),
        ("learning_rate", 1e-7, 0.01),
    ):
        item = recipe[key]
        if (
            type(item) not in (int, float)
            or not lower <= item <= upper
            or not math.isfinite(item)
        ):
            raise ValueError(f"{key} must be a finite number in [{lower}, {upper}]")
        recipe[key] = float(item)
    recipe["target_modules"] = validate_target_modules(recipe["target_modules"])
    if type(recipe["gradient_checkpointing"]) is not bool:
        raise ValueError("gradient_checkpointing must be a boolean")
    if recipe["loss_mode"] not in ("model_default", "supervised_token"):
        raise ValueError("unsupported loss_mode")
    if recipe["lr_scheduler_type"] not in ("linear", "cosine", "constant"):
        raise ValueError("unsupported lr_scheduler_type")
    if "train_sha256" in recipe:
        digest = recipe["train_sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("train_sha256 must be a lowercase SHA-256 digest")
    if "max_supervised_tokens" in recipe:
        tokens = recipe["max_supervised_tokens"]
        if type(tokens) is not int or not 1 <= tokens <= 10**10:
            raise ValueError("max_supervised_tokens must be a positive bounded integer")
    return recipe


def load_recipe(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        data = stream.read(_MAX_RECIPE_BYTES + 1)
    if len(data) > _MAX_RECIPE_BYTES:
        raise ValueError("training recipe exceeds the size limit")
    return validate_recipe(json.loads(data))
