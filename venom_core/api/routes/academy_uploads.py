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


def validate_training_record(record: Dict[str, Any]) -> bool:
    """Validate whether one training record is complete enough for ingestion."""
    if not isinstance(record, dict):
        return False

    instruction = record.get("instruction", "")
    output = record.get("output", "")
    if len(instruction) < 10 or len(output) < 10:
        return False
    return True


def append_training_record_if_valid(curator: Any, record: Dict[str, Any]) -> int:
    """Append record to curator only when it passes validation."""
    if not validate_training_record(record):
        return 0
    curator.examples.append(record)
    return 1


def ingest_jsonl_upload(curator: Any, file_path: Path, *, logger: Any) -> int:
    """Ingest JSONL upload into curator examples."""
    import json

    count = 0
    with open(file_path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                count += append_training_record_if_valid(curator, record)
            except Exception as exc:
                logger.warning("Failed to parse JSONL line: %s", exc)
    return count


def ingest_json_upload(curator: Any, file_path: Path) -> int:
    """Ingest JSON upload into curator examples."""
    import json

    with open(file_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return sum(append_training_record_if_valid(curator, record) for record in data)
    if isinstance(data, dict):
        return append_training_record_if_valid(curator, data)
    return 0


def ingest_text_upload(curator: Any, file_path: Path) -> int:
    """Ingest plain-text/markdown upload into curator examples."""
    count = 0
    with open(file_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    sections = content.split("\n\n")
    for i in range(0, len(sections) - 1, 2):
        instruction = sections[i].strip()
        output = sections[i + 1].strip() if i + 1 < len(sections) else ""
        if not instruction or not output:
            continue
        count += append_training_record_if_valid(
            curator,
            {"instruction": instruction, "input": "", "output": output},
        )
    return count


def ingest_csv_upload(curator: Any, file_path: Path) -> int:
    """Ingest CSV upload into curator examples."""
    import csv

    count = 0
    with open(file_path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            record = {
                "instruction": row.get("instruction", row.get("prompt", "")),
                "input": row.get("input", ""),
                "output": row.get("output", row.get("response", "")),
            }
            count += append_training_record_if_valid(curator, record)
    return count


def ingest_upload_file(curator: Any, file_path: Path, *, logger: Any) -> int:
    """Ingest one upload file according to extension."""
    ext = file_path.suffix.lower()
    try:
        if ext == ".jsonl":
            return ingest_jsonl_upload(curator, file_path, logger=logger)
        if ext == ".json":
            return ingest_json_upload(curator, file_path)
        if ext in {".md", ".txt"}:
            return ingest_text_upload(curator, file_path)
        if ext == ".csv":
            return ingest_csv_upload(curator, file_path)
        return 0
    except Exception as exc:
        logger.error("Failed to ingest file %s: %s", file_path, exc)
        raise


def ingest_uploads_for_ids(
    *,
    curator: Any,
    upload_ids: List[str],
    uploads_dir: Path,
    check_path_traversal_fn: Any,
    ingest_upload_file_fn: Any,
    logger: Any,
) -> int:
    """Ingest uploaded files selected by ids."""
    uploads_count = 0
    for upload_idx, file_id in enumerate(upload_ids, start=1):
        if not check_path_traversal_fn(file_id):
            logger.warning(
                "Skipped upload entry due to invalid identifier (idx=%s)",
                upload_idx,
            )
            continue

        file_path = uploads_dir / file_id
        if not file_path.exists():
            logger.warning(
                "Skipped upload entry because file was not found (idx=%s)",
                upload_idx,
            )
            continue

        try:
            uploads_count += ingest_upload_file_fn(curator, file_path)
        except Exception as exc:
            logger.warning(
                "Failed to ingest upload entry (idx=%s, error=%s)",
                upload_idx,
                type(exc).__name__,
            )
    return uploads_count


def ingest_converted_files_for_ids(
    *,
    curator: Any,
    conversion_file_ids: List[str],
    check_path_traversal_fn: Any,
    resolve_existing_user_file_fn: Any,
    ingest_upload_file_fn: Any,
    logger: Any,
) -> int:
    """Ingest converted files selected by ids."""
    converted_count = 0
    for file_idx, file_id in enumerate(conversion_file_ids, start=1):
        if not check_path_traversal_fn(file_id):
            logger.warning(
                "Skipped converted file due to invalid identifier (idx=%s)",
                file_idx,
            )
            continue
        try:
            item, file_path = resolve_existing_user_file_fn(file_id=file_id)
            if str(item.get("category") or "") != "converted":
                logger.warning(
                    "Skipped conversion file because category is not converted (idx=%s)",
                    file_idx,
                )
                continue
            converted_count += ingest_upload_file_fn(curator, file_path)
        except Exception as exc:
            logger.warning(
                "Failed to ingest converted file (idx=%s, error=%s)",
                file_idx,
                type(exc).__name__,
            )
    return converted_count


def ingest_uploads_for_preview(
    *,
    curator: Any,
    upload_ids: List[str],
    warnings: List[str],
    uploads_dir: Path,
    check_path_traversal_fn: Any,
    ingest_upload_file_fn: Any,
) -> int:
    """Ingest selected uploaded files for preview and collect warnings."""
    uploads_count = 0
    for file_id in upload_ids:
        if not check_path_traversal_fn(file_id):
            warnings.append(f"Invalid file_id (path traversal): {file_id}")
            continue
        file_path = uploads_dir / file_id
        if not file_path.exists():
            warnings.append(f"Upload not found: {file_id}")
            continue
        try:
            uploads_count += ingest_upload_file_fn(curator, file_path)
        except Exception as exc:
            warnings.append(f"Failed to ingest {file_id}: {str(exc)}")
    return uploads_count


def _exception_detail(exc: Exception) -> str | None:
    detail = getattr(exc, "detail", None)
    if detail is None:
        return None
    return str(detail)


def ingest_converted_files_for_preview(
    *,
    curator: Any,
    conversion_file_ids: List[str],
    warnings: List[str],
    check_path_traversal_fn: Any,
    resolve_existing_user_file_fn: Any,
    ingest_upload_file_fn: Any,
) -> int:
    """Ingest selected converted files for preview and collect warnings."""
    converted_count = 0
    for file_id in conversion_file_ids:
        if not check_path_traversal_fn(file_id):
            warnings.append(f"Invalid converted file_id (path traversal): {file_id}")
            continue
        try:
            item, file_path = resolve_existing_user_file_fn(file_id=file_id)
            if str(item.get("category") or "") != "converted":
                warnings.append(f"File is not converted: {file_id}")
                continue
            converted_count += ingest_upload_file_fn(curator, file_path)
        except Exception as exc:
            detail = _exception_detail(exc)
            if detail:
                warnings.append(f"Converted file unavailable ({file_id}): {detail}")
            else:
                warnings.append(
                    f"Failed to ingest converted file {file_id}: {str(exc)}"
                )
    return converted_count


def add_low_examples_warning(
    *,
    warnings: List[str],
    total_examples: int,
    quality_profile: str,
) -> None:
    """Append warning for low number of examples based on quality profile."""
    recommended_min_examples = {
        "strict": 150,
        "balanced": 100,
        "lenient": 50,
    }.get(quality_profile, 100)
    if total_examples >= recommended_min_examples:
        return
    warnings.append(
        f"Low number of examples ({total_examples}). Recommended for profile "
        f"'{quality_profile}': >= {recommended_min_examples}"
    )


def build_preview_samples(curator: Any, *, limit: int = 5) -> List[Dict[str, str]]:
    """Build compact sample payload from first examples in curator."""
    samples: List[Dict[str, str]] = []
    examples = getattr(curator, "examples", None)
    if not examples:
        return samples
    for example in examples[:limit]:
        output = str(example.get("output", ""))
        samples.append(
            {
                "instruction": str(example.get("instruction", "")),
                "input": str(example.get("input", "")),
                "output": output[:200] + ("..." if len(output) > 200 else ""),
            }
        )
    return samples
