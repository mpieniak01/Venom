"""Testy jednostkowe dla ModelRegistry."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core.model_registry import (
    HuggingFaceModelProvider,
    ModelCapabilities,
    ModelMetadata,
    ModelOperation,
    ModelProvider,
    ModelRegistry,
    ModelStatus,
    OllamaModelProvider,
    OperationStatus,
)


def test_model_capabilities_creation():
    """Test tworzenia ModelCapabilities."""
    caps = ModelCapabilities(
        supports_system_role=False,
        allowed_roles=["user", "assistant"],
        max_context_length=2048,
    )

    assert caps.supports_system_role is False
    assert "user" in caps.allowed_roles
    assert caps.max_context_length == 2048


def test_model_metadata_creation():
    """Test tworzenia ModelMetadata."""
    metadata = ModelMetadata(
        name="test-model",
        provider=ModelProvider.OLLAMA,
        display_name="Test Model",
        size_gb=4.0,
        status=ModelStatus.INSTALLED,
    )

    assert metadata.name == "test-model"
    assert metadata.provider == ModelProvider.OLLAMA
    assert metadata.size_gb == pytest.approx(4.0)


def test_model_metadata_to_dict():
    """Test konwersji ModelMetadata do słownika."""
    metadata = ModelMetadata(
        name="test-model",
        provider=ModelProvider.HUGGINGFACE,
        display_name="Test Model",
    )

    data = metadata.to_dict()

    assert data["name"] == "test-model"
    assert data["provider"] == "huggingface"
    assert "capabilities" in data
    assert isinstance(data["capabilities"], dict)


def test_model_operation_creation():
    """Test tworzenia ModelOperation."""
    operation = ModelOperation(
        operation_id="op-123",
        model_name="test-model",
        operation_type="install",
        status=OperationStatus.PENDING,
    )

    assert operation.operation_id == "op-123"
    assert operation.status == OperationStatus.PENDING
    assert operation.progress == pytest.approx(0.0)


def test_model_operation_to_dict():
    """Test konwersji ModelOperation do słownika."""
    operation = ModelOperation(
        operation_id="op-123",
        model_name="test-model",
        operation_type="install",
        status=OperationStatus.COMPLETED,
        progress=100.0,
    )

    data = operation.to_dict()

    assert data["operation_id"] == "op-123"
    assert data["status"] == "completed"
    assert data["progress"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_ollama_provider_list_models():
    """Test listowania modeli z Ollama."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:latest", "size": 4 * 1024**3},
                {"name": "phi3:latest", "size": 7 * 1024**3},
            ]
        }

        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        provider = OllamaModelProvider()
        models = await provider.list_available_models()

        assert len(models) == 2
        assert models[0].name == "llama3:latest"
        assert models[0].provider == ModelProvider.OLLAMA
        assert models[0].runtime == "ollama"


@pytest.mark.asyncio
async def test_ollama_provider_list_models_error():
    """Test listowania modeli gdy Ollama nie jest dostępny."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=Exception("Connection error")
        )

        provider = OllamaModelProvider()
        models = await provider.list_available_models()

        assert len(models) == 0


@pytest.mark.asyncio
async def test_ollama_provider_install_model_success():
    """Test instalacji modelu przez Ollama."""
    with patch("asyncio.create_subprocess_exec") as mock_subprocess:
        mock_process = AsyncMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = AsyncMock(
            side_effect=[b"pulling manifest\n", b"success\n", b""]
        )
        mock_process.wait = AsyncMock(return_value=None)
        mock_process.returncode = 0
        mock_process.stderr = AsyncMock()
        mock_subprocess.return_value = mock_process

        provider = OllamaModelProvider()
        result = await provider.install_model("llama3:latest")

        assert result is True
        mock_subprocess.assert_called_once()


@pytest.mark.asyncio
async def test_ollama_provider_install_model_invalid_name():
    """Test instalacji modelu z nieprawidłową nazwą."""
    provider = OllamaModelProvider()
    result = await provider.install_model("invalid name!")

    assert result is False


@pytest.mark.asyncio
async def test_ollama_provider_remove_model_success():
    """Test usuwania modelu z Ollama."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        provider = OllamaModelProvider()
        result = await provider.remove_model("llama3:latest")

        assert result is True
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_huggingface_provider_list_models():
    """Test listowania modeli z HuggingFace."""
    provider = HuggingFaceModelProvider()
    models = await provider.list_available_models()

    assert len(models) > 0
    assert any(m.provider == ModelProvider.HUGGINGFACE for m in models)


