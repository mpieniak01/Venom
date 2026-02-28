"""Domain helpers for Academy user-file resolution and source conversion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def resolve_workspace_file_path(
    workspace: dict[str, Path],
    *,
    file_id: str,
    category: str,
    get_conversion_output_dir_fn: Callable[[], Path],
    resolve_workspace_file_path_impl: Callable[..., Path],
) -> Path:
    """Resolve file path inside workspace with category-aware rules."""
    return resolve_workspace_file_path_impl(
        workspace,
        file_id=file_id,
        category=category,
        get_conversion_output_dir_fn=get_conversion_output_dir_fn,
    )


def load_conversion_item_from_workspace(
    workspace: dict[str, Path],
    *,
    file_id: str,
    user_conversion_metadata_lock_fn: Callable[[Path], Any],
    load_user_conversion_metadata_fn: Callable[[Path], list[dict[str, Any]]],
    find_conversion_item_fn: Callable[
        [list[dict[str, Any]], str], dict[str, Any] | None
    ],
    load_conversion_item_impl: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Load one conversion item metadata entry for a workspace."""
    return load_conversion_item_impl(
        workspace,
        file_id=file_id,
        user_conversion_metadata_lock_fn=user_conversion_metadata_lock_fn,
        load_user_conversion_metadata_fn=load_user_conversion_metadata_fn,
        find_conversion_item_fn=find_conversion_item_fn,
    )


def resolve_existing_user_file(
    *,
    user_id: str,
    file_id: str,
    get_user_conversion_workspace_fn: Callable[[str], dict[str, Path]],
    load_conversion_item_fn: Callable[[dict[str, Path], str], dict[str, Any]],
    resolve_workspace_file_path_fn: Callable[[dict[str, Path], str, str], Path],
) -> tuple[dict[str, Any], Path]:
    """Resolve metadata + path for existing user file and assert disk presence."""
    workspace = get_user_conversion_workspace_fn(user_id)
    item = load_conversion_item_fn(workspace, file_id)
    file_path = resolve_workspace_file_path_fn(
        workspace,
        file_id,
        str(item.get("category") or "source"),
    )
    if not file_path.exists():
        raise FileNotFoundError("File not found on disk")
    return item, file_path


def markdown_from_binary_document(source_path: Path, ext: str) -> str:
    """Convert binary docs to markdown via pandoc or fallback extractors."""
    raise NotImplementedError("Use markdown_from_binary_document_with_impls().")


def markdown_from_binary_document_with_impls(
    source_path: Path,
    ext: str,
    *,
    ext_pdf: str,
    ext_docx: str,
    convert_with_pandoc_fn: Callable[[Path, Path], bool],
    extract_text_from_pdf_fn: Callable[[Path], str],
    extract_text_from_docx_fn: Callable[[Path], str],
) -> str:
    """Convert binary docs with injected conversion/extraction callables."""
    temp_md_path = source_path.with_suffix(source_path.suffix + ".pandoc.md")
    try:
        if convert_with_pandoc_fn(source_path, temp_md_path):
            return temp_md_path.read_text(encoding="utf-8", errors="ignore")
    finally:
        temp_md_path.unlink(missing_ok=True)

    if ext == ext_pdf:
        return extract_text_from_pdf_fn(source_path)
    if ext == ext_docx:
        return extract_text_from_docx_fn(source_path)

    raise ValueError(
        "DOC conversion requires Pandoc with system support for legacy .doc files"
    )


def source_to_markdown(source_path: Path) -> str:
    """Convert supported source file to markdown text."""
    raise NotImplementedError("Use source_to_markdown_with_impls().")


def source_to_markdown_with_impls(
    source_path: Path,
    *,
    ext_md: str,
    ext_txt: str,
    ext_json: str,
    ext_jsonl: str,
    ext_csv: str,
    ext_doc: str,
    ext_docx: str,
    ext_pdf: str,
    markdown_from_json_fn: Callable[[Path], str],
    markdown_from_jsonl_fn: Callable[[Path], str],
    markdown_from_csv_fn: Callable[[Path], str],
    markdown_from_binary_document_fn: Callable[[Path, str], str],
) -> str:
    """Convert source to markdown with injected converter callables."""
    ext = source_path.suffix.lower()
    if ext in {ext_md, ext_txt}:
        return source_path.read_text(encoding="utf-8", errors="ignore")

    markdown_builders: dict[str, Callable[[Path], str]] = {
        ext_json: markdown_from_json_fn,
        ext_jsonl: markdown_from_jsonl_fn,
        ext_csv: markdown_from_csv_fn,
    }
    builder = markdown_builders.get(ext)
    if builder:
        return builder(source_path)

    if ext in {ext_doc, ext_docx, ext_pdf}:
        return markdown_from_binary_document_fn(source_path, ext)

    raise ValueError(f"Unsupported source extension: {ext}")


def source_to_records(source_path: Path) -> list[dict[str, str]]:
    """Convert supported source file to canonical Academy training records."""
    raise NotImplementedError("Use source_to_records_with_impls().")


def source_to_records_with_impls(
    source_path: Path,
    *,
    ext_json: str,
    ext_jsonl: str,
    ext_csv: str,
    records_from_json_file_fn: Callable[[Path], list[dict[str, str]]],
    records_from_jsonl_file_fn: Callable[[Path], list[dict[str, str]]],
    records_from_csv_file_fn: Callable[[Path], list[dict[str, str]]],
    source_to_markdown_fn: Callable[[Path], str],
    records_from_text_fn: Callable[[str], list[dict[str, str]]],
) -> list[dict[str, str]]:
    """Convert source to records with injected parser callables."""
    ext = source_path.suffix.lower()
    record_builders: dict[str, Callable[[Path], list[dict[str, str]]]] = {
        ext_json: records_from_json_file_fn,
        ext_jsonl: records_from_jsonl_file_fn,
        ext_csv: records_from_csv_file_fn,
    }
    builder = record_builders.get(ext)
    if builder:
        return builder(source_path)

    text = source_to_markdown_fn(source_path)
    return records_from_text_fn(text)
