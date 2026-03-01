"""Unit tests for academy_storage and academy_conversion helper modules."""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from venom_core.api.routes import (
    academy_conversion,
    academy_route_handlers,
    academy_storage,
)


def test_academy_route_handlers_compatibility_shim_exports_handlers() -> None:
    assert hasattr(academy_route_handlers, "curate_dataset_handler")


@patch("venom_core.config.SETTINGS")
def test_academy_storage_paths_and_validators(mock_settings, tmp_path):
    mock_settings.ACADEMY_TRAINING_DIR = str(tmp_path)
    mock_settings.ACADEMY_ALLOWED_DATASET_EXTENSIONS = [".jsonl", ".txt"]
    mock_settings.ACADEMY_ALLOWED_EXTENSIONS = [".jsonl", ".txt"]
    mock_settings.ACADEMY_MAX_UPLOAD_SIZE_MB = 1

    uploads_dir = academy_storage.get_uploads_dir()
    assert uploads_dir.exists()
    assert academy_storage.get_uploads_metadata_file().name == "metadata.jsonl"
    assert academy_storage.get_uploads_metadata_lock_file().name == "metadata.lock"

    assert academy_storage.validate_file_extension("x.txt")
    assert not academy_storage.validate_file_extension("x.exe")
    assert academy_storage.validate_file_extension("x.bin", allowed_extensions=[".bin"])
    assert academy_storage.validate_file_size(100)
    assert not academy_storage.validate_file_size(2 * 1024 * 1024)

    assert academy_storage.is_path_within_base(tmp_path / "a", tmp_path)
    assert not academy_storage.is_path_within_base(Path("/tmp"), tmp_path)
    assert academy_storage.check_path_traversal("safe-file.json")
    assert not academy_storage.check_path_traversal("../etc/passwd")
    assert academy_storage.is_safe_file_id("file_01-abc.jsonl")
    assert not academy_storage.is_safe_file_id("bad/name.json")


def test_academy_storage_file_lock_and_metadata_ops(tmp_path):
    file_path = tmp_path / "lock.txt"
    file_path.write_text("", encoding="utf-8")
    with academy_storage.file_lock(file_path, "a") as handle:
        handle.write("ok")
    assert file_path.read_text(encoding="utf-8") == "ok"

    metadata_file = tmp_path / "metadata.jsonl"
    with patch(
        "venom_core.api.routes.academy_storage.get_uploads_metadata_file",
        return_value=metadata_file,
    ):
        academy_storage.save_upload_metadata({"id": "a", "name": "one"})
        academy_storage.save_upload_metadata({"id": "b", "name": "two"})
        loaded = academy_storage.load_uploads_metadata()
        assert len(loaded) == 2
        academy_storage.delete_upload_metadata("a")
        loaded = academy_storage.load_uploads_metadata()
        assert len(loaded) == 1
        assert loaded[0]["id"] == "b"


def test_academy_storage_load_uploads_metadata_on_error(tmp_path):
    metadata_file = tmp_path / "metadata.jsonl"
    metadata_file.write_text('{"id":"x"}\n', encoding="utf-8")
    with (
        patch(
            "venom_core.api.routes.academy_storage.get_uploads_metadata_file",
            return_value=metadata_file,
        ),
        patch(
            "venom_core.api.routes.academy_storage.open",
            side_effect=RuntimeError("boom"),
        ),
    ):
        assert academy_storage.load_uploads_metadata() == []


def test_academy_storage_hashes_and_estimates(tmp_path):
    f = tmp_path / "x.txt"
    f.write_bytes(b"abc")
    assert academy_storage.compute_file_hash(f) == academy_storage.compute_bytes_hash(
        b"abc"
    )
    assert academy_storage.compute_bytes_hash(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )

    jsonl_data = b'{"a":1}\n{"a":2}\n\n'
    assert academy_storage.estimate_records_from_content("x.jsonl", jsonl_data) == 2
    json_data = json.dumps([{"a": 1}, {"a": 2}]).encode("utf-8")
    assert academy_storage.estimate_records_from_content("x.json", json_data) == 2
    json_obj = json.dumps({"a": 1}).encode("utf-8")
    assert academy_storage.estimate_records_from_content("x.json", json_obj) == 1
    text_data = b"one\n\n two\n\nthree"
    assert academy_storage.estimate_records_from_content("x.txt", text_data) >= 1
    assert academy_storage.estimate_records_from_content("x.bin", b"??") == 0


