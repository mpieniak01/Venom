"""Start a child with CUDA libraries from the selected interpreter's own venv.

No package imports, downloads, global loader changes or other venvs are needed.
This must run before the child starts: changing LD_LIBRARY_PATH after importing
an extension does not repair the dynamic linker's search path.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path


def library_path(prefix: Path, inherited: str = "") -> str:
    directories = sorted(prefix.glob("lib/python*/site-packages/nvidia/*/lib"))
    paths = [str(path.resolve()) for path in directories if path.is_dir()]
    driver = Path("/usr/lib/wsl/lib")
    if driver.is_dir():
        paths.append(str(driver))
    paths.extend(part for part in inherited.split(os.pathsep) if part)
    return os.pathsep.join(dict.fromkeys(paths))


def _shebang_python(entry: Path) -> str | None:
    with entry.open("rb") as stream:
        first = stream.readline(4096).decode("utf-8", errors="replace").strip()
    words = shlex.split(first[2:]) if first.startswith("#!") else []
    if words and Path(words[0]).name == "env":
        words = words[1:]
        if words and words[0] == "-S":
            words = words[1:]
        resolved = shutil.which(words[0]) if words else None
        words = [resolved] if resolved else []
    if (
        words
        and Path(words[0]).name.startswith("python")
        and os.access(words[0], os.X_OK)
    ):
        return str(Path(words[0]).absolute())
    return None


def command_python(command: str, root: Path) -> str:
    """Read the console entry's interpreter without resolving venv Python symlinks."""
    entry = Path(command)
    if not entry.is_absolute():
        found = shutil.which(command) if "/" not in command else str(root / entry)
        if not found:
            raise ValueError("uvicorn_command_not_found")
        entry = Path(found)
    entry = entry.resolve(strict=True)
    interpreter = _shebang_python(entry)
    if interpreter:
        return interpreter
    # Pip may use a /bin/sh trampoline when the venv path contains spaces.
    for name in ("python", "python3"):
        candidate = entry.parent / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.absolute())
    raise ValueError("uvicorn_python_not_found")


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--print-command-python":
        print(command_python(sys.argv[3], Path(sys.argv[2])))
        return
    if len(sys.argv) < 2:
        raise SystemExit("usage: with_gpu_libraries.py COMMAND [ARG ...]")
    environment = dict(os.environ)
    path = library_path(Path(sys.prefix), environment.get("LD_LIBRARY_PATH", ""))
    if path:
        environment["LD_LIBRARY_PATH"] = path
    os.execvpe(sys.argv[1], sys.argv[1:], environment)


if __name__ == "__main__":
    main()
