"""Testy jednostkowe dla HuggingFaceSkill."""

from unittest.mock import MagicMock, patch

import pytest

from venom_core.execution.skills.huggingface_skill import HuggingFaceSkill


@pytest.fixture
def mock_hf_api():
    """Fixture dla zmockowanego Hugging Face API."""
    with patch("venom_core.execution.skills.huggingface_skill.HfApi") as mock:
        yield mock


@pytest.fixture
def hf_skill(mock_hf_api):
    """Fixture dla HuggingFaceSkill."""
    skill = HuggingFaceSkill()
    return skill


def test_huggingface_skill_initialization(mock_hf_api):
    """Test inicjalizacji HuggingFaceSkill."""
    skill = HuggingFaceSkill()
    assert skill.api is not None
    mock_hf_api.assert_called_once()


def test_huggingface_skill_initialization_with_token(mock_hf_api):
    """Test inicjalizacji HuggingFaceSkill z tokenem."""
    test_token = "test_hf_token_123"
    skill = HuggingFaceSkill(hf_token=test_token)
    assert skill.api is not None
    mock_hf_api.assert_called_with(token=test_token)


def test_search_models_success(hf_skill):
    """Test wyszukiwania modeli - sukces."""
    # Mock modeli
    mock_model1 = MagicMock()
    mock_model1.id = "distilbert-base-uncased"
    mock_model1.pipeline_tag = "text-classification"
    mock_model1.downloads = 10000
    mock_model1.likes = 100
    mock_model1.tags = ["pytorch", "transformers", "text-classification"]

    mock_model2 = MagicMock()
    mock_model2.id = "bert-base-onnx"
    mock_model2.pipeline_tag = "fill-mask"
    mock_model2.downloads = 5000
    mock_model2.likes = 50
    mock_model2.tags = ["onnx", "pytorch", "transformers"]

    # Skonfiguruj mock list_models
    hf_skill.api.list_models = MagicMock(return_value=[mock_model1, mock_model2])

    # Wywołaj search_models
    result = hf_skill.search_models(
        task="text-classification", query="sentiment", sort="downloads"
    )

    # Asercje
    assert "distilbert-base-uncased" in result
    assert "bert-base-onnx" in result
    assert "10,000" in result
    assert "text-classification" in result
    hf_skill.api.list_models.assert_called_once()


def test_search_models_prefer_onnx(hf_skill):
    """Test preferencji modeli ONNX."""
    # Mock modeli - ONNX i standardowy
    mock_onnx = MagicMock()
    mock_onnx.id = "model-onnx"
    mock_onnx.pipeline_tag = "text-classification"
    mock_onnx.downloads = 1000
    mock_onnx.likes = 10
    mock_onnx.tags = ["onnx", "pytorch"]

    mock_standard = MagicMock()
    mock_standard.id = "model-standard"
    mock_standard.pipeline_tag = "text-classification"
    mock_standard.downloads = 5000  # Więcej pobrań ale nie ONNX
    mock_standard.likes = 50
    mock_standard.tags = ["pytorch", "transformers"]

    # Lista z standardowym modelem jako pierwszy (więcej pobrań)
    hf_skill.api.list_models = MagicMock(return_value=[mock_standard, mock_onnx])

    result = hf_skill.search_models(task="text-classification")

    # ONNX powinien być preferowany i wyżej w wynikach
    assert "✅ ONNX" in result
    # Sprawdź że model-onnx jest wymieniony
    assert "model-onnx" in result


def test_search_models_prefer_gguf(hf_skill):
    """Test preferencji modeli GGUF."""
    mock_gguf = MagicMock()
    mock_gguf.id = "model-gguf"
    mock_gguf.pipeline_tag = "text-generation"
    mock_gguf.downloads = 1000
    mock_gguf.likes = 10
    mock_gguf.tags = ["gguf", "llama"]

    hf_skill.api.list_models = MagicMock(return_value=[mock_gguf])

    result = hf_skill.search_models(query="llama")

    assert "✅ GGUF" in result
    assert "model-gguf" in result


def test_search_models_no_results(hf_skill):
    """Test wyszukiwania modeli - brak wyników."""
    hf_skill.api.list_models = MagicMock(return_value=[])

    result = hf_skill.search_models(query="nonexistent")

    assert "Nie znaleziono modeli" in result


def test_search_models_without_task(hf_skill):
    """Test wyszukiwania modeli bez określonego zadania."""
    mock_model = MagicMock()
    mock_model.id = "general-model"
    mock_model.pipeline_tag = "text-generation"
    mock_model.downloads = 1000
    mock_model.likes = 10
    mock_model.tags = ["pytorch"]

    hf_skill.api.list_models = MagicMock(return_value=[mock_model])

    result = hf_skill.search_models(query="test")

    assert "general-model" in result
    # Sprawdź że filter nie jest przekazany gdy task jest pusty
    call_kwargs = hf_skill.api.list_models.call_args[1]
    assert "filter" not in call_kwargs


