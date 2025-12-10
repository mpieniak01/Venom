"""Testy jednostkowe dla ModelManager."""

import pytest

from venom_core.core.model_manager import ModelManager, ModelVersion


def test_model_version_creation():
    """Test tworzenia wersji modelu."""
    version = ModelVersion(
        version_id="v1.0",
        base_model="phi3:latest",
        adapter_path="/path/to/adapter",
        performance_metrics={"accuracy": 0.95},
    )

    assert version.version_id == "v1.0"
    assert version.base_model == "phi3:latest"
    assert version.adapter_path == "/path/to/adapter"
    assert version.performance_metrics["accuracy"] == 0.95
    assert version.is_active is False


def test_model_version_to_dict():
    """Test konwersji wersji modelu do słownika."""
    version = ModelVersion(
        version_id="v1.0",
        base_model="phi3:latest",
        created_at="2024-01-01T00:00:00",
    )

    data = version.to_dict()

    assert data["version_id"] == "v1.0"
    assert data["base_model"] == "phi3:latest"
    assert data["created_at"] == "2024-01-01T00:00:00"
    assert "performance_metrics" in data


def test_model_manager_initialization(tmp_path):
    """Test inicjalizacji ModelManager."""
    manager = ModelManager(models_dir=str(tmp_path))

    assert manager.models_dir.exists()
    assert len(manager.versions) == 0
    assert manager.active_version is None


def test_model_manager_register_version(tmp_path):
    """Test rejestracji nowej wersji."""
    manager = ModelManager(models_dir=str(tmp_path))

    version = manager.register_version(
        version_id="v1.0",
        base_model="phi3:latest",
        adapter_path="/path/to/adapter",
        performance_metrics={"accuracy": 0.95},
    )

    assert version.version_id == "v1.0"
    assert "v1.0" in manager.versions
    assert version.is_active is False


def test_model_manager_activate_version(tmp_path):
    """Test aktywacji wersji."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Zarejestruj dwie wersje
    manager.register_version("v1.0", "phi3:latest")
    manager.register_version("v1.1", "phi3:latest", adapter_path="/path/to/adapter")

    # Aktywuj v1.0
    success = manager.activate_version("v1.0")
    assert success is True
    assert manager.active_version == "v1.0"
    assert manager.versions["v1.0"].is_active is True

    # Aktywuj v1.1 (v1.0 powinno się dezaktywować)
    success = manager.activate_version("v1.1")
    assert success is True
    assert manager.active_version == "v1.1"
    assert manager.versions["v1.0"].is_active is False
    assert manager.versions["v1.1"].is_active is True


def test_model_manager_activate_nonexistent_version(tmp_path):
    """Test aktywacji nieistniejącej wersji."""
    manager = ModelManager(models_dir=str(tmp_path))

    success = manager.activate_version("v999")
    assert success is False


def test_model_manager_get_active_version(tmp_path):
    """Test pobierania aktywnej wersji."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Brak aktywnej wersji
    assert manager.get_active_version() is None

    # Zarejestruj i aktywuj
    manager.register_version("v1.0", "phi3:latest")
    manager.activate_version("v1.0")

    active = manager.get_active_version()
    assert active is not None
    assert active.version_id == "v1.0"


def test_model_manager_get_version(tmp_path):
    """Test pobierania wersji po ID."""
    manager = ModelManager(models_dir=str(tmp_path))

    manager.register_version("v1.0", "phi3:latest")

    version = manager.get_version("v1.0")
    assert version is not None
    assert version.version_id == "v1.0"

    # Nieistniejąca wersja
    assert manager.get_version("v999") is None


