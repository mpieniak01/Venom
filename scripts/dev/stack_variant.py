"""Application composition only: variants share each environment's persisted state."""

from pathlib import Path
from typing import Mapping


def apply_variant(
    root: Path, values: dict[str, str], overrides: Mapping[str, str]
) -> None:
    variant = values.get("VENOM_VARIANT", "venom").lower()
    if variant not in {"venom", "studio"}:
        raise ValueError("VENOM_VARIANT must be venom|studio")
    values["VENOM_VARIANT"] = variant
    if variant == "studio":
        values["WEB_DIR"] = str(root / "web-studio")
        values["API_APP"] = "venom_core.studio_main:app"
        values["VENOM_UI_READY_PATH"] = "/chat2"
        values["NEXT_PUBLIC_FEATURE_CHAT2"] = "true"
    elif "VENOM_VARIANT" in overrides:
        values["WEB_DIR"] = str(root / "web-next")
        values["API_APP"] = "venom_core.main:app"
        values["VENOM_UI_READY_PATH"] = "/"
        values["NEXT_PUBLIC_FEATURE_CHAT2"] = "false"
