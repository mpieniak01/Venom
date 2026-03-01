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


def test_file_resolution_wrappers_and_binary_paths(tmp_path: Path) -> None:
    workspace = {"base_dir": tmp_path}
    source = tmp_path / "x.pdf"
    source.write_text("bin", encoding="utf-8")

    assert (
        file_resolution.resolve_workspace_file_path(
            workspace,
            file_id="f1",
            category="source",
            get_conversion_output_dir_fn=lambda: tmp_path,
            resolve_workspace_file_path_impl=lambda _ws, **_kw: source,
        )
        == source
    )

    loaded = file_resolution.load_conversion_item_from_workspace(
        workspace,
        file_id="f1",
        user_conversion_metadata_lock_fn=lambda _path: None,
        load_user_conversion_metadata_fn=lambda _path: [{"file_id": "f1"}],
        find_conversion_item_fn=lambda _items, _id: {"file_id": "f1"},
        load_conversion_item_impl=lambda _ws, **_kw: {"file_id": "f1"},
    )
    assert loaded["file_id"] == "f1"

    tmp_md = source.with_suffix(source.suffix + ".pandoc.md")
    tmp_md.write_text("# ok", encoding="utf-8")
    assert (
        file_resolution.markdown_from_binary_document_with_impls(
            source,
            ".pdf",
            ext_pdf=".pdf",
            ext_docx=".docx",
            convert_with_pandoc_fn=lambda _src, _dst: True,
            extract_text_from_pdf_fn=lambda _src: "pdf",
            extract_text_from_docx_fn=lambda _src: "docx",
        )
        == "# ok"
    )
    assert not tmp_md.exists()

    assert (
        file_resolution.markdown_from_binary_document_with_impls(
            source,
            ".pdf",
            ext_pdf=".pdf",
            ext_docx=".docx",
            convert_with_pandoc_fn=lambda _src, _dst: False,
            extract_text_from_pdf_fn=lambda _src: "pdf-extract",
            extract_text_from_docx_fn=lambda _src: "docx-extract",
        )
        == "pdf-extract"
    )

    with pytest.raises(ValueError):
        file_resolution.markdown_from_binary_document_with_impls(
            source.with_suffix(".doc"),
            ".doc",
            ext_pdf=".pdf",
            ext_docx=".docx",
            convert_with_pandoc_fn=lambda _src, _dst: False,
            extract_text_from_pdf_fn=lambda _src: "pdf",
            extract_text_from_docx_fn=lambda _src: "docx",
        )


def test_source_builders_and_notimplemented(tmp_path: Path) -> None:
    source = tmp_path / "x.json"
    source.write_text("{}", encoding="utf-8")
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
            markdown_from_json_fn=lambda _p: "json-md",
            markdown_from_jsonl_fn=lambda _p: "jsonl-md",
            markdown_from_csv_fn=lambda _p: "csv-md",
            markdown_from_binary_document_fn=lambda _p, _ext: "bin-md",
        )
        == "json-md"
    )

    source_csv = tmp_path / "x.csv"
    source_csv.write_text("a,b", encoding="utf-8")
    assert file_resolution.source_to_records_with_impls(
        source_csv,
        ext_json=".json",
        ext_jsonl=".jsonl",
        ext_csv=".csv",
        records_from_json_file_fn=lambda _p: [],
        records_from_jsonl_file_fn=lambda _p: [],
        records_from_csv_file_fn=lambda _p: [
            {"instruction": "i", "input": "", "output": "o"}
        ],
        source_to_markdown_fn=lambda _p: "x",
        records_from_text_fn=lambda _text: [],
    ) == [{"instruction": "i", "input": "", "output": "o"}]

    source_txt = tmp_path / "x.txt"
    source_txt.write_text("hello", encoding="utf-8")
    assert (
        file_resolution.source_to_records_with_impls(
            source_txt,
            ext_json=".json",
            ext_jsonl=".jsonl",
            ext_csv=".csv",
            records_from_json_file_fn=lambda _p: [],
            records_from_jsonl_file_fn=lambda _p: [],
            records_from_csv_file_fn=lambda _p: [],
            source_to_markdown_fn=lambda _p: "markdown",
            records_from_text_fn=lambda text: [
                {"instruction": text, "input": "", "output": "ok"}
            ],
        )[0]["instruction"]
        == "markdown"
    )

    with pytest.raises(ValueError):
        file_resolution.source_to_markdown_with_impls(
            tmp_path / "x.bin",
            ext_md=".md",
            ext_txt=".txt",
            ext_json=".json",
            ext_jsonl=".jsonl",
            ext_csv=".csv",
            ext_doc=".doc",
            ext_docx=".docx",
            ext_pdf=".pdf",
            markdown_from_json_fn=lambda _p: "",
            markdown_from_jsonl_fn=lambda _p: "",
            markdown_from_csv_fn=lambda _p: "",
            markdown_from_binary_document_fn=lambda _p, _ext: "",
        )

    with pytest.raises(NotImplementedError):
        file_resolution.markdown_from_binary_document(source, ".pdf")
    with pytest.raises(NotImplementedError):
        file_resolution.source_to_markdown(source)
    with pytest.raises(NotImplementedError):
        file_resolution.source_to_records(source)
