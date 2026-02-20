"""Tests for Academy dataset conversion workspace endpoints (task 163)."""

from __future__ import annotations

import builtins
import io
import json
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy as academy_routes


def _build_client() -> TestClient:
    app = FastAPI()
    academy_routes.set_dependencies(
        professor=MagicMock(),
        dataset_curator=MagicMock(),
        gpu_habitat=MagicMock(training_containers={}),
        lessons_store=MagicMock(),
        model_manager=MagicMock(),
    )
    app.include_router(academy_routes.router)
    return TestClient(app)


def test_conversion_upload_and_list(tmp_path):
    client = _build_client()
    with (
        patch("venom_core.config.SETTINGS.ENABLE_ACADEMY", True),
        patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)),
        patch(
            "venom_core.api.routes.academy.require_localhost_request", return_value=None
        ),
    ):
        src_file = io.BytesIO(b"Question\n\nAnswer")
        src_file.name = "sample.txt"
        upload_response = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files={"files": ("sample.txt", src_file, "text/plain")},
            headers={"X-Actor": "tester-1"},
        )
        assert upload_response.status_code == 200
        upload_payload = upload_response.json()
        assert upload_payload["uploaded"] == 1

        list_response = client.get(
            "/api/v1/academy/dataset/conversion/files",
            headers={"X-Actor": "tester-1"},
        )
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["user_id"] == "tester-1"
        assert len(list_payload["source_files"]) == 1
        assert list_payload["source_files"][0]["name"] == "sample.txt"


def test_conversion_convert_preview_and_download(tmp_path):
    client = _build_client()
    with (
        patch("venom_core.config.SETTINGS.ENABLE_ACADEMY", True),
        patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)),
        patch(
            "venom_core.api.routes.academy.require_localhost_request", return_value=None
        ),
    ):
        src_file = io.BytesIO(b"Instruction one\n\nOutput one")
        src_file.name = "source.txt"
        upload_response = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files={"files": ("source.txt", src_file, "text/plain")},
            headers={"X-Actor": "tester-preview"},
        )
        source_file_id = upload_response.json()["files"][0]["file_id"]

        convert_response = client.post(
            f"/api/v1/academy/dataset/conversion/files/{source_file_id}/convert",
            json={"target_format": "md"},
            headers={"X-Actor": "tester-preview"},
        )
        assert convert_response.status_code == 200
        converted_file_id = convert_response.json()["converted_file"]["file_id"]

        preview_response = client.get(
            f"/api/v1/academy/dataset/conversion/files/{converted_file_id}/preview",
            headers={"X-Actor": "tester-preview"},
        )
        assert preview_response.status_code == 200
        assert "Instruction one" in preview_response.json()["preview"]

        download_response = client.get(
            f"/api/v1/academy/dataset/conversion/files/{converted_file_id}/download",
            headers={"X-Actor": "tester-preview"},
        )
        assert download_response.status_code == 200
        assert len(download_response.content) > 0


def test_conversion_preview_rejects_non_text_file(tmp_path):
    client = _build_client()
    with (
        patch("venom_core.config.SETTINGS.ENABLE_ACADEMY", True),
        patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)),
        patch(
            "venom_core.api.routes.academy.require_localhost_request", return_value=None
        ),
    ):
        src_file = io.BytesIO(b"instruction,output\nA,B\n")
        src_file.name = "source.csv"
        upload_response = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files={"files": ("source.csv", src_file, "text/csv")},
            headers={"X-Actor": "tester-csv"},
        )
        file_id = upload_response.json()["files"][0]["file_id"]

        preview_response = client.get(
            f"/api/v1/academy/dataset/conversion/files/{file_id}/preview",
            headers={"X-Actor": "tester-csv"},
        )
        assert preview_response.status_code == 400
        assert (
            "Preview supported only for .txt and .md files"
            in preview_response.json()["detail"]
        )


