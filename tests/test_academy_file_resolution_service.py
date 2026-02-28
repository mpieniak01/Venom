from __future__ import annotations

from pathlib import Path

import pytest

from venom_core.services.academy import file_resolution


def test_resolve_existing_user_file_returns_item_and_path(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir(parents=True)
    payload = source / "item.txt"
    payload.write_text("ok", encoding="utf-8")

    item = {"file_id": "item", "category": "source"}

    result_item, result_path = file_resolution.resolve_existing_user_file(
        user_id="u1",
        file_id="item",
        get_user_conversion_workspace_fn=lambda _uid: {"source_dir": source},
        load_conversion_item_fn=lambda _workspace, _fid: item,
        resolve_workspace_file_path_fn=lambda _workspace, _fid, _category: payload,
    )

    assert result_item is item
    assert result_path == payload


def test_resolve_existing_user_file_raises_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError):
        file_resolution.resolve_existing_user_file(
            user_id="u1",
            file_id="item",
            get_user_conversion_workspace_fn=lambda _uid: {"source_dir": tmp_path},
            load_conversion_item_fn=lambda _workspace, _fid: {
                "file_id": "item",
                "category": "source",
            },
            resolve_workspace_file_path_fn=lambda _workspace, _fid, _category: missing,
        )


def test_source_to_markdown_for_text_file(tmp_path: Path) -> None:
    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")

    assert (
        file_resolution.source_to_markdown_with_impls(
            source,
            ext_md=".md",
            ext_txt=".txt",
            ext_json=".json",
            ext_jsonl=".jsonl",
            ext_csv=".csv",
            ext_doc=".doc",
            ext_docx=".docx",
            ext_pdf=".pdf",
            markdown_from_json_fn=lambda _p: "json",
            markdown_from_jsonl_fn=lambda _p: "jsonl",
            markdown_from_csv_fn=lambda _p: "csv",
            markdown_from_binary_document_fn=lambda _p, _ext: "bin",
        )
        == "hello"
    )


def test_source_to_records_for_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "dataset.jsonl"
    source.write_text(
        '{"instruction":"q","input":"","output":"a"}\n',
        encoding="utf-8",
    )

    records = file_resolution.source_to_records_with_impls(
        source,
        ext_json=".json",
        ext_jsonl=".jsonl",
        ext_csv=".csv",
        records_from_json_file_fn=lambda _p: [],
        records_from_jsonl_file_fn=lambda _p: [
            {"instruction": "q", "input": "", "output": "a"}
        ],
        records_from_csv_file_fn=lambda _p: [],
        source_to_markdown_fn=lambda _p: "",
        records_from_text_fn=lambda _text: [],
    )

    assert records == [{"instruction": "q", "input": "", "output": "a"}]
