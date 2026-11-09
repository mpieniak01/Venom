"""Restrict native tool catalogs independently of model proposals."""

from collections.abc import Mapping, Sequence
from typing import Literal, get_args

GEMMA4_E4B_MODEL_ID = "gemma4:e4b"
LFM3_READ_MODEL_ID = "lfm3:1.7b"
FileReadToolName = Literal[
    "FileSkill-file_exists", "FileSkill-list_files", "FileSkill-read_file"
]
FILE_READ_TOOLS = frozenset(get_args(FileReadToolName))


def is_functiongemma_model(model_id: str) -> bool:
    """Recognize FunctionGemma tags and aliases that retain the family name."""
    return "functiongemma" in model_id.casefold().replace("-", "").replace("_", "")


def is_read_only_tool_model(model_id: str) -> bool:
    return model_id == LFM3_READ_MODEL_ID or is_functiongemma_model(model_id)


def file_read_filters(
    filters: Mapping[str, Sequence[str]] | None,
) -> dict[str, list[str]]:
    """Intersect caller filters with the supported file read tools."""
    restricted = {key: list(value) for key, value in (filters or {}).items()}
    included = restricted.get("included_functions")
    restricted["included_functions"] = sorted(
        FILE_READ_TOOLS if included is None else FILE_READ_TOOLS.intersection(included)
    )
    return restricted
