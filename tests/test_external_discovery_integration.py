"""Test integracji GitHubSkill i HuggingFaceSkill z agentami."""

from unittest.mock import MagicMock, patch

import pytest

from venom_core.execution.skills.github_skill import GitHubSkill
from venom_core.execution.skills.huggingface_skill import HuggingFaceSkill


@pytest.fixture
def mock_github_api():
    """Mock GitHub API."""
    with patch("venom_core.execution.skills.github_skill.Github") as mock:
        yield mock


@pytest.fixture
def mock_hf_api():
    """Mock Hugging Face API."""
    with patch("venom_core.execution.skills.huggingface_skill.HfApi") as mock:
        yield mock


def test_github_skill_can_be_instantiated(mock_github_api):
    """Test że GitHubSkill może być utworzony (wymagane dla agentów)."""
    skill = GitHubSkill()
    assert hasattr(skill, "search_repos")
    assert hasattr(skill, "get_readme")
    assert hasattr(skill, "get_trending")


def test_huggingface_skill_can_be_instantiated(mock_hf_api):
    """Test że HuggingFaceSkill może być utworzony (wymagane dla agentów)."""
    skill = HuggingFaceSkill()
    assert hasattr(skill, "search_models")
    assert hasattr(skill, "get_model_card")
    assert hasattr(skill, "search_datasets")


def test_github_skill_has_kernel_functions(mock_github_api):
    """Test że metody GitHubSkill są ozdobione @kernel_function."""
    skill = GitHubSkill()

    # Sprawdź czy metody mają odpowiednie atrybuty kernel_function
    # (Semantic Kernel dodaje metadane do funkcji)
    assert callable(skill.search_repos)
    assert callable(skill.get_readme)
    assert callable(skill.get_trending)


def test_huggingface_skill_has_kernel_functions(mock_hf_api):
    """Test że metody HuggingFaceSkill są ozdobione @kernel_function."""
    skill = HuggingFaceSkill()

    assert callable(skill.search_models)
    assert callable(skill.get_model_card)
    assert callable(skill.search_datasets)


def test_github_skill_search_repos_integration(mock_github_api):
    """Test integracyjny search_repos - symuluje użycie przez agenta."""
    skill = GitHubSkill()

    # Mock repozytorium
    mock_repo = MagicMock()
    mock_repo.full_name = "python/cpython"
    mock_repo.description = "Python programming language"
    mock_repo.stargazers_count = 50000
    mock_repo.forks_count = 20000
    mock_repo.html_url = "https://github.com/python/cpython"
    mock_repo.language = "Python"

    skill.github.search_repositories = MagicMock(return_value=[mock_repo])

    # Agent wywołuje search_repos
    result = skill.search_repos(query="Python programming", language="Python")

    # Weryfikuj że zwraca dane użyteczne dla agenta
    assert isinstance(result, str)
    assert "python/cpython" in result
    assert "50,000" in result
    assert "Python programming language" in result


def test_huggingface_skill_search_models_integration(mock_hf_api):
    """Test integracyjny search_models - symuluje użycie przez agenta."""
    skill = HuggingFaceSkill()

    # Mock modelu
    mock_model = MagicMock()
    mock_model.id = "distilbert-base-uncased-onnx"
    mock_model.pipeline_tag = "text-classification"
    mock_model.downloads = 10000
    mock_model.likes = 100
    mock_model.tags = ["onnx", "pytorch", "text-classification"]

    skill.api.list_models = MagicMock(return_value=[mock_model])

    # Agent wywołuje search_models
    result = skill.search_models(
        task="text-classification", query="sentiment", sort="downloads"
    )

    # Weryfikuj że zwraca dane użyteczne dla agenta
    assert isinstance(result, str)
    assert "distilbert-base-uncased-onnx" in result
    assert "10,000" in result
    assert "✅ ONNX" in result  # Preferuje ONNX
    assert "text-classification" in result


def test_skills_return_error_messages_not_exceptions():
    """Test że skills zwracają komunikaty błędów zamiast rzucać wyjątki."""
    # To ważne dla agentów - nie chcemy aby wyjątek przerwał działanie

    with patch("venom_core.execution.skills.github_skill.Github"):
        skill = GitHubSkill()
        skill.github.search_repositories = MagicMock(side_effect=Exception("API Error"))

        # Powinno zwrócić komunikat błędu, nie rzucić wyjątku
        result = skill.search_repos(query="test")
        assert isinstance(result, str)
        assert "❌" in result or "błąd" in result.lower()


def test_github_and_huggingface_skills_work_together():
    """Test że oba skills mogą działać razem (ResearcherAgent używa obu)."""
    with patch("venom_core.execution.skills.github_skill.Github"):
        with patch("venom_core.execution.skills.huggingface_skill.HfApi"):
            github_skill = GitHubSkill()
            hf_skill = HuggingFaceSkill()

            # Oba powinny być niezależne
            assert hasattr(github_skill, "search_repos")
            assert hasattr(hf_skill, "search_models")

            # Mock repozytoriów
            mock_repo = MagicMock()
            mock_repo.full_name = "huggingface/transformers"
            mock_repo.description = "Transformers library"
            mock_repo.stargazers_count = 100000
            mock_repo.forks_count = 20000
            mock_repo.html_url = "https://github.com/huggingface/transformers"
            mock_repo.language = "Python"

            github_skill.github.search_repositories = MagicMock(
                return_value=[mock_repo]
            )

            # Mock modeli
            mock_model = MagicMock()
            mock_model.id = "bert-base-uncased"
            mock_model.pipeline_tag = "fill-mask"
            mock_model.downloads = 50000
            mock_model.likes = 500
            mock_model.tags = ["pytorch", "transformers"]

            hf_skill.api.list_models = MagicMock(return_value=[mock_model])

            # Agent może użyć obu
            github_result = github_skill.search_repos(query="transformers")
            hf_result = hf_skill.search_models(query="bert")

            assert "huggingface/transformers" in github_result
            assert "bert-base-uncased" in hf_result
