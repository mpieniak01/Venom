"""Linux PID-identity retirement used by the shared Node UI lifecycle."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def retire(pid: int, ticks: str, root: Path) -> None:
    from scripts.dev.qualification_process import identity
    from scripts.dev.runtime_teardown import EngineOwner, stop_engines

    if pid <= 1 or not ticks or not ticks.isdecimal():
        raise ValueError("Missing verified process identity")
    try:
        observed = identity(pid)
    except (ProcessLookupError, FileNotFoundError):
        return
    if observed["start_ticks"] != ticks or observed["cwd"] != str(root.resolve()):
        raise ValueError("Process identity differs; no signal sent")
    if Path(f"/proc/{pid}").stat().st_uid != os.getuid():
        raise ValueError("Process belongs to another OS user")
    stop_engines([EngineOwner("application", pid, observed)])


if __name__ == "__main__":
    retire(int(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
