"""Tests for Academy dataset conversion workspace endpoints (task 163)."""

from __future__ import annotations

import io
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
