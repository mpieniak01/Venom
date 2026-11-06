"""Bridge the historical 192 retention fixtures to the six-action prototype."""

from __future__ import annotations

import json
import re
from copy import deepcopy

from .cases import ACTIONS, CONTEXT, LABELS, action_text, set_context
from .score import active_selection, previous_reads, safe_path

QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')
DEPTH = re.compile(
    r"(?:głębokości wynosi|limicie poziomów|depth parameter is|level limit of) (\d+)"
)
RECURSIVE = {
    "uwzględnij zagnieżdżone foldery",
    "wejdź do gałęzi podrzędnych",
    "include nested folders",
    "traverse descendant directories",
}
NON_RECURSIVE = {
    "pomiń zawartość folderów zagnieżdżonych",
    "nie schodź na niższe poziomy",
    "skip the contents of nested folders",
    "do not traverse to lower levels",
}


def binding_from_request(record, files):
    """Extract the archived fixture's explicit inputs without consulting its expected action."""
    prompt = record["messages"][-2]["content"]
    words = prompt.casefold()
    values = [json.loads(token) for token in QUOTED.findall(prompt)]
    paths = [value for value in values if "/" in value and safe_path(value)]
    contents = [value for value in values if value not in paths]
    if len(paths) == 2 and (
        "pomiń" in words or "leave " in words and " alone" in words
    ):
        paths = paths[:1]
    body = contents[0] if len(contents) == 1 else None
    if body is None and ("zero-byte" in words or "bez bajtów" in words):
        body = ""
    active = None
    active_requested = re.search(r"\bACTIVE\b", prompt) is not None
    if active_requested:
        for path, content in previous_reads(record):
            if files.get(path) == content:
                active = active_selection(content)
                break
    depth = DEPTH.search(words)
    recursive = None
    if any(value in words for value in RECURSIVE):
        recursive = True
    if any(value in words for value in NON_RECURSIVE):
        recursive = False
    return {
        "paths": paths,
        "body": body,
        "active": active,
        "active_requested": active_requested,
        "recursive": recursive,
        "max_depth": int(depth[1]) if depth else None,
    }


def adapt(case, narrow_system):
    updated = deepcopy(case)
    record, oracle = updated["record"], updated["oracle"]
    context = binding_from_request(record, oracle["fixture"]["files"])
    system = set_context(narrow_system, context)
    record["messages"][0]["content"] += CONTEXT + system.split(CONTEXT, 1)[1]
    family = oracle["family"]
    expected = oracle["expected_calls"]
    if expected:
        action = next(
            key for key, name in ACTIONS.items() if name == expected[0]["name"]
        )
        result = "call"
    else:
        action = LABELS.get(family, family if family in ACTIONS else "approval")
        result = {
            "missing_content": "missing_body",
            "withdrawn_content": "missing_body",
            "missing_destination": "missing_path",
            "safety": "untrusted_instruction",
        }.get(family, action)
    oracle["expected_action"], oracle["expected_result"] = action, result
    if family != "preview":
        oracle["reference_text"] = None
    record["messages"][-1] = {"role": "assistant", "content": action_text(action)}
    return updated
