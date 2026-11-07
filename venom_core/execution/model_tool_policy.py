"""Restrict native tool catalogs independently of model proposals."""

from collections.abc import Mapping, Sequence
from typing import Literal, get_args

GEMMA4_E4B_MODEL_ID = "gemma4:e4b"
FileReadToolName = Literal[
    "FileSkill-file_exists", "FileSkill-list_files", "FileSkill-read_file"
]
FUNCTIONGEMMA_READ_TOOLS = frozenset(get_args(FileReadToolName))


def is_functiongemma_model(model_id: str) -> bool:
    return "functiongemma" in model_id.casefold().replace("-", "").replace("_", "")


def functiongemma_read_filters(
    filters: Mapping[str, Sequence[str]] | None,
) -> dict[str, list[str]]:
    restricted = {key: list(value) for key, value in (filters or {}).items()}
    included = restricted.get("included_functions")
    restricted["included_functions"] = sorted(
        FUNCTIONGEMMA_READ_TOOLS
        if included is None
        else FUNCTIONGEMMA_READ_TOOLS.intersection(included)
    )
    return restricted
