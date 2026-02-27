"""Conversion and user-workspace helpers for Academy routes."""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, TextIO

import anyio

from venom_core.api.routes import academy_storage
from venom_core.api.schemas.academy import DatasetConversionFileInfo
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

EXT_JSON = ".json"
EXT_JSONL = ".jsonl"
EXT_MD = ".md"
EXT_TXT = ".txt"
EXT_CSV = ".csv"
EXT_DOC = ".doc"
EXT_DOCX = ".docx"
EXT_PDF = ".pdf"


def sanitize_user_id(user_id: str) -> str:
    """Keep user workspace path-safe: only alnum, dash, underscore."""
    safe = "".join(ch for ch in user_id if ch.isalnum() or ch in {"-", "_"})
    return safe or "local-user"


def get_user_conversion_workspace(user_id: str) -> Dict[str, Path]:
    """Return user conversion workspace paths and ensure directories exist."""
    from venom_core.config import SETTINGS

    base_dir = Path(SETTINGS.ACADEMY_USER_DATA_DIR) / user_id
    source_dir = base_dir / "source"
    converted_dir = base_dir / "converted"
    metadata_file = base_dir / "files.json"
    for path in (base_dir, source_dir, converted_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "base_dir": base_dir,
        "source_dir": source_dir,
        "converted_dir": converted_dir,
        "metadata_file": metadata_file,
    }


