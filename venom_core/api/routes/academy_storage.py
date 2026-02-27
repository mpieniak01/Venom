"""Storage/hash/path helpers for Academy routes."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Platform-specific file locking
fcntl: Any = None
msvcrt: Any = None
HAS_FCNTL = False
HAS_MSVCRT = False
try:
    import fcntl as _fcntl

    fcntl = _fcntl
    HAS_FCNTL = True
except ImportError:
    try:
        import msvcrt as _msvcrt

        msvcrt = _msvcrt
        HAS_MSVCRT = True
    except ImportError:
        HAS_MSVCRT = False


def is_path_within_base(path: Path, base: Path) -> bool:
    """Return True when `path` is located under `base` (after resolve)."""
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def get_uploads_dir() -> Path:
    """Return uploads directory under ACADEMY_TRAINING_DIR."""
    from venom_core.config import SETTINGS

    uploads_dir = Path(SETTINGS.ACADEMY_TRAINING_DIR) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir


def get_uploads_metadata_file() -> Path:
    """Return uploads metadata file path."""
    return get_uploads_dir() / "metadata.jsonl"


def validate_file_extension(
    filename: str,
    *,
    allowed_extensions: list[str] | None = None,
) -> bool:
    """Validate file extension against allowed list."""
    from venom_core.config import SETTINGS

    ext = Path(filename).suffix.lower()
    resolved_allowed_extensions = allowed_extensions
    if resolved_allowed_extensions is None:
        resolved_allowed_extensions = getattr(
            SETTINGS,
            "ACADEMY_ALLOWED_DATASET_EXTENSIONS",
            SETTINGS.ACADEMY_ALLOWED_EXTENSIONS,
        )
    return ext in resolved_allowed_extensions


def validate_file_size(size_bytes: int) -> bool:
    """Validate file size against configured Academy max upload size."""
    from venom_core.config import SETTINGS

    max_bytes = SETTINGS.ACADEMY_MAX_UPLOAD_SIZE_MB * 1024 * 1024
    return size_bytes <= max_bytes


def check_path_traversal(filename: str) -> bool:
    """Validate filename does not contain traversal markers."""
    return ".." not in filename and "/" not in filename and "\\" not in filename


def is_safe_file_id(filename: str) -> bool:
    """Validate identifier can be safely used to build local file paths."""
    if not check_path_traversal(filename):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{1,255}", filename))


@contextmanager
def file_lock(file_path: Path, mode: str = "r"):
    """Context manager for atomic file access with cross-platform locking."""
    with open(file_path, mode, encoding="utf-8") as handle:
        locked = False
        try:
            if HAS_FCNTL:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                locked = True
            elif HAS_MSVCRT and msvcrt is not None:
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                locked = True
            yield handle
        finally:
            if locked:
                if HAS_FCNTL:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                elif HAS_MSVCRT and msvcrt is not None:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def get_uploads_metadata_lock_file() -> Path:
    """Return lock file path used for uploads metadata operations."""
    return get_uploads_metadata_file().with_suffix(".lock")


@contextmanager
def uploads_metadata_lock():
    """Global lock for read/write/delete operations on uploads metadata."""
    lock_file = get_uploads_metadata_lock_file()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.touch(exist_ok=True)
    with file_lock(lock_file, "a"):
        yield


def load_uploads_metadata() -> List[Dict[str, Any]]:
    """Load uploads metadata from JSONL file."""
    metadata_file = get_uploads_metadata_file()
    uploads: List[Dict[str, Any]] = []
    try:
        with uploads_metadata_lock():
            if not metadata_file.exists():
                return []
            with open(metadata_file, "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        uploads.append(json.loads(line))
    except Exception as exc:
        logger.warning(f"Failed to load uploads metadata: {exc}")
    return uploads


def save_upload_metadata(upload_info: Dict[str, Any]) -> None:
    """Append upload metadata to JSONL file with locking."""
    metadata_file = get_uploads_metadata_file()
    try:
        with uploads_metadata_lock():
            metadata_file.touch(exist_ok=True)
            with open(metadata_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(upload_info, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to save upload metadata: %s", exc, exc_info=True)
        raise


def delete_upload_metadata(file_id: str) -> None:
    """Delete upload metadata entry via atomic read-modify-write."""
    metadata_file = get_uploads_metadata_file()
    temp_file = metadata_file.with_suffix(".tmp")
    try:
        with uploads_metadata_lock():
            if not metadata_file.exists():
                return

            uploads = []
            with open(metadata_file, "r", encoding="utf-8") as in_handle:
                for line in in_handle:
                    if line.strip():
                        upload = json.loads(line)
                        if upload.get("id") != file_id:
                            uploads.append(upload)

            with open(temp_file, "w", encoding="utf-8") as out_handle:
                for upload in uploads:
                    out_handle.write(json.dumps(upload, ensure_ascii=False) + "\n")

            temp_file.replace(metadata_file)

    except Exception as exc:
        logger.error(f"Failed to delete upload metadata: {exc}")
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to remove temporary metadata file {temp_file}: "
                    f"{cleanup_error}"
                )


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 file hash."""
    import hashlib

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_bytes_hash(content: bytes) -> str:
    """Compute SHA256 hash for in-memory bytes."""
    import hashlib

    return hashlib.sha256(content).hexdigest()


def estimate_records_from_content(filename: str, content: bytes) -> int:
    """Estimate record count from file content stored in memory."""
    filename_lc = filename.lower()

    if filename_lc.endswith(".jsonl"):
        text = content.decode("utf-8", errors="ignore")
        return sum(1 for line in text.splitlines() if line.strip())

    if filename_lc.endswith(".json"):
        text = content.decode("utf-8", errors="ignore")
        data = json.loads(text)
        if isinstance(data, list):
            return len(data)
        return 1

    if filename_lc.endswith((".md", ".txt", ".csv")):
        text = content.decode("utf-8", errors="ignore")
        return max(1, len(text.split("\n\n")))

    return 0
