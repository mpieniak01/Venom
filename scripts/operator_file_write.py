"""Review and apply one exact workspace write from a local operator terminal."""

import argparse
import json
import sys
from pathlib import Path

from venom_core.config import SETTINGS
from venom_core.core.permission_guard import permission_guard
from venom_core.core.state_manager import StateManager
from venom_core.execution.operator_file_write import (
    MAX_CONTENT_BYTES,
    OperatorFileWrites,
)


def _read(path: Path, limit: int) -> bytes:
    """Read at most one byte past the configured input limit."""
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file_write_input_too_large")
    return data


def _proposal(path: Path) -> tuple[str, bytes]:
    """Validate the exact path and UTF-8 content carried by a proposal file."""
    value = json.loads(_read(path, MAX_CONTENT_BYTES * 6 + 4096))
    if (
        not isinstance(value, dict)
        or set(value) != {"file_path", "content"}
        or not isinstance(value["file_path"], str)
        or not isinstance(value["content"], str)
    ):
        raise ValueError("file_write_proposal_invalid")
    return value["file_path"], value["content"].encode("utf-8")


def main() -> int:
    """Preview the exact terminal request and commit it only after operator confirmation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--path", required=True, help="Ścieżka w workspace Venoma")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--content-file", type=Path, help="Treść wybrana przez operatora"
    )
    source.add_argument("--empty", action="store_true", help="Jawnie pusty plik")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--proposal", type=Path, help="Opcjonalna propozycja JSON modelu"
    )
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("Zapis wymaga potwierdzenia w lokalnym terminalu.")
    try:
        content = b"" if args.empty else _read(args.content_file, MAX_CONTENT_BYTES)
        proposed_path, proposed_bytes = (
            _proposal(args.proposal) if args.proposal else (args.path, content)
        )
        if (proposed_path, proposed_bytes) != (args.path, content):
            raise ValueError("file_write_approval_mismatch")
        writes = OperatorFileWrites(Path(SETTINGS.WORKSPACE_ROOT))
        approval = writes.prepare(
            args.session, args.path, content, overwrite=args.overwrite
        )
        print(
            json.dumps(
                {
                    "path": args.path,
                    "content": content.decode(),
                    "overwrite": args.overwrite,
                },
                indent=2,
            )
        )
        if input('Aby zatwierdzić, wpisz "zapisz": ') != "zapisz":
            return 1
        permission_guard.set_state_manager(
            StateManager(state_file_path=SETTINGS.STATE_FILE_PATH)
        )
        writes.execute(
            approval,
            args.session,
            proposed_path,
            proposed_bytes,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError, EOFError) as error:
        print(f"Odrzucono zapis: {error}", file=sys.stderr)
        return 1
    print("Plik zapisany.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