def test_conversion_helpers_for_records_and_targets(tmp_path):
    txt_path = tmp_path / "sample.txt"
    txt_path.write_text("Instrukcja A\n\nOdpowiedz A", encoding="utf-8")
    records_from_txt = academy_routes._source_to_records(txt_path)  # noqa: SLF001
    assert records_from_txt
    assert records_from_txt[0]["instruction"] == "Instrukcja A"
    assert records_from_txt[0]["output"] == "Odpowiedz A"

    md_path = tmp_path / "sample.md"
    md_path.write_text("## Sekcja\n\nTresc", encoding="utf-8")
    records_from_md = academy_routes._source_to_records(md_path)  # noqa: SLF001
    assert records_from_md

    json_path = tmp_path / "sample.json"
    json_path.write_text(
        json.dumps(
            [{"instruction": "Pytanie", "input": "Kontekst", "output": "Wynik"}]
        ),
        encoding="utf-8",
    )
    records_from_json = academy_routes._source_to_records(json_path)  # noqa: SLF001
    assert records_from_json == [
        {"instruction": "Pytanie", "input": "Kontekst", "output": "Wynik"}
    ]

    jsonl_path = tmp_path / "sample.jsonl"
    jsonl_path.write_text(
        '{"instruction":"A","output":"B"}\n'
        "invalid-line\n"
        '{"prompt":"C","response":"D"}\n',
        encoding="utf-8",
    )
    records_from_jsonl = academy_routes._source_to_records(jsonl_path)  # noqa: SLF001
    assert len(records_from_jsonl) == 2
    assert records_from_jsonl[0]["instruction"] == "A"
    assert records_from_jsonl[1]["output"] == "D"

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "instruction,input,output\nPrompt,Context,Result\n", encoding="utf-8"
    )
    records_from_csv = academy_routes._source_to_records(csv_path)  # noqa: SLF001
    assert records_from_csv == [
        {"instruction": "Prompt", "input": "Context", "output": "Result"}
    ]

    md_out = tmp_path / "out.md"
    txt_out = tmp_path / "out.txt"
    json_out = tmp_path / "out.json"
    jsonl_out = tmp_path / "out.jsonl"
    csv_out = tmp_path / "out.csv"

    academy_routes._write_records_as_target(records_from_csv, "md", md_out)  # noqa: SLF001
    academy_routes._write_records_as_target(records_from_csv, "txt", txt_out)  # noqa: SLF001
    academy_routes._write_records_as_target(records_from_csv, "json", json_out)  # noqa: SLF001
    academy_routes._write_records_as_target(records_from_csv, "jsonl", jsonl_out)  # noqa: SLF001
    academy_routes._write_records_as_target(records_from_csv, "csv", csv_out)  # noqa: SLF001

    assert "Prompt" in md_out.read_text(encoding="utf-8")
    assert "Result" in txt_out.read_text(encoding="utf-8")
    assert json.loads(json_out.read_text(encoding="utf-8"))[0]["output"] == "Result"
    assert (
        json.loads(jsonl_out.read_text(encoding="utf-8").strip())["output"] == "Result"
    )
    assert "instruction,input,output" in csv_out.read_text(encoding="utf-8")


def test_conversion_helpers_markdown_for_data_formats(tmp_path):
    json_path = tmp_path / "payload.json"
    json_path.write_text('{"a":1}', encoding="utf-8")
    jsonl_path = tmp_path / "payload.jsonl"
    jsonl_path.write_text('{"k":"v"}\ninvalid\n', encoding="utf-8")
    csv_path = tmp_path / "payload.csv"
    csv_path.write_text("x,y\n1,2\n", encoding="utf-8")

    md_from_json = academy_routes._source_to_markdown(json_path)  # noqa: SLF001
    md_from_jsonl = academy_routes._source_to_markdown(jsonl_path)  # noqa: SLF001
    md_from_csv = academy_routes._source_to_markdown(csv_path)  # noqa: SLF001

    assert md_from_json.startswith("```json")
    assert "jsonl" in md_from_jsonl
    assert md_from_csv.startswith("```csv")