@pytest.mark.asyncio
async def test_huggingface_provider_install_model():
    """Test instalacji modelu z HuggingFace (mock)."""
    pytest.importorskip("huggingface_hub")

    with patch("huggingface_hub.snapshot_download") as mock_download:
        mock_download.return_value = "/path/to/model"

        provider = HuggingFaceModelProvider(
            cache_dir=str(Path(tempfile.gettempdir()) / "test_cache")
        )
        result = await provider.install_model("google/gemma-2b-it")

        assert result is True
        mock_download.assert_called_once()


@pytest.mark.asyncio
async def test_huggingface_provider_remove_model(tmp_path):
    """Test usuwania modelu z HuggingFace cache."""
    provider = HuggingFaceModelProvider(cache_dir=str(tmp_path))

    # Utwórz katalog modelu
    model_dir = tmp_path / "google--gemma-2b-it"
    model_dir.mkdir()

    result = await provider.remove_model("google/gemma-2b-it")

    assert result is True
    assert not model_dir.exists()


def test_model_registry_initialization(tmp_path):
    """Test inicjalizacji ModelRegistry."""
    registry = ModelRegistry(models_dir=str(tmp_path))

    assert registry.models_dir.exists()
    assert len(registry.manifest) == 0
    assert ModelProvider.OLLAMA in registry.providers
    assert ModelProvider.HUGGINGFACE in registry.providers


def test_model_registry_load_manifest(tmp_path):
    """Test ładowania manifestu z dysku."""
    manifest_path = tmp_path / "manifest.json"
    manifest_data = {
        "models": [
            {
                "name": "test-model",
                "provider": "ollama",
                "display_name": "Test Model",
                "status": "installed",
                "runtime": "ollama",
                "capabilities": {},
            }
        ]
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)

    registry = ModelRegistry(models_dir=str(tmp_path))

    assert len(registry.manifest) == 1
    assert "test-model" in registry.manifest


def test_model_registry_save_manifest(tmp_path):
    """Test zapisywania manifestu na dysk."""
    registry = ModelRegistry(models_dir=str(tmp_path))

    metadata = ModelMetadata(
        name="test-model",
        provider=ModelProvider.OLLAMA,
        display_name="Test Model",
    )
    registry.manifest["test-model"] = metadata
    registry._save_manifest()

    assert registry.manifest_path.exists()

    with open(registry.manifest_path, "r") as f:
        data = json.load(f)
        assert len(data["models"]) == 1
        assert data["models"][0]["name"] == "test-model"


