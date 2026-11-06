"""Restrict the FunctionGemma tool surface independently of model proposals."""

from collections.abc import Mapping, Sequence

FUNCTIONGEMMA_READ_TOOLS = frozenset(
    {"FileSkill-file_exists", "FileSkill-list_files", "FileSkill-read_file"}
)


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