@patch("venom_core.config.SETTINGS")
def test_academy_conversion_workspace_and_metadata(mock_settings, tmp_path):
    mock_settings.ACADEMY_USER_DATA_DIR = str(tmp_path / "users")
    mock_settings.ACADEMY_CONVERSION_OUTPUT_DIR = str(tmp_path / "conv-out")

    assert academy_conversion.sanitize_user_id("a/b:c?d") == "abcd"
    assert academy_conversion.sanitize_user_id("////") == "local-user"

    ws = academy_conversion.get_user_conversion_workspace("u1")
    assert ws["source_dir"].exists()
    assert ws["converted_dir"].exists()
    assert academy_conversion.get_conversion_output_dir().exists()

    lock_path = academy_conversion.get_user_conversion_lock_file(ws["base_dir"])
    assert lock_path.name == ".metadata.lock"
    with academy_conversion.user_conversion_metadata_lock(ws["base_dir"]):
        assert lock_path.exists()

    metadata_file = ws["metadata_file"]
    assert academy_conversion.load_user_conversion_metadata(metadata_file) == []
    academy_conversion.save_user_conversion_metadata(metadata_file, [{"file_id": "a"}])
    assert (
        academy_conversion.load_user_conversion_metadata(metadata_file)[0]["file_id"]
        == "a"
    )

    metadata_file.write_text('{"x":1}', encoding="utf-8")
    assert academy_conversion.load_user_conversion_metadata(metadata_file) == []
    metadata_file.write_text("not-json", encoding="utf-8")
    assert academy_conversion.load_user_conversion_metadata(metadata_file) == []


def test_academy_conversion_records_and_markdown_builders(tmp_path):
    assert academy_conversion.build_conversion_file_id(extension="json").endswith(
        ".json"
    )
    assert academy_conversion.build_conversion_file_id(extension=".CSV").endswith(
        ".csv"
    )

    records = academy_conversion.records_from_text("instr\n\nout")
    assert records and records[0]["instruction"]
    assert academy_conversion.records_from_text("single paragraph")[0]["output"]

    md = academy_conversion.serialize_records_to_markdown(records)
    assert "## Example 1" in md

    json_file = tmp_path / "a.json"
    json_file.write_text(
        json.dumps(
            [{"instruction": "i", "output": "o"}, {"prompt": "p", "response": "r"}]
        ),
        encoding="utf-8",
    )
    assert len(academy_conversion.records_from_json_file(json_file)) == 2

    json_obj_file = tmp_path / "b.json"
    json_obj_file.write_text(json.dumps({"output": "x"}), encoding="utf-8")
    rec_obj = academy_conversion.records_from_json_file(json_obj_file)
    assert rec_obj[0]["instruction"] == "Prepare an answer based on the provided data."

    non_dict_json = tmp_path / "c.json"
    non_dict_json.write_text(json.dumps("x"), encoding="utf-8")
    assert academy_conversion.records_from_json_file(non_dict_json) == []

    jsonl_file = tmp_path / "a.jsonl"
    jsonl_file.write_text(
        '{"instruction":"i","output":"o"}\n'
        '{"prompt":"p","response":"r"}\n'
        "bad-json\n"
        "123\n",
        encoding="utf-8",
    )
    assert len(academy_conversion.records_from_jsonl_file(jsonl_file)) == 2

    csv_file = tmp_path / "a.csv"
    csv_file.write_text(
        "instruction,input,output\ni1,,o1\n,,skip\np2,,r2\n",
        encoding="utf-8",
    )
    assert len(academy_conversion.records_from_csv_file(csv_file)) == 2

    assert "```json" in academy_conversion.markdown_from_json(json_file)
    assert "```jsonl" in academy_conversion.markdown_from_jsonl(jsonl_file)
    assert "```csv" in academy_conversion.markdown_from_csv(csv_file)


