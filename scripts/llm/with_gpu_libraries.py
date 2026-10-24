"""Start a child with CUDA libraries from the selected interpreter's own venv.

No package imports, downloads, global loader changes or other venvs are needed.
This must run before the child starts: changing LD_LIBRARY_PATH after importing
an extension does not repair the dynamic linker's search path.
"""

from __future__ import annotations

import os
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


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: with_gpu_libraries.py COMMAND [ARG ...]")
    environment = dict(os.environ)
    path = library_path(Path(sys.prefix), environment.get("LD_LIBRARY_PATH", ""))
    if path:
        environment["LD_LIBRARY_PATH"] = path
    os.execvpe(sys.argv[1], sys.argv[1:], environment)


if __name__ == "__main__":
    main()