def test_conversion_helpers_doc_pdf_branches(tmp_path):
    pdf_path = tmp_path / "file.pdf"
    docx_path = tmp_path / "file.docx"
    doc_path = tmp_path / "file.doc"
    pdf_path.write_bytes(b"%PDF fake")
    docx_path.write_bytes(b"DOCX fake")
    doc_path.write_bytes(b"DOC fake")

    with patch(
        "venom_core.api.routes.academy._convert_with_pandoc", return_value=False
    ):
        with patch(
            "venom_core.api.routes.academy._extract_text_from_pdf",
            return_value="pdf-text",
        ):
            assert academy_routes._source_to_markdown(pdf_path) == "pdf-text"  # noqa: SLF001
        with patch(
            "venom_core.api.routes.academy._extract_text_from_docx",
            return_value="docx-text",
        ):
            assert academy_routes._source_to_markdown(docx_path) == "docx-text"  # noqa: SLF001
        try:
            academy_routes._source_to_markdown(doc_path)  # noqa: SLF001
            assert False, "Expected ValueError for legacy .doc without pandoc support"
        except ValueError as exc:
            assert "DOC conversion requires Pandoc" in str(exc)


def test_conversion_helpers_pandoc_success_and_missing_import(tmp_path):
    src = tmp_path / "in.docx"
    out = tmp_path / "out.md"
    src.write_bytes(b"X")
    out.write_text("converted", encoding="utf-8")

    class _P:
        @staticmethod
        def convert_file(*args, **kwargs):
            return None

    with patch.dict("sys.modules", {"pypandoc": _P}):
        assert academy_routes._convert_with_pandoc(src, out) is True  # noqa: SLF001

    with patch(
        "builtins.__import__",
        side_effect=ImportError("no pypandoc"),
    ):
        assert academy_routes._convert_with_pandoc(src, out) is False  # noqa: SLF001


def test_conversion_helpers_metadata_and_workspace(tmp_path):
    with patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)):
        workspace = academy_routes._get_user_conversion_workspace("user_a")  # noqa: SLF001
        assert workspace["base_dir"].exists()
        assert workspace["source_dir"].exists()
        assert workspace["converted_dir"].exists()

        items = [
            {
                "file_id": "f1",
                "name": "n1.txt",
                "extension": ".txt",
                "size_bytes": 10,
                "created_at": "2026-01-01T00:00:00",
                "category": "source",
            }
        ]
        academy_routes._save_user_conversion_metadata(  # noqa: SLF001
            workspace["metadata_file"], items
        )
        loaded = academy_routes._load_user_conversion_metadata(  # noqa: SLF001
            workspace["metadata_file"]
        )
        assert loaded == items
        assert academy_routes._find_conversion_item(loaded, "f1") is not None  # noqa: SLF001
        assert academy_routes._find_conversion_item(loaded, "nope") is None  # noqa: SLF001
        norm = academy_routes._normalize_conversion_item(loaded[0])  # noqa: SLF001
        assert norm.file_id == "f1"
        generated_id = academy_routes._build_conversion_file_id(  # noqa: SLF001
            extension=".txt"
        )
        assert generated_id.endswith(".txt")
        assert "abc" not in generated_id

        workspace["metadata_file"].write_text("{bad-json", encoding="utf-8")
        assert (
            academy_routes._load_user_conversion_metadata(workspace["metadata_file"])
            == []
        )  # noqa: SLF001


