"""Coverage tests for GitHubSkill - fully mocked, no PyGithub required."""

from unittest.mock import MagicMock, patch

import pytest

import venom_core.execution.skills.github_skill as github_skill_module
from venom_core.execution.skills.github_skill import (
    MAX_README_LENGTH,
    MAX_REPOS_RESULTS,
    PYGITHUB_MISSING_MSG,
    GitHubSkill,
)


# ---------------------------------------------------------------------------
# Helpers to build mock repo objects
# ---------------------------------------------------------------------------


def _make_mock_repo(
    full_name="user/repo",
    description="A test repo",
    stars=100,
    forks=10,
    url="https://github.com/user/repo",
    language="Python",
    created_at=None,
):
    repo = MagicMock()
    repo.full_name = full_name
    repo.description = description
    repo.stargazers_count = stars
    repo.forks_count = forks
    repo.html_url = url
    repo.language = language
    if created_at is None:
        repo.created_at = MagicMock()
        repo.created_at.strftime = MagicMock(return_value="2024-01-01")
    else:
        repo.created_at = created_at
    return repo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def patched_github():
    """Patch Github class and provide a mock instance + Auth.

    Note: GithubException is intentionally NOT patched here so that the module's
    own fallback GithubException class (a plain Exception subclass) stays in place.
    Tests that need to trigger the GithubException handler use that class directly.
    """
    with (
        patch.object(github_skill_module, "_GITHUB_AVAILABLE", True),
        patch.object(github_skill_module, "Github") as mock_cls,
        patch.object(github_skill_module, "Auth") as mock_auth,
    ):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_cls, mock_instance, mock_auth


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def test_init_without_token_no_env(patched_github, monkeypatch):
    """Initialises with unauthenticated Github when no token present."""
    mock_cls, mock_instance, _ = patched_github
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    skill = GitHubSkill()
    assert skill.github is mock_instance
    mock_cls.assert_called_once_with()


def test_init_with_explicit_token(patched_github):
    """Initialises with Auth.Token when explicit token provided."""
    mock_cls, mock_instance, mock_auth = patched_github
    skill = GitHubSkill(github_token="tok123")
    mock_auth.Token.assert_called_once_with("tok123")
    mock_cls.assert_called_once()


def test_init_with_env_token(patched_github, monkeypatch):
    """Reads GITHUB_TOKEN from environment when no explicit token."""
    mock_cls, mock_instance, mock_auth = patched_github
    monkeypatch.setenv("GITHUB_TOKEN", "env_token")
    skill = GitHubSkill()
    mock_auth.Token.assert_called_once_with("env_token")


def test_init_unavailable_dependency(monkeypatch):
    """When PyGithub is not installed, github attribute is None."""
    monkeypatch.setattr(github_skill_module, "_GITHUB_AVAILABLE", False)
    skill = GitHubSkill()
    assert skill.github is None


# ---------------------------------------------------------------------------
# search_repos
# ---------------------------------------------------------------------------


def test_search_repos_no_github():
    """Returns PYGITHUB_MISSING_MSG when github is None."""
    skill = GitHubSkill.__new__(GitHubSkill)
    skill.github = None
    assert skill.search_repos("x") == PYGITHUB_MISSING_MSG


def test_search_repos_returns_top_results(patched_github):
    """Returns formatted output for found repos."""
    _, mock_instance, _ = patched_github
    repos = [_make_mock_repo(full_name=f"u/r{i}", stars=1000 - i) for i in range(3)]
    mock_instance.search_repositories.return_value = repos

    skill = GitHubSkill()
    result = skill.search_repos("django", language="Python", sort="stars")

    assert "u/r0" in result
    assert "u/r1" in result
    mock_instance.search_repositories.assert_called_once()
    call_kw = mock_instance.search_repositories.call_args[1]
    assert "language:Python" in call_kw["query"]
    assert call_kw["sort"] == "stars"


def test_search_repos_limits_to_max(patched_github):
    """Returns at most MAX_REPOS_RESULTS repos even if more available."""
    _, mock_instance, _ = patched_github
    many_repos = [_make_mock_repo(full_name=f"u/r{i}") for i in range(10)]
    mock_instance.search_repositories.return_value = many_repos

    skill = GitHubSkill()
    result = skill.search_repos("test")

    # Only first MAX_REPOS_RESULTS should appear
    for i in range(MAX_REPOS_RESULTS):
        assert f"u/r{i}" in result
    assert f"u/r{MAX_REPOS_RESULTS}" not in result