def test_academy_conversion_extractors_and_pandoc_branches(tmp_path, monkeypatch):
    pdf_file = tmp_path / "a.pdf"
    pdf_file.write_text("x", encoding="utf-8")
    docx_file = tmp_path / "a.docx"
    docx_file.write_text("x", encoding="utf-8")

    fake_pypdf = ModuleType("pypdf")

    class _FakePdfReader:
        def __init__(self, _):
            self.pages = [
                SimpleNamespace(extract_text=lambda: "page-1"),
                SimpleNamespace(extract_text=lambda: " "),
            ]

    fake_pypdf.PdfReader = _FakePdfReader
    monkeypatch.setitem(__import__("sys").modules, "pypdf", fake_pypdf)
    assert academy_conversion.extract_text_from_pdf(pdf_file) == "page-1"

    fake_docx = ModuleType("docx")

    class _FakeDocument:
        def __init__(self, _):
            self.paragraphs = [SimpleNamespace(text="p1"), SimpleNamespace(text="")]

    fake_docx.Document = _FakeDocument
    monkeypatch.setitem(__import__("sys").modules, "docx", fake_docx)
    assert academy_conversion.extract_text_from_docx(docx_file) == "p1"

    monkeypatch.delitem(__import__("sys").modules, "pypandoc", raising=False)
    assert academy_conversion.convert_with_pandoc(pdf_file, tmp_path / "x.md") is False

    fake_pandoc = ModuleType("pypandoc")

    def _convert_file(*_args, **kwargs):
        output = Path(kwargs["outputfile"])
        output.write_text("# converted", encoding="utf-8")

    fake_pandoc.convert_file = _convert_file
    monkeypatch.setitem(__import__("sys").modules, "pypandoc", fake_pandoc)
    out = tmp_path / "pandoc.md"
    assert academy_conversion.convert_with_pandoc(docx_file, out) is True
    assert out.read_text(encoding="utf-8") == "# converted"

    def _raise_convert(*_args, **_kwargs):
        raise RuntimeError("boom")

    fake_pandoc.convert_file = _raise_convert
    assert academy_conversion.convert_with_pandoc(docx_file, out) is False


def test_academy_conversion_source_dispatchers(tmp_path, monkeypatch):
    md_file = tmp_path / "a.md"
    md_file.write_text("hello", encoding="utf-8")
    txt_file = tmp_path / "a.txt"
    txt_file.write_text("hello txt", encoding="utf-8")
    json_file = tmp_path / "a.json"
    json_file.write_text(
        json.dumps({"instruction": "i", "output": "o"}), encoding="utf-8"
    )
    jsonl_file = tmp_path / "a.jsonl"
    jsonl_file.write_text('{"instruction":"i","output":"o"}\n', encoding="utf-8")
    csv_file = tmp_path / "a.csv"
    csv_file.write_text("instruction,input,output\ni,,o\n", encoding="utf-8")
    pdf_file = tmp_path / "a.pdf"
    pdf_file.write_text("x", encoding="utf-8")
    docx_file = tmp_path / "a.docx"
    docx_file.write_text("x", encoding="utf-8")
    doc_file = tmp_path / "a.doc"
    doc_file.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        academy_conversion,
        "markdown_from_binary_document",
        lambda _path, ext: f"binary:{ext}",
    )

    assert academy_conversion.source_to_markdown(md_file) == "hello"
    assert academy_conversion.source_to_markdown(txt_file) == "hello txt"
    assert "```json" in academy_conversion.source_to_markdown(json_file)
    assert "```jsonl" in academy_conversion.source_to_markdown(jsonl_file)
    assert "```csv" in academy_conversion.source_to_markdown(csv_file)
    assert academy_conversion.source_to_markdown(pdf_file) == "binary:.pdf"
    assert academy_conversion.source_to_markdown(docx_file) == "binary:.docx"
    assert academy_conversion.source_to_markdown(doc_file) == "binary:.doc"

    bad = tmp_path / "a.bin"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        academy_conversion.source_to_markdown(bad)

    assert academy_conversion.source_to_records(json_file)
    assert academy_conversion.source_to_records(jsonl_file)
    assert academy_conversion.source_to_records(csv_file)
    assert academy_conversion.source_to_records(md_file)


