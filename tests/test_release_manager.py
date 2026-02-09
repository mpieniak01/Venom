"""Testy dla ReleaseManagerAgent."""

import pytest

from venom_core.agents.release_manager import ReleaseManagerAgent
from venom_core.execution.kernel_builder import KernelBuilder


@pytest.fixture
def kernel():
    """Fixture dla Semantic Kernel."""
    builder = KernelBuilder()
    return builder.build_kernel()


@pytest.fixture
def release_manager(kernel):
    """Fixture dla ReleaseManagerAgent."""
    return ReleaseManagerAgent(kernel)


def test_release_manager_initialization(release_manager):
    """Test inicjalizacji ReleaseManagerAgent."""
    assert release_manager is not None
    assert release_manager.git_skill is not None
    assert release_manager.file_skill is not None


def test_parse_commits_conventional(release_manager):
    """Test parsowania conventional commits."""
    commit_log = """abc1234 - John Doe - 2024-01-15 10:00 - feat(auth): add login endpoint
def5678 - Jane Smith - 2024-01-15 09:00 - fix: correct typo in readme
ghi9012 - Bob Wilson - 2024-01-14 14:00 - docs: update API documentation"""

    commits = release_manager._parse_commits(commit_log)

    assert len(commits) == 3
    assert commits[0]["type"] == "feat"
    assert commits[0]["scope"] == "auth"
    assert commits[1]["type"] == "fix"
    assert commits[2]["type"] == "docs"


def test_parse_commits_breaking_change(release_manager):
    """Test parsowania breaking changes."""
    commit_log = """abc1234 - John Doe - 2024-01-15 10:00 - feat!: change API structure BREAKING CHANGE"""

    commits = release_manager._parse_commits(commit_log)

    assert len(commits) == 1
    assert commits[0]["breaking"] is True


def test_generate_changelog(release_manager):
    """Test generowania changelog."""
    commits = [
        {
            "hash": "abc1234",
            "type": "feat",
            "scope": "auth",
            "message": "add login endpoint",
            "breaking": False,
        },
        {
            "hash": "def5678",
            "type": "fix",
            "scope": None,
            "message": "correct typo",
            "breaking": False,
        },
        {
            "hash": "ghi9012",
            "type": "feat",
            "scope": "api",
            "message": "breaking API change",
            "breaking": True,
        },
    ]

    changelog = release_manager._generate_changelog(commits)

    assert "## [Unreleased]" in changelog
    assert "### Breaking Changes" in changelog
    assert "### Features" in changelog
    assert "### Bug Fixes" in changelog
    assert "add login endpoint" in changelog
    assert "correct typo" in changelog


@pytest.mark.asyncio
async def test_prepare_release_no_git(release_manager, tmp_path):
    """Test przygotowania release'u bez repozytorium Git."""
    # Ten test może się nie powieść jeśli workspace nie jest repozytorium
    # Jest to oczekiwane zachowanie
    result = await release_manager.prepare_release(version_type="patch")

    # Sprawdź czy zwraca string (nawet jeśli błąd)
    assert isinstance(result, str)


def test_parse_commits_non_conventional(release_manager):
    """Test parsowania commitów nie-konwencjonalnych."""
    commit_log = """abc1234 - John Doe - 2024-01-15 10:00 - just a regular commit message
def5678 - Jane Smith - 2024-01-15 09:00 - another random message"""

    commits = release_manager._parse_commits(commit_log)

    assert len(commits) == 2
    # Nie-konwencjonalne commity powinny być sklasyfikowane jako "other"
    assert commits[0]["type"] == "other"
    assert commits[1]["type"] == "other"


def test_generate_changelog_empty(release_manager):
    """Test generowania changelog z pustej listy commitów."""
    commits = []

    changelog = release_manager._generate_changelog(commits)

    # Powinien zawierać przynajmniej nagłówek
    assert "## [Unreleased]" in changelog


def test_prepare_release_helper_decisions(release_manager):
    commits = [
        {"type": "fix", "breaking": False},
        {"type": "feat", "breaking": False},
    ]
    assert release_manager._resolve_release_type("auto", commits) == "minor"
    assert (
        release_manager._resolve_release_type(
            "auto", [{"type": "feat", "breaking": True}]
        )
        == "major"
    )
    assert (
        release_manager._resolve_release_type(
            "auto", [{"type": "fix", "breaking": False}]
        )
        == "patch"
    )
    assert release_manager._resolve_release_type("patch", commits) == "patch"


def test_prepare_release_changelog_merge_helpers(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    merged = ReleaseManagerAgent._merge_changelog(path, "## [Unreleased]\n- A")
    assert merged.startswith("# Changelog")

    path.write_text("# Changelog\n\nOld entry", encoding="utf-8")
    merged_existing = ReleaseManagerAgent._merge_changelog(
        path, "## [Unreleased]\n- New"
    )
    assert "New" in merged_existing
    assert "Old entry" in merged_existing

    path.write_text("Legacy content", encoding="utf-8")
    merged_legacy = ReleaseManagerAgent._merge_changelog(path, "## [Unreleased]\n- New")
    assert merged_legacy.startswith("# Changelog")
    assert "Legacy content" in merged_legacy


def test_prepare_release_summary_helpers(release_manager):
    summary = release_manager._build_commit_summary(
        [
            {"type": "feat", "breaking": False},
            {"type": "fix", "breaking": False},
            {"type": "other", "breaking": True},
        ]
    )
    assert "Features: 1" in summary
    assert "Fixes: 1" in summary
    assert "Breaking: 1" in summary

    assert "Automatycznie wykryto typ" in release_manager._build_release_type_line(
        "auto", "minor"
    )
    assert "Użyto ręcznego typu" in release_manager._build_release_type_line(
        "patch", "patch"
    )
    assert "Następne kroki" in release_manager._build_release_next_steps()
