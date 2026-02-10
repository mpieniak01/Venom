"""Testy fallbacków GitHubSkill gdy optional dependency jest niedostępne."""

from venom_core.execution.skills import github_skill as github_skill_module


def test_github_skill_returns_missing_dependency_message(monkeypatch):
    monkeypatch.setattr(github_skill_module, "_GITHUB_AVAILABLE", False)

    skill = github_skill_module.GitHubSkill()

    assert skill.search_repos("test") == github_skill_module.PYGITHUB_MISSING_MSG
    assert skill.get_readme("owner/repo") == github_skill_module.PYGITHUB_MISSING_MSG
    assert skill.get_trending("python") == github_skill_module.PYGITHUB_MISSING_MSG
