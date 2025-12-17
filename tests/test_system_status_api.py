"""Testy API dla endpointu /api/v1/system/status."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import tylko potrzebnych rzeczy zamiast całego app
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


class TestSystemStatusAPI:
    """Testy dla endpointu /api/v1/system/status."""

    def test_system_status_success(self, client):
        """Test poprawnego pobrania statusu systemu z metrykami pamięci."""
        # Mock service monitor
        with patch("venom_core.api.routes.system._service_monitor") as mock_monitor:
            mock_monitor.get_memory_metrics.return_value = {
                "memory_usage_mb": 8192.50,
                "memory_total_mb": 16384.00,
                "memory_usage_percent": 50.0,
                "vram_usage_mb": 2048.00,
                "vram_total_mb": 8192.00,
                "vram_usage_percent": 25.0,
            }
            mock_monitor.get_summary.return_value = {
                "system_healthy": True,
                "total_services": 5,
                "online": 5,
                "offline": 0,
            }

            response = client.get("/api/v1/system/status")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["system_healthy"] is True
            assert data["memory_usage_mb"] == 8192.50
            assert data["memory_total_mb"] == 16384.00
            assert data["memory_usage_percent"] == 50.0
            assert data["vram_usage_mb"] == 2048.00
            assert data["vram_total_mb"] == 8192.00
            assert data["vram_usage_percent"] == 25.0

    def test_system_status_without_gpu(self, client):
        """Test statusu systemu bez dostępnego GPU (VRAM = null)."""
        with patch("venom_core.api.routes.system._service_monitor") as mock_monitor:
            mock_monitor.get_memory_metrics.return_value = {
                "memory_usage_mb": 4096.25,
                "memory_total_mb": 8192.00,
                "memory_usage_percent": 50.03,
                "vram_usage_mb": None,
                "vram_total_mb": None,
                "vram_usage_percent": None,
            }
            mock_monitor.get_summary.return_value = {
                "system_healthy": True,
                "total_services": 3,
                "online": 3,
                "offline": 0,
            }

            response = client.get("/api/v1/system/status")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["memory_usage_mb"] == 4096.25
            assert data["vram_usage_mb"] is None
            assert data["vram_total_mb"] is None
            assert data["vram_usage_percent"] is None

    def test_system_status_service_monitor_unavailable(self, client):
        """Test błędu 503 gdy ServiceMonitor nie jest dostępny."""
        with patch("venom_core.api.routes.system._service_monitor", None):
            response = client.get("/api/v1/system/status")

            assert response.status_code == 503
            assert "ServiceMonitor" in response.json()["detail"]

    def test_system_status_internal_error(self, client):
        """Test błędu 500 gdy get_memory_metrics rzuca wyjątek."""
        with patch("venom_core.api.routes.system._service_monitor") as mock_monitor:
            mock_monitor.get_memory_metrics.side_effect = Exception(
                "Błąd pobierania metryk"
            )

            response = client.get("/api/v1/system/status")

            assert response.status_code == 500
            assert "Błąd wewnętrzny" in response.json()["detail"]

    def test_system_status_unhealthy_system(self, client):
        """Test statusu dla systemu w złym stanie (critical service offline)."""
        with patch("venom_core.api.routes.system._service_monitor") as mock_monitor:
            mock_monitor.get_memory_metrics.return_value = {
                "memory_usage_mb": 15000.00,
                "memory_total_mb": 16384.00,
                "memory_usage_percent": 91.55,
                "vram_usage_mb": 7500.00,
                "vram_total_mb": 8192.00,
                "vram_usage_percent": 91.55,
            }
            mock_monitor.get_summary.return_value = {
                "system_healthy": False,
                "total_services": 5,
                "online": 3,
                "offline": 2,
                "critical_offline": ["Local LLM"],
            }

            response = client.get("/api/v1/system/status")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["system_healthy"] is False
            # Wysokie użycie pamięci
            assert data["memory_usage_percent"] > 90
            assert data["vram_usage_percent"] > 90