@pytest.mark.asyncio
async def test_model_registry_list_available_models(tmp_path):
    """Test listowania dostępnych modeli."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}

        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        registry = ModelRegistry(models_dir=str(tmp_path))
        models = await registry.list_available_models()

        assert len(models) >= 2  # Przynajmniej modele z HF stub


@pytest.mark.asyncio
async def test_model_registry_install_model(tmp_path):
    """Test instalacji modelu przez registry."""
    with patch("asyncio.create_subprocess_exec") as mock_subprocess:
        mock_process = AsyncMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = AsyncMock(
            side_effect=[b"pulling manifest\n", b""]
        )
        mock_process.wait = AsyncMock(return_value=None)
        mock_process.returncode = 0
        mock_process.stderr = AsyncMock()
        mock_subprocess.return_value = mock_process

        registry = ModelRegistry(models_dir=str(tmp_path))
        operation_id = await registry.install_model(
            "llama3:latest", ModelProvider.OLLAMA, "ollama"
        )

        assert operation_id is not None

        # Poczekaj chwilę na wykonanie zadania w tle
        await asyncio.sleep(0.5)

        operation = registry.get_operation_status(operation_id)
        assert operation is not None
        assert operation.model_name == "llama3:latest"


@pytest.mark.asyncio
async def test_model_registry_remove_model(tmp_path):
    """Test usuwania modelu przez registry."""
    registry = ModelRegistry(models_dir=str(tmp_path))

    # Dodaj model do manifestu
    metadata = ModelMetadata(
        name="test-model",
        provider=ModelProvider.OLLAMA,
        display_name="Test Model",
        status=ModelStatus.INSTALLED,
    )
    registry.manifest["test-model"] = metadata
    registry._save_manifest()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        operation_id = await registry.remove_model("test-model")

        assert operation_id is not None

        # Poczekaj chwilę
        await asyncio.sleep(0.5)

        operation = registry.get_operation_status(operation_id)
        assert operation is not None


def test_model_registry_get_model_capabilities(tmp_path):
    """Test pobierania capabilities modelu."""
    registry = ModelRegistry(models_dir=str(tmp_path))

    # Dodaj model z capabilities
    caps = ModelCapabilities(supports_system_role=False)
    metadata = ModelMetadata(
        name="gemma-2b",
        provider=ModelProvider.HUGGINGFACE,
        display_name="Gemma 2B",
        capabilities=caps,
    )
    registry.manifest["gemma-2b"] = metadata

    result_caps = registry.get_model_capabilities("gemma-2b")

    assert result_caps is not None
    assert result_caps.supports_system_role is False


def test_model_registry_get_model_capabilities_not_found(tmp_path):
    """Test pobierania capabilities nieistniejącego modelu."""
    registry = ModelRegistry(models_dir=str(tmp_path))

    result_caps = registry.get_model_capabilities("non-existent")

    assert result_caps is None


def test_model_registry_list_operations(tmp_path):
    """Test listowania operacji."""
    registry = ModelRegistry(models_dir=str(tmp_path))

    # Dodaj kilka operacji
    for i in range(5):
        op = ModelOperation(
            operation_id=f"op-{i}",
            model_name=f"model-{i}",
            operation_type="install",
            status=OperationStatus.COMPLETED,
        )
        registry.operations[f"op-{i}"] = op

    operations = registry.list_operations(limit=3)

    assert len(operations) == 3


@pytest.mark.asyncio
async def test_model_registry_activate_model(tmp_path):
    """Test aktywacji modelu."""
    registry = ModelRegistry(models_dir=str(tmp_path))

    # Dodaj model do manifestu
    metadata = ModelMetadata(
        name="test-model",
        provider=ModelProvider.OLLAMA,
        display_name="Test Model",
        status=ModelStatus.INSTALLED,
    )
    registry.manifest["test-model"] = metadata

    result = await registry.activate_model("test-model", "ollama")

    # W aktualnej implementacji to jest stub
    assert result is True


@pytest.mark.asyncio
async def test_model_registry_activate_model_not_found(tmp_path):
    """Test aktywacji nieistniejącego modelu."""
    registry = ModelRegistry(models_dir=str(tmp_path))

    result = await registry.activate_model("non-existent", "ollama")

    assert result is False


@pytest.mark.asyncio
async def test_model_registry_concurrent_operations(tmp_path):
    """Test że operacje per runtime są serializowane."""
    registry = ModelRegistry(models_dir=str(tmp_path))

    # Timestamps to verify serialization
    timestamps = []

    def fake_create_subprocess_exec(*args, **kwargs):
        """Fake subprocess that records timestamps."""
        loop = asyncio.get_event_loop()
        timestamps.append(loop.time())

        mock_process = AsyncMock()
        mock_process.stdout = MagicMock()

        # Create a simple list for readline to iterate through
        lines = [b"pulling manifest\n", b""]
        line_idx = [0]  # Use list to allow mutation in closure

        async def fake_readline():
            # Symuluj czas trwania operacji
            if line_idx[0] == 0:
                await asyncio.sleep(0.2)
            idx = line_idx[0]
            line_idx[0] += 1
            return lines[idx] if idx < len(lines) else b""

        mock_process.stdout.readline = fake_readline
        mock_process.wait = AsyncMock(return_value=None)
        mock_process.returncode = 0
        mock_process.stderr = AsyncMock()
        return mock_process

    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=fake_create_subprocess_exec,
    ):
        # Uruchamiamy dwie instalacje współbieżnie
        op1 = await registry.install_model("model1", ModelProvider.OLLAMA, "ollama")
        op2 = await registry.install_model("model2", ModelProvider.OLLAMA, "ollama")

        assert op1 != op2

        # Poczekaj na zakończenie obu operacji
        await asyncio.sleep(1.0)

        # Obie operacje powinny się zakończyć
        assert registry.get_operation_status(op1) is not None
        assert registry.get_operation_status(op2) is not None

        # Sprawdzamy, że subprocess dla drugiej operacji startuje dopiero po zakończeniu pierwszej
        assert len(timestamps) == 2
        assert timestamps[1] - timestamps[0] >= 0.2


@pytest.mark.asyncio
async def test_huggingface_list_models_integration(tmp_path):
    """Test integracji HuggingFaceModelProvider z HF Hub API (PR-132B)."""
    from unittest.mock import AsyncMock

    from venom_core.core.model_registry import HuggingFaceModelProvider

    provider = HuggingFaceModelProvider(cache_dir=str(tmp_path))

    # Mock client.list_models
    mock_models_data = [
        {
            "id": "meta-llama/Llama-2-7b-hf",
            "modelId": "meta-llama/Llama-2-7b-hf",
            "downloads": 1000000,
            "likes": 5000,
            "tags": ["text-generation", "llama"],
        },
        {
            "id": "mistralai/Mistral-7B-v0.1",
            "modelId": "mistralai/Mistral-7B-v0.1",
            "downloads": 800000,
            "likes": 4000,
            "tags": ["text-generation", "mistral"],
        },
    ]

    provider.client.list_models = AsyncMock(return_value=mock_models_data)

    models = await provider.list_available_models()

    # Sprawdź że zwrócono modele z API
    assert len(models) == 2
    assert models[0].name == "meta-llama/Llama-2-7b-hf"
    assert models[1].name == "mistralai/Mistral-7B-v0.1"


@pytest.mark.asyncio
async def test_huggingface_list_models_fallback_on_empty(tmp_path):
    """Test fallbacku do popularnych modeli gdy API zwraca pusty wynik (PR-132B)."""
    from unittest.mock import AsyncMock

    from venom_core.core.model_registry import HuggingFaceModelProvider

    provider = HuggingFaceModelProvider(cache_dir=str(tmp_path))
    provider.client.list_models = AsyncMock(return_value=[])

    models = await provider.list_available_models()

    # Sprawdź że zwrócono fallback modele
    assert len(models) >= 1
    assert any("gemma" in m.name.lower() or "phi" in m.name.lower() for m in models)


@pytest.mark.asyncio
async def test_huggingface_list_models_fallback_on_error(tmp_path):
    """Test fallbacku do popularnych modeli przy błędzie API (PR-132B)."""
    from unittest.mock import AsyncMock

    from venom_core.core.model_registry import HuggingFaceModelProvider

    provider = HuggingFaceModelProvider(cache_dir=str(tmp_path))
    provider.client.list_models = AsyncMock(side_effect=Exception("API error"))

    models = await provider.list_available_models()

    # Sprawdź że zwrócono fallback modele
    assert len(models) >= 1
    assert models[0].name == "google/gemma-2b-it"


@pytest.mark.asyncio
async def test_huggingface_get_model_info_success(tmp_path):
    """Test pobierania info o modelu z HF Hub API (PR-132B)."""
    from unittest.mock import AsyncMock

    from venom_core.core.model_registry import HuggingFaceModelProvider

    provider = HuggingFaceModelProvider(cache_dir=str(tmp_path))

    mock_model_data = {
        "id": "microsoft/phi-3-mini-4k-instruct",
        "downloads": 500000,
        "likes": 3000,
        "tags": ["text-generation", "phi"],
        "author": "microsoft",
        "pipeline_tag": "text-generation",
    }

    provider.client.get_model_info = AsyncMock(return_value=mock_model_data)

    model_info = await provider.get_model_info("microsoft/phi-3-mini-4k-instruct")

    assert model_info is not None
    assert model_info.name == "microsoft/phi-3-mini-4k-instruct"


@pytest.mark.asyncio
async def test_huggingface_get_model_info_not_found(tmp_path):
    """Test gdy model nie istnieje w HF Hub (PR-132B)."""
    from unittest.mock import AsyncMock

    from venom_core.core.model_registry import HuggingFaceModelProvider

    provider = HuggingFaceModelProvider(cache_dir=str(tmp_path))
    provider.client.get_model_info = AsyncMock(return_value=None)
    provider.client.list_models = AsyncMock(return_value=[])

    model_info = await provider.get_model_info("nonexistent/model")

    # Sprawdź że zwrócono None
    assert model_info is None


@pytest.mark.asyncio
async def test_huggingface_get_model_info_fallback(tmp_path):
    """Test fallbacku do listy popularnych modeli (PR-132B)."""
    from unittest.mock import AsyncMock

    from venom_core.core.model_registry import HuggingFaceModelProvider

    provider = HuggingFaceModelProvider(cache_dir=str(tmp_path))
    provider.client.get_model_info = AsyncMock(side_effect=Exception("API error"))
    # Mock list_available_models zwraca fallback z gemma
    provider.client.list_models = AsyncMock(return_value=[])

    model_info = await provider.get_model_info("google/gemma-2b-it")

    # Sprawdź że znaleziono model w fallbacku
    assert model_info is not None
    assert model_info.name == "google/gemma-2b-it"