def test_get_model_card_success(hf_skill):
    """Test pobierania Model Card - sukces."""
    # Mock model info
    mock_model_info = MagicMock()
    mock_model_info.id = "test-model"
    mock_model_info.downloads = 1000
    mock_model_info.likes = 50
    mock_model_info.pipeline_tag = "text-classification"
    mock_model_info.tags = ["pytorch", "transformers"]
    mock_model_info.card_data = {"license": "MIT"}

    hf_skill.api.model_info = MagicMock(return_value=mock_model_info)

    result = hf_skill.get_model_card("test-model")

    assert "test-model" in result
    assert "1,000" in result
    assert "text-classification" in result
    assert "MIT" in result
    hf_skill.api.model_info.assert_called_with("test-model")


def test_get_model_card_not_found(hf_skill):
    """Test pobierania Model Card - model nie znaleziony."""
    from huggingface_hub.utils import RepositoryNotFoundError
    from unittest.mock import Mock

    # RepositoryNotFoundError wymaga parametru response
    mock_response = Mock()
    mock_response.status_code = 404
    hf_skill.api.model_info = MagicMock(
        side_effect=RepositoryNotFoundError("Not found", response=mock_response)
    )

    result = hf_skill.get_model_card("nonexistent-model")

    assert "❌" in result
    assert "nie znaleziony" in result


def test_get_model_card_without_card_data(hf_skill):
    """Test pobierania Model Card gdy brak card_data."""
    mock_model_info = MagicMock()
    mock_model_info.id = "test-model"
    mock_model_info.downloads = 100
    mock_model_info.likes = 5
    mock_model_info.pipeline_tag = "text-generation"
    mock_model_info.tags = ["pytorch"]
    mock_model_info.card_data = None

    hf_skill.api.model_info = MagicMock(return_value=mock_model_info)

    result = hf_skill.get_model_card("test-model")

    # Powinien zwrócić wynik mimo braku card_data
    assert "test-model" in result


def test_search_datasets_success(hf_skill):
    """Test wyszukiwania zbiorów danych - sukces."""
    # Mock datasets
    mock_dataset1 = MagicMock()
    mock_dataset1.id = "imdb"
    mock_dataset1.downloads = 50000
    mock_dataset1.likes = 200
    mock_dataset1.tags = ["text-classification", "sentiment"]

    mock_dataset2 = MagicMock()
    mock_dataset2.id = "squad"
    mock_dataset2.downloads = 30000
    mock_dataset2.likes = 150
    mock_dataset2.tags = ["question-answering"]

    hf_skill.api.list_datasets = MagicMock(return_value=[mock_dataset1, mock_dataset2])

    result = hf_skill.search_datasets(query="sentiment")

    assert "imdb" in result
    assert "squad" in result
    assert "50,000" in result
    assert "sentiment" in result
    hf_skill.api.list_datasets.assert_called_once()


def test_search_datasets_no_results(hf_skill):
    """Test wyszukiwania zbiorów danych - brak wyników."""
    hf_skill.api.list_datasets = MagicMock(return_value=[])

    result = hf_skill.search_datasets(query="nonexistent")

    assert "Nie znaleziono zbiorów danych" in result


def test_search_datasets_error_handling(hf_skill):
    """Test obsługi błędów podczas wyszukiwania zbiorów danych."""
    hf_skill.api.list_datasets = MagicMock(side_effect=Exception("API Error"))

    result = hf_skill.search_datasets(query="test")

    assert "❌" in result
    assert "Wystąpił błąd" in result


def test_search_models_limits_results(hf_skill):
    """Test limitowania liczby wyników."""
    # Stwórz więcej niż 5 modeli
    models = []
    for i in range(10):
        mock_model = MagicMock()
        mock_model.id = f"model-{i}"
        mock_model.pipeline_tag = "text-classification"
        mock_model.downloads = 1000 - i * 100
        mock_model.likes = 10
        mock_model.tags = ["pytorch"]
        models.append(mock_model)

    hf_skill.api.list_models = MagicMock(return_value=models)

    result = hf_skill.search_models(query="test")

    # Powinno być max 5 wyników
    # Sprawdź że nie ma modelu-5 lub wyższych (ponieważ limitujemy do 5)
    lines = result.split("\n")
    result_count = sum(1 for line in lines if line.startswith("["))
    assert result_count <= 5


def test_search_models_error_handling(hf_skill):
    """Test obsługi błędów podczas wyszukiwania modeli."""
    hf_skill.api.list_models = MagicMock(side_effect=Exception("API Error"))

    result = hf_skill.search_models(query="test")

    assert "❌" in result
    assert "Wystąpił błąd" in result
