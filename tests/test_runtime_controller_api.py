"""Testy API dla endpointów Runtime Controller."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system


@pytest.fixture
def test_app():
    """Fixture dla testowej aplikacji FastAPI."""
    app = FastAPI()
    app.include_router(system.router)
    return app


@pytest.fixture
def client(test_app):
    """Fixture dla klienta testowego FastAPI."""
    return TestClient(test_app)


class TestRuntimeStatusAPI:
    """Testy dla endpointu /api/v1/runtime/status."""

    def test_runtime_status_success(self, client):
        """Test poprawnego pobrania statusu runtime."""
        with patch(
            "venom_core.api.routes.system.runtime_controller"
        ) as mock_controller:
            # Mock service info
            mock_service = MagicMock()
            mock_service.name = "backend"
            mock_service.service_type.value = "backend"
            mock_service.status.value = "running"
            mock_service.pid = 12345
            mock_service.port = 8000
            mock_service.cpu_percent = 5.5
            mock_service.memory_mb = 256.0
            mock_service.uptime_seconds = 3600
            mock_service.last_log = "Server started"
            mock_service.error_message = None

            mock_controller.get_all_services_status.return_value = [mock_service]

            response = client.get("/api/v1/runtime/status")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["services"]) == 1
            assert data["services"][0]["name"] == "backend"
            assert data["services"][0]["status"] == "running"
            assert data["services"][0]["pid"] == 12345

    def test_runtime_status_error(self, client):
        """Test błędu podczas pobierania statusu runtime."""
        with patch(
            "venom_core.api.routes.system.runtime_controller"
        ) as mock_controller:
            mock_controller.get_all_services_status.side_effect = Exception(
                "Test error"
            )

            response = client.get("/api/v1/runtime/status")

            assert response.status_code == 500
            assert "Błąd wewnętrzny" in response.json()["detail"]


class TestRuntimeActionAPI:
    """Testy dla endpointu /api/v1/runtime/{service}/{action}."""

    def test_start_service_success(self, client):
        """Test pomyślnego uruchomienia usługi."""
        with patch(
            "venom_core.api.routes.system.runtime_controller"
        ) as mock_controller:
            mock_controller.start_service.return_value = {
                "success": True,
                "message": "Usługa uruchomiona",
            }

            response = client.post("/api/v1/runtime/backend/start")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "uruchomiona" in data["message"]

    def test_stop_service_success(self, client):
        """Test pomyślnego zatrzymania usługi."""
        with patch(
            "venom_core.api.routes.system.runtime_controller"
        ) as mock_controller:
            mock_controller.stop_service.return_value = {
                "success": True,
                "message": "Usługa zatrzymana",
            }

            response = client.post("/api/v1/runtime/backend/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_restart_service_success(self, client):
        """Test pomyślnego restartu usługi."""
        with patch(
            "venom_core.api.routes.system.runtime_controller"
        ) as mock_controller:
            mock_controller.restart_service.return_value = {
                "success": True,
                "message": "Usługa zrestartowana",
            }

            response = client.post("/api/v1/runtime/backend/restart")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_invalid_service(self, client):
        """Test błędnej nazwy usługi."""
        response = client.post("/api/v1/runtime/invalid_service/start")

        assert response.status_code == 400
        assert "Nieznana usługa" in response.json()["detail"]

    def test_invalid_action(self, client):
        """Test błędnej akcji."""
        response = client.post("/api/v1/runtime/backend/invalid_action")

        assert response.status_code == 400
        assert "Nieznana akcja" in response.json()["detail"]


class TestRuntimeHistoryAPI:
    """Testy dla endpointu /api/v1/runtime/history."""

    def test_get_history_success(self, client):
        """Test poprawnego pobrania historii."""
        with patch(
            "venom_core.api.routes.system.runtime_controller"
        ) as mock_controller:
            mock_controller.get_history.return_value = [
                {
                    "timestamp": "2024-01-01T12:00:00",
                    "service": "backend",
                    "action": "start",
                    "success": True,
                    "message": "Started successfully",
                }
            ]

            response = client.get("/api/v1/runtime/history?limit=50")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["history"]) == 1
            assert data["history"][0]["service"] == "backend"


class TestRuntimeProfileAPI:
    """Testy dla endpointu /api/v1/runtime/profile/{profile_name}."""

    def test_apply_profile_success(self, client):
        """Test pomyślnej aplikacji profilu."""
        with patch(
            "venom_core.api.routes.system.runtime_controller"
        ) as mock_controller:
            mock_controller.apply_profile.return_value = {
                "success": True,
                "message": "Profil full zastosowany",
                "results": [],
            }

            response = client.post("/api/v1/runtime/profile/full")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "full" in data["message"]

    def test_apply_profile_unknown(self, client):
        """Test aplikacji nieznanego profilu."""
        with patch(
            "venom_core.api.routes.system.runtime_controller"
        ) as mock_controller:
            mock_controller.apply_profile.return_value = {
                "success": False,
                "message": "Nieznany profil: unknown",
            }

            response = client.post("/api/v1/runtime/profile/unknown")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Nieznany profil" in data["message"]
