"""Targeted tests for PlatformSkill integration branches."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import venom_core.execution.skills.platform_skill as platform_skill_mod
from venom_core.execution.skills.platform_skill import (
    GITHUB_NOT_CONFIGURED_ERROR,
    PlatformSkill,
)


class _Secret:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


class GithubException(Exception):
    def __init__(self, status: int = 400, message: str = "bad request"):
        super().__init__(message)
        self.status = status
        self.data = {"message": message}


def _mock_settings(
    github_token: str = "gh_token",
    repo_name: str = "acme/repo",
    discord: str = "https://discord.test/webhook",
    slack: str = "https://slack.test/webhook",
):
    return SimpleNamespace(
        GITHUB_TOKEN=_Secret(github_token),
        GITHUB_REPO_NAME=repo_name,
        DISCORD_WEBHOOK_URL=_Secret(discord),
        SLACK_WEBHOOK_URL=_Secret(slack),
    )


def _make_issue(number: int, title: str, body: str = "", is_pr: bool = False):
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.body = body
    issue.state = "open"
    issue.created_at = datetime(2025, 1, 1, 10, 0, 0)
    issue.updated_at = datetime(2025, 1, 1, 12, 0, 0)
    issue.labels = [SimpleNamespace(name="bug")]
    issue.assignees = [SimpleNamespace(login="bot")]
    issue.html_url = f"https://github.test/issues/{number}"
    issue.pull_request = object() if is_pr else None
    return issue


def test_get_assigned_issues_returns_not_configured_when_missing_client(monkeypatch):
    monkeypatch.setattr(platform_skill_mod, "SETTINGS", _mock_settings("", ""))
    skill = PlatformSkill()
    assert skill.get_assigned_issues() == GITHUB_NOT_CONFIGURED_ERROR


def test_get_assigned_issues_success_skips_pull_requests(monkeypatch):
    monkeypatch.setattr(platform_skill_mod, "SETTINGS", _mock_settings())
    skill = PlatformSkill()

    repo = MagicMock()
    repo.get_issues.return_value = [
        _make_issue(1, "Issue one", "A" * 20, is_pr=False),
        _make_issue(2, "PR masquerading as issue", is_pr=True),
    ]
    skill.github_client = MagicMock()
    skill.github_client.get_repo.return_value = repo

    result = skill.get_assigned_issues(state="open")
    assert "Znaleziono 1 Issues" in result
    assert "#1: Issue one" in result
    assert "PR masquerading" not in result


def test_get_issue_details_and_create_pr_success(monkeypatch):
    monkeypatch.setattr(platform_skill_mod, "SETTINGS", _mock_settings())
    skill = PlatformSkill()

    issue = _make_issue(7, "Fix bug", "Detailed body")
    comment = MagicMock()
    comment.user.login = "alice"
    comment.created_at = datetime(2025, 1, 2, 10, 0, 0)
    comment.body = "Looks good"
    issue.get_comments.return_value = [comment]

    pr = MagicMock()
    pr.number = 12
    pr.title = "PR title"
    pr.html_url = "https://github.test/pulls/12"

    repo = MagicMock()
    repo.get_issue.return_value = issue
    repo.create_pull.return_value = pr

    skill.github_client = MagicMock()
    skill.github_client.get_repo.return_value = repo

    details = skill.get_issue_details(7)
    created = skill.create_pull_request("feat", "PR title", "Body")

    assert "Issue #7: Fix bug" in details
    assert "Komentarze (1):" in details
    assert "Utworzono Pull Request #12" in created


def test_comment_on_issue_handles_github_exception(monkeypatch):
    monkeypatch.setattr(platform_skill_mod, "SETTINGS", _mock_settings())
    skill = PlatformSkill()

    issue = MagicMock()
    issue.create_comment.side_effect = GithubException(403, "forbidden")
    repo = MagicMock()
    repo.get_issue.return_value = issue
    skill.github_client = MagicMock()
    skill.github_client.get_repo.return_value = repo

    result = skill.comment_on_issue(5, "msg")
    assert "Błąd GitHub API: 403" in result


@pytest.mark.asyncio
async def test_send_notification_validates_channel_and_webhook(monkeypatch):
    monkeypatch.setattr(
        platform_skill_mod, "SETTINGS", _mock_settings(discord="", slack="")
    )
    skill = PlatformSkill()

    bad_channel = await skill.send_notification("msg", channel="teams")
    no_webhook = await skill.send_notification("msg", channel="discord")

    assert "Nieznany kanał" in bad_channel
    assert "Webhook URL nie skonfigurowany" in no_webhook


@pytest.mark.asyncio
async def test_send_notification_success_and_http_error(monkeypatch):
    monkeypatch.setattr(platform_skill_mod, "SETTINGS", _mock_settings())
    skill = PlatformSkill()

    client = MagicMock()
    client.apost = AsyncMock(return_value=None)

    class _CM:
        async def __aenter__(self):
            return client

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        platform_skill_mod, "TrafficControlledHttpClient", lambda **_: _CM()
    )
    ok = await skill.send_notification("hello", channel="discord")
    assert "Wysłano powiadomienie" in ok
    client.apost.assert_awaited_once()

    request = httpx.Request("POST", "https://discord.test/webhook")
    response = httpx.Response(status_code=429, request=request, text="rate limited")
    client.apost = AsyncMock(
        side_effect=httpx.HTTPStatusError("boom", request=request, response=response)
    )
    err = await skill.send_notification("hello", channel="discord")
    assert "Błąd HTTP 429" in err


def test_check_connection_reports_connected_and_error(monkeypatch):
    monkeypatch.setattr(platform_skill_mod, "SETTINGS", _mock_settings())
    skill = PlatformSkill()

    skill.github_client = MagicMock()
    skill.github_client.get_user.return_value.login = "bot"
    status_ok = skill.check_connection()
    assert status_ok["github"]["configured"] is True
    assert status_ok["github"]["connected"] is True

    skill.github_client.get_user.side_effect = RuntimeError("api down")
    status_bad = skill.check_connection()
    assert status_bad["github"]["connected"] is False
    assert "api down" in str(status_bad["github"]["error"])
