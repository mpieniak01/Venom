"""Upload/list/delete dataset-file helpers for Academy routes."""

from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anyio


async def persist_uploaded_file(
    *,
    file: Any,
    file_path: Path,
    max_size_bytes: int,
) -> tuple[int, bytes]:
    """Persist upload stream while enforcing max-size limit."""
    size_bytes = 0
    collected_chunks: list[bytes] = []
    async with await anyio.open_file(file_path, "wb") as out_file:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > max_size_bytes:
                raise ValueError(f"FILE_TOO_LARGE:{size_bytes}")
            await out_file.write(chunk)
            collected_chunks.append(chunk)
    return size_bytes, b"".join(collected_chunks)


def cleanup_uploaded_file(file_path: Path, *, logger: Any) -> None:
    """Delete orphan upload file (best-effort)."""
    if not file_path.exists():
        return
    try:
        file_path.unlink()
    except OSError as cleanup_error:
        logger.warning(
            "Failed to cleanup orphan upload file (error=%s)",
            type(cleanup_error).__name__,
        )


def upload_error(filename: str, message: str) -> tuple[None, Dict[str, str]]:
    """Build upload error tuple."""
    return None, {"name": filename, "error": message}


def validate_upload_filename(
    *,
    file: Any,
    settings: Any,
    check_path_traversal_fn: Any,
    validate_file_extension_fn: Any,
    allowed_extensions: list[str] | None = None,
) -> tuple[Optional[str], Optional[Dict[str, str]]]:
    """Validate filename/path/extension for one upload object."""
    if not hasattr(file, "filename") or not file.filename:
        return None, None
    filename = file.filename
    if not check_path_traversal_fn(filename):
        return None, {"name": filename, "error": "Invalid filename (path traversal)"}
    resolved_allowed_extensions = allowed_extensions or getattr(
        settings,
        "ACADEMY_ALLOWED_DATASET_EXTENSIONS",
        settings.ACADEMY_ALLOWED_EXTENSIONS,
    )
    if not validate_file_extension_fn(
        filename,
        allowed_extensions=resolved_allowed_extensions,
    ):
        return None, {
            "name": filename,
            "error": f"Invalid file extension. Allowed: {resolved_allowed_extensions}",
        }
    return filename, None


async def persist_with_limits(
    *,
    file: Any,
    file_path: Path,
    filename: str,
    settings: Any,
    logger: Any,
    cleanup_uploaded_file_fn: Any,
) -> tuple[Optional[tuple[int, bytes]], Optional[Dict[str, str]]]:
    """Persist upload and map size/save errors to API payload."""
    try:
        max_size_bytes = settings.ACADEMY_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        size_bytes, content_bytes = await persist_uploaded_file(
            file=file,
            file_path=file_path,
            max_size_bytes=max_size_bytes,
        )
        return (size_bytes, content_bytes), None
    except ValueError as exc:
        cleanup_uploaded_file_fn(file_path)
        if str(exc).startswith("FILE_TOO_LARGE:"):
            size_bytes = int(str(exc).split(":", 1)[1])
            return None, {
                "name": filename,
                "error": (
                    f"File too large ({size_bytes} bytes, "
                    f"max {settings.ACADEMY_MAX_UPLOAD_SIZE_MB} MB)"
                ),
            }
        return upload_error(filename, f"Failed to save file: {str(exc)}")
    except Exception as exc:
        cleanup_uploaded_file_fn(file_path)
        logger.error(
            "Failed to persist uploaded file (error=%s)",
            type(exc).__name__,
        )
        return upload_error(filename, f"Failed to save file: {str(exc)}")


def build_upload_info(
    *,
    file_id: str,
    filename: str,
    size_bytes: int,
    content_bytes: bytes,
    tag: str,
    description: str,
    compute_bytes_hash_fn: Any,
    estimate_records_from_content_fn: Any,
    logger: Any,
) -> Dict[str, Any]:
    """Build persisted upload metadata payload."""
    sha256_hash = compute_bytes_hash_fn(content_bytes)
    mime_type, _ = mimetypes.guess_type(filename)
    mime_type = mime_type or "application/octet-stream"
    records_estimate = 0
    try:
        records_estimate = estimate_records_from_content_fn(filename, content_bytes)
    except Exception as exc:
        logger.warning(
            "Failed to estimate records for uploaded file (error=%s)",
            type(exc).__name__,
        )
    return {
        "id": file_id,
        "name": filename,
        "size_bytes": size_bytes,
        "mime": mime_type,
        "created_at": datetime.now().isoformat(),
        "status": "ready",
        "records_estimate": records_estimate,
        "sha256": sha256_hash,
        "tag": tag,
        "description": description,
    }


