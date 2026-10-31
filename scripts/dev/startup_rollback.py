"""Rollback only resources proved to have been started by the failed attempt."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping


def api_owner_token(receipt: Mapping[str, Any]) -> tuple[int, str]:
    pid, stamp = receipt.get("pid"), receipt.get("stamp")
    if (
        type(pid) is not int
        or pid <= 1
        or not isinstance(stamp, str)
        or not stamp.isdecimal()
    ):
        raise ValueError("Invalid original API startup identity")
    return pid, stamp


def rollback_api(
    root: Path, values: Mapping[str, str], receipt: Mapping[str, Any]
) -> None:
    from scripts.dev.stack_profile import stop

    # stop validates both captured files against this original Popen token,
    # binds pidfds to that process and preserves any replacement receipts.
    stop(root, values, ("PID_FILE",), expected={"PID_FILE": api_owner_token(receipt)})


def retire_unrecorded_api(root: Path, receipt: Mapping[str, Any]) -> None:
    """Use the shared pidfd helper if recording a known spawn failed."""
    from scripts.dev.retire_process import retire

    pid, stamp = api_owner_token(receipt)
    retire(pid, stamp, root)


def _preexisting(owner: Any, previous: list[Any]) -> bool:
    for old in previous:
        if old.kind != owner.kind:
            continue
        # A preexisting service may automatically restart while UI launch fails.
        # Its explicit service ownership is preserved, including the new MainPID.
        if old.service and old.service == owner.service:
            return True
        stamp = owner.observed.get("start_ticks")
        if stamp and old.pid == owner.pid and old.observed.get("start_ticks") == stamp:
            return True
    return False


def rollback_new_engines(
    root: Path, values: Mapping[str, str], previous: list[Any]
) -> None:
    from scripts.dev.runtime_teardown import engine_owners, stop_engines

    current = engine_owners(root, values)
    created = [owner for owner in current if not _preexisting(owner, previous)]
    if created:
        stop_engines(created)
        remaining = engine_owners(root, values)
        if any(not _preexisting(owner, previous) for owner in remaining):
            raise ValueError(
                "Failed startup rollback incomplete; new engine owner remains"
            )


def run_start_stack(
    root: Path, values: dict[str, str], previous: list[Any] | None
) -> None:
    try:
        subprocess.run(
            ["bash", str(root / "scripts/dev/start_stack.sh")],
            env={**values, "VENOM_STACK_RESOLVED": "1"},
            check=True,
        )
    except BaseException:
        if previous is not None:
            rollback_new_engines(root, values, previous)
        raise


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Rollback an original API startup attempt"
    )
    parser.add_argument(
        "receipt",
        help="Original spawn pid/start-stamp JSON, never read from a mutable PID file",
    )
    args = parser.parse_args()
    receipt = json.loads(args.receipt)
    root = Path(__file__).resolve().parents[2]
    rollback_api(root, os.environ, receipt)


if __name__ == "__main__":
    main()
