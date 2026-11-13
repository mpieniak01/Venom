"""Validate sealed Omni LoRA initialization inputs without loading the base model."""

import json
import re
from pathlib import Path

from scripts.academy.omni_pl_chat_data import sha256
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from scripts.academy.omni_pl_chat_recipe import LANGUAGE_TARGET_MODULES

ADAPTER_CONFIG = "adapter_config.json"
ADAPTER_WEIGHTS = "adapter_model.safetensors"
HANDOFF_FIELDS = {
    "schema_version",
    "adapter_id",
    "model",
    "revision",
    "snapshot_sha256",
    "config_sha256",
    "weights_sha256",
}
_MAX_CONFIG_BYTES = 16 * 1024
_MODEL_ALIASES = {"/inputs/model"}
_OPTIONAL_DEFAULTS = {
    "alora_invocation_tokens": None,
    "alpha_pattern": {},
    "arrow_config": None,
    "auto_mapping": None,
    "corda_config": None,
    "ensure_weight_tying": False,
    "eva_config": None,
    "exclude_modules": None,
    "fan_in_fan_out": False,
    "init_lora_weights": True,
    "kasa_config": None,
    "layer_replication": None,
    "layers_pattern": None,
    "layers_to_transform": None,
    "loftq_config": {},
    "lora_bias": False,
    "lora_ga_config": None,
    "megatron_config": None,
    "megatron_core": "megatron.core",
    "modules_to_save": None,
    "monteclora_config": None,
    "qalora_group_size": 16,
    "rank_pattern": {},
    "target_parameters": None,
    "trainable_token_indices": None,
    "use_bdlora": None,
    "use_dora": False,
    "use_qalora": False,
    "use_rslora": False,
    "velora_config": None,
}
_REQUIRED_CONFIG_FIELDS = {
    "base_model_name_or_path",
    "bias",
    "lora_alpha",
    "lora_dropout",
    "peft_type",
    "r",
    "target_modules",
    "task_type",
}
_LANGUAGE_SELECTOR = re.compile(r"model\\\.language_model\\\.\.\*\\\.\(([a-z0-9_|]+)\)")


def _read_object(path: Path) -> dict:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > _MAX_CONFIG_BYTES
    ):
        raise ValueError("experiment_initial_adapter_file_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("experiment_initial_adapter_config_invalid")
    return value


def read_initial_adapter_handoff(path: Path) -> dict:
    return _read_object(path)


def _check_identity(identity: dict) -> None:
    pin = _read_object(SNAPSHOT_PIN)
    if (
        identity.keys() != HANDOFF_FIELDS
        or type(identity["schema_version"]) is not int
        or identity["schema_version"] != 1
        or not isinstance(identity["adapter_id"], str)
        or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", identity["adapter_id"])
        or identity["model"] != pin["repo"]
        or identity["revision"] != pin["revision"]
        or identity["snapshot_sha256"] != sha256(SNAPSHOT_PIN)
    ):
        raise ValueError("experiment_initial_adapter_identity_invalid")


def _check_config(config: dict, identity: dict, recipe: dict) -> None:
    metadata = {"revision", "peft_version", "inference_mode"}
    if (
        not _REQUIRED_CONFIG_FIELDS <= config.keys()
        or config.keys()
        - (_REQUIRED_CONFIG_FIELDS | _OPTIONAL_DEFAULTS.keys() | metadata)
        or any(
            config[key] != default
            for key, default in _OPTIONAL_DEFAULTS.items()
            if key in config
        )
    ):
        raise ValueError("experiment_initial_adapter_config_unsupported")
    if (
        config["base_model_name_or_path"] not in (*_MODEL_ALIASES, identity["model"])
        or config.get("revision") not in (None, identity["revision"])
        or config["peft_type"] != "LORA"
        or config["task_type"] != "CAUSAL_LM"
        or config["bias"] != "none"
        or type(config["r"]) is not int
        or config["r"] != recipe["rank"]
        or type(config["lora_alpha"]) is not int
        or config["lora_alpha"] != recipe["alpha"]
        or type(config["lora_dropout"]) not in (int, float)
        or config["lora_dropout"] != recipe["dropout"]
    ):
        raise ValueError("experiment_initial_adapter_recipe_mismatch")
    selector = config["target_modules"]
    match = (
        _LANGUAGE_SELECTOR.fullmatch(selector) if isinstance(selector, str) else None
    )
    modules = match[1].split("|") if match else []
    if (
        not modules
        or len(set(modules)) != len(modules)
        or set(modules) - set(LANGUAGE_TARGET_MODULES)
        or set(modules) != set(recipe["target_modules"])
    ):
        raise ValueError("experiment_initial_adapter_modules_mismatch")


def verify_initial_adapter(directory: Path, identity: dict, recipe: dict) -> dict:
    """Verify the pinned base, both sealed files and compatible vanilla LoRA settings."""
    _check_identity(identity)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("experiment_initial_adapter_directory_invalid")
    config_path = directory / ADAPTER_CONFIG
    config = _read_object(config_path)
    weights = directory / ADAPTER_WEIGHTS
    if weights.is_symlink() or not weights.is_file():
        raise ValueError("experiment_initial_adapter_file_invalid")
    if (
        sha256(config_path) != identity["config_sha256"]
        or sha256(weights) != identity["weights_sha256"]
    ):
        raise ValueError("experiment_initial_adapter_changed")
    _check_config(config, identity, recipe)
    return config
