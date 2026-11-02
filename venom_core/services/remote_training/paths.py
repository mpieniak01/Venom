"""Constrain operator paths before filesystem access or subprocess execution."""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

_PRIVATE = {".ssh", ".aws", ".git", ".codex", "secrets", "credentials"}


def _data_roots() -> tuple[Path, ...]:
    candidates = (
        Path.cwd().absolute(),
        Path.home().absolute(),
        Path(tempfile.gettempdir()).absolute(),
        Path("/srv"),
        Path("/opt"),
        Path("/models"),
        Path("/mnt"),
        Path("/workspace"),
    )
    return tuple(root for root in candidates if len(root.parts) > 1)


def _lexical_path(value: str | Path) -> Path:
    raw = str(value)
    path = Path(raw).expanduser()
    if not raw or any(ord(char) < 32 for char in raw) or ".." in path.parts:
        raise ValueError("remote_training_operator_path_invalid")
    if any(
        part.lower() in _PRIVATE or part.lower().startswith(".env")
        for part in path.parts
    ):
        raise ValueError("remote_training_operator_path_sensitive")
    return path.absolute()


def operator_path(value: str | Path, *, allow_symlinks: bool = False) -> Path:
    """Allow data roots used by local workspaces and provisioned training hosts."""
    path = _lexical_path(value)
    roots = _data_roots()
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError("remote_training_operator_path_outside_roots")
    if not allow_symlinks and any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("remote_training_operator_path_symlink")
    resolved = path.resolve()
    _lexical_path(resolved)
    if not any(resolved.is_relative_to(root.resolve()) for root in roots):
        raise ValueError("remote_training_operator_path_outside_roots")
    return resolved


def python_path(value: str | Path) -> Path:
    """Accept a Python executable in approved environments, never arbitrary commands."""
    path = _lexical_path(value)
    if re.fullmatch(r"python(?:3(?:[.]14(?:[.]8)?)?)?", path.name) is None:
        raise ValueError("remote_training_python_path_invalid")
    resolved = path.resolve()
    runtimes = (
        Path(sys.base_prefix).resolve(),
        Path.home() / ".local/share/venom-python",
        Path.home() / ".local/share/uv/python",
        Path.home() / ".pyenv/versions",
        Path("/opt/hostedtoolcache/Python"),
    )
    if not any(resolved.is_relative_to(root) for root in runtimes if root != Path("/")):
        raise ValueError("remote_training_python_runtime_untrusted")
    if resolved.parent.name != "bin" or not resolved.is_file():
        raise ValueError("remote_training_python_runtime_invalid")
    if re.fullmatch(r"python(?:3(?:[.]14(?:[.]8)?)?)?", resolved.name) is None:
        raise ValueError("remote_training_python_runtime_invalid")
    # Preserve the virtualenv path so CPython finds the matching pyvenv.cfg.
    return path
