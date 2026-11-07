"""Resolve a clear directory listing within the registered FileSkill workspace."""

import re
from collections.abc import Callable
from pathlib import Path

from venom_core.execution.skills.base_skill import SecurityError

LIST_FILES = "FileSkill-list_files"
READ_FILE = "FileSkill-read_file"

_PATH = re.compile(r""""([^"\r\n]+)"|'([^'\r\n]+)'|`([^`\r\n]+)`""")
_EXPLICIT = re.compile(
    r"(?:wypisz|wylistuj|pokaż (?:listę|spis|wykaz|nazwy|pozycje)|"
    r"poproszę listę|daj (?:listę|wykaz)|list|give me the entries|"
    r"show (?:the )?(?:list|entries|names))"
    r"(?: (?:nazwy |pozycji |the names of )?"
    r"(?:plików(?: i podkatalogów)?|files(?: and subdirectories)?))?"
    r"(?: (?:pozycji )?(?:w|z|pod|dla|in|under|of|for)(?: (?:katalogu|folderze|the directory))?)?"
)
_CONTENTS = re.compile(r"(?:pokaż zawartość|show (?:the )?contents of)")
_DEPTH = re.compile(
    r"(?:przy limicie poziomów|limit głębokości|z limitem głębokości|"
    r"with a (?:level|depth) limit of|depth limit) ([0-9]{1,2})"
)
_DEFAULT = re.compile(
    r"(?:przy (?:standardowych ustawieniach funkcji|ustawieniach domyślnych)|"
    r"użyj ustawień domyślnych|using (?:the function's )?standard settings|"
    r"use (?:the )?standard settings)"
)
_RECURSIVE = {
    "rekurencyjnie": True,
    "wejdź do gałęzi podrzędnych": True,
    "uwzględnij podkatalogi": True,
    "z podkatalogami": True,
    "recursively": True,
    "traverse descendant directories": True,
    "include nested directories": True,
    "bez rekurencji": False,
    "bez podkatalogów": False,
    "nie schodź na niższe poziomy": False,
    "pozostań na bieżącym poziomie": False,
    "non-recursively": False,
    "do not traverse to lower levels": False,
    "stay at the current directory level": False,
}


def directory_listing(
    request: str,
    validate_path: Callable[[str], Path],
    proposed_path: str | None = None,
) -> dict[str, str | bool | int] | None:
    """Accept one literal path and only recognized listing clauses."""
    request = request.strip()
    if not request or len(request) > 4096:
        return None
    paths = list(_PATH.finditer(request))
    if len(paths) == 1:
        match = paths[0]
        path = next(value for value in match.groups() if value is not None)
        prefix, suffix = request[: match.start()], request[match.end() :]
    elif not paths and proposed_path:
        pattern = rf"(?<!\S){re.escape(proposed_path)}(?=$|[\s.!?;])"
        matches = list(re.finditer(pattern, request))
        if len(matches) != 1:
            return None
        match = matches[0]
        path, prefix, suffix = (
            proposed_path,
            request[: match.start()],
            request[match.end() :],
        )
    else:
        return None
    if proposed_path is not None and path != proposed_path:
        return None
    if not path.strip() or "\x00" in path:
        return None
    prefix = prefix.strip().casefold()
    explicit = bool(_EXPLICIT.fullmatch(prefix))
    if not explicit and not _CONTENTS.fullmatch(prefix):
        return None
    recursive, depth = None, None
    for clause in re.split(r"[.!?;]+", suffix.casefold()):
        clause = clause.strip()
        if not clause or _DEFAULT.fullmatch(clause):
            continue
        if clause in _RECURSIVE and recursive is None:
            recursive = _RECURSIVE[clause]
            continue
        match_depth = _DEPTH.fullmatch(clause)
        if match_depth and depth is None and 1 <= int(match_depth[1]) <= 20:
            depth = int(match_depth[1])
            continue
        return None
    if not explicit and recursive is None and depth is None:
        return None
    try:
        if not validate_path(path).is_dir():
            return None
    except (OSError, RuntimeError, SecurityError, ValueError):
        return None
    return {
        "directory": path,
        "recursive": False if recursive is None else recursive,
        "max_depth": 3 if depth is None else depth,
    }
