"""Conversion and user-workspace helpers for Academy routes."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, TextIO

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