def test_search_repos_no_results(patched_github):
    """Returns 'not found' message when result list is empty."""
    _, mock_instance, _ = patched_github
    mock_instance.search_repositories.return_value = []

    skill = GitHubSkill()
    result = skill.search_repos("zzz_nonexistent_query_xyz")
    assert "Nie znaleziono" in result


def test_search_repos_missing_description(patched_github):
    """Repo with None description shows fallback text."""
    _, mock_instance, _ = patched_github
    repo = _make_mock_repo(description=None)
    mock_instance.search_repositories.return_value = [repo]

    skill = GitHubSkill()
    result = skill.search_repos("test")
    assert "Brak opisu" in result


def test_search_repos_missing_language(patched_github):
    """Repo with None language shows fallback text."""
    _, mock_instance, _ = patched_github
    repo = _make_mock_repo(language=None)
    mock_instance.search_repositories.return_value = [repo]

    skill = GitHubSkill()
    result = skill.search_repos("test")
    assert "Nieznany" in result


def test_search_repos_github_exception(patched_github):
    """GithubException is caught and returned as error string."""
    _, mock_instance, _ = patched_github
    exc = github_skill_module.GithubException("rate limited")
    exc.status = 403
    mock_instance.search_repositories.side_effect = exc

    skill = GitHubSkill()
    result = skill.search_repos("test")
    assert "❌" in result


def test_search_repos_generic_exception(patched_github):
    """Unexpected exception is caught and returned as error string."""
    _, mock_instance, _ = patched_github
    mock_instance.search_repositories.side_effect = ValueError("unexpected")

    skill = GitHubSkill()
    result = skill.search_repos("test")
    assert "❌" in result


def test_search_repos_without_language_filter(patched_github):
    """Without language filter, query is passed as-is."""
    _, mock_instance, _ = patched_github
    mock_instance.search_repositories.return_value = [_make_mock_repo()]

    skill = GitHubSkill()
    skill.search_repos("fastapi")

    call_kw = mock_instance.search_repositories.call_args[1]
    assert "language:" not in call_kw["query"]


# ---------------------------------------------------------------------------
# get_readme
# ---------------------------------------------------------------------------


def test_get_readme_no_github():
    """Returns PYGITHUB_MISSING_MSG when github is None."""
    skill = GitHubSkill.__new__(GitHubSkill)
    skill.github = None
    assert skill.get_readme("owner/repo") == PYGITHUB_MISSING_MSG


def test_get_readme_success(patched_github):
    """Returns readme content with repo metadata."""
    _, mock_instance, _ = patched_github
    mock_repo = _make_mock_repo(stars=2500)
    readme = MagicMock()
    readme.decoded_content = b"# Hello World\n\nContent"
    mock_repo.get_readme.return_value = readme
    mock_instance.get_repo.return_value = mock_repo

    skill = GitHubSkill()
    result = skill.get_readme("user/repo")

    assert "Hello World" in result
    assert "2,500" in result
    mock_instance.get_repo.assert_called_once_with("user/repo")


def test_get_readme_from_full_url(patched_github):
    """Extracts owner/repo from full GitHub URL."""
    _, mock_instance, _ = patched_github
    mock_repo = _make_mock_repo()
    readme = MagicMock()
    readme.decoded_content = b"# README"
    mock_repo.get_readme.return_value = readme
    mock_instance.get_repo.return_value = mock_repo

    skill = GitHubSkill()
    skill.get_readme("https://github.com/user/repo")
    mock_instance.get_repo.assert_called_once_with("user/repo")


def test_get_readme_truncates_long_content(patched_github):
    """Truncates readme content exceeding MAX_README_LENGTH."""
    _, mock_instance, _ = patched_github
    mock_repo = _make_mock_repo()
    readme = MagicMock()
    readme.decoded_content = b"A" * (MAX_README_LENGTH + 500)
    mock_repo.get_readme.return_value = readme
    mock_instance.get_repo.return_value = mock_repo

    skill = GitHubSkill()
    result = skill.get_readme("user/repo")
    assert "obcięty" in result


def test_get_readme_404_exception(patched_github):
    """404 GithubException returns 'not found' message."""
    _, mock_instance, _ = patched_github
    exc = github_skill_module.GithubException("Not Found")
    exc.status = 404
    mock_instance.get_repo.side_effect = exc

    skill = GitHubSkill()
    result = skill.get_readme("user/missing")
    assert "Nie znaleziono" in result


