"""Download exactly the public source revisions used by G01; verify before rename."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

SOURCES = (
    (
        "nvidia/When2Call",
        "0582f7749df63a96fdc3070932e83e72396ace53",
        "train/when2call_train_sft.jsonl",
        "3eb20258557513579995ff55c09fcc33fabf2cd2004dea49dc3a0ba9880e631c",
    ),
    (
        "Team-ACE/ToolACE",
        "6bda777c88d21e5a204703c1ee45597a8fa4f734",
        "data.json",
        "ba12c083fca7e8da48c67ad5b895e495447da7c66e39a2e19742c082e6cb537e",
    ),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    receipts = []
    for repo, revision, name, checksum in SOURCES:
        url = f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{name}"
        target = args.data_root / "raw" / repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        if not target.exists():
            with (
                urllib.request.urlopen(url, timeout=90) as response,
                temporary.open("wb") as stream,
            ):
                while block := response.read(1024 * 1024):
                    stream.write(block)
            if (
                hashlib.file_digest(temporary.open("rb"), "sha256").hexdigest()
                != checksum
            ):
                raise ValueError("download_checksum_mismatch:" + repo)
            temporary.replace(target)
        if hashlib.file_digest(target.open("rb"), "sha256").hexdigest() != checksum:
            raise ValueError("existing_source_checksum_mismatch:" + repo)
        receipts.append(
            {
                "repo": repo,
                "revision": revision,
                "url": url,
                "sha256": checksum,
                "local_path": str(target.resolve()),
                "bytes": target.stat().st_size,
            }
        )
    (args.data_root / "download-manifest.json").write_text(
        json.dumps(receipts, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