def get_conversion_output_dir() -> Path:
    """Return global conversion output directory."""
    from venom_core.config import SETTINGS

    output_dir = Path(SETTINGS.ACADEMY_CONVERSION_OUTPUT_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_user_conversion_lock_file(base_dir: Path) -> Path:
    """Return lock file path for per-user conversion metadata."""
    return base_dir / ".metadata.lock"


@contextmanager
def user_conversion_metadata_lock(base_dir: Path):
    """Lock conversion metadata operations for the given user workspace."""
    lock_file = get_user_conversion_lock_file(base_dir)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.touch(exist_ok=True)
    with academy_storage.file_lock(lock_file, "a"):
        yield


def load_user_conversion_metadata(metadata_file: Path) -> List[Dict[str, Any]]:
    """Load user conversion metadata JSON list from disk."""
    if not metadata_file.exists():
        return []
    try:
        with open(metadata_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("Failed to read conversion metadata: %s", exc)
    return []


def save_user_conversion_metadata(
    metadata_file: Path,
    items: List[Dict[str, Any]],
) -> None:
    """Persist user conversion metadata atomically."""
    temp_file = metadata_file.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)
    temp_file.replace(metadata_file)


def normalize_conversion_item(raw: Dict[str, Any]) -> DatasetConversionFileInfo:
    """Normalize raw metadata entry to API schema."""
    return DatasetConversionFileInfo(
        file_id=str(raw.get("file_id") or ""),
        name=str(raw.get("name") or ""),
        extension=str(raw.get("extension") or ""),
        size_bytes=int(raw.get("size_bytes") or 0),
        created_at=str(raw.get("created_at") or datetime.now().isoformat()),
        category=str(raw.get("category") or "source"),
        source_file_id=(
            str(raw.get("source_file_id"))
            if raw.get("source_file_id") is not None
            else None
        ),
        target_format=(
            str(raw.get("target_format")) if raw.get("target_format") else None
        ),
        selected_for_training=bool(raw.get("selected_for_training", False)),
        status=str(raw.get("status") or "ready"),
        error=(str(raw.get("error")) if raw.get("error") else None),
    )


def find_conversion_item(
    items: List[Dict[str, Any]],
    file_id: str,
) -> Dict[str, Any] | None:
    """Find conversion item by file_id."""
    for item in items:
        if str(item.get("file_id")) == file_id:
            return item
    return None


def build_conversion_file_id(*, extension: str | None = None) -> str:
    """Build deterministic-ish conversion file id with timestamp and random suffix."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_id = uuid.uuid4().hex[:8]
    suffix = ""
    if extension:
        normalized_extension = extension.lower()
        if not normalized_extension.startswith("."):
            normalized_extension = f".{normalized_extension}"
        suffix = normalized_extension
    return f"{ts}_{unique_id}{suffix}"


def serialize_records_to_markdown(records: List[Dict[str, str]]) -> str:
    """Serialize records to a readable markdown representation."""
    chunks: List[str] = []
    for idx, item in enumerate(records, start=1):
        instruction = item.get("instruction", "").strip()
        input_text = item.get("input", "").strip()
        output = item.get("output", "").strip()
        chunks.append(f"## Example {idx}")
        chunks.append(f"### Instruction\n{instruction or '(empty)'}")
        if input_text:
            chunks.append(f"### Input\n{input_text}")
        chunks.append(f"### Output\n{output or '(empty)'}")
    return "\n\n".join(chunks).strip() + ("\n" if chunks else "")


def records_from_text(content: str) -> List[Dict[str, str]]:
    """Build training records from plain text chunks."""
    sections = [item.strip() for item in content.split("\n\n") if item.strip()]
    records: List[Dict[str, str]] = []
    for i in range(0, len(sections), 2):
        instruction = sections[i]
        output = sections[i + 1] if i + 1 < len(sections) else ""
        if not instruction:
            continue
        if not output:
            output = instruction
        records.append(
            {
                "instruction": instruction[:2000],
                "input": "",
                "output": output[:8000],
            }
        )
    if not records and content.strip():
        records.append(
            {
                "instruction": "Summarize and structure the document content.",
                "input": "",
                "output": content.strip()[:12000],
            }
        )
    return records


def records_from_json_file(source_path: Path) -> List[Dict[str, str]]:
    """Build records from JSON source file."""
    with open(source_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    items: List[Dict[str, Any]]
    if isinstance(payload, list):
        items = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        items = [payload]
    else:
        return []

    records: List[Dict[str, str]] = []
    for item in items:
        instruction = str(item.get("instruction") or item.get("prompt") or "").strip()
        input_text = str(item.get("input") or "").strip()
        output = str(item.get("output") or item.get("response") or "").strip()
        if not instruction and output:
            instruction = "Prepare an answer based on the provided data."
        if instruction and output:
            records.append(
                {"instruction": instruction, "input": input_text, "output": output}
            )
    return records


def records_from_jsonl_file(source_path: Path) -> List[Dict[str, str]]:
    """Build records from JSONL source file."""
    records: List[Dict[str, str]] = []
    with open(source_path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            instruction = str(
                item.get("instruction") or item.get("prompt") or ""
            ).strip()
            input_text = str(item.get("input") or "").strip()
            output = str(item.get("output") or item.get("response") or "").strip()
            if instruction and output:
                records.append(
                    {"instruction": instruction, "input": input_text, "output": output}
                )
    return records


def records_from_csv_file(source_path: Path) -> List[Dict[str, str]]:
    """Build records from CSV source file."""
    import csv

    records: List[Dict[str, str]] = []
    with open(source_path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            instruction = str(row.get("instruction") or row.get("prompt") or "").strip()
            input_text = str(row.get("input") or "").strip()
            output = str(row.get("output") or row.get("response") or "").strip()
            if instruction and output:
                records.append(
                    {"instruction": instruction, "input": input_text, "output": output}
                )
    return records


def extract_text_from_pdf(source_path: Path) -> str:
    """Extract plain text from PDF file."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError(
            "PDF conversion requires optional dependency 'pypdf'."
        ) from exc

    reader = PdfReader(str(source_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(item.strip() for item in pages if item.strip())


def extract_text_from_docx(source_path: Path) -> str:
    """Extract plain text from DOCX file."""
    try:
        from docx import Document
    except ImportError as exc:
        raise ValueError(
            "DOCX conversion requires optional dependency 'python-docx'."
        ) from exc

    doc = Document(str(source_path))
    paragraphs = [item.text.strip() for item in doc.paragraphs if item.text.strip()]
    return "\n\n".join(paragraphs)


def convert_with_pandoc(source_path: Path, output_path: Path) -> bool:
    """Try to convert document to markdown with pypandoc."""
    try:
        import pypandoc
    except ImportError:
        return False

    source_ext = source_path.suffix.lower().lstrip(".")
    input_format: str | None = None
    if source_ext == "docx":
        input_format = "docx"
    elif source_ext == "doc":
        input_format = "doc"
    try:
        if input_format:
            pypandoc.convert_file(
                str(source_path),
                to="md",
                format=input_format,
                outputfile=str(output_path),
            )
        else:
            pypandoc.convert_file(
                str(source_path),
                to="md",
                outputfile=str(output_path),
            )
        return output_path.exists() and output_path.stat().st_size > 0
    except Exception as exc:
        logger.warning(
            "Pandoc conversion failed for '%s': %s",
            source_path.name,
            exc,
        )
        return False


def markdown_from_json(source_path: Path) -> str:
    """Render JSON file as markdown fenced code."""
    payload = json.loads(source_path.read_text(encoding="utf-8", errors="ignore"))
    return f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"


def markdown_from_jsonl(source_path: Path) -> str:
    """Render JSONL file as markdown fenced code."""
    lines = source_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    pretty_lines: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            pretty_lines.append(json.dumps(json.loads(line), ensure_ascii=False))
        except json.JSONDecodeError:
            pretty_lines.append(line)
    return "```jsonl\n" + "\n".join(pretty_lines) + "\n```"


def markdown_from_csv(source_path: Path) -> str:
    """Render CSV file as markdown fenced code."""
    return (
        "```csv\n" + source_path.read_text(encoding="utf-8", errors="ignore") + "\n```"
    )


def markdown_from_binary_document(source_path: Path, ext: str) -> str:
    """Extract markdown/plain text from binary document source."""
    temp_md_path = source_path.with_suffix(source_path.suffix + ".pandoc.md")
    if convert_with_pandoc(source_path, temp_md_path):
        content = temp_md_path.read_text(encoding="utf-8", errors="ignore")
        temp_md_path.unlink(missing_ok=True)
        return content
    temp_md_path.unlink(missing_ok=True)
    if ext == EXT_PDF:
        return extract_text_from_pdf(source_path)
    if ext == EXT_DOCX:
        return extract_text_from_docx(source_path)
    raise ValueError(
        "DOC conversion requires Pandoc with system support for legacy .doc files"
    )


def source_to_markdown(source_path: Path) -> str:
    """Convert source file to markdown/text representation."""
    ext = source_path.suffix.lower()
    if ext in {EXT_MD, EXT_TXT}:
        return source_path.read_text(encoding="utf-8", errors="ignore")

    markdown_builders: dict[str, Callable[[Path], str]] = {
        EXT_JSON: markdown_from_json,
        EXT_JSONL: markdown_from_jsonl,
        EXT_CSV: markdown_from_csv,
    }
    builder = markdown_builders.get(ext)
    if builder:
        return builder(source_path)

    if ext in {EXT_DOC, EXT_DOCX, EXT_PDF}:
        return markdown_from_binary_document(source_path, ext)

    raise ValueError(f"Unsupported source extension: {ext}")


def source_to_records(source_path: Path) -> List[Dict[str, str]]:
    """Convert source file to Academy training records."""
    ext = source_path.suffix.lower()
    record_builders: dict[str, Callable[[Path], List[Dict[str, str]]]] = {
        EXT_JSON: records_from_json_file,
        EXT_JSONL: records_from_jsonl_file,
        EXT_CSV: records_from_csv_file,
    }
    builder = record_builders.get(ext)
    if builder:
        return builder(source_path)
    text = source_to_markdown(source_path)
    return records_from_text(text)


def write_target_markdown(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    """Write records in markdown format."""
    out_file.write(serialize_records_to_markdown(records))


def write_target_text(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    """Write records in plain text format."""
    lines: list[str] = []
    for item in records:
        lines.append(item.get("instruction", ""))
        lines.append(item.get("output", ""))
        lines.append("")
    out_file.write("\n".join(lines).strip() + "\n")


def write_target_json(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    """Write records in pretty JSON format."""
    out_file.write(json.dumps(records, ensure_ascii=False, indent=2))


def write_target_jsonl(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    """Write records in JSONL format."""
    jsonl_text = (
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n"
    )
    out_file.write(jsonl_text)


def write_target_csv(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    """Write records in CSV format."""
    import csv

    writer = csv.DictWriter(out_file, fieldnames=["instruction", "input", "output"])
    writer.writeheader()
    for item in records:
        writer.writerow(
            {
                "instruction": item.get("instruction", ""),
                "input": item.get("input", ""),
                "output": item.get("output", ""),
            }
        )


def write_records_as_target(
    records: List[Dict[str, str]],
    target_format: str,
) -> Path:
    """Persist records in target format and return generated output path."""
    from venom_core.config import SETTINGS

    default_target_extensions = {
        "md": EXT_MD,
        "txt": EXT_TXT,
        "json": EXT_JSON,
        "jsonl": EXT_JSONL,
        "csv": EXT_CSV,
    }
    target_extensions = getattr(
        SETTINGS,
        "ACADEMY_CONVERSION_TARGET_EXTENSIONS",
        default_target_extensions,
    )
    ext = target_extensions.get(target_format)
    if not ext:
        raise ValueError(f"Unsupported target format: {target_format}")

    target_writers: dict[str, Callable[[TextIO, List[Dict[str, str]]], None]] = {
        "md": write_target_markdown,
        "txt": write_target_text,
        "json": write_target_json,
        "jsonl": write_target_jsonl,
        "csv": write_target_csv,
    }
    writer = target_writers.get(target_format)
    if not writer:
        raise ValueError(f"Unsupported target format: {target_format}")

    output_dir = get_conversion_output_dir()
    fd, temp_path = tempfile.mkstemp(
        prefix="conv_",
        suffix=ext,
        dir=str(output_dir),
    )
    safe_output_path = Path(temp_path).resolve()
    output_dir_resolved = output_dir.resolve()
    if not safe_output_path.is_relative_to(output_dir_resolved):
        os.close(fd)
        try:
            safe_output_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ValueError("Conversion output path escapes configured output directory")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as out_file:
            writer(out_file, records)
        return safe_output_path
    except Exception:
        try:
            safe_output_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def build_conversion_item(
    *,
    file_id: str,
    filename: str,
    path: Path,
    category: str,
    source_file_id: str | None = None,
    target_format: str | None = None,
) -> Dict[str, Any]:
    """Build metadata dictionary for source/converted file entry."""
    return {
        "file_id": file_id,
        "name": filename,
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "created_at": datetime.now().isoformat(),
        "category": category,
        "source_file_id": source_file_id,
        "target_format": target_format,
        "selected_for_training": False,
        "status": "ready",
        "error": None,
    }


def resolve_workspace_file_path(
    workspace: Dict[str, Path],
    *,
    file_id: str,
    category: str,
    get_conversion_output_dir_fn: Callable[[], Path],
) -> Path:
    """Resolve file path in source/converted workspace with path guards."""
    if category == "source":
        base_dir = workspace["source_dir"]
        base_dir_resolved = base_dir.resolve()
        candidate = (base_dir / file_id).resolve()
        if not candidate.is_relative_to(base_dir_resolved):
            raise ValueError("Invalid file path")
        return candidate
    if category == "converted":
        converted_output_dir = get_conversion_output_dir_fn()
        converted_output_dir_resolved = converted_output_dir.resolve()
        global_candidate = (converted_output_dir / file_id).resolve()
        if global_candidate.is_relative_to(converted_output_dir_resolved):
            if global_candidate.exists():
                return global_candidate
        # Backward-compat fallback for historical files created per-user.
        legacy_dir = workspace["converted_dir"]
        legacy_dir_resolved = legacy_dir.resolve()
        legacy_candidate = (legacy_dir / file_id).resolve()
        if not legacy_candidate.is_relative_to(legacy_dir_resolved):
            raise ValueError("Invalid file path")
        return legacy_candidate
    raise ValueError("Invalid file category")


def load_conversion_item_from_workspace(
    workspace: Dict[str, Path],
    *,
    file_id: str,
    user_conversion_metadata_lock_fn: Callable[[Path], Any],
    load_user_conversion_metadata_fn: Callable[[Path], List[Dict[str, Any]]],
    find_conversion_item_fn: Callable[
        [List[Dict[str, Any]], str], Dict[str, Any] | None
    ],
) -> Dict[str, Any]:
    """Load one conversion item from workspace metadata."""
    with user_conversion_metadata_lock_fn(workspace["base_dir"]):
        items = load_user_conversion_metadata_fn(workspace["metadata_file"])
        item = find_conversion_item_fn(items, file_id)
    if not item:
        raise FileNotFoundError("File not found")
    return item


def resolve_existing_user_file(
    *,
    workspace: Dict[str, Path],
    file_id: str,
    user_conversion_metadata_lock_fn: Callable[[Path], Any],
    load_user_conversion_metadata_fn: Callable[[Path], List[Dict[str, Any]]],
    find_conversion_item_fn: Callable[
        [List[Dict[str, Any]], str], Dict[str, Any] | None
    ],
    resolve_workspace_file_path_fn: Callable[[Dict[str, Path]], Path] | None = None,
    get_conversion_output_dir_fn: Callable[[], Path] | None = None,
) -> tuple[Dict[str, Any], Path]:
    """Resolve metadata item and validated on-disk path for a user file."""
    item = load_conversion_item_from_workspace(
        workspace,
        file_id=file_id,
        user_conversion_metadata_lock_fn=user_conversion_metadata_lock_fn,
        load_user_conversion_metadata_fn=load_user_conversion_metadata_fn,
        find_conversion_item_fn=find_conversion_item_fn,
    )
    if resolve_workspace_file_path_fn is not None:
        file_path = resolve_workspace_file_path_fn(workspace)
    else:
        file_path = resolve_workspace_file_path(
            workspace,
            file_id=file_id,
            category=str(item.get("category") or "source"),
            get_conversion_output_dir_fn=(
                get_conversion_output_dir_fn or get_conversion_output_dir
            ),
        )
    if not file_path.exists():
        raise FileNotFoundError("File not found on disk")
    return item, file_path


def get_selected_converted_file_ids(
    *,
    workspace: Dict[str, Path],
    user_conversion_metadata_lock_fn: Callable[[Path], Any],
    load_user_conversion_metadata_fn: Callable[[Path], List[Dict[str, Any]]],
    check_path_traversal_fn: Callable[[str], bool],
) -> List[str]:
    """Get converted file ids marked for training."""
    with user_conversion_metadata_lock_fn(workspace["base_dir"]):
        items = load_user_conversion_metadata_fn(workspace["metadata_file"])
    selected_ids: List[str] = []
    for item in items:
        if str(item.get("category") or "") != "converted":
            continue
        if not bool(item.get("selected_for_training", False)):
            continue
        file_id = str(item.get("file_id") or "")
        if file_id and check_path_traversal_fn(file_id):
            selected_ids.append(file_id)
    return selected_ids


def resolve_conversion_file_ids_for_dataset(
    *,
    requested_ids: List[str] | None = None,
    selected_ids_fn: Callable[[], List[str]],
) -> List[str]:
    """Resolve explicit conversion ids or fallback to selected ones."""
    if requested_ids is not None:
        return requested_ids
    return selected_ids_fn()


def list_conversion_files_for_user(
    *,
    user_id: str,
    workspace: Dict[str, Path],
    user_conversion_metadata_lock_fn: Callable[[Path], Any],
    load_user_conversion_metadata_fn: Callable[[Path], List[Dict[str, Any]]],
    normalize_conversion_item_fn: Callable[[Dict[str, Any]], Any],
) -> Dict[str, Any]:
    """Build response payload for listing user conversion files."""
    with user_conversion_metadata_lock_fn(workspace["base_dir"]):
        items = load_user_conversion_metadata_fn(workspace["metadata_file"])
    source_files = [
        normalize_conversion_item_fn(item)
        for item in items
        if str(item.get("category")) == "source"
    ]
    converted_files = [
        normalize_conversion_item_fn(item)
        for item in items
        if str(item.get("category")) == "converted"
    ]
    return {
        "user_id": user_id,
        "workspace_dir": str(workspace["base_dir"]),
        "source_files": source_files,
        "converted_files": converted_files,
    }


async def upload_conversion_files_for_user(
    *,
    files: list[Any],
    workspace: Dict[str, Path],
    settings: Any,
    user_conversion_metadata_lock_fn: Callable[[Path], Any],
    load_user_conversion_metadata_fn: Callable[[Path], List[Dict[str, Any]]],
    save_user_conversion_metadata_fn: Callable[[Path, List[Dict[str, Any]]], None],
    validate_upload_filename_fn: Callable[
        ..., tuple[str | None, Dict[str, str] | None]
    ],
    persist_with_limits_fn: Callable[..., Any],
    build_conversion_file_id_fn: Callable[..., str],
    build_conversion_item_fn: Callable[..., Dict[str, Any]],
    normalize_conversion_item_fn: Callable[[Dict[str, Any]], Any],
) -> Dict[str, Any]:
    """Upload source files for conversion and update per-user metadata."""
    uploaded: List[Dict[str, Any]] = []
    failed: List[Dict[str, str]] = []
    with user_conversion_metadata_lock_fn(workspace["base_dir"]):
        items = load_user_conversion_metadata_fn(workspace["metadata_file"])
        for file in files:
            filename, filename_error = validate_upload_filename_fn(
                file,
                settings,
                allowed_extensions=getattr(
                    settings,
                    "ACADEMY_ALLOWED_CONVERSION_EXTENSIONS",
                    settings.ACADEMY_ALLOWED_EXTENSIONS,
                ),
            )
            if filename_error:
                failed.append(filename_error)
                continue
            if not filename:
                continue
            file_id = build_conversion_file_id_fn(
                extension=Path(filename).suffix.lower()
            )
            file_path = workspace["source_dir"] / file_id
            persisted, persist_error = await persist_with_limits_fn(
                file=file,
                file_path=file_path,
                filename=filename,
                settings=settings,
            )
            if persist_error or not persisted:
                failed.append(
                    persist_error
                    or {"name": filename, "error": "Failed to persist uploaded file"}
                )
                continue
            item = build_conversion_item_fn(
                file_id=file_id,
                filename=filename,
                path=file_path,
                category="source",
            )
            items.append(item)
            uploaded.append(item)
        save_user_conversion_metadata_fn(workspace["metadata_file"], items)
    return {
        "success": len(uploaded) > 0,
        "uploaded": len(uploaded),
        "failed": len(failed),
        "files": [normalize_conversion_item_fn(item).model_dump() for item in uploaded],
        "errors": failed,
        "message": f"Uploaded {len(uploaded)} file(s), failed {len(failed)}",
    }


def convert_dataset_source_file(
    *,
    file_id: str,
    workspace: Dict[str, Path],
    target_format: str,
    check_path_traversal_fn: Callable[[str], bool],
    user_conversion_metadata_lock_fn: Callable[[Path], Any],
    load_user_conversion_metadata_fn: Callable[[Path], List[Dict[str, Any]]],
    save_user_conversion_metadata_fn: Callable[[Path, List[Dict[str, Any]]], None],
    find_conversion_item_fn: Callable[
        [List[Dict[str, Any]], str], Dict[str, Any] | None
    ],
    resolve_workspace_file_path_fn: Callable[..., Path],
    source_to_records_fn: Callable[[Path], List[Dict[str, str]]],
    write_records_as_target_fn: Callable[[List[Dict[str, str]], str], Path],
    build_conversion_item_fn: Callable[..., Dict[str, Any]],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Convert a source file to selected target format and persist metadata."""
    if not check_path_traversal_fn(file_id):
        raise ValueError(f"Invalid file_id: {file_id}")
    with user_conversion_metadata_lock_fn(workspace["base_dir"]):
        items = load_user_conversion_metadata_fn(workspace["metadata_file"])
        source_item = find_conversion_item_fn(items, file_id)
        if not source_item:
            raise FileNotFoundError("Source file not found")
        if str(source_item.get("category")) != "source":
            raise ValueError("Conversion requires source file")
        source_path = resolve_workspace_file_path_fn(
            workspace,
            file_id=file_id,
            category="source",
        )
        if not source_path.exists():
            raise FileNotFoundError("Source file not found on disk")
        records = source_to_records_fn(source_path)
        if not records:
            raise ValueError("No valid records produced from source file")
        converted_path = write_records_as_target_fn(records, target_format)
        source_stem = Path(str(source_item.get("name") or "dataset")).name
        converted_name = f"{Path(source_stem).stem}.{target_format}"
        converted_item = build_conversion_item_fn(
            file_id=converted_path.name,
            filename=converted_name,
            path=converted_path,
            category="converted",
            source_file_id=file_id,
            target_format=target_format,
        )
        items.append(converted_item)
        save_user_conversion_metadata_fn(workspace["metadata_file"], items)
    return source_item, converted_item


def set_conversion_training_selection(
    *,
    file_id: str,
    selected_for_training: bool,
    workspace: Dict[str, Path],
    check_path_traversal_fn: Callable[[str], bool],
    user_conversion_metadata_lock_fn: Callable[[Path], Any],
    load_user_conversion_metadata_fn: Callable[[Path], List[Dict[str, Any]]],
    save_user_conversion_metadata_fn: Callable[[Path, List[Dict[str, Any]]], None],
    find_conversion_item_fn: Callable[
        [List[Dict[str, Any]], str], Dict[str, Any] | None
    ],
) -> Dict[str, Any]:
    """Mark converted file as selected/unselected for training."""
    if not check_path_traversal_fn(file_id):
        raise ValueError(f"Invalid file_id: {file_id}")
    with user_conversion_metadata_lock_fn(workspace["base_dir"]):
        items = load_user_conversion_metadata_fn(workspace["metadata_file"])
        item = find_conversion_item_fn(items, file_id)
        if not item:
            raise FileNotFoundError("File not found")
        if str(item.get("category") or "") != "converted":
            raise ValueError("Only converted files can be marked for training")
        item["selected_for_training"] = bool(selected_for_training)
        save_user_conversion_metadata_fn(workspace["metadata_file"], items)
    return item


async def read_text_preview(
    *,
    file_path: Path,
    max_chars: int = 20_000,
) -> tuple[str, bool]:
    """Read UTF-8 file preview with truncation marker."""
    async with await anyio.open_file(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore",
    ) as file_obj:
        preview_plus_one = await file_obj.read(max_chars + 1)
    truncated = len(preview_plus_one) > max_chars
    return preview_plus_one[:max_chars], truncated


def guess_media_type(file_path: Path) -> str:
    """Guess download media type from file extension."""
    return mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
