"""Testy jednostkowe dla Academy API v2 (upload, scope, preview)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy as academy_routes


@pytest.fixture
def mock_professor():
    return MagicMock()


@pytest.fixture
def mock_dataset_curator():
    mock = MagicMock()
    mock.clear = MagicMock()
    mock.examples = []
    mock.collect_from_lessons = MagicMock(return_value=150)
    mock.collect_from_git_history = MagicMock(return_value=50)
    mock.collect_from_task_history = MagicMock(return_value=30)
    mock.filter_low_quality = MagicMock(return_value=10)
    mock.save_dataset = MagicMock(return_value="./data/training/dataset_123.jsonl")
    mock.get_statistics = MagicMock(
        return_value={
            "total_examples": 220,
            "avg_input_length": 250,
            "avg_output_length": 180,
        }
    )
    return mock


@pytest.fixture
def mock_gpu_habitat():
    mock = MagicMock()
    mock.training_containers = {}
    mock.is_gpu_available = MagicMock(return_value=True)
    return mock


@pytest.fixture
def mock_lessons_store():
    mock = MagicMock()
    mock.get_statistics = MagicMock(return_value={"total_lessons": 250})
    return mock


@pytest.fixture
def mock_model_manager():
    return MagicMock()


@pytest.fixture
def app_with_academy(
    mock_professor,
    mock_dataset_curator,
    mock_gpu_habitat,
    mock_lessons_store,
    mock_model_manager,
):
    app = FastAPI()
    academy_routes.set_dependencies(
        professor=mock_professor,
        dataset_curator=mock_dataset_curator,
        gpu_habitat=mock_gpu_habitat,
        lessons_store=mock_lessons_store,
        model_manager=mock_model_manager,
    )
    app.include_router(academy_routes.router)
    return app


@pytest.fixture
def client(app_with_academy):
    # Bypass localhost guard dla testów
    with patch(
        "venom_core.api.routes.academy.require_localhost_request", return_value=None
    ):
        yield TestClient(app_with_academy)


@pytest.fixture
def strict_client(app_with_academy):
    # Nie bypass localhost guard - testuje go
    yield TestClient(app_with_academy)


# ==================== Upload Tests ====================


def test_upload_files_success(client, tmp_path):
    """Test upload plików - success case"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        with patch("venom_core.api.routes.academy._save_upload_metadata"):
            # Przygotuj plik testowy
            test_file = io.BytesIO(b'{"instruction":"test","input":"","output":"test output"}')
            test_file.name = "test.jsonl"

            response = client.post(
                "/api/v1/academy/dataset/upload",
                files={"files": ("test.jsonl", test_file, "application/jsonl")},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["uploaded"] == 1
            assert len(data["files"]) == 1
            assert data["files"][0]["name"] == "test.jsonl"


def test_upload_invalid_extension(client, tmp_path):
    """Test upload pliku z niepoprawnym rozszerzeniem"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        test_file = io.BytesIO(b"malicious code")
        test_file.name = "malware.exe"

        response = client.post(
            "/api/v1/academy/dataset/upload",
            files={"files": ("malware.exe", test_file, "application/octet-stream")},
        )

        assert response.status_code == 400
        assert "Invalid file extension" in response.json()["detail"]


def test_upload_path_traversal(client, tmp_path):
    """Test path traversal protection"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        test_file = io.BytesIO(b"content")
        test_file.name = "../../../etc/passwd"

        response = client.post(
            "/api/v1/academy/dataset/upload",
            files={"files": ("../../../etc/passwd", test_file, "text/plain")},
        )

        assert response.status_code == 400
        assert "path traversal" in response.json()["detail"].lower()


def test_upload_file_too_large(client, tmp_path):
    """Test upload pliku za dużego"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        # Utwórz duży plik (30MB)
        large_content = b"x" * (30 * 1024 * 1024)
        test_file = io.BytesIO(large_content)
        test_file.name = "large.jsonl"

        response = client.post(
            "/api/v1/academy/dataset/upload",
            files={"files": ("large.jsonl", test_file, "application/jsonl")},
        )

        assert response.status_code == 400
        assert "too large" in response.json()["detail"].lower()


def test_upload_localhost_only(strict_client, tmp_path):
    """Test że upload wymaga localhost"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        test_file = io.BytesIO(b"content")
        test_file.name = "test.jsonl"

        # strict_client nie ma bypass localhost guard
        response = strict_client.post(
            "/api/v1/academy/dataset/upload",
            files={"files": ("test.jsonl", test_file, "application/jsonl")},
        )

        assert response.status_code == 403


def test_upload_json_array_records_estimate(client, tmp_path):
    """Test uploadu JSON array - szacowanie rekordów"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        json_data = [{"instruction": "test1", "output": "out1"}, {"instruction": "test2", "output": "out2"}]
        content = json.dumps(json_data).encode()
        
        files = {
            "files": ("test.json", io.BytesIO(content), "application/json")
        }

        response = client.post("/api/v1/academy/dataset/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        # Should estimate 2 records
        assert data["files"][0]["records_estimate"] >= 1


def test_upload_json_single_object_records_estimate(client, tmp_path):
    """Test uploadu pojedynczego JSON - szacowanie 1 rekord"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        json_data = {"instruction": "test", "output": "out"}
        content = json.dumps(json_data).encode()
        
        files = {
            "files": ("test.json", io.BytesIO(content), "application/json")
        }

        response = client.post("/api/v1/academy/dataset/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        # Single object should estimate 1 record
        assert data["files"][0]["records_estimate"] == 1


def test_upload_markdown_records_estimate(client, tmp_path):
    """Test uploadu Markdown - szacowanie rekordów"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        md_content = "Question 1\n\nAnswer 1\n\nQuestion 2\n\nAnswer 2".encode()
        
        files = {
            "files": ("test.md", io.BytesIO(md_content), "text/markdown")
        }

        response = client.post("/api/v1/academy/dataset/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        # Should estimate records based on double newlines
        assert data["files"][0]["records_estimate"] >= 1


def test_upload_txt_records_estimate(client, tmp_path):
    """Test uploadu TXT - szacowanie rekordów"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        txt_content = "Section 1\n\nSection 2\n\nSection 3".encode()
        
        files = {
            "files": ("test.txt", io.BytesIO(txt_content), "text/plain")
        }

        response = client.post("/api/v1/academy/dataset/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["records_estimate"] >= 1


# ==================== List/Delete Uploads Tests ====================


def test_list_uploads(client):
    """Test listowania uploadów"""
    mock_uploads = [
        {
            "id": "file1",
            "name": "test1.jsonl",
            "size_bytes": 1024,
            "mime": "application/jsonl",
            "created_at": "2024-01-01T00:00:00",
            "status": "ready",
            "records_estimate": 10,
            "sha256": "abc123",
        }
    ]

    with patch(
        "venom_core.api.routes.academy._load_uploads_metadata",
        return_value=mock_uploads,
    ):
        response = client.get("/api/v1/academy/dataset/uploads")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "test1.jsonl"


def test_delete_upload_success(client, tmp_path):
    """Test usuwania uploadu"""
    test_file = tmp_path / "test_file.jsonl"
    test_file.write_text("test")

    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        with patch("venom_core.api.routes.academy._delete_upload_metadata"):
            response = client.delete("/api/v1/academy/dataset/uploads/test_file.jsonl")

            assert response.status_code == 200
            assert response.json()["success"] is True
            assert not test_file.exists()


def test_delete_upload_not_found(client, tmp_path):
    """Test usuwania nieistniejącego uploadu"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        response = client.delete("/api/v1/academy/dataset/uploads/nonexistent.jsonl")

        assert response.status_code == 404


# ==================== Preview Tests ====================


def test_preview_dataset(client, mock_dataset_curator):
    """Test preview datasetu"""
    # Przygotuj przykłady w curator
    mock_dataset_curator.examples = [
        {"instruction": "test instruction 1", "input": "", "output": "output result 1"},
        {"instruction": "test instruction 2", "input": "", "output": "output result 2"},
    ]

    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=Path("/tmp")):
        response = client.post(
            "/api/v1/academy/dataset/preview",
            json={
                "include_lessons": True,
                "include_git": False,
                "lessons_limit": 100,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_examples" in data
        assert "by_source" in data
        assert "warnings" in data
        assert "samples" in data


def test_preview_with_low_examples_warning(client, mock_dataset_curator):
    """Test preview z ostrzeżeniem o małej liczbie przykładów"""
    # Mock curator stats to return less than 50 examples
    mock_dataset_curator.get_statistics = MagicMock(
        return_value={
            "total_examples": 30,
            "avg_input_length": 100,
            "avg_output_length": 80,
        }
    )
    mock_dataset_curator.examples = []

    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=Path("/tmp")):
        response = client.post(
            "/api/v1/academy/dataset/preview",
            json={
                "include_lessons": False,
                "include_git": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Should have warning about low number of examples
        assert len(data["warnings"]) > 0
        assert any("low number" in w.lower() for w in data["warnings"])


def test_preview_with_uploads(client, mock_dataset_curator, tmp_path):
    """Test preview z uploadami"""
    # Create a test upload file
    upload_file = tmp_path / "test.jsonl"
    upload_file.write_text('{"instruction": "test instruction here", "input": "", "output": "output result here"}\n')

    mock_dataset_curator.examples = [
        {"instruction": "test instruction here", "input": "", "output": "output result here"}
    ]

    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        response = client.post(
            "/api/v1/academy/dataset/preview",
            json={
                "include_lessons": False,
                "include_git": False,
                "upload_ids": ["test.jsonl"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "by_source" in data
        assert "uploads" in data["by_source"]


def test_preview_with_long_output_truncation(client, mock_dataset_curator):
    """Test preview obcina długie outputy"""
    # Create an example with very long output
    long_output = "x" * 300  # More than 200 chars
    mock_dataset_curator.examples = [
        {"instruction": "test instruction here", "input": "", "output": long_output}
    ]

    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=Path("/tmp")):
        response = client.post(
            "/api/v1/academy/dataset/preview",
            json={
                "include_lessons": False,
                "include_git": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Check that output is truncated with "..."
        if data["samples"]:
            assert len(data["samples"][0]["output"]) <= 203  # 200 chars + "..."
            assert data["samples"][0]["output"].endswith("...")


def test_preview_with_git_and_task_history(client, mock_dataset_curator):
    """Test preview z git i task history"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=Path("/tmp")):
        response = client.post(
            "/api/v1/academy/dataset/preview",
            json={
                "include_lessons": False,
                "include_git": True,
                "include_task_history": True,
                "git_commits_limit": 50,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "by_source" in data
        # Check that the curator methods were called
        mock_dataset_curator.collect_from_git_history.assert_called_once_with(max_commits=50)
        mock_dataset_curator.collect_from_task_history.assert_called_once()


def test_preview_with_missing_upload_warning(client, mock_dataset_curator, tmp_path):
    """Test preview z ostrzeżeniem o brakującym uploadzie"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        response = client.post(
            "/api/v1/academy/dataset/preview",
            json={
                "include_lessons": False,
                "include_git": False,
                "upload_ids": ["nonexistent.jsonl"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Should have warning about missing upload
        assert len(data["warnings"]) > 0
        assert any("not found" in w.lower() for w in data["warnings"])


def test_preview_with_failed_ingest_warning(client, mock_dataset_curator, tmp_path):
    """Test preview z ostrzeżeniem o failed ingest"""
    # Create a file that will fail to ingest
    bad_file = tmp_path / "bad.jsonl"
    bad_file.write_text('{"instruction": "test", "output": "test"}\n')

    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        with patch(
            "venom_core.api.routes.academy._ingest_upload_file",
            side_effect=Exception("Ingest error"),
        ):
            response = client.post(
                "/api/v1/academy/dataset/preview",
                json={
                    "include_lessons": False,
                    "include_git": False,
                    "upload_ids": ["bad.jsonl"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            # Should have warning about failed ingest
            assert len(data["warnings"]) > 0
            assert any("failed to ingest" in w.lower() for w in data["warnings"])


# ==================== Trainable Models Tests ====================


def test_get_trainable_models(client):
    """Test endpointu modeli trenowalnych"""
    response = client.get("/api/v1/academy/models/trainable")

    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    
    # Sprawdź, że są modele trainable i non-trainable
    trainable_count = sum(1 for m in data if m["trainable"])
    non_trainable_count = sum(1 for m in data if not m["trainable"])
    
    assert trainable_count > 0
    assert non_trainable_count > 0
    
    # Sprawdź struktur modelu
    model = data[0]
    assert "model_id" in model
    assert "label" in model
    assert "provider" in model
    assert "trainable" in model
    assert "recommended" in model


# ==================== Curate with Scope Tests ====================


def test_curate_with_scope(client, mock_dataset_curator, tmp_path):
    """Test kuracji z wybranym scope"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        response = client.post(
            "/api/v1/academy/dataset",
            json={
                "include_lessons": True,
                "include_git": False,
                "include_task_history": True,
                "lessons_limit": 100,
                "upload_ids": [],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "statistics" in data
        assert "by_source" in data["statistics"]


def test_curate_with_uploads(client, mock_dataset_curator, tmp_path):
    """Test kuracji z uploadami"""
    # Create a test upload file
    upload_file = tmp_path / "test.jsonl"
    upload_file.write_text('{"instruction": "test instruction here", "input": "", "output": "output result here"}\n')

    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        response = client.post(
            "/api/v1/academy/dataset",
            json={
                "include_lessons": False,
                "include_git": False,
                "upload_ids": ["test.jsonl"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


def test_curate_with_git(client, mock_dataset_curator, tmp_path):
    """Test kuracji z git history"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        response = client.post(
            "/api/v1/academy/dataset",
            json={
                "include_lessons": False,
                "include_git": True,
                "git_commits_limit": 75,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Verify git_commits_limit was passed correctly
        mock_dataset_curator.collect_from_git_history.assert_called_with(max_commits=75)


def test_curate_with_missing_upload_continues(client, mock_dataset_curator, tmp_path):
    """Test kuracji z brakującym uploadem - powinien kontynuować"""
    with patch("venom_core.api.routes.academy._get_uploads_dir", return_value=tmp_path):
        response = client.post(
            "/api/v1/academy/dataset",
            json={
                "include_lessons": False,
                "include_git": False,
                "upload_ids": ["nonexistent.jsonl"],
            },
        )

        # Should succeed despite missing upload
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# ==================== Training Validation Tests ====================


def test_train_with_trainable_model(client, tmp_path):
    """Test treningu z trenowalnym modelem - powinien przejść walidację"""
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text('{"instruction":"test","input":"","output":"test"}')

    with patch("venom_core.api.routes.academy._get_gpu_habitat") as mock_habitat:
        mock_habitat_instance = MagicMock()
        mock_habitat_instance.run_training_job = MagicMock(
            return_value={
                "job_name": "test_job",
                "container_id": "abc123",
            }
        )
        mock_habitat.return_value = mock_habitat_instance

        response = client.post(
            "/api/v1/academy/train",
            json={
                "dataset_path": str(dataset_path),
                "base_model": "unsloth/Phi-3-mini-4k-instruct",
                "lora_rank": 16,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


def test_train_with_non_trainable_model(client, tmp_path):
    """Test treningu z nietrenowalnym modelem - powinien zwrócić 400"""
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text('{"instruction":"test","input":"","output":"test"}')

    response = client.post(
        "/api/v1/academy/train",
        json={
            "dataset_path": str(dataset_path),
            "base_model": "gpt-4",  # Non-trainable model
            "lora_rank": 16,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    
    # Sprawdź czy zwraca poprawny kod błędu
    if isinstance(detail, dict):
        assert detail.get("error") == "MODEL_NOT_TRAINABLE" or detail.get("reason_code") == "MODEL_NOT_TRAINABLE"
    else:
        assert "not trainable" in detail.lower()


# ==================== Validation Utilities Tests ====================


def test_validate_file_extension():
    """Test walidacji rozszerzeń plików"""
    from venom_core.api.routes.academy import _validate_file_extension

    assert _validate_file_extension("test.jsonl") is True
    assert _validate_file_extension("test.json") is True
    assert _validate_file_extension("test.md") is True
    assert _validate_file_extension("test.txt") is True
    assert _validate_file_extension("test.csv") is True
    assert _validate_file_extension("test.exe") is False
    assert _validate_file_extension("test.sh") is False


def test_check_path_traversal():
    """Test wykrywania path traversal"""
    from venom_core.api.routes.academy import _check_path_traversal

    assert _check_path_traversal("test.txt") is True
    assert _check_path_traversal("my_file.jsonl") is True
    assert _check_path_traversal("../etc/passwd") is False
    assert _check_path_traversal("../../malicious") is False
    assert _check_path_traversal("folder/file.txt") is False  # No subfolders allowed
    assert _check_path_traversal("file\\windows\\path") is False


def test_is_model_trainable():
    """Test funkcji sprawdzającej czy model jest trenowalny"""
    from venom_core.api.routes.academy import _is_model_trainable

    # Trainable models
    assert _is_model_trainable("unsloth/Phi-3-mini-4k-instruct") is True
    assert _is_model_trainable("unsloth/Llama-3.2-1B-Instruct") is True
    assert _is_model_trainable("Phi-3.5-mini") is True
    assert _is_model_trainable("Mistral-7B") is True

    # Non-trainable models
    assert _is_model_trainable("gpt-4") is False
    assert _is_model_trainable("claude-3-opus") is False
    assert _is_model_trainable("gemini-pro") is False


# ==================== Ingestion Tests ====================


def test_ingest_jsonl_file(tmp_path):
    """Test ingestion pliku JSONL"""
    from venom_core.api.routes.academy import _ingest_upload_file

    # Utwórz plik JSONL
    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text(
        '{"instruction":"test1 instruction","input":"","output":"output1 text here"}\n'
        '{"instruction":"test2 instruction","input":"","output":"output2 text here"}\n'
    )

    # Create a simple mock with a real list
    mock_curator = MagicMock()
    mock_curator.examples = []
    
    count = _ingest_upload_file(mock_curator, jsonl_file)

    assert count == 2
    assert len(mock_curator.examples) == 2


def test_ingest_json_file(tmp_path):
    """Test ingestion pliku JSON"""
    from venom_core.api.routes.academy import _ingest_upload_file

    # Utwórz plik JSON (array)
    json_file = tmp_path / "test.json"
    json_file.write_text(
        json.dumps([
            {"instruction": "test1 instruction", "input": "", "output": "output1 text here"},
            {"instruction": "test2 instruction", "input": "", "output": "output2 text here"},
        ])
    )

    # Create a simple mock with a real list
    mock_curator = MagicMock()
    mock_curator.examples = []
    
    count = _ingest_upload_file(mock_curator, json_file)

    assert count == 2
    assert len(mock_curator.examples) == 2


def test_validate_training_record():
    """Test walidacji rekordu treningowego"""
    from venom_core.api.routes.academy import _validate_training_record

    # Valid record
    assert (
        _validate_training_record(
            {
                "instruction": "This is a valid instruction",
                "input": "",
                "output": "This is a valid output",
            }
        )
        is True
    )

    # Too short instruction
    assert (
        _validate_training_record(
            {"instruction": "short", "input": "", "output": "This is a valid output"}
        )
        is False
    )

    # Too short output
    assert (
        _validate_training_record(
            {"instruction": "This is a valid instruction", "input": "", "output": "x"}
        )
        is False
    )

    # Not a dict
    assert _validate_training_record("not a dict") is False