def test_conversion_route_negative_paths_and_limits(tmp_path):
    client = _build_client()
    with (
        patch("venom_core.config.SETTINGS.ENABLE_ACADEMY", True),
        patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)),
        patch("venom_core.config.SETTINGS.ACADEMY_MAX_UPLOADS_PER_REQUEST", 1),
        patch(
            "venom_core.api.routes.academy.require_localhost_request", return_value=None
        ),
    ):
        no_file_response = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            headers={"X-Actor": "limit-tester"},
        )
        assert no_file_response.status_code == 400

        too_many_response = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files=[
                ("files", ("a.txt", io.BytesIO(b"a"), "text/plain")),
                ("files", ("b.txt", io.BytesIO(b"b"), "text/plain")),
            ],
            headers={"X-Actor": "limit-tester"},
        )
        assert too_many_response.status_code == 400

        invalid_convert = client.post(
            "/api/v1/academy/dataset/conversion/files/../bad/convert",
            json={"target_format": "md"},
            headers={"X-Actor": "limit-tester"},
        )
        assert invalid_convert.status_code in {400, 404}

        invalid_preview = client.get(
            "/api/v1/academy/dataset/conversion/files/../bad/preview",
            headers={"X-Actor": "limit-tester"},
        )
        assert invalid_preview.status_code in {400, 404}

        invalid_download = client.get(
            "/api/v1/academy/dataset/conversion/files/../bad/download",
            headers={"X-Actor": "limit-tester"},
        )
        assert invalid_download.status_code in {400, 404}


def test_conversion_route_convert_errors_for_missing_or_invalid_content(tmp_path):
    client = _build_client()
    with (
        patch("venom_core.config.SETTINGS.ENABLE_ACADEMY", True),
        patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)),
        patch(
            "venom_core.api.routes.academy.require_localhost_request", return_value=None
        ),
    ):
        missing_response = client.post(
            "/api/v1/academy/dataset/conversion/files/20260101_x.txt/convert",
            json={"target_format": "md"},
            headers={"X-Actor": "missing"},
        )
        assert missing_response.status_code == 404

        upload_response = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files={"files": ("invalid.json", io.BytesIO(b"{"), "application/json")},
            headers={"X-Actor": "invalid-json"},
        )
        file_id = upload_response.json()["files"][0]["file_id"]

        bad_convert_response = client.post(
            f"/api/v1/academy/dataset/conversion/files/{file_id}/convert",
            json={"target_format": "md"},
            headers={"X-Actor": "invalid-json"},
        )
        assert bad_convert_response.status_code == 400
        assert "Conversion failed" in bad_convert_response.json()["detail"]


def test_conversion_user_isolation_between_actors(tmp_path):
    client = _build_client()
    with (
        patch("venom_core.config.SETTINGS.ENABLE_ACADEMY", True),
        patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)),
        patch(
            "venom_core.api.routes.academy.require_localhost_request", return_value=None
        ),
    ):
        resp1 = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files={"files": ("user1.txt", io.BytesIO(b"user1"), "text/plain")},
            headers={"X-Actor": "user-1"},
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files={"files": ("user2.txt", io.BytesIO(b"user2"), "text/plain")},
            headers={"X-Actor": "user-2"},
        )
        assert resp2.status_code == 200

        list1 = client.get(
            "/api/v1/academy/dataset/conversion/files",
            headers={"X-Actor": "user-1"},
        )
        list2 = client.get(
            "/api/v1/academy/dataset/conversion/files",
            headers={"X-Actor": "user-2"},
        )
        assert list1.status_code == 200
        assert list2.status_code == 200
        names1 = [f["name"] for f in list1.json().get("source_files", [])]
        names2 = [f["name"] for f in list2.json().get("source_files", [])]
        assert "user1.txt" in names1
        assert "user2.txt" not in names1
        assert "user2.txt" in names2
        assert "user1.txt" not in names2


