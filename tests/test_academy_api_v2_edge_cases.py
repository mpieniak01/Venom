"""Testy edge cases dla Academy API v2 - podniesienie pokrycia."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.api.routes import academy as academy_routes

# ==================== Ingest File Edge Cases ====================


def test_ingest_jsonl_with_empty_lines(tmp_path):
    """Test ingestowania JSONL z pustymi liniami"""
    from venom_core.api.routes.academy import _ingest_upload_file

    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text(
        '\n\n{"instruction": "test instruction 1", "input": "", "output": "output result 1"}\n\n\n{"instruction": "test instruction 2", "input": "", "output": "output result 2"}\n\n'
    )

    mock_curator = MagicMock()
    mock_curator.examples = []
    count = _ingest_upload_file(mock_curator, jsonl_file)

    assert count == 2
    assert len(mock_curator.examples) == 2


def test_ingest_jsonl_with_invalid_lines(tmp_path):
    """Test ingestowania JSONL z nieprawidłowymi liniami"""
    from venom_core.api.routes.academy import _ingest_upload_file

    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text(
        '{"instruction": "test instruction 1", "input": "", "output": "output result 1"}\n'
        "not valid json\n"
        '{"instruction": "test instruction 2", "input": "", "output": "output result 2"}\n'
    )

    mock_curator = MagicMock()
    mock_curator.examples = []
    count = _ingest_upload_file(mock_curator, jsonl_file)

    # Powinien pominąć nieprawidłową linię
    assert count == 2


def test_ingest_json_array(tmp_path):
    """Test ingestowania JSON array"""
    from venom_core.api.routes.academy import _ingest_upload_file

    json_file = tmp_path / "test.json"
    json_file.write_text(
        json.dumps(
            [
                {
                    "instruction": "test instruction 1",
                    "input": "",
                    "output": "output result 1",
                },
                {
                    "instruction": "test instruction 2",
                    "input": "",
                    "output": "output result 2",
                },
            ]
        )
    )

    mock_curator = MagicMock()
    mock_curator.examples = []
    count = _ingest_upload_file(mock_curator, json_file)

    assert count == 2


def test_ingest_json_single_object(tmp_path):
    """Test ingestowania pojedynczego JSON object"""
    from venom_core.api.routes.academy import _ingest_upload_file

    json_file = tmp_path / "test.json"
    json_file.write_text(
        json.dumps(
            {
                "instruction": "test instruction here",
                "input": "",
                "output": "output result here",
            }
        )
    )

    mock_curator = MagicMock()
    mock_curator.examples = []
    count = _ingest_upload_file(mock_curator, json_file)

    assert count == 1


def test_ingest_markdown(tmp_path):
    """Test ingestowania pliku Markdown"""
    from venom_core.api.routes.academy import _ingest_upload_file

    md_file = tmp_path / "test.md"
    md_file.write_text(
        "What is Python programming?\n\n"
        "Python is a high-level programming language.\n\n"
        "What is FastAPI framework?\n\n"
        "FastAPI is a modern web framework for Python."
    )

    mock_curator = MagicMock()
    mock_curator.examples = []
    count = _ingest_upload_file(mock_curator, md_file)

    assert count == 2
    assert mock_curator.examples[0]["instruction"] == "What is Python programming?"
    assert (
        mock_curator.examples[0]["output"]
        == "Python is a high-level programming language."
    )


def test_ingest_txt(tmp_path):
    """Test ingestowania pliku TXT"""
    from venom_core.api.routes.academy import _ingest_upload_file

    txt_file = tmp_path / "test.txt"
    txt_file.write_text(
        "Question number 1 here\n\nAnswer number 1 here\n\nQuestion number 2 here\n\nAnswer number 2 here"
    )

    mock_curator = MagicMock()
    mock_curator.examples = []
    count = _ingest_upload_file(mock_curator, txt_file)

    assert count == 2


def test_ingest_csv(tmp_path):
    """Test ingestowania pliku CSV"""
    from venom_core.api.routes.academy import _ingest_upload_file

    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "instruction,input,output\n"
        '"What is Artificial Intelligence?","","AI is machine intelligence simulation"\n'
        '"What is Machine Learning here?","","ML is a subset of AI technologies"\n'
    )

    mock_curator = MagicMock()
    mock_curator.examples = []
    count = _ingest_upload_file(mock_curator, csv_file)

    assert count == 2


def test_ingest_csv_with_alternative_columns(tmp_path):
    """Test ingestowania CSV z alternatywnymi nazwami kolumn"""
    from venom_core.api.routes.academy import _ingest_upload_file

    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "prompt,response\n"
        '"What is Artificial Intelligence?","AI is machine intelligence simulation"\n'
    )

    mock_curator = MagicMock()
    mock_curator.examples = []
    count = _ingest_upload_file(mock_curator, csv_file)

    assert count == 1
    assert mock_curator.examples[0]["instruction"] == "What is Artificial Intelligence?"
    assert mock_curator.examples[0]["output"] == "AI is machine intelligence simulation"


def test_ingest_markdown_with_odd_sections(tmp_path):
    """Test ingestowania MD z nieparzystą liczbą sekcji"""
    from venom_core.api.routes.academy import _ingest_upload_file

    md_file = tmp_path / "test.md"
    # Tylko 3 sekcje - ostatnia nie będzie miała pary
    md_file.write_text(
        "Question number 1 goes here\n\nAnswer number 1 is here\n\nOrphan section without pair"
    )

    mock_curator = MagicMock()
    mock_curator.examples = []
    count = _ingest_upload_file(mock_curator, md_file)

    # Powinien zignorować orphan section
    assert count == 1


# ==================== Validation Edge Cases ====================


def test_validate_training_record_missing_fields():
    """Test walidacji rekordu bez wymaganych pól"""
    from venom_core.api.routes.academy import _validate_training_record

    # Brak instruction
    assert not _validate_training_record({"input": "", "output": "test output here"})

    # Brak output
    assert not _validate_training_record(
        {"instruction": "test instruction", "input": ""}
    )

    # Puste instruction
    assert not _validate_training_record(
        {"instruction": "", "input": "", "output": "test output here"}
    )

    # Puste output
    assert not _validate_training_record(
        {"instruction": "test instruction", "input": "", "output": ""}
    )

    # Too short instruction (< 10 chars)
    assert not _validate_training_record(
        {"instruction": "short", "input": "", "output": "test output here"}
    )

    # Too short output (< 10 chars)
    assert not _validate_training_record(
        {"instruction": "test instruction", "input": "", "output": "short"}
    )


def test_validate_training_record_valid():
    """Test walidacji poprawnego rekordu"""
    from venom_core.api.routes.academy import _validate_training_record

    # Poprawny rekord (obie wartości >= 10 chars)
    result = _validate_training_record(
        {
            "instruction": "test instruction here",
            "input": "",
            "output": "result output here",
        }
    )
    assert result is True

    # Z inputem
    result = _validate_training_record(
        {
            "instruction": "test instruction here",
            "input": "context info",
            "output": "result output here",
        }
    )
    assert result is True


# ==================== Upload Metadata Helpers ====================


def test_upload_metadata_roundtrip_with_lock(tmp_path):
    """Zapis i odczyt metadata uploadów powinien działać poprawnie."""
    with patch("venom_core.config.SETTINGS.ACADEMY_TRAINING_DIR", str(tmp_path)):
        academy_routes._save_upload_metadata(
            {
                "id": "file-1",
                "name": "a.jsonl",
                "size_bytes": 10,
                "mime": "application/jsonl",
                "created_at": "2026-02-13T12:00:00",
                "status": "ready",
                "records_estimate": 1,
                "sha256": "abc",
            }
        )
        academy_routes._save_upload_metadata(
            {
                "id": "file-2",
                "name": "b.txt",
                "size_bytes": 12,
                "mime": "text/plain",
                "created_at": "2026-02-13T12:00:01",
                "status": "ready",
                "records_estimate": 2,
                "sha256": "def",
            }
        )

        uploads = academy_routes._load_uploads_metadata()

    assert len(uploads) == 2
    assert {u["id"] for u in uploads} == {"file-1", "file-2"}


def test_load_uploads_metadata_ignores_invalid_lines(tmp_path):
    """Uszkodzona linia metadata nie powinna wywalić całego odczytu."""
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = uploads_dir / "metadata.jsonl"
    metadata_file.write_text('{"id":"ok"}\nINVALID\n', encoding="utf-8")

    with patch("venom_core.config.SETTINGS.ACADEMY_TRAINING_DIR", str(tmp_path)):
        uploads = academy_routes._load_uploads_metadata()

    # Funkcja zachowuje poprawnie sparsowane rekordy sprzed błędnej linii.
    assert uploads == [{"id": "ok"}]


def test_delete_upload_metadata_filters_selected_id(tmp_path):
    """Usunięcie metadata powinno zostawić tylko pozostałe rekordy."""
    with patch("venom_core.config.SETTINGS.ACADEMY_TRAINING_DIR", str(tmp_path)):
        academy_routes._save_upload_metadata({"id": "keep", "name": "k"})
        academy_routes._save_upload_metadata({"id": "drop", "name": "d"})

        academy_routes._delete_upload_metadata("drop")
        uploads = academy_routes._load_uploads_metadata()

    assert len(uploads) == 1
    assert uploads[0]["id"] == "keep"


def test_delete_upload_metadata_cleanup_temp_on_replace_error(tmp_path):
    """Przy błędzie replace plik tymczasowy powinien zostać posprzątany."""
    with patch("venom_core.config.SETTINGS.ACADEMY_TRAINING_DIR", str(tmp_path)):
        academy_routes._save_upload_metadata({"id": "x", "name": "x"})
        metadata_file = academy_routes._get_uploads_metadata_file()
        tmp_file = metadata_file.with_suffix(".tmp")

        with patch("pathlib.Path.replace", side_effect=OSError("replace-fail")):
            academy_routes._delete_upload_metadata("x")

        assert not tmp_file.exists()


@pytest.mark.asyncio
async def test_upload_dataset_files_normalizes_non_string_tag_and_description(tmp_path):
    class _Form:
        def getlist(self, key):
            if key == "files":
                return [object()]
            return []

        def get(self, key, default=None):
            if key == "tag":
                return object()
            if key == "description":
                return object()
            return default

    class _Req:
        async def form(self):
            return _Form()

    with (
        patch("venom_core.api.routes.academy._ensure_academy_enabled"),
        patch("venom_core.api.routes.academy.require_localhost_request"),
        patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path),
        patch(
            "venom_core.api.routes.academy._process_uploaded_file",
            new=AsyncMock(return_value=({"id": "f1"}, None)),
        ) as process_mock,
    ):
        result = await academy_routes.upload_dataset_files(_Req())

    assert result["success"] is True
    process_mock.assert_awaited_once()
    call_kwargs = process_mock.await_args.kwargs
    assert call_kwargs["tag"] == "user-upload"
    assert call_kwargs["description"] == ""
