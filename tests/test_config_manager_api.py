"""Testy API dla endpointów Config Manager."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system_config


@pytest.fixture
def test_app():
    """Fixture dla testowej aplikacji FastAPI."""
    app = FastAPI()
    app.include_router(system_config.router)
    return app


@pytest.fixture
def client(test_app):
    """Fixture dla klienta testowego FastAPI."""
    return TestClient(test_app, client=("127.0.0.1", 50000))


@pytest.fixture
def remote_client(test_app):
    """Fixture dla klienta testowego symulującego host zdalny."""
    return TestClient(test_app, client=("10.10.10.10", 50000))


class TestConfigRuntimeAPI:
    """Testy dla endpointu /api/v1/config/runtime."""

    def test_get_config_success(self, client):
        """Test poprawnego pobrania konfiguracji."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.get_effective_config_with_sources.return_value = (
                {
                    "AI_MODE": "LOCAL",
                    "LLM_SERVICE_TYPE": "local",
                    "ENABLE_HIVE": "false",
                    "OPENAI_API_KEY": "sk-****1234",  # Maskowany
                },
                {
                    "AI_MODE": "env",
                    "LLM_SERVICE_TYPE": "env",
                    "ENABLE_HIVE": "default",
                    "OPENAI_API_KEY": "env",
                },
            )

            response = client.get("/api/v1/config/runtime?mask_secrets=true")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "AI_MODE" in data["config"]
            assert data["config"]["AI_MODE"] == "LOCAL"
            assert data["config_sources"]["ENABLE_HIVE"] == "default"

    def test_get_config_no_mask(self, client):
        """Test pobrania konfiguracji bez maskowania."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.get_effective_config_with_sources.return_value = (
                {
                    "AI_MODE": "LOCAL",
                    "OPENAI_API_KEY": "sk-test1234567890",
                },
                {
                    "AI_MODE": "env",
                    "OPENAI_API_KEY": "env",
                },
            )

            response = client.get("/api/v1/config/runtime?mask_secrets=false")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            # W prawdziwym przypadku byłby pełny klucz
            assert "OPENAI_API_KEY" in data["config"]

    def test_update_config_success(self, client):
        """Test pomyślnej aktualizacji konfiguracji."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.update_config.return_value = {
                "success": True,
                "message": "Zaktualizowano 2 parametrów",
                "restart_required": ["backend"],
                "changed_keys": ["AI_MODE", "LLM_SERVICE_TYPE"],
                "backup_path": "/path/to/backup",
            }

            response = client.post(
                "/api/v1/config/runtime",
                json={"updates": {"AI_MODE": "HYBRID", "LLM_SERVICE_TYPE": "openai"}},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "backend" in data["restart_required"]
            assert len(data["changed_keys"]) == 2

    def test_update_config_validation_error(self, client):
        """Test błędu walidacji."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.update_config.return_value = {
                "success": False,
                "message": "Błąd walidacji: invalid_key nie jest dozwolony",
                "restart_required": [],
            }

            response = client.post(
                "/api/v1/config/runtime",
                json={"updates": {"INVALID_KEY": "value"}},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "walidacji" in data["message"]

    def test_update_config_error(self, client):
        """Test błędu podczas aktualizacji."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.update_config.side_effect = Exception("Test error")

            response = client.post(
                "/api/v1/config/runtime",
                json={"updates": {"AI_MODE": "HYBRID"}},
            )

            assert response.status_code == 500
            assert "Błąd wewnętrzny" in response.json()["detail"]

    def test_update_config_remote_host_forbidden(self, remote_client):
        """Test blokady zmiany konfiguracji dla hosta zdalnego."""
        response = remote_client.post(
            "/api/v1/config/runtime",
            json={"updates": {"AI_MODE": "HYBRID"}},
        )
        assert response.status_code == 403


class TestConfigBackupsAPI:
    """Testy dla endpointu /api/v1/config/backups."""

    def test_get_backups_success(self, client):
        """Test poprawnego pobrania listy backupów."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.get_backup_list.return_value = [
                {
                    "filename": ".env-20240101-120000",
                    "path": "/path/to/backup",
                    "size_bytes": 1024,
                    "created_at": "2024-01-01T12:00:00",
                }
            ]

            response = client.get("/api/v1/config/backups?limit=20")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["backups"]) == 1
            assert data["backups"][0]["filename"] == ".env-20240101-120000"

    def test_get_backups_empty(self, client):
        """Test pustej listy backupów."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.get_backup_list.return_value = []

            response = client.get("/api/v1/config/backups")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["backups"]) == 0

    def test_get_backups_remote_host_forbidden(self, remote_client):
        """Test blokady listowania backupów dla hosta zdalnego."""
        response = remote_client.get("/api/v1/config/backups")
        assert response.status_code == 403


class TestConfigRestoreAPI:
    """Testy dla endpointu /api/v1/config/restore."""

    def test_restore_backup_success(self, client):
        """Test pomyślnego przywrócenia backupu."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.restore_backup.return_value = {
                "success": True,
                "message": "Przywrócono .env z backupu",
                "restart_required": ["backend", "ui"],
            }

            response = client.post(
                "/api/v1/config/restore",
                json={"backup_filename": ".env-20240101-120000"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "backend" in data["restart_required"]

    def test_restore_backup_not_found(self, client):
        """Test przywrócenia nieistniejącego backupu."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.restore_backup.return_value = {
                "success": False,
                "message": "Backup nie istnieje",
            }

            response = client.post(
                "/api/v1/config/restore",
                json={"backup_filename": ".env-nonexistent"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "nie istnieje" in data["message"]

    def test_restore_backup_error(self, client):
        """Test błędu podczas przywracania."""
        with patch(
            "venom_core.api.routes.system_config.config_manager"
        ) as mock_manager:
            mock_manager.restore_backup.side_effect = Exception("Test error")

            response = client.post(
                "/api/v1/config/restore",
                json={"backup_filename": ".env-20240101-120000"},
            )

            assert response.status_code == 500
            assert "Błąd wewnętrzny" in response.json()["detail"]

    def test_restore_backup_remote_host_forbidden(self, remote_client):
        """Test blokady restore backupu dla hosta zdalnego."""
        response = remote_client.post(
            "/api/v1/config/restore",
            json={"backup_filename": ".env-20240101-120000"},
        )
        assert response.status_code == 403
