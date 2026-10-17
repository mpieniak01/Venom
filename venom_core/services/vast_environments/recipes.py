"""Reviewed runtime recipes, independent of public template executable payloads."""

import os
from pathlib import Path

from venom_core.infrastructure.providers.vast.client import VastClient, VastError
from venom_core.infrastructure.providers.vast.models import WorkloadProfile, amount
from venom_core.services.vast_environments.startup import startup

RECIPES = {
    "inspect": {
        "purpose": "host_inspection",
        "requires": ["python3", "nvidia-smi"],
        "port": None,
    },
    "ollama": {
        "purpose": "llm_multimodal_tools",
        "requires": ["ollama", "curl"],
        "port": 11434,
    },
    "vllm": {
        "purpose": "openai_compatible_inference",
        "requires": ["vllm", "torch", "curl"],
        "port": 8000,
    },
    "pytorch": {
        "purpose": "vision_audio_worker",
        "requires": ["torch", "transformers"],
        "port": None,
    },
}


def validate_recipe(profile: WorkloadProfile) -> None:
    if bool(profile.template_hash) != bool(profile.template_configuration_sha256):
        raise VastError("vast.template_provenance_required")
    if profile.worker_packages and (
        profile.mode != "pytorch" or profile.download_gb <= 0
    ):
        raise VastError("vast.worker_install_download_budget_required")
    if profile.mode in {"ollama", "vllm"} and (
        not profile.model or not profile.model_digest
    ):
        raise VastError("vast.model_digest_required")
    if profile.mode == "vllm" and (
        len(profile.model_digest) != 40
        or any(char not in "0123456789abcdef" for char in profile.model_digest)
    ):
        raise VastError("vast.huggingface_revision_required")


def selected_template(client: VastClient, template_hash: str) -> dict:
    matches = [
        row
        for row in client.templates(template_hash)
        if row.get("hash_id") == template_hash
    ]
    if len(matches) != 1:
        raise VastError("vast.template_missing")
    return matches[0]


def repository(image: str) -> str:
    name = image.split("@", 1)[0].removeprefix("docker.io/")
    separator = name.rfind(":")
    return name[:separator] if separator > name.rfind("/") else name


def verify_template(client: VastClient, profile: WorkloadProfile) -> None:
    validate_recipe(profile)
    if not profile.template_hash:
        return
    row = selected_template(client, profile.template_hash)
    if row.get("configuration_sha256") != profile.template_configuration_sha256:
        raise VastError("vast.template_changed")
    if row.get("use_ssh") is not True or repository(
        str(row.get("image", ""))
    ) != repository(profile.image):
        raise VastError("vast.template_image_or_ssh_mismatch")
    disk = amount(row.get("recommended_disk_space"))
    if disk is None:
        raise VastError("vast.template_disk_unknown")
    constraints = row.get("runtime_constraints", {"constraints": {}, "unresolved": []})
    if (
        profile.runtime.template_constraints != constraints["constraints"]
        or profile.runtime.unresolved_constraints != constraints["unresolved"]
    ):
        raise VastError("vast.template_constraints_changed")
    if profile.disk_gb < disk:
        raise VastError("vast.template_disk_insufficient")


def prepare(
    client: VastClient,
    profile: WorkloadProfile,
    mode: str,
    template_hash: str | None,
    output: Path,
) -> dict:
    values = {**profile.model_dump(), "mode": mode}
    if template_hash:
        row = selected_template(client, template_hash)
        constraints = row.get(
            "runtime_constraints", {"constraints": {}, "unresolved": []}
        )
        values["runtime"] = {
            **profile.runtime.model_dump(),
            "template_constraints": constraints["constraints"],
            "unresolved_constraints": constraints["unresolved"],
        }
        values.update(
            template_hash=template_hash,
            template_configuration_sha256=row["configuration_sha256"],
        )
    result = WorkloadProfile.model_validate(values)
    verify_template(client, result)
    # The profile is local configuration. Never overwrite an existing operator profile.
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(result.model_dump_json(indent=2) + "\n")
    return {
        "profile_path": str(output),
        "profile": result.model_dump(mode="json"),
        "startup": startup(result),
        "recipe": RECIPES[result.mode],
        "template_policy": "reviewed_constraints; environment/startup/args_replaced",
        "readiness": "not_tested",
        "paid_resources_created": False,
    }