def test_model_manager_get_all_versions(tmp_path):
    """Test pobierania wszystkich wersji."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Pusta lista
    assert len(manager.get_all_versions()) == 0

    # Dodaj wersje
    manager.register_version("v1.0", "phi3:latest")
    manager.register_version("v1.1", "phi3:latest")
    manager.register_version("v1.2", "phi3:latest")

    all_versions = manager.get_all_versions()
    assert len(all_versions) == 3


def test_model_manager_get_genealogy(tmp_path):
    """Test pobierania genealogii modeli."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Dodaj wersje
    manager.register_version("v1.0", "phi3:latest")
    manager.register_version("v1.1", "phi3:latest")
    manager.activate_version("v1.1")

    genealogy = manager.get_genealogy()

    assert genealogy["total_versions"] == 2
    assert genealogy["active_version"] == "v1.1"
    assert len(genealogy["versions"]) == 2


def test_model_manager_compare_versions(tmp_path):
    """Test porównywania wersji."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Dodaj wersje z metrykami
    manager.register_version(
        "v1.0", "phi3:latest", performance_metrics={"accuracy": 0.90, "loss": 0.5}
    )
    manager.register_version(
        "v1.1", "phi3:latest", performance_metrics={"accuracy": 0.95, "loss": 0.3}
    )

    comparison = manager.compare_versions("v1.0", "v1.1")

    assert comparison is not None
    assert "metrics_diff" in comparison
    assert "accuracy" in comparison["metrics_diff"]
    assert comparison["metrics_diff"]["accuracy"]["v1"] == 0.90
    assert comparison["metrics_diff"]["accuracy"]["v2"] == 0.95
    assert comparison["metrics_diff"]["accuracy"]["diff"] == pytest.approx(0.05)


def test_model_manager_compare_nonexistent_versions(tmp_path):
    """Test porównywania nieistniejących wersji."""
    manager = ModelManager(models_dir=str(tmp_path))

    comparison = manager.compare_versions("v1.0", "v1.1")
    assert comparison is None


def test_model_manager_is_lora_adapter_nonexistent(tmp_path):
    """Test sprawdzania nieistniejącego adaptera."""
    manager = ModelManager(models_dir=str(tmp_path))

    assert manager._is_lora_adapter("/nonexistent/path") is False


def test_model_manager_is_lora_adapter_valid(tmp_path):
    """Test sprawdzania prawidłowego adaptera LoRA."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Utwórz katalog z plikami adaptera
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()

    # Utwórz wymagane pliki
    (adapter_dir / "adapter_config.json").write_text('{"peft_type": "LORA"}')
    (adapter_dir / "adapter_model.bin").write_text("dummy model data")

    assert manager._is_lora_adapter(str(adapter_dir)) is True


def test_model_manager_is_lora_adapter_missing_files(tmp_path):
    """Test sprawdzania adaptera z brakującymi plikami."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Utwórz katalog tylko z config (bez modelu)
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text('{"peft_type": "LORA"}')

    assert manager._is_lora_adapter(str(adapter_dir)) is False


def test_model_manager_load_adapter_nonexistent_version(tmp_path):
    """Test ładowania adaptera dla nieistniejącej wersji."""
    manager = ModelManager(models_dir=str(tmp_path))

    result = manager.load_adapter_for_kernel("v999", None)
    assert result is False


def test_model_manager_load_adapter_no_adapter_path(tmp_path):
    """Test ładowania adaptera bez ścieżki."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Zarejestruj wersję bez adaptera
    manager.register_version("v1.0", "phi3:latest", adapter_path=None)

    result = manager.load_adapter_for_kernel("v1.0", None)
    assert result is False


# Testy dla nowych metod zarządzania modelami (THE_ARMORY)


def test_model_manager_get_models_size_gb_empty(tmp_path):
    """Test obliczania rozmiaru przy pustym katalogu."""
    manager = ModelManager(models_dir=str(tmp_path))
    size = manager.get_models_size_gb()
    assert size == 0.0


