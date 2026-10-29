"""Server-owned, single-model VAST chat profile. No network on discovery."""

from pathlib import Path
from typing import Any

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import WorkloadProfile
from venom_core.services.vast_environments.cli import ssh_profile
from venom_core.services.vast_environments.recipes import validate_recipe

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / ".venom_runtime/vast/prepared/chat-gemma4-26b-q4-24gb.json"
SSH_PROFILE = ROOT / "secrets/ssh/vast/connection.json"


def profile(settings: Any, duration: int | None = None) -> WorkloadProfile:
    path = Path(getattr(settings, "VAST_CHAT_PROFILE_FILE", "") or DEFAULT_PROFILE)
    try:
        value = WorkloadProfile.model_validate_json(path.read_text(encoding="utf-8"))
        validate_recipe(value)
        if value.mode != "ollama" or not value.model or value.download_gb <= 0:
            raise ValueError
        if len(value.model_digest) != 64 or any(
            c not in "0123456789abcdef" for c in value.model_digest
        ):
            raise ValueError
        if duration is not None:
            value = WorkloadProfile.model_validate(
                {**value.model_dump(), "duration_minutes": duration}
            )
        return value
    except (OSError, ValueError):
        raise VastError("vast.management_profile_invalid") from None


def ssh_paths() -> tuple[Path, Path]:
    value = ssh_profile(SSH_PROFILE)
    identity, known = Path(value["identity_file"]), Path(value["known_hosts"])
    if not identity.is_file() or not Path(str(identity) + ".pub").is_file():
        raise VastError("vast.ssh_identity_missing")
    return identity, known
