"""Pinned Gemma identity and read-only snapshot qualification, without model imports."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

MODEL = "google/gemma-4-12B-it"
LOADER = "Gemma4UnifiedForConditionalGeneration"
SNAPSHOT_FILES = frozenset(
    {
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "chat_template.jinja",
        "processor_config.json",
    }
)
_SHA = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class GemmaProfile:
    """Explicit offline identity; files are SHA-256 values of checkpoint metadata."""

    model: str
    revision: str
    loader: str
    context: int
    enable_thinking: bool
    files: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.files, Mapping):
            raise ValueError("gemma_profile_files_invalid")
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))
        self.validate()

    @classmethod
    def load(cls, path: Path) -> GemmaProfile:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("gemma_profile_schema_invalid")
        version = data.pop("schema_version", None)
        if type(version) is not int or version != 1:
            raise ValueError("gemma_profile_schema_invalid")
        try:
            return cls(**data)
        except TypeError as exc:
            raise ValueError("gemma_profile_fields_invalid") from exc

    def validate(self) -> None:
        if self.model != MODEL or self.loader != LOADER:
            raise ValueError("gemma_profile_model_invalid")
        if not isinstance(self.revision, str) or not _REVISION.fullmatch(self.revision):
            raise ValueError("gemma_profile_revision_unpinned")
        if type(self.context) is not int or not 1 <= self.context <= 262144:
            raise ValueError("gemma_profile_context_invalid")
        if type(self.enable_thinking) is not bool:
            raise ValueError("gemma_profile_thinking_invalid")
        if set(self.files) != SNAPSHOT_FILES or any(
            not isinstance(value, str) or not _SHA.fullmatch(value)
            for value in self.files.values()
        ):
            raise ValueError("gemma_profile_files_invalid")

    def identity(self) -> dict[str, Any]:
        self.validate()
        return {
            "model": self.model,
            "revision": self.revision,
            "loader": self.loader,
            "context": self.context,
            "enable_thinking": self.enable_thinking,
            "files": dict(self.files),
        }

    def validate_snapshot(self, snapshot: Path) -> dict[str, str]:
        """Verify files in the explicitly selected, resolved snapshot directory.

        The root may be an operator-selected directory alias; its files must be
        materialized, not HF cache links pointing to a shared blob store.
        """
        root = snapshot.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("gemma_snapshot_not_directory")
        verified = {}
        for name, expected in self.files.items():
            path = root / name
            # HF cache snapshots use links; only an explicitly materialized snapshot
            # is accepted for portable qualification instead of silently traversing.
            if path.is_symlink() or not path.is_file():
                raise ValueError("gemma_snapshot_file_invalid:" + name)
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != expected:
                raise ValueError("gemma_snapshot_hash_mismatch:" + name)
            verified[name] = actual
        config = json.loads((root / "config.json").read_text())
        if not isinstance(config, dict) or config.get("architectures") != [self.loader]:
            raise ValueError("gemma_snapshot_loader_mismatch")
        text_config = config.get("text_config")
        limit = (
            text_config.get("max_position_embeddings")
            if isinstance(text_config, dict)
            else None
        )
        if type(limit) is not int or self.context > limit:
            raise ValueError("gemma_snapshot_context_mismatch")
        return verified
