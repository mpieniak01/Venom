"""Server-owned, single-model VAST chat profile. No network on discovery."""

from pathlib import Path
from typing import Any

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import WorkloadProfile
from venom_core.services.vast_environments.cli import ssh_profile
from venom_core.services.vast_environments.recipes import validate_recipe
from venom_core.utils.runtime_state import runtime_state_root

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = (
    runtime_state_root(ROOT) / "vast/prepared/chat-gemma4-26b-q4-24gb.json"
)
SSH_PROFILE = ROOT / "secrets/ssh/vast/connection.json"
INVALID_SSH_PROFILE = "vast.invalid_ssh_profile"
TRUSTED_SSH_ROOTS = (Path.home() / ".ssh", ROOT / "secrets/ssh")


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


def _trusted_ssh_files() -> dict[str, Path]:
    """Only enumerated regular files from private SSH stores can be identities."""
    files = {}
    for root in TRUSTED_SSH_ROOTS:
        for candidate in root.rglob("*"):
            if not candidate.is_symlink() and candidate.is_file():
                files[str(candidate)] = candidate
    return files


def ssh_paths() -> tuple[Path, Path]:
    value = ssh_profile(SSH_PROFILE)
    files = _trusted_ssh_files()
    # Profile text is only a lookup key, never a filesystem existence probe.
    identity = files.get(str(Path(value["identity_file"]).expanduser()))
    if identity is None or str(identity) + ".pub" not in files:
        raise VastError(INVALID_SSH_PROFILE)
    known = Path(value["known_hosts"]).expanduser()
    if not any(known.is_relative_to(root) for root in TRUSTED_SSH_ROOTS):
        raise VastError(INVALID_SSH_PROFILE)
    known = known.resolve()
    if not any(known.is_relative_to(root.resolve()) for root in TRUSTED_SSH_ROOTS):
        raise VastError(INVALID_SSH_PROFILE)
    return identity, known
