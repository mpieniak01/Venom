"""Testy jednostkowe dla GitHubSkill."""

from unittest.mock import MagicMock, patch

import pytest

from venom_core.execution.skills.github_skill import GitHubSkill


@pytest.fixture
def mock_github():
    """Fixture dla zmockowanego GitHub API."""
    with patch("venom_core.execution.skills.github_skill.Github") as mock:
        yield mock


@pytest.fixture
def github_skill(mock_github):
    """Fixture dla GitHubSkill."""
    skill = GitHubSkill()
    return skill


def test_github_skill_initialization_without_token(mock_github):
    """Test inicjalizacji GitHubSkill bez tokenu."""
    skill = GitHubSkill()
    assert skill.github is not None
    mock_github.assert_called_once()


def test_github_skill_initialization_with_token(mock_github):
    """Test inicjalizacji GitHubSkill z tokenem."""
    test_token = "test_github_token_123"
    skill = GitHubSkill(github_token=test_token)
    assert skill.github is not None
    # Sprawdź że Auth.Token został użyty
    mock_github.assert_called()


def test_search_repos_success(github_skill, mock_github):
    """Test wyszukiwania repozytoriów - sukces."""
    # Mock repozytoriów
    mock_repo1 = MagicMock()
    mock_repo1.full_name = "user/repo1"
    mock_repo1.description = "Test repo 1"
    mock_repo1.stargazers_count = 1000
    mock_repo1.forks_count = 100
    mock_repo1.html_url = "https://github.com/user/repo1"
    mock_repo1.language = "Python"

    mock_repo2 = MagicMock()
    mock_repo2.full_name = "user/repo2"
    mock_repo2.description = "Test repo 2"
    mock_repo2.stargazers_count = 500
    mock_repo2.forks_count = 50
    mock_repo2.html_url = "https://github.com/user/repo2"
    mock_repo2.language = "JavaScript"

    # Skonfiguruj mock search_repositories
    github_skill.github.search_repositories = MagicMock(
        return_value=[mock_repo1, mock_repo2]
    )

    # Wywołaj search_repos
    result = github_skill.search_repos(query="test", language="Python", sort="stars")

    # Asercje
    assert "user/repo1" in result
    assert "user/repo2" in result
    assert "1,000" in result  # Formatowanie liczby
    assert "Python" in result
    github_skill.github.search_repositories.assert_called_once()


def test_search_repos_no_results(github_skill):
    """Test wyszukiwania repozytoriów - brak wyników."""
    # Mock pustej listy
    github_skill.github.search_repositories = MagicMock(return_value=[])

    result = github_skill.search_repos(query="nonexistent")

    assert "Nie znaleziono repozytoriów" in result


def test_search_repos_with_language_filter(github_skill):
    """Test wyszukiwania z filtrem języka."""
    mock_repo = MagicMock()
    mock_repo.full_name = "user/repo"
    mock_repo.description = "Test"
    mock_repo.stargazers_count = 100
    mock_repo.forks_count = 10
    mock_repo.html_url = "https://github.com/user/repo"
    mock_repo.language = "Python"

    github_skill.github.search_repositories = MagicMock(return_value=[mock_repo])

    github_skill.search_repos(query="test", language="Python")

    # Sprawdź że zapytanie zawiera language:Python
    call_args = github_skill.github.search_repositories.call_args
    assert "language:Python" in call_args[1]["query"]


def test_get_readme_success(github_skill):
    """Test pobierania README - sukces."""
    # Mock repozytorium
    mock_repo = MagicMock()
    mock_repo.full_name = "user/repo"
    mock_repo.stargazers_count = 1000
    mock_repo.html_url = "https://github.com/user/repo"

    # Mock README
    mock_readme = MagicMock()
    mock_readme.decoded_content = b"# Test README\n\nThis is a test."
    mock_repo.get_readme = MagicMock(return_value=mock_readme)

    github_skill.github.get_repo = MagicMock(return_value=mock_repo)

    result = github_skill.get_readme("user/repo")

    assert "user/repo" in result
    assert "Test README" in result
    assert "1,000" in result


def test_get_readme_from_url(github_skill):
    """Test pobierania README z pełnego URL."""
    mock_repo = MagicMock()
    mock_repo.full_name = "user/repo"
    mock_repo.stargazers_count = 100
    mock_repo.html_url = "https://github.com/user/repo"

    mock_readme = MagicMock()
    mock_readme.decoded_content = b"# README"
    mock_repo.get_readme = MagicMock(return_value=mock_readme)

    github_skill.github.get_repo = MagicMock(return_value=mock_repo)

    result = github_skill.get_readme("https://github.com/user/repo")

    assert "user/repo" in result
    github_skill.github.get_repo.assert_called_with("user/repo")


def test_get_readme_not_found(github_skill):
    """Test pobierania README - repozytorium nie znalezione."""
    from github import GithubException

    # Mock GithubException dla 404
    github_skill.github.get_repo = MagicMock(
        side_effect=GithubException(404, {"message": "Not Found"})
    )

    result = github_skill.get_readme("user/nonexistent")

    assert "❌" in result
    assert "Nie znaleziono" in result


def test_get_trending_success(github_skill):
    """Test wyszukiwania popularnych projektów - sukces."""
    # Mock repozytoriów
    mock_repo = MagicMock()
    mock_repo.full_name = "user/trending-repo"
    mock_repo.description = "Trending project"
    mock_repo.stargazers_count = 5000
    mock_repo.html_url = "https://github.com/user/trending-repo"
    mock_repo.language = "Python"
    mock_repo.created_at = MagicMock()
    mock_repo.created_at.strftime = MagicMock(return_value="2024-01-01")

    github_skill.github.search_repositories = MagicMock(return_value=[mock_repo])

    result = github_skill.get_trending(topic="machine-learning")

    assert "Popularne projekty" in result
    assert "user/trending-repo" in result
    assert "5,000" in result
    assert "2024-01-01" in result


def test_extract_repo_name_from_url(github_skill):
    """Test ekstrakcji nazwy repozytorium z URL."""
    # Test z pełnym URL
    result = github_skill._extract_repo_name("https://github.com/user/repo")
    assert result == "user/repo"

    # Test z URL z trailing slash
    result = github_skill._extract_repo_name("https://github.com/user/repo/")
    assert result == "user/repo"

    # Test z już sformatowaną nazwą
    result = github_skill._extract_repo_name("user/repo")
    assert result == "user/repo"


def test_extract_repo_name_invalid(github_skill):
    """Test ekstrakcji nazwy - nieprawidłowy format."""
    with pytest.raises(ValueError):
        github_skill._extract_repo_name("invalid")


def test_search_repos_error_handling(github_skill):
    """Test obsługi błędów podczas wyszukiwania."""
    from github import GithubException

    github_skill.github.search_repositories = MagicMock(
        side_effect=GithubException(500, {"message": "Server Error"})
    )

    result = github_skill.search_repos(query="test")

    assert "❌" in result
    assert "Błąd" in result
