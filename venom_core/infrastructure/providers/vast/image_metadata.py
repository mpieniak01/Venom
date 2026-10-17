"""Allowlisted OCI configuration facts; no arbitrary environment values exported."""

import re

from venom_core.infrastructure.providers.vast.runtime_contracts import version_parts


def runtime_metadata(config: dict, config_digest: str) -> dict:
    env = config.get("config", {}).get("Env") or []
    facts = {}
    if isinstance(env, list):
        for item in env[:1024]:
            if not isinstance(item, str):
                continue
            key, sep, value = item.partition("=")
            if sep and key in {
                "CUDA_VERSION",
                "NVIDIA_REQUIRE_CUDA",
                "NVIDIA_DRIVER_CAPABILITIES",
            }:
                if (
                    len(value) <= 1024
                    and value.isascii()
                    and all(32 <= ord(x) < 127 for x in value)
                ):
                    facts[key] = value
    version = facts.get("CUDA_VERSION", "")
    if version_parts(version) is None:
        version = ""
    requirement = facts.get("NVIDIA_REQUIRE_CUDA", "")
    match = re.fullmatch(r"cuda>=([0-9.]{1,19})", requirement)
    minimum = match[1] if match and version_parts(match[1]) is not None else ""
    capabilities = facts.get("NVIDIA_DRIVER_CAPABILITIES", "")
    if not re.fullmatch(r"[a-z,]{0,128}", capabilities):
        capabilities = ""
    return {
        "source": "registry_config_digest",
        "config_digest": config_digest,
        "cuda": version,
        "min_cuda": minimum,
        "driver_capabilities": capabilities,
        "cuda_requirement": "simple_minimum"
        if minimum
        else "requires_runtime_inspection",
        "qualification": "declaration_only",
    }