def test_conversion_rejects_invalid_target_format(tmp_path):
    client = _build_client()
    with (
        patch("venom_core.config.SETTINGS.ENABLE_ACADEMY", True),
        patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)),
        patch(
            "venom_core.api.routes.academy.require_localhost_request", return_value=None
        ),
    ):
        upload_response = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files={"files": ("source.txt", io.BytesIO(b"A\n\nB"), "text/plain")},
            headers={"X-Actor": "tester-invalid-format"},
        )
        source_file_id = upload_response.json()["files"][0]["file_id"]
        convert_response = client.post(
            f"/api/v1/academy/dataset/conversion/files/{source_file_id}/convert",
            json={"target_format": "xml"},
            headers={"X-Actor": "tester-invalid-format"},
        )
        assert convert_response.status_code == 422


def test_conversion_preview_reports_truncation_for_large_text(tmp_path):
    client = _build_client()
    with (
        patch("venom_core.config.SETTINGS.ENABLE_ACADEMY", True),
        patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)),
        patch(
            "venom_core.api.routes.academy.require_localhost_request", return_value=None
        ),
    ):
        large_text = ("x" * 22000).encode("utf-8")
        upload_response = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files={"files": ("big.txt", io.BytesIO(large_text), "text/plain")},
            headers={"X-Actor": "preview-large"},
        )
        file_id = upload_response.json()["files"][0]["file_id"]
        preview_response = client.get(
            f"/api/v1/academy/dataset/conversion/files/{file_id}/preview",
            headers={"X-Actor": "preview-large"},
        )
        assert preview_response.status_code == 200
        payload = preview_response.json()
        assert payload["truncated"] is True
        assert len(payload["preview"]) == 20000


def test_conversion_pdf_docx_missing_optional_dependency_errors(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    docx_path = tmp_path / "sample.docx"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    docx_path.write_bytes(b"PK\x03\x04")

    original_import = builtins.__import__

    def _deny_optional(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"pypdf", "docx"}:
            raise ImportError(f"missing {name}")
        return original_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=_deny_optional):
        try:
            academy_routes._extract_text_from_pdf(pdf_path)  # noqa: SLF001
            assert False, "Expected ValueError for missing pypdf"
        except ValueError as exc:
            assert "pypdf" in str(exc)

        try:
            academy_routes._extract_text_from_docx(docx_path)  # noqa: SLF001
            assert False, "Expected ValueError for missing python-docx"
        except ValueError as exc:
            assert "python-docx" in str(exc)


def test_conversion_mark_converted_file_for_training(tmp_path):
    client = _build_client()
    with (
        patch("venom_core.config.SETTINGS.ENABLE_ACADEMY", True),
        patch("venom_core.config.SETTINGS.ACADEMY_USER_DATA_DIR", str(tmp_path)),
        patch(
            "venom_core.api.routes.academy.require_localhost_request", return_value=None
        ),
    ):
        upload_response = client.post(
            "/api/v1/academy/dataset/conversion/upload",
            files={"files": ("source.txt", io.BytesIO(b"A\n\nB"), "text/plain")},
            headers={"X-Actor": "training-select"},
        )
        source_file_id = upload_response.json()["files"][0]["file_id"]
        convert_response = client.post(
            f"/api/v1/academy/dataset/conversion/files/{source_file_id}/convert",
            json={"target_format": "md"},
            headers={"X-Actor": "training-select"},
        )
        assert convert_response.status_code == 200
        converted_file_id = convert_response.json()["converted_file"]["file_id"]

        mark_response = client.post(
            f"/api/v1/academy/dataset/conversion/files/{converted_file_id}/training-selection",
            json={"selected_for_training": True},
            headers={"X-Actor": "training-select"},
        )
        assert mark_response.status_code == 200
        assert mark_response.json()["selected_for_training"] is True

        list_response = client.get(
            "/api/v1/academy/dataset/conversion/files",
            headers={"X-Actor": "training-select"},
        )
        assert list_response.status_code == 200
        converted_entries = list_response.json()["converted_files"]
        marked_entry = next(
            entry
            for entry in converted_entries
            if entry["file_id"] == converted_file_id
        )
        assert marked_entry["selected_for_training"] is True
