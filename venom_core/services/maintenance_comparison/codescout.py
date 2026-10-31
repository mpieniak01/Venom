"""Pinned OpenHands CodeScout submission contract; no invented semantic fields."""

import ast
from pathlib import Path

SOURCE = "https://github.com/OpenHands/codescout/blob/f25decf9f7edde4fd7f4427e71a05c18aaf27eba/src/tools/localization_finish.py"


def finish_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "localization_finish",
            "description": "Submit the relevant code locations and end the task. Use paths relative to the repository root. Supply class_name for a class/method and function_name for a function/method.",
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string"},
                                "class_name": {"type": ["string", "null"]},
                                "function_name": {"type": ["string", "null"]},
                            },
                            "required": ["file"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["locations"],
                "additionalProperties": False,
            },
        },
    }


def validate_submission(arguments: dict) -> None:
    if set(arguments) != {"locations"} or not isinstance(arguments["locations"], list):
        raise ValueError("codescout_locations_required")
    for location in arguments["locations"]:
        if not isinstance(location, dict) or set(location) - {
            "file",
            "class_name",
            "function_name",
        }:
            raise ValueError("codescout_location_invalid")
        if not isinstance(location.get("file"), str) or not location["file"]:
            raise ValueError("codescout_file_required")
        if any(
            value is not None and not isinstance(value, str)
            for key, value in location.items()
            if key != "file"
        ):
            raise ValueError("codescout_symbol_invalid")


def _safe_source(repo: Path, value) -> Path | None:
    if (
        not isinstance(value, str)
        or Path(value).is_absolute()
        or ".." in Path(value).parts
    ):
        return None
    path = repo / value
    if (
        path.suffix != ".py"
        or not path.is_file()
        or not path.resolve().is_relative_to(repo.resolve())
    ):
        return None
    return path


def _nodes(tree):
    for top in tree.body:
        if isinstance(top, ast.ClassDef):
            yield top.name, None, top
            for method in top.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield top.name, method.name, method
        elif isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield None, top.name, top


def _observed_location(repo: Path, location: dict, outputs: str):
    source = _safe_source(repo, location.get("file"))
    if source is None:
        return None
    try:
        text = source.read_text()
        tree = ast.parse(text)
    except (OSError, UnicodeError, SyntaxError):
        return None
    owner, function = location.get("class_name"), location.get("function_name")
    if function and "." in function:
        prefix, function = function.rsplit(".", 1)
        if owner is not None and owner != prefix:
            return None
        owner = prefix
    for class_name, function_name, node in _nodes(tree):
        if (class_name, function_name) != (owner, function):
            continue
        excerpt = (ast.get_source_segment(text, node) or "").splitlines()[0].strip()
        if len(excerpt) >= 12 and excerpt in outputs:
            return location["file"], function or owner
    return None


def grade_submission(repo: Path, case, run: dict) -> bool:
    locations = run["final"].get("locations", [])
    outputs = "\n".join(
        c["result"].get("stdout", "") for c in run["calls"] if c["name"] == "Terminal"
    )
    if not case.expected_locations:
        return locations == []
    found = {_observed_location(repo, location, outputs) for location in locations}
    return (
        None not in found
        and set(case.expected_locations) <= found
        and len(found) <= len(case.expected_locations) + 1
    )