@patch("venom_core.config.SETTINGS")
def test_academy_conversion_write_targets_and_output_file(
    mock_settings, tmp_path, monkeypatch
):
    mock_settings.ACADEMY_CONVERSION_OUTPUT_DIR = str(tmp_path / "conv")
    mock_settings.ACADEMY_CONVERSION_TARGET_EXTENSIONS = {
        "md": ".md",
        "txt": ".txt",
        "json": ".json",
        "jsonl": ".jsonl",
        "csv": ".csv",
    }
    records = [{"instruction": "i", "input": "", "output": "o"}]

    md_path = academy_conversion.write_records_as_target(records, "md")
    assert md_path.suffix == ".md"
    assert "Example 1" in md_path.read_text(encoding="utf-8")

    txt_path = academy_conversion.write_records_as_target(records, "txt")
    assert txt_path.suffix == ".txt"
    json_path = academy_conversion.write_records_as_target(records, "json")
    assert json_path.suffix == ".json"
    jsonl_path = academy_conversion.write_records_as_target(records, "jsonl")
    assert jsonl_path.suffix == ".jsonl"
    csv_path = academy_conversion.write_records_as_target(records, "csv")
    assert csv_path.suffix == ".csv"

    with pytest.raises(ValueError):
        academy_conversion.write_records_as_target(records, "bin")

    mock_settings.ACADEMY_CONVERSION_TARGET_EXTENSIONS = {"x": ".txt"}
    with pytest.raises(ValueError):
        academy_conversion.write_records_as_target(records, "x")

    mock_settings.ACADEMY_CONVERSION_TARGET_EXTENSIONS = {
        "md": ".md",
        "txt": ".txt",
        "json": ".json",
        "jsonl": ".jsonl",
        "csv": ".csv",
    }

    original_rel = Path.is_relative_to
    monkeypatch.setattr(Path, "is_relative_to", lambda self, other: False)
    with pytest.raises(ValueError):
        academy_conversion.write_records_as_target(records, "md")
    monkeypatch.setattr(Path, "is_relative_to", original_rel)

    def _boom(_out_file, _records):
        raise RuntimeError("writer-fail")

    monkeypatch.setattr(academy_conversion, "write_target_markdown", _boom)
    with pytest.raises(RuntimeError):
        academy_conversion.write_records_as_target(records, "md")


def test_academy_conversion_binary_document_fallbacks(tmp_path, monkeypatch):
    source_path = tmp_path / "a.pdf"
    source_path.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        academy_conversion,
        "convert_with_pandoc",
        lambda _s, out: out.write_text("pandoc md", encoding="utf-8") or True,
    )
    md = academy_conversion.markdown_from_binary_document(source_path, ".pdf")
    assert "pandoc md" in md

    monkeypatch.setattr(academy_conversion, "convert_with_pandoc", lambda *_: False)
    monkeypatch.setattr(
        academy_conversion, "extract_text_from_pdf", lambda _p: "pdf-text"
    )
    assert (
        academy_conversion.markdown_from_binary_document(source_path, ".pdf")
        == "pdf-text"
    )

    source_docx = tmp_path / "a.docx"
    source_docx.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        academy_conversion, "extract_text_from_docx", lambda _p: "docx-text"
    )
    assert (
        academy_conversion.markdown_from_binary_document(source_docx, ".docx")
        == "docx-text"
    )

    with pytest.raises(ValueError):
        academy_conversion.markdown_from_binary_document(tmp_path / "a.doc", ".doc")


def test_academy_conversion_normalize_find_and_build_item(tmp_path):
    raw = {
        "file_id": "f1",
        "name": "n",
        "extension": ".txt",
        "size_bytes": 5,
        "category": "source",
        "selected_for_training": 1,
    }
    item = academy_conversion.normalize_conversion_item(raw)
    assert item.file_id == "f1"
    assert item.selected_for_training is True
    assert academy_conversion.find_conversion_item([raw], "f1") is not None
    assert academy_conversion.find_conversion_item([raw], "nope") is None

    existing = tmp_path / "f.txt"
    existing.write_text("abc", encoding="utf-8")
    built = academy_conversion.build_conversion_item(
        file_id="id1",
        filename="f.txt",
        path=existing,
        category="source",
        source_file_id=None,
        target_format=None,
    )
    assert built["size_bytes"] == 3

    missing = tmp_path / "missing.txt"
    built_missing = academy_conversion.build_conversion_item(
        file_id="id2",
        filename="missing.txt",
        path=missing,
        category="converted",
        source_file_id="id1",
        target_format="jsonl",
    )
    assert built_missing["size_bytes"] == 0
