#!/usr/bin/env python3
"""Explicitly prepare the public default question bank in an ignored local directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "0a5dbe44bde0ee7eb5b9a3363b8ee7d131af28d5"
SOURCE_PATH = "data/datasets/eval_questions.json"
SOURCE_SHA256 = "5f95e6852947fd57b1db722a0a51492c2bdabd8468331ff8cbfd6c5dc1e3d639"
SOURCE_URL = f"https://raw.githubusercontent.com/mpieniak01/Venom/{SOURCE_REVISION}/{SOURCE_PATH}"
MAX_BYTES = 1024 * 1024


def validate(payload: bytes) -> int:
    """Reject invalid question banks without modifying an existing local file."""
    if len(payload) > MAX_BYTES:
        raise ValueError("question_bank_too_large")
    value = json.loads(payload)
    questions = value.get("questions") if isinstance(value, dict) else None
    if not isinstance(questions, list) or not questions:
        raise ValueError("question_bank_empty_or_invalid")
    for question in questions:
        if not isinstance(question, dict) or type(question.get("id")) is not int:
            raise ValueError("question_bank_invalid_id")
        if (
            not isinstance(question.get("question"), str)
            or not question["question"].strip()
        ):
            raise ValueError("question_bank_invalid_question")
    return len(questions)


def read_local(path: Path) -> bytes:
    """Read at most the declared bank budget, including for operator-owned files."""
    with path.open("rb") as stream:
        return stream.read(MAX_BYTES + 1)


def prepare(root: Path, *, download: bool = False) -> dict:
    """Reuse local data; otherwise restore the pinned public blob, with opt-in HTTP."""
    destination = root / SOURCE_PATH
    if destination.is_symlink():
        raise ValueError("question_bank_destination_symlink")
    if destination.exists():
        count = validate(read_local(destination))
        return {
            "path": str(destination),
            "source": "existing_local",
            "questions": count,
            "created": False,
        }
    try:
        result = subprocess.run(
            ["git", "show", SOURCE_REVISION + ":" + SOURCE_PATH],
            cwd=root,
            capture_output=True,
            check=False,
            timeout=10,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"},
        )
        payload = result.stdout if result.returncode == 0 else None
    except FileNotFoundError:
        payload = None
    source = "pinned_git_history"
    if payload is None:
        if not download:
            raise FileNotFoundError(
                "Pinned question bank unavailable locally; rerun with --download"
            )
        with urlopen(SOURCE_URL, timeout=30) as response:
            payload = response.read(MAX_BYTES + 1)
        source = "pinned_public_download"
    if hashlib.sha256(payload).hexdigest() != SOURCE_SHA256:
        raise ValueError("question_bank_source_checksum_mismatch")
    count = validate(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix="questions-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.is_symlink():
                raise ValueError("question_bank_destination_symlink")
            return {
                "path": str(destination),
                "source": "existing_local",
                "questions": validate(read_local(destination)),
                "created": False,
            }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "path": str(destination),
        "source": source,
        "revision": SOURCE_REVISION,
        "sha256": SOURCE_SHA256,
        "questions": count,
        "created": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Allow GET of the checksum-pinned public source if local Git history is unavailable",
    )
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, download=args.download), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
