"""Testy API dla endpointów Runtime Controller."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system_runtime


@pytest.fixture
def test_app():
    """Fixture dla testowej aplikacji FastAPI."""
    app = FastAPI()
    app.include_router(system_runtime.router)
    return app


@pytest.fixture
def client(test_app):
    """Fixture dla klienta testowego FastAPI."""
    return TestClient(test_app)


class TestRuntimeStatusAPI:
    """Testy dla endpointu /api/v1/runtime/status."""

    def test_runtime_status_success(self, client):
        """Test poprawnego pobrania statusu runtime."""
        with (
            patch(
                "venom_core.api.routes.system_runtime.runtime_controller"
            ) as mock_controller,
            patch("venom_core.api.routes.system_deps._service_monitor", None),
            patch(
                "venom_core.api.routes.system_runtime._fetch_ollama_runtime_version",
                return_value=None,
            ),
        ):
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
            mock_service.actionable = True

            mock_controller.get_all_services_status.return_value = [mock_service]

            response = client.get("/api/v1/runtime/status")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["services"]) == 1
            assert data["services"][0]["name"] == "backend"
            assert data["services"][0]["status"] == "running"
            assert data["services"][0]["pid"] == 12345
            assert data["services"][0]["actionable"] is True
            assert "runtime_version" in data["services"][0]

    def test_runtime_status_with_non_actionable_services(self, client):
        """Test statusu runtime z usługami non-actionable (Hive/Nexus/BackgroundTasks)."""
        with (
            patch(
                "venom_core.api.routes.system_runtime.runtime_controller"
            ) as mock_controller,
            patch("venom_core.api.routes.system_deps._service_monitor", None),
            patch(
                "venom_core.api.routes.system_runtime._fetch_ollama_runtime_version",
                return_value=None,
            ),
        ):
            # Mock actionable service (backend)
            mock_backend = MagicMock()
            mock_backend.name = "backend"
            mock_backend.service_type.value = "backend"
            mock_backend.status.value = "running"
            mock_backend.pid = 12345
            mock_backend.port = 8000
            mock_backend.cpu_percent = 5.5
            mock_backend.memory_mb = 256.0
            mock_backend.uptime_seconds = 3600
            mock_backend.last_log = "Server started"
            mock_backend.error_message = None
            mock_backend.actionable = True

            # Mock non-actionable service (hive)
            mock_hive = MagicMock()
            mock_hive.name = "hive"
            mock_hive.service_type.value = "hive"
            mock_hive.status.value = "stopped"
            mock_hive.pid = None
            mock_hive.port = None
            mock_hive.cpu_percent = 0.0
            mock_hive.memory_mb = 0.0
            mock_hive.uptime_seconds = None
            mock_hive.last_log = None
            mock_hive.error_message = None
            mock_hive.actionable = False

            mock_controller.get_all_services_status.return_value = [
                mock_backend,
                mock_hive,
            ]

            response = client.get("/api/v1/runtime/status")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["services"]) == 2

            # Check backend (actionable)
            backend_service = next(
                s for s in data["services"] if s["name"] == "backend"
            )
            assert backend_service["actionable"] is True

            # Check hive (non-actionable)
            hive_service = next(s for s in data["services"] if s["name"] == "hive")
            assert hive_service["actionable"] is False

    def test_runtime_status_includes_ollama_version(self, client):
        """Test że endpoint zwraca wykrytą wersję dla karty Ollama."""
        with (
            patch(
                "venom_core.api.routes.system_runtime.runtime_controller"
            ) as mock_controller,
            patch("venom_core.api.routes.system_deps._service_monitor", None),
            patch(
                "venom_core.api.routes.system_runtime._fetch_ollama_runtime_version",
                return_value="0.16.1",
            ),
        ):
            mock_ollama = MagicMock()
            mock_ollama.name = "Ollama"
            mock_ollama.service_type = system_runtime.ServiceType.LLM_OLLAMA
            mock_ollama.status.value = "running"
            mock_ollama.pid = 123
            mock_ollama.port = 11434
            mock_ollama.cpu_percent = 0.0
            mock_ollama.memory_mb = 0.0
            mock_ollama.uptime_seconds = None
            mock_ollama.last_log = None
            mock_ollama.error_message = None
            mock_ollama.actionable = True
            mock_controller.get_all_services_status.return_value = [mock_ollama]

            response = client.get("/api/v1/runtime/status")

            assert response.status_code == 200
            data = response.json()
            assert data["services"][0]["runtime_version"] == "0.16.1"

    def test_runtime_status_error(self, client):
        """Test błędu podczas pobierania statusu runtime."""
        with patch(
            "venom_core.api.routes.system_runtime.runtime_controller"
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
            "venom_core.api.routes.system_runtime.runtime_controller"
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
            "venom_core.api.routes.system_runtime.runtime_controller"
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
            "venom_core.api.routes.system_runtime.runtime_controller"
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
            "venom_core.api.routes.system_runtime.runtime_controller"
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
            "venom_core.api.routes.system_runtime.runtime_controller"
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
            "venom_core.api.routes.system_runtime.runtime_controller"
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
