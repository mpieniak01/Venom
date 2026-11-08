"""Application composition only: variants share each environment's persisted state."""

from pathlib import Path
from typing import Mapping


def apply_variant(
    root: Path, values: dict[str, str], overrides: Mapping[str, str]
) -> None:
    configured = "VENOM_VARIANT" in values
    variant = values.get("VENOM_VARIANT", "venom").lower()
    if variant not in {"venom", "studio"}:
        raise ValueError("VENOM_VARIANT must be venom|studio")
    values["VENOM_VARIANT"] = variant
    if values.get("OLLAMA_NUM_PARALLEL", "0").strip() in {"", "0"}:
        values["OLLAMA_NUM_PARALLEL"] = "1"
    if variant == "studio":
        if values.get("OLLAMA_CONTEXT_LENGTH", "0").strip() in {"", "0"}:
            values["OLLAMA_CONTEXT_LENGTH"] = "4096"
        values.setdefault("OLLAMA_MAX_LOADED_MODELS", "1")
        values["WEB_DIR"] = str(root / "web-studio")
        values["API_APP"] = "venom_core.studio_main:app"
        values["VENOM_UI_READY_PATH"] = "/chat2"
        values["NEXT_PUBLIC_FEATURE_CHAT2"] = "true"
    elif configured:
        values["WEB_DIR"] = str(root / "web-next")
        values["API_APP"] = "venom_core.main:app"
        values["VENOM_UI_READY_PATH"] = "/"
        values["NEXT_PUBLIC_FEATURE_CHAT2"] = "false"
