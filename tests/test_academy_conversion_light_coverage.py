from __future__ import annotations

import io
import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from venom_core.api.routes import academy_conversion


class _Dumpable:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, object]:
        return dict(self._payload)


@contextmanager
def _dummy_lock(_path: Path):
    yield


@patch("venom_core.config.SETTINGS")
def test_workspace_metadata_and_basic_helpers(mock_settings, tmp_path: Path) -> None:
    mock_settings.ACADEMY_USER_DATA_DIR = str(tmp_path / "users")
    mock_settings.ACADEMY_CONVERSION_OUTPUT_DIR = str(tmp_path / "out")

    assert academy_conversion.sanitize_user_id("abc-1_2") == "abc-1_2"
    assert academy_conversion.sanitize_user_id("a/b:c") == "abc"
    assert academy_conversion.sanitize_user_id("////") == "local-user"

    workspace = academy_conversion.get_user_conversion_workspace("u1")
    assert workspace["base_dir"].exists()
    assert workspace["source_dir"].exists()
    assert workspace["converted_dir"].exists()
    assert academy_conversion.get_conversion_output_dir().exists()

    lock_file = academy_conversion.get_user_conversion_lock_file(workspace["base_dir"])
    with academy_conversion.user_conversion_metadata_lock(workspace["base_dir"]):
        assert lock_file.exists()

    metadata_file = workspace["metadata_file"]
    assert academy_conversion.load_user_conversion_metadata(metadata_file) == []

    academy_conversion.save_user_conversion_metadata(
        metadata_file,
        [{"file_id": "f1"}, "skip"],
    )
    loaded = academy_conversion.load_user_conversion_metadata(metadata_file)
    assert loaded == [{"file_id": "f1"}]

    metadata_file.write_text("not-json", encoding="utf-8")
    assert academy_conversion.load_user_conversion_metadata(metadata_file) == []

    normalized = academy_conversion.normalize_conversion_item(
        {
            "file_id": "x",
            "name": "n",
            "extension": ".txt",
            "size_bytes": "12",
            "category": "source",
            "selected_for_training": 1,
        }
    )
    assert normalized.file_id == "x"
    assert normalized.size_bytes == 12
    assert normalized.selected_for_training is True

    assert academy_conversion.find_conversion_item([{"file_id": "x"}], "x") is not None
    assert academy_conversion.find_conversion_item([{"file_id": "x"}], "y") is None

    assert academy_conversion.build_conversion_file_id(extension="json").endswith(
        ".json"
    )
    assert academy_conversion.build_conversion_file_id(extension=".CSV").endswith(
        ".csv"
    )