def test_get_readme_other_github_exception(patched_github):
    """Non-404 GithubException returns generic error message."""
    _, mock_instance, _ = patched_github
    exc = github_skill_module.GithubException("server error")
    exc.status = 500
    mock_instance.get_repo.side_effect = exc

    skill = GitHubSkill()
    result = skill.get_readme("user/repo")
    assert "❌" in result


def test_get_readme_generic_exception(patched_github):
    """Unexpected exception is caught and returned as error string."""
    _, mock_instance, _ = patched_github
    mock_instance.get_repo.side_effect = ValueError("bad input")

    skill = GitHubSkill()
    result = skill.get_readme("user/repo")
    assert "❌" in result


# ---------------------------------------------------------------------------
# get_trending
# ---------------------------------------------------------------------------


def test_get_trending_no_github():
    """Returns PYGITHUB_MISSING_MSG when github is None."""
    skill = GitHubSkill.__new__(GitHubSkill)
    skill.github = None
    assert skill.get_trending("python") == PYGITHUB_MISSING_MSG


def test_get_trending_success(patched_github):
    """Returns formatted trending output."""
    _, mock_instance, _ = patched_github
    repos = [_make_mock_repo(full_name="hot/project", stars=9000)]
    mock_instance.search_repositories.return_value = repos

    skill = GitHubSkill()
    result = skill.get_trending("machine-learning")
    assert "Popularne projekty" in result
    assert "hot/project" in result
    assert "9,000" in result


def test_get_trending_no_results(patched_github):
    """Returns 'not found' message when no trending repos."""
    _, mock_instance, _ = patched_github
    mock_instance.search_repositories.return_value = []

    skill = GitHubSkill()
    result = skill.get_trending("xyzzy_nonexistent_topic")
    assert "Nie znaleziono" in result


def test_get_trending_github_exception(patched_github):
    """GithubException propagates as error string."""
    _, mock_instance, _ = patched_github
    exc = github_skill_module.GithubException("rate limited")
    exc.status = 403
    mock_instance.search_repositories.side_effect = exc

    skill = GitHubSkill()
    result = skill.get_trending("python")
    assert "❌" in result


def test_get_trending_generic_exception(patched_github):
    """Unexpected exception is caught and returned as error string."""
    _, mock_instance, _ = patched_github
    mock_instance.search_repositories.side_effect = RuntimeError("network error")

    skill = GitHubSkill()
    result = skill.get_trending("python")
    assert "❌" in result


# ---------------------------------------------------------------------------
# _extract_repo_name
# ---------------------------------------------------------------------------


def test_extract_repo_name_short_form(patched_github):
    _, mock_instance, _ = patched_github
    skill = GitHubSkill()
    assert skill._extract_repo_name("owner/repo") == "owner/repo"


def test_extract_repo_name_full_url(patched_github):
    _, mock_instance, _ = patched_github
    skill = GitHubSkill()
    assert skill._extract_repo_name("https://github.com/owner/repo") == "owner/repo"


def test_extract_repo_name_url_with_trailing_slash(patched_github):
    _, mock_instance, _ = patched_github
    skill = GitHubSkill()
    assert skill._extract_repo_name("https://github.com/owner/repo/") == "owner/repo"


def test_extract_repo_name_invalid_raises(patched_github):
    _, mock_instance, _ = patched_github
    skill = GitHubSkill()
    with pytest.raises(ValueError):
        skill._extract_repo_name("no_slash_here")


# ---------------------------------------------------------------------------
# close / context manager
# ---------------------------------------------------------------------------


def test_close_calls_github_close(patched_github):
    """close() calls github.close() when github is set."""
    _, mock_instance, _ = patched_github
    skill = GitHubSkill()
    skill.close()
    mock_instance.close.assert_called_once()


def test_close_noop_when_github_none():
    """close() is safe when github is None."""
    skill = GitHubSkill.__new__(GitHubSkill)
    skill.github = None
    skill.close()  # Should not raise


def test_context_manager(patched_github):
    """Context manager calls close() on exit."""
    _, mock_instance, _ = patched_github
    with GitHubSkill() as skill:
        assert skill.github is mock_instance
    mock_instance.close.assert_called_once()
