"""Store an explicitly supplied stdin credential in private, ignored runtime state."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path


def store_credential(root: Path, destination: Path, credential: str) -> None:
    target = destination.resolve()
    allowed = (root.resolve() / ".venom_runtime").resolve()
    if not target.is_relative_to(allowed) or target == allowed:
        raise ValueError("credential_destination_denied")
    value = credential.strip()
    if not re.fullmatch(r"sk-or-v1-[A-Za-z0-9_-]{16,512}", value):
        raise ValueError("credential_format_invalid")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    fd, name = tempfile.mkstemp(prefix="credential-", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(value)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".venom_runtime/openrouter/credential")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        store_credential(root, root / args.path, sys.stdin.read(4097))
    except (ValueError, OSError):
        print(
            "OpenRouter credential bridge failed; no credential is printed.",
            file=sys.stderr,
        )
        return 1
    print(
        "OpenRouter credential stored with private permissions; provider remains disabled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