def test_model_manager_get_models_size_gb_with_files(tmp_path):
    """Test obliczania rozmiaru z plikami."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Utwórz plik testowy o rozmiarze 1MB
    test_file = tmp_path / "test_model.gguf"
    test_file.write_bytes(b"x" * (1024 * 1024))  # 1MB

    size = manager.get_models_size_gb()
    # 1MB = ~0.001 GB
    assert size > 0.0
    assert size < 0.01  # Powinno być około 0.001 GB


def test_model_manager_check_storage_quota_within_limit(tmp_path):
    """Test Resource Guard - w limicie."""
    manager = ModelManager(models_dir=str(tmp_path))
    # Przy pustym katalogu, powinno być OK
    result = manager.check_storage_quota(additional_size_gb=1.0)
    assert result is True


def test_model_manager_check_storage_quota_exceeds_limit(tmp_path):
    """Test Resource Guard - przekroczenie limitu."""
    from venom_core.core.model_manager import MAX_STORAGE_GB

    manager = ModelManager(models_dir=str(tmp_path))
    # Próba dodania więcej niż limit
    result = manager.check_storage_quota(additional_size_gb=MAX_STORAGE_GB + 1)
    assert result is False


@pytest.mark.asyncio
async def test_model_manager_list_local_models_empty(tmp_path):
    """Test listowania modeli przy pustym katalogu."""
    from unittest.mock import AsyncMock, MagicMock, patch

    manager = ModelManager(models_dir=str(tmp_path))

    with patch("httpx.AsyncClient") as mock_client:
        # Mock Ollama API response (empty)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}

        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        models = await manager.list_local_models()
        assert isinstance(models, list)
        assert len(models) >= 0


@pytest.mark.asyncio
async def test_model_manager_list_local_models_with_local_file(tmp_path):
    """Test listowania modeli z lokalnym plikiem."""
    from unittest.mock import AsyncMock, patch

    manager = ModelManager(models_dir=str(tmp_path))

    # Utwórz plik modelu
    test_file = tmp_path / "test_model.gguf"
    test_file.write_bytes(b"x" * 1000)

    with patch("httpx.AsyncClient") as mock_client:
        # Mock Ollama API response (error)
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=Exception("Connection error")
        )

        models = await manager.list_local_models()
        assert len(models) >= 1

        # Sprawdź czy nasz model jest na liście
        model_names = [m["name"] for m in models]
        assert "test_model.gguf" in model_names


@pytest.mark.asyncio
async def test_model_manager_pull_model_no_space(tmp_path):
    """Test pobierania modelu bez miejsca (Resource Guard)."""
    from unittest.mock import patch

    manager = ModelManager(models_dir=str(tmp_path))

    with patch.object(manager, "check_storage_quota", return_value=False) as mock_check:
        result = await manager.pull_model("test-model")
        assert result is False
        mock_check.assert_called_once()


@pytest.mark.asyncio
async def test_model_manager_delete_model_active(tmp_path):
    """Test usuwania aktywnego modelu (powinno być zablokowane)."""
    manager = ModelManager(models_dir=str(tmp_path))

    # Zarejestruj i aktywuj model
    manager.register_version("test-v1", "test-model")
    manager.activate_version("test-v1")

    result = await manager.delete_model("test-v1")
    assert result is False


@pytest.mark.asyncio
async def test_model_manager_unload_all(tmp_path):
    """Test panic button - zwolnienie wszystkich zasobów."""
    from unittest.mock import MagicMock, patch

    manager = ModelManager(models_dir=str(tmp_path))

    # Ustaw aktywną wersję
    manager.register_version("test-v1", "test-model")
    manager.activate_version("test-v1")
    assert manager.active_version is not None

    # Mock subprocess
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = await manager.unload_all()
        assert result is True
        assert manager.active_version is None


@pytest.mark.asyncio
async def test_model_manager_get_usage_metrics(tmp_path):
    """Test pobierania metryk użycia."""
    from unittest.mock import AsyncMock, MagicMock, patch

    manager = ModelManager(models_dir=str(tmp_path))

    # Utwórz plik testowy
    test_file = tmp_path / "test_model.gguf"
    test_file.write_bytes(b"x" * (1024 * 1024))  # 1MB

    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}

        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        metrics = await manager.get_usage_metrics()

        assert "disk_usage_gb" in metrics
        assert "disk_limit_gb" in metrics
        assert "disk_usage_percent" in metrics
        assert "vram_usage_mb" in metrics
        assert "models_count" in metrics
        assert metrics["disk_usage_gb"] > 0