def test_records_markdown_and_source_dispatch(tmp_path: Path) -> None:
    records = academy_conversion.records_from_text("instr\n\nout")
    assert records[0]["instruction"] == "instr"
    assert academy_conversion.records_from_text("single")[0]["output"] == "single"
    assert "## Example 1" in academy_conversion.serialize_records_to_markdown(records)

    json_file = tmp_path / "a.json"
    json_file.write_text(
        json.dumps(
            [
                {"instruction": "i", "output": "o"},
                {"prompt": "p", "response": "r"},
            ]
        ),
        encoding="utf-8",
    )
    assert len(academy_conversion.records_from_json_file(json_file)) == 2

    obj_file = tmp_path / "obj.json"
    obj_file.write_text(json.dumps({"output": "r"}), encoding="utf-8")
    assert academy_conversion.records_from_json_file(obj_file)[0]["instruction"]

    invalid_obj = tmp_path / "invalid_obj.json"
    invalid_obj.write_text(json.dumps("str"), encoding="utf-8")
    assert academy_conversion.records_from_json_file(invalid_obj) == []

    jsonl_file = tmp_path / "a.jsonl"
    jsonl_file.write_text(
        '{"instruction":"i","output":"o"}\n'
        '{"prompt":"p","response":"r"}\n'
        "bad-json\n123\n",
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

    md_file = tmp_path / "a.md"
    md_file.write_text("hello", encoding="utf-8")
    txt_file = tmp_path / "a.txt"
    txt_file.write_text("hello-txt", encoding="utf-8")

    assert academy_conversion.source_to_markdown(md_file) == "hello"
    assert academy_conversion.source_to_markdown(txt_file) == "hello-txt"
    assert "```json" in academy_conversion.source_to_markdown(json_file)
    assert academy_conversion.source_to_records(json_file)
    assert academy_conversion.source_to_records(jsonl_file)
    assert academy_conversion.source_to_records(csv_file)
    assert academy_conversion.source_to_records(md_file)

    bad_file = tmp_path / "a.unsupported"
    bad_file.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported source extension"):
        academy_conversion.source_to_markdown(bad_file)


def test_binary_document_and_target_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_file = tmp_path / "a.pdf"
    docx_file = tmp_path / "a.docx"
    doc_file = tmp_path / "a.doc"
    pdf_file.write_text("x", encoding="utf-8")
    docx_file.write_text("x", encoding="utf-8")
    doc_file.write_text("x", encoding="utf-8")

    def _pandoc_ok(_src: Path, out: Path) -> bool:
        out.write_text("converted-md", encoding="utf-8")
        return True

    monkeypatch.setattr(academy_conversion, "convert_with_pandoc", _pandoc_ok)
    assert (
        academy_conversion.markdown_from_binary_document(pdf_file, ".pdf")
        == "converted-md"
    )

    monkeypatch.setattr(academy_conversion, "convert_with_pandoc", lambda *_: False)
    monkeypatch.setattr(
        academy_conversion, "extract_text_from_pdf", lambda _path: "pdf"
    )
    monkeypatch.setattr(
        academy_conversion, "extract_text_from_docx", lambda _path: "docx"
    )

    assert academy_conversion.markdown_from_binary_document(pdf_file, ".pdf") == "pdf"
    assert (
        academy_conversion.markdown_from_binary_document(docx_file, ".docx") == "docx"
    )
    with pytest.raises(ValueError, match="DOC conversion requires Pandoc"):
        academy_conversion.markdown_from_binary_document(doc_file, ".doc")

    records = [{"instruction": "i", "input": "", "output": "o"}]

    out_md = io.StringIO()
    academy_conversion.write_target_markdown(out_md, records)
    assert "## Example 1" in out_md.getvalue()

    out_txt = io.StringIO()
    academy_conversion.write_target_text(out_txt, records)
    assert "i" in out_txt.getvalue()

    out_json = io.StringIO()
    academy_conversion.write_target_json(out_json, records)
    assert out_json.getvalue().startswith("[")

    out_jsonl = io.StringIO()
    academy_conversion.write_target_jsonl(out_jsonl, records)
    assert out_jsonl.getvalue().endswith("\n")

    out_csv = io.StringIO()
    academy_conversion.write_target_csv(out_csv, records)
    assert "instruction,input,output" in out_csv.getvalue()


@patch("venom_core.config.SETTINGS")
def test_write_records_as_target_guards_and_cleanup(
    mock_settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "conv"
    output_dir.mkdir(parents=True, exist_ok=True)
    mock_settings.ACADEMY_CONVERSION_OUTPUT_DIR = str(output_dir)
    mock_settings.ACADEMY_CONVERSION_TARGET_EXTENSIONS = {
        "md": ".md",
        "txt": ".txt",
        "json": ".json",
        "jsonl": ".jsonl",
        "csv": ".csv",
    }

    records = [{"instruction": "i", "input": "", "output": "o"}]
    assert academy_conversion.write_records_as_target(records, "md").suffix == ".md"
    assert academy_conversion.write_records_as_target(records, "txt").suffix == ".txt"
    assert academy_conversion.write_records_as_target(records, "json").suffix == ".json"
    assert (
        academy_conversion.write_records_as_target(records, "jsonl").suffix == ".jsonl"
    )
    assert academy_conversion.write_records_as_target(records, "csv").suffix == ".csv"

    with pytest.raises(ValueError, match="Unsupported target format"):
        academy_conversion.write_records_as_target(records, "bin")

    outside_path = tmp_path / "outside.tmp"
    fd = os.open(outside_path, os.O_RDWR | os.O_CREAT)
    monkeypatch.setattr(
        academy_conversion.tempfile,
        "mkstemp",
        lambda **_kwargs: (fd, str(outside_path)),
    )
    with pytest.raises(ValueError, match="escapes configured output directory"):
        academy_conversion.write_records_as_target(records, "md")
    assert not outside_path.exists()


@patch("venom_core.config.SETTINGS")
def test_write_records_as_target_writer_exception_cleanup(
    mock_settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "conv"
    output_dir.mkdir(parents=True, exist_ok=True)
    mock_settings.ACADEMY_CONVERSION_OUTPUT_DIR = str(output_dir)
    mock_settings.ACADEMY_CONVERSION_TARGET_EXTENSIONS = {
        "md": ".md",
        "txt": ".txt",
        "json": ".json",
        "jsonl": ".jsonl",
        "csv": ".csv",
    }

    def _boom(_out_file: io.TextIOBase, _records: list[dict[str, str]]) -> None:
        raise RuntimeError("writer-boom")

    monkeypatch.setattr(academy_conversion, "write_target_markdown", _boom)

    before = {p.name for p in output_dir.iterdir()}
    with pytest.raises(RuntimeError, match="writer-boom"):
        academy_conversion.write_records_as_target(
            [{"instruction": "i", "input": "", "output": "o"}],
            "md",
        )
    after = {p.name for p in output_dir.iterdir()}
    assert before == after


def test_workspace_path_resolvers_and_existing_file_loader(tmp_path: Path) -> None:
    workspace = {
        "base_dir": tmp_path,
        "metadata_file": tmp_path / "files.json",
        "source_dir": tmp_path / "source",
        "converted_dir": tmp_path / "converted",
    }
    workspace["source_dir"].mkdir(parents=True, exist_ok=True)
    workspace["converted_dir"].mkdir(parents=True, exist_ok=True)

    source_file = workspace["source_dir"] / "src.txt"
    source_file.write_text("x", encoding="utf-8")

    global_converted = tmp_path / "global"
    global_converted.mkdir(parents=True, exist_ok=True)
    global_file = global_converted / "c1.jsonl"
    global_file.write_text("{}", encoding="utf-8")

    assert (
        academy_conversion.resolve_workspace_file_path(
            workspace,
            file_id="src.txt",
            category="source",
            get_conversion_output_dir_fn=lambda: global_converted,
        )
        == source_file.resolve()
    )

    assert (
        academy_conversion.resolve_workspace_file_path(
            workspace,
            file_id="c1.jsonl",
            category="converted",
            get_conversion_output_dir_fn=lambda: global_converted,
        )
        == global_file.resolve()
    )

    legacy_file = workspace["converted_dir"] / "legacy.jsonl"
    legacy_file.write_text("{}", encoding="utf-8")
    assert (
        academy_conversion.resolve_workspace_file_path(
            workspace,
            file_id="legacy.jsonl",
            category="converted",
            get_conversion_output_dir_fn=lambda: global_converted,
        )
        == legacy_file.resolve()
    )

    with pytest.raises(ValueError, match="Invalid file path"):
        academy_conversion.resolve_workspace_file_path(
            workspace,
            file_id="../escape",
            category="source",
            get_conversion_output_dir_fn=lambda: global_converted,
        )

    with pytest.raises(ValueError, match="Invalid file path"):
        academy_conversion.resolve_workspace_file_path(
            workspace,
            file_id="../escape",
            category="converted",
            get_conversion_output_dir_fn=lambda: global_converted,
        )

    with pytest.raises(ValueError, match="Invalid file category"):
        academy_conversion.resolve_workspace_file_path(
            workspace,
            file_id="x",
            category="other",
            get_conversion_output_dir_fn=lambda: global_converted,
        )

    items = [{"file_id": "src.txt", "category": "source"}]
    loaded_item = academy_conversion.load_conversion_item_from_workspace(
        workspace,
        file_id="src.txt",
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: items,
        find_conversion_item_fn=academy_conversion.find_conversion_item,
    )
    assert loaded_item["file_id"] == "src.txt"

    with pytest.raises(FileNotFoundError, match="File not found"):
        academy_conversion.load_conversion_item_from_workspace(
            workspace,
            file_id="missing",
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: items,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
        )

    item, path = academy_conversion.resolve_existing_user_file(
        workspace=workspace,
        file_id="src.txt",
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: items,
        find_conversion_item_fn=academy_conversion.find_conversion_item,
        get_conversion_output_dir_fn=lambda: global_converted,
    )
    assert item["file_id"] == "src.txt"
    assert path.exists()

    custom_item, custom_path = academy_conversion.resolve_existing_user_file(
        workspace=workspace,
        file_id="src.txt",
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: items,
        find_conversion_item_fn=academy_conversion.find_conversion_item,
        resolve_workspace_file_path_fn=lambda _ws: source_file,
    )
    assert custom_item["file_id"] == "src.txt"
    assert custom_path == source_file

    with pytest.raises(FileNotFoundError, match="File not found on disk"):
        academy_conversion.resolve_existing_user_file(
            workspace=workspace,
            file_id="src.txt",
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: items,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
            resolve_workspace_file_path_fn=lambda _ws: workspace["source_dir"]
            / "missing",
        )


@pytest.mark.asyncio
async def test_upload_convert_selection_preview_and_media(tmp_path: Path) -> None:
    workspace = {
        "base_dir": tmp_path,
        "metadata_file": tmp_path / "files.json",
        "source_dir": tmp_path / "source",
        "converted_dir": tmp_path / "converted",
    }
    workspace["source_dir"].mkdir(parents=True, exist_ok=True)
    workspace["converted_dir"].mkdir(parents=True, exist_ok=True)

    items: list[dict[str, object]] = []

    class _Upload:
        def __init__(self, filename: str) -> None:
            self.filename = filename

    async def _persist(**kwargs):
        file_path: Path = kwargs["file_path"]
        filename: str = kwargs["filename"]
        if filename == "persist-err.json":
            return None, {"name": filename, "error": "persist error"}
        file_path.write_text("{}", encoding="utf-8")
        return (2, b"{}"), None

    payload = await academy_conversion.upload_conversion_files_for_user(
        files=[
            _Upload("ok.json"),
            _Upload("invalid.ext"),
            _Upload("persist-err.json"),
            _Upload("skip.json"),
        ],
        workspace=workspace,
        settings=SimpleNamespace(
            ACADEMY_ALLOWED_EXTENSIONS=[".json", ".txt"],
            ACADEMY_ALLOWED_CONVERSION_EXTENSIONS=[".json"],
        ),
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: items,
        save_user_conversion_metadata_fn=lambda _path, updated: items.clear()
        or items.extend(updated),
        validate_upload_filename_fn=lambda file,
        _settings,
        *,
        allowed_extensions=None: (
            file.filename,
            None,
        )
        if file.filename == "ok.json"
        else (
            None,
            {"name": file.filename, "error": "bad ext"},
        )
        if file.filename == "invalid.ext"
        else (
            file.filename,
            None,
        )
        if file.filename == "persist-err.json"
        else (None, None),
        persist_with_limits_fn=_persist,
        build_conversion_file_id_fn=lambda extension=None: f"id{extension or ''}",
        build_conversion_item_fn=academy_conversion.build_conversion_item,
        normalize_conversion_item_fn=lambda item: _Dumpable(
            {"file_id": item["file_id"]}
        ),
    )
    assert payload["uploaded"] == 1
    assert payload["failed"] == 2
    assert payload["success"] is True

    source_path = workspace["source_dir"] / "source-id.json"
    source_path.write_text('{"instruction":"i","output":"o"}', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid file_id"):
        academy_conversion.convert_dataset_source_file(
            file_id="../bad",
            workspace=workspace,
            target_format="jsonl",
            check_path_traversal_fn=lambda _v: False,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: items,
            save_user_conversion_metadata_fn=lambda _path, _payload: None,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
            resolve_workspace_file_path_fn=lambda *_args, **_kwargs: source_path,
            source_to_records_fn=lambda _path: [
                {"instruction": "i", "input": "", "output": "o"}
            ],
            write_records_as_target_fn=lambda _records, _fmt: tmp_path / "out.jsonl",
            build_conversion_item_fn=academy_conversion.build_conversion_item,
        )

    with pytest.raises(FileNotFoundError, match="Source file not found"):
        academy_conversion.convert_dataset_source_file(
            file_id="missing",
            workspace=workspace,
            target_format="jsonl",
            check_path_traversal_fn=lambda _v: True,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: [],
            save_user_conversion_metadata_fn=lambda _path, _payload: None,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
            resolve_workspace_file_path_fn=lambda *_args, **_kwargs: source_path,
            source_to_records_fn=lambda _path: [
                {"instruction": "i", "input": "", "output": "o"}
            ],
            write_records_as_target_fn=lambda _records, _fmt: tmp_path / "out.jsonl",
            build_conversion_item_fn=academy_conversion.build_conversion_item,
        )

    source_items = [
        {"file_id": "source-id", "name": "source.json", "category": "source"}
    ]
    converted_items = [
        {"file_id": "converted-id", "name": "out.jsonl", "category": "converted"}
    ]

    with pytest.raises(ValueError, match="Conversion requires source file"):
        academy_conversion.convert_dataset_source_file(
            file_id="converted-id",
            workspace=workspace,
            target_format="jsonl",
            check_path_traversal_fn=lambda _v: True,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: converted_items,
            save_user_conversion_metadata_fn=lambda _path, _payload: None,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
            resolve_workspace_file_path_fn=lambda *_args, **_kwargs: source_path,
            source_to_records_fn=lambda _path: [
                {"instruction": "i", "input": "", "output": "o"}
            ],
            write_records_as_target_fn=lambda _records, _fmt: tmp_path / "out.jsonl",
            build_conversion_item_fn=academy_conversion.build_conversion_item,
        )

    with pytest.raises(FileNotFoundError, match="Source file not found on disk"):
        academy_conversion.convert_dataset_source_file(
            file_id="source-id",
            workspace=workspace,
            target_format="jsonl",
            check_path_traversal_fn=lambda _v: True,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: source_items,
            save_user_conversion_metadata_fn=lambda _path, _payload: None,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
            resolve_workspace_file_path_fn=lambda *_args, **_kwargs: workspace[
                "source_dir"
            ]
            / "missing.json",
            source_to_records_fn=lambda _path: [
                {"instruction": "i", "input": "", "output": "o"}
            ],
            write_records_as_target_fn=lambda _records, _fmt: tmp_path / "out.jsonl",
            build_conversion_item_fn=academy_conversion.build_conversion_item,
        )

    with pytest.raises(ValueError, match="No valid records produced"):
        academy_conversion.convert_dataset_source_file(
            file_id="source-id",
            workspace=workspace,
            target_format="jsonl",
            check_path_traversal_fn=lambda _v: True,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: source_items,
            save_user_conversion_metadata_fn=lambda _path, _payload: None,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
            resolve_workspace_file_path_fn=lambda *_args, **_kwargs: source_path,
            source_to_records_fn=lambda _path: [],
            write_records_as_target_fn=lambda _records, _fmt: tmp_path / "out.jsonl",
            build_conversion_item_fn=academy_conversion.build_conversion_item,
        )

    written_target = tmp_path / "ok.jsonl"
    written_target.write_text('{"instruction":"i","output":"o"}\n', encoding="utf-8")
    saved_payload: list[list[dict[str, object]]] = []

    source_item, converted_item = academy_conversion.convert_dataset_source_file(
        file_id="source-id",
        workspace=workspace,
        target_format="jsonl",
        check_path_traversal_fn=lambda _v: True,
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: source_items,
        save_user_conversion_metadata_fn=lambda _path, payload: saved_payload.append(
            list(payload)
        ),
        find_conversion_item_fn=academy_conversion.find_conversion_item,
        resolve_workspace_file_path_fn=lambda *_args, **_kwargs: source_path,
        source_to_records_fn=lambda _path: [
            {"instruction": "i", "input": "", "output": "o"}
        ],
        write_records_as_target_fn=lambda _records, _fmt: written_target,
        build_conversion_item_fn=academy_conversion.build_conversion_item,
    )
    assert source_item["file_id"] == "source-id"
    assert converted_item["category"] == "converted"
    assert saved_payload

    with pytest.raises(ValueError, match="Invalid file_id"):
        academy_conversion.set_conversion_training_selection(
            file_id="../bad",
            selected_for_training=True,
            workspace=workspace,
            check_path_traversal_fn=lambda _v: False,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: converted_items,
            save_user_conversion_metadata_fn=lambda _path, _items: None,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
        )

    with pytest.raises(FileNotFoundError, match="File not found"):
        academy_conversion.set_conversion_training_selection(
            file_id="missing",
            selected_for_training=True,
            workspace=workspace,
            check_path_traversal_fn=lambda _v: True,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: [],
            save_user_conversion_metadata_fn=lambda _path, _items: None,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
        )

    with pytest.raises(ValueError, match="Only converted files"):
        academy_conversion.set_conversion_training_selection(
            file_id="source-id",
            selected_for_training=True,
            workspace=workspace,
            check_path_traversal_fn=lambda _v: True,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: source_items,
            save_user_conversion_metadata_fn=lambda _path, _items: None,
            find_conversion_item_fn=academy_conversion.find_conversion_item,
        )

    updated = academy_conversion.set_conversion_training_selection(
        file_id="converted-id",
        selected_for_training=True,
        workspace=workspace,
        check_path_traversal_fn=lambda _v: True,
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: converted_items,
        save_user_conversion_metadata_fn=lambda _path, payload: None,
        find_conversion_item_fn=academy_conversion.find_conversion_item,
    )
    assert updated["selected_for_training"] is True

    selected = academy_conversion.get_selected_converted_file_ids(
        workspace=workspace,
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: [
            {"category": "source", "selected_for_training": True, "file_id": "s"},
            {"category": "converted", "selected_for_training": False, "file_id": "c0"},
            {
                "category": "converted",
                "selected_for_training": True,
                "file_id": "../bad",
            },
            {"category": "converted", "selected_for_training": True, "file_id": "c1"},
        ],
        check_path_traversal_fn=lambda file_id: ".." not in file_id,
    )
    assert selected == ["c1"]

    assert academy_conversion.resolve_conversion_file_ids_for_dataset(
        requested_ids=["a", "b"],
        selected_ids_fn=lambda: ["x"],
    ) == ["a", "b"]
    assert academy_conversion.resolve_conversion_file_ids_for_dataset(
        requested_ids=None,
        selected_ids_fn=lambda: ["x"],
    ) == ["x"]

    listed = academy_conversion.list_conversion_files_for_user(
        user_id="u1",
        workspace=workspace,
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: source_items + converted_items,
        normalize_conversion_item_fn=lambda item: {"id": item["file_id"]},
    )
    assert listed["user_id"] == "u1"
    assert listed["source_files"] == [{"id": "source-id"}]
    assert {"id": "converted-id"} in listed["converted_files"]

    preview_file = tmp_path / "preview.txt"
    preview_file.write_text("abcdef", encoding="utf-8")
    preview, truncated = await academy_conversion.read_text_preview(
        file_path=preview_file,
        max_chars=5,
    )
    assert preview == "abcde"
    assert truncated is True

    assert (
        academy_conversion.guess_media_type(tmp_path / "a.bin")
        == "application/octet-stream"
    )
