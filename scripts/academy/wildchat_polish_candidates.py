"""Select Polish user prompts from pinned WildChat Parquet into a local review queue.

The queue contains neither assistant outputs nor source user/IP identifiers. It is
never accepted training data. Run with explicit shard choices and a bounded limit.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
import unicodedata
from pathlib import Path

import requests

SOURCE_REPO = "allenai/WildChat-4.8M"
SOURCE_REVISION = "c827c6df8fcf008219ffaffa4d1dd77491099367"
SHARD_COUNT = 86
OUTPUT_ROOT = (
    Path(__file__).resolve().parents[2] / "test-results/polish-chat-candidates"
).resolve()
_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?48\s*)?(?:\d[\s-]?){9}(?!\d)")
_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)


class RangeReader(io.RawIOBase):
    """Read pinned Parquet footer and selected columns with verified HTTP ranges."""

    def __init__(self, url: str, size: int, session: requests.Session):
        self.url, self.size, self.session = url, size, session
        self.pos = 0
        self.direct: str | None = None

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        next_pos = base + offset
        if not 0 <= next_pos <= self.size:
            raise ValueError("seek outside file")
        self.pos = next_pos
        return self.pos

    def read(self, n: int = -1) -> bytes:
        end = self.size if n < 0 else min(self.pos + n, self.size)
        if end <= self.pos:
            return b""
        start = self.pos
        for retry in range(3):
            with self.session.get(
                self.direct or self.url,
                headers={"Range": f"bytes={start}-{end - 1}"},
                timeout=20,
                stream=True,
            ) as response:
                expected = f"bytes {start}-{end - 1}/{self.size}"
                if (
                    response.status_code == 206
                    and response.headers.get("Content-Range") == expected
                ):
                    payload = response.content
                    if len(payload) == end - start:
                        self.pos = end
                        self.direct = response.url
                        return payload
                self.direct = None
            time.sleep(0.2 * (retry + 1))
        raise OSError(f"range read failed at {start}-{end - 1}")


def source_url(shard: int) -> str:
    if not 0 <= shard < SHARD_COUNT:
        raise ValueError("unknown shard")
    filename = f"train-{shard:05d}-of-{SHARD_COUNT:05d}.parquet"
    return f"https://huggingface.co/datasets/{SOURCE_REPO}/resolve/{SOURCE_REVISION}/data/{filename}"


def user_candidate(row: dict, shard: int, group: int, index: int) -> dict | None:
    """Keep only short, Polish, user-authored turns without obvious identifiers."""
    conversation = row.get("conversation")
    if not isinstance(conversation, list) or not conversation:
        return None
    turns = [message for message in conversation if message.get("role") == "user"]
    if not 1 <= len(turns) <= 5:
        return None
    if any(message.get("language") != "Polish" for message in turns):
        return None
    prompts = [message.get("content") for message in turns]
    if any(
        not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 1200
        for prompt in prompts
    ):
        return None
    text = "\n".join(prompts)
    if len(text) > 2500 or any(
        pattern.search(text) for pattern in (_EMAIL, _PHONE, _LINK)
    ):
        return None
    normalized = "\u241e".join(
        " ".join(unicodedata.normalize("NFKC", value).casefold().split())
        for value in prompts
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return {
        "candidate_id": f"wildchat-{shard:02d}-{group:03d}-{index:05d}",
        "source_repo": SOURCE_REPO,
        "source_revision": SOURCE_REVISION,
        "source_record_id": f"shard={shard};group={group};row={index}",
        "license": "ODC-BY-1.0",
        "user_prompts": prompts,
        "user_turns": len(prompts),
        "normalized_user_sha256": digest,
        "quality_status": "pending_review",
        "training_eligible": False,
    }


def select(shards: list[int], groups_per_shard: int, limit: int, output: Path) -> dict:
    import pyarrow.parquet as pq

    if (
        not shards
        or len(set(shards)) != len(shards)
        or not 1 <= groups_per_shard <= 4
        or not 1 <= limit <= 500
    ):
        raise ValueError("invalid bounded selection")
    for shard in shards:
        source_url(shard)
    output = output.resolve()
    if not output.is_relative_to(OUTPUT_ROOT) or output.suffix != ".jsonl":
        raise ValueError(f"review queue must be a JSONL under {OUTPUT_ROOT}")
    if output.exists():
        raise FileExistsError(output)
    selected: list[dict] = []
    seen: set[str] = set()
    checked = 0
    with requests.Session() as session:
        for shard in shards:
            url = source_url(shard)
            response = session.head(url, allow_redirects=True, timeout=20)
            response.raise_for_status()
            size = int(response.headers["Content-Length"])
            with RangeReader(url, size, session) as reader:
                file = pq.ParquetFile(reader)
                indexes = sorted(
                    {
                        int(
                            (file.metadata.num_row_groups - 1)
                            * i
                            / max(1, groups_per_shard - 1)
                        )
                        for i in range(groups_per_shard)
                    }
                )
                for group in indexes:
                    languages = file.read_row_group(group, columns=["language"])[
                        "language"
                    ].to_pylist()
                    positions = [
                        i
                        for i, language in enumerate(languages)
                        if language == "Polish"
                    ]
                    if not positions:
                        continue
                    columns = [
                        "conversation.list.element.role",
                        "conversation.list.element.language",
                        "conversation.list.element.content",
                    ]
                    rows = (
                        file.read_row_group(group, columns=columns)
                        .take(positions)
                        .to_pylist()
                    )
                    for position, row in zip(positions, rows, strict=True):
                        checked += 1
                        candidate = user_candidate(row, shard, group, position)
                        if (
                            candidate is None
                            or candidate["normalized_user_sha256"] in seen
                        ):
                            continue
                        seen.add(candidate["normalized_user_sha256"])
                        selected.append(candidate)
                        if len(selected) >= limit:
                            break
                    if len(selected) >= limit:
                        break
            if len(selected) >= limit:
                break
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        for row in selected:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "checked_polish_rows": checked,
        "selected_pending_review": len(selected),
        "shards": shards,
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--shards", default="0,40,85", help="Comma-separated indices or all"
    )
    parser.add_argument("--groups-per-shard", type=int, default=3)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    shards = (
        list(range(SHARD_COUNT))
        if args.shards == "all"
        else [int(value) for value in args.shards.split(",")]
    )
    print(
        json.dumps(
            select(shards, args.groups_per_shard, args.limit, args.output),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