async def process_uploaded_file(
    *,
    file: Any,
    uploads_dir: Path,
    tag: str,
    description: str,
    settings: Any,
    check_path_traversal_fn: Any,
    validate_file_extension_fn: Any,
    compute_bytes_hash_fn: Any,
    estimate_records_from_content_fn: Any,
    save_upload_metadata_fn: Any,
    cleanup_uploaded_file_fn: Any,
    logger: Any,
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """Process one multipart file item into upload metadata or error."""
    filename, filename_error = validate_upload_filename(
        file=file,
        settings=settings,
        check_path_traversal_fn=check_path_traversal_fn,
        validate_file_extension_fn=validate_file_extension_fn,
        allowed_extensions=getattr(
            settings,
            "ACADEMY_ALLOWED_DATASET_EXTENSIONS",
            settings.ACADEMY_ALLOWED_EXTENSIONS,
        ),
    )
    if filename_error:
        return None, filename_error
    if not filename:
        return None, None

    file_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{filename}"
    file_path = uploads_dir / file_id
    persisted, persist_error = await persist_with_limits(
        file=file,
        file_path=file_path,
        filename=filename,
        settings=settings,
        logger=logger,
        cleanup_uploaded_file_fn=cleanup_uploaded_file_fn,
    )
    if persist_error:
        return None, persist_error
    if not persisted:
        return upload_error(filename, "Failed to persist file")
    size_bytes, content_bytes = persisted

    try:
        upload_info = build_upload_info(
            file_id=file_id,
            filename=filename,
            size_bytes=size_bytes,
            content_bytes=content_bytes,
            tag=tag,
            description=description,
            compute_bytes_hash_fn=compute_bytes_hash_fn,
            estimate_records_from_content_fn=estimate_records_from_content_fn,
            logger=logger,
        )
        save_upload_metadata_fn(upload_info)
        return upload_info, None
    except Exception as exc:
        cleanup_uploaded_file_fn(file_path)
        logger.error(
            "Unexpected error while processing uploaded file (error=%s)",
            type(exc).__name__,
        )
        return None, {"name": filename, "error": f"Unexpected error: {str(exc)}"}


def build_upload_response(
    uploaded_files: List[Dict[str, Any]],
    failed_files: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Build stable upload endpoint response payload."""
    message = f"Uploaded {len(uploaded_files)} file(s) successfully"
    if failed_files:
        message += f", {len(failed_files)} file(s) failed"
    return {
        "success": len(uploaded_files) > 0,
        "uploaded": len(uploaded_files),
        "failed": len(failed_files),
        "files": uploaded_files,
        "errors": failed_files,
        "message": message,
    }


def parse_upload_form(form: Any) -> Tuple[list[Any], str, str]:
    """Normalize multipart fields used by upload endpoint."""
    files = form.getlist("files")
    tag = form.get("tag", "user-upload")
    description = form.get("description", "")
    if not isinstance(tag, str):
        tag = "user-upload"
    if not isinstance(description, str):
        description = ""
    return files, tag, description


def delete_upload_file(
    *,
    file_id: str,
    uploads_dir: Path,
    check_path_traversal_fn: Any,
    delete_upload_metadata_fn: Any,
    logger: Any,
) -> Dict[str, Any]:
    """Delete upload file+metadata with path-validation guard."""
    if not check_path_traversal_fn(file_id):
        raise ValueError(f"Invalid file_id (path traversal): {file_id}")

    file_path = uploads_dir / file_id
    if not file_path.exists():
        raise FileNotFoundError(file_id)

    file_path.unlink()
    delete_upload_metadata_fn(file_id)
    logger.info(f"Deleted upload: {file_id}")
    return {
        "success": True,
        "message": f"Upload deleted: {file_id}",
    }
