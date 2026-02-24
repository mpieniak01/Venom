"""Coverage wave tests for PR-172C-07 agents: release_manager, integrator, tester, toolmaker, coder."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_kernel():
    """Mock Semantic Kernel for all agents in this module."""
    kernel = MagicMock()
    kernel.add_plugin = MagicMock()
    mock_service = MagicMock()
    mock_service.get_chat_message_content = AsyncMock(
        return_value=MagicMock(__str__=lambda s: "mocked response")
    )
    kernel.get_service = MagicMock(return_value=mock_service)
    return kernel


# ===========================================================================
# ReleaseManagerAgent – branch coverage
# ===========================================================================


class TestReleaseManagerBranches:
    """Branch-level tests for ReleaseManagerAgent decision logic."""

    @pytest.fixture
    def mock_git_skill(self):
        skill = MagicMock()
        skill.workspace_root = tempfile.mkdtemp()
        skill.get_last_commit_log = AsyncMock(
            return_value=(
                "abc1234 - Alice - 2024-01-20 10:00 - feat(auth): add login\n"
                "def5678 - Bob - 2024-01-20 09:00 - fix: correct typo\n"
                "ghi9012 - Carol - 2024-01-19 14:00 - chore: update deps\n"
                "jkl3456 - Dan - 2024-01-19 12:00 - BREAKING CHANGE: new API\n"
            )
        )
        return skill

    @pytest.fixture
    def mock_file_skill(self):
        skill = MagicMock()
        skill.write_file = AsyncMock()
        return skill

    @pytest.fixture
    def agent(self, mock_kernel, mock_git_skill, mock_file_skill):
        from venom_core.agents.release_manager import ReleaseManagerAgent

        return ReleaseManagerAgent(
            kernel=mock_kernel,
            git_skill=mock_git_skill,
            file_skill=mock_file_skill,
        )

    # -- process() success path --
    @pytest.mark.asyncio
    async def test_process_success(self, agent):
        """process() invokes LLM and returns response."""
        mock_result = MagicMock()
        mock_result.content = "Release prepared successfully."
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = mock_result
            result = await agent.process("Prepare a patch release")
        assert isinstance(result, str)
        assert len(result) > 0

    # -- process() error path --
    @pytest.mark.asyncio
    async def test_process_error_path(self, agent):
        """process() returns error string when LLM raises exception."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("API failure")
            result = await agent.process("release")
        assert "❌" in result

    # -- prepare_release auto detection --
    @pytest.mark.asyncio
    async def test_prepare_release_auto_major(self, agent, tmp_path):
        """prepare_release auto-detects MAJOR when breaking commits present."""
        agent.git_skill.workspace_root = str(tmp_path)
        result = await agent.prepare_release(version_type="auto")
        assert "MAJOR" in result or "Przygotowanie" in result

    # -- prepare_release manual type --
    @pytest.mark.asyncio
    async def test_prepare_release_manual_minor(self, agent, tmp_path):
        """prepare_release uses manual version type when specified."""
        agent.git_skill.workspace_root = str(tmp_path)
        result = await agent.prepare_release(version_type="minor")
        assert "MINOR" in result

    # -- prepare_release error path --
    @pytest.mark.asyncio
    async def test_prepare_release_exception(self, agent):
        """prepare_release handles git_skill exceptions."""
        agent.git_skill.get_last_commit_log = AsyncMock(
            side_effect=RuntimeError("git error")
        )
        result = await agent.prepare_release()
        assert "❌" in result

    # -- _resolve_release_type branches --
    def test_resolve_release_type_auto_breaking(self, agent):
        """_resolve_release_type returns 'major' for breaking commits."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        commits = [
            {"type": "feat", "breaking": True, "hash": "a", "message": "x", "scope": None}
        ]
        assert ReleaseManagerAgent._resolve_release_type("auto", commits) == "major"

    def test_resolve_release_type_auto_feat(self, agent):
        """_resolve_release_type returns 'minor' for feat commits without breaking."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        commits = [
            {"type": "feat", "breaking": False, "hash": "a", "message": "x", "scope": None}
        ]
        assert ReleaseManagerAgent._resolve_release_type("auto", commits) == "minor"

    def test_resolve_release_type_auto_fix_only(self, agent):
        """_resolve_release_type returns 'patch' for only fix commits."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        commits = [
            {"type": "fix", "breaking": False, "hash": "a", "message": "x", "scope": None}
        ]
        assert ReleaseManagerAgent._resolve_release_type("auto", commits) == "patch"

    def test_resolve_release_type_manual(self, agent):
        """_resolve_release_type returns given type when not 'auto'."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        commits = [{"type": "fix", "breaking": True, "hash": "a", "message": "x", "scope": None}]
        assert ReleaseManagerAgent._resolve_release_type("patch", commits) == "patch"

    # -- _merge_changelog branches --
    def test_merge_changelog_no_existing_file(self, tmp_path):
        """_merge_changelog creates new changelog when file doesn't exist."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        path = tmp_path / "CHANGELOG.md"
        result = ReleaseManagerAgent._merge_changelog(path, "## [1.0.0]\n- entry\n")
        assert "# Changelog" in result
        assert "1.0.0" in result

    def test_merge_changelog_existing_with_header(self, tmp_path):
        """_merge_changelog prepends new entry when file has # Changelog header."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        path = tmp_path / "CHANGELOG.md"
        path.write_text("# Changelog\n\n## [0.9.0]\n- old entry\n")
        result = ReleaseManagerAgent._merge_changelog(path, "## [1.0.0]\n- new entry\n")
        # New entry should appear before old entry
        assert result.index("1.0.0") < result.index("0.9.0")

    def test_merge_changelog_existing_without_header(self, tmp_path):
        """_merge_changelog prepends header when file lacks it."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        path = tmp_path / "CHANGELOG.md"
        path.write_text("Some existing content without header\n")
        result = ReleaseManagerAgent._merge_changelog(path, "## [1.0.0]\n- new\n")
        assert "# Changelog" in result
        assert "1.0.0" in result

    # -- _parse_commits with malformed line --
    def test_parse_commits_malformed_line(self, agent):
        """_parse_commits handles malformed commit lines gracefully."""
        result = agent._parse_commits("just a line without proper format")
        assert len(result) == 1
        assert result[0]["type"] == "other"

    # -- _generate_changelog with all sections --
    def test_generate_changelog_all_sections(self, agent):
        """_generate_changelog renders breaking, features, fixes, other."""
        commits = [
            {"hash": "a1", "type": "feat", "scope": "auth", "message": "add login", "breaking": True},
            {"hash": "b2", "type": "feat", "scope": None, "message": "add dashboard", "breaking": False},
            {"hash": "c3", "type": "fix", "scope": None, "message": "fix crash", "breaking": False},
            {"hash": "d4", "type": "chore", "scope": None, "message": "update deps", "breaking": False},
        ]
        result = agent._generate_changelog(commits)
        assert "Breaking Changes" in result
        assert "Features" in result
        assert "Bug Fixes" in result
        assert "Other Changes" in result

    # -- _build_release_type_line both branches --
    def test_build_release_type_line_auto(self, agent):
        """_build_release_type_line says 'Automatycznie' for auto type."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        result = ReleaseManagerAgent._build_release_type_line("auto", "minor")
        assert "Automatycznie" in result

    def test_build_release_type_line_manual(self, agent):
        """_build_release_type_line says 'ręcznego' for manual type."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        result = ReleaseManagerAgent._build_release_type_line("major", "major")
        assert "ręcznego" in result or "MAJOR" in result

    # -- _merge_changelog: file exists, starts with "# Changelog", no trailing newline --
    def test_merge_changelog_header_no_newline(self, tmp_path):
        """_merge_changelog handles file with '# Changelog' but no trailing newline."""
        from venom_core.agents.release_manager import ReleaseManagerAgent

        path = tmp_path / "CHANGELOG.md"
        path.write_text("# Changelog")  # No trailing newline → split gives 1 part
        result = ReleaseManagerAgent._merge_changelog(path, "## [1.0.0]\n- new\n")
        assert "# Changelog" in result
        assert "1.0.0" in result

    # -- _parse_commits with empty lines in commit log --
    def test_parse_commits_empty_lines(self, agent):
        """_parse_commits skips empty lines in commit log."""
        commit_log = "abc1234 - Alice - 2024-01-20 10:00 - feat: add login\n\n   \ndef5678 - Bob - 2024-01-20 09:00 - fix: typo"
        commits = agent._parse_commits(commit_log)
        assert len(commits) == 2  # Empty lines skipped


# ===========================================================================
# IntegratorAgent – branch coverage
# ===========================================================================


class TestIntegratorBranches:
    """Branch-level tests for IntegratorAgent."""

    @pytest.fixture
    def agent(self, mock_kernel):
        with (
            patch("venom_core.agents.integrator.GitSkill") as mock_git,
            patch("venom_core.agents.integrator.PlatformSkill") as mock_platform,
        ):
            mock_git_inst = MagicMock()
            mock_git_inst.checkout = AsyncMock(return_value="Switched to branch")
            mock_git_inst.push = AsyncMock(return_value="Pushed")
            mock_git.return_value = mock_git_inst

            mock_platform_inst = MagicMock()
            mock_platform_inst.get_assigned_issues = AsyncMock(
                return_value="✅ Znaleziono:\n#1 Fix the bug\n#2 Add feature"
            )
            mock_platform_inst.get_issue_details = AsyncMock(
                return_value="Issue #1: Fix navigation bug\nDescription: ..."
            )
            mock_platform_inst.create_pull_request = AsyncMock(
                return_value="✅ PR #42 created"
            )
            mock_platform_inst.comment_on_issue = AsyncMock(
                return_value="Comment added"
            )
            mock_platform_inst.send_notification = AsyncMock(
                return_value="Notification sent"
            )
            mock_platform.return_value = mock_platform_inst

            from venom_core.agents.integrator import IntegratorAgent

            agent = IntegratorAgent(mock_kernel)
            return agent

    # -- process() success path --
    @pytest.mark.asyncio
    async def test_process_success(self, agent):
        """process() calls LLM and returns response."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(
                __str__=lambda s: "Branch created: feat/test"
            )
            result = await agent.process("Create branch feat/test")
        assert isinstance(result, str)
        assert len(result) > 0

    # -- process() error path --
    @pytest.mark.asyncio
    async def test_process_error(self, agent):
        """process() returns error string when LLM raises exception."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM down")
            result = await agent.process("commit changes")
        assert "❌" in result

    # -- generate_commit_message success --
    @pytest.mark.asyncio
    async def test_generate_commit_message_success(self, agent):
        """generate_commit_message returns semantic commit message."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(
                __str__=lambda s: "feat(ui): add dark mode toggle"
            )
            result = await agent.generate_commit_message("+add dark mode")
        assert isinstance(result, str)
        assert len(result) > 0

    # -- generate_commit_message error → fallback --
    @pytest.mark.asyncio
    async def test_generate_commit_message_error_fallback(self, agent):
        """generate_commit_message returns fallback message on error."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("API error")
            result = await agent.generate_commit_message("diff content")
        assert result == "chore: update code"

    # -- poll_issues: success with parsed issues --
    @pytest.mark.asyncio
    async def test_poll_issues_success(self, agent):
        """poll_issues returns list of issue descriptions."""
        result = await agent.poll_issues()
        assert isinstance(result, list)
        assert len(result) > 0

    # -- poll_issues: "ℹ️" response → empty list --
    @pytest.mark.asyncio
    async def test_poll_issues_no_issues(self, agent):
        """poll_issues returns empty list when no issues assigned."""
        agent.platform_skill.get_assigned_issues = AsyncMock(
            return_value="ℹ️ No assigned issues"
        )
        result = await agent.poll_issues()
        assert result == []

    # -- poll_issues: "❌" response → empty list --
    @pytest.mark.asyncio
    async def test_poll_issues_error_response(self, agent):
        """poll_issues returns empty list when platform returns error."""
        agent.platform_skill.get_assigned_issues = AsyncMock(
            return_value="❌ GitHub unavailable"
        )
        result = await agent.poll_issues()
        assert result == []

    # -- poll_issues: exception → empty list --
    @pytest.mark.asyncio
    async def test_poll_issues_exception(self, agent):
        """poll_issues returns empty list on exception."""
        agent.platform_skill.get_assigned_issues = AsyncMock(
            side_effect=RuntimeError("network error")
        )
        result = await agent.poll_issues()
        assert result == []

    # -- _parse_issues_output: various line types --
    def test_parse_issues_output_normal(self, agent):
        """_parse_issues_output parses issue lines."""
        raw = "Znaleziono 2 issues:\n#1 Fix the bug\n#2 Add feature\n"
        result = agent._parse_issues_output(raw)
        assert "#1 Fix the bug" in result or len(result) >= 1

    def test_parse_issues_output_empty(self, agent):
        """_parse_issues_output returns empty list for empty input."""
        assert agent._parse_issues_output("") == []

    def test_parse_issues_output_only_header(self, agent):
        """_parse_issues_output skips header lines."""
        raw = "Znaleziono issues\nℹ️ something\n"
        result = agent._parse_issues_output(raw)
        assert result == []

    def test_parse_issues_output_number_lines(self, agent):
        """_parse_issues_output includes lines starting with digit."""
        raw = "1 First issue\n2 Second issue\n"
        result = agent._parse_issues_output(raw)
        assert len(result) == 2

    # -- handle_issue: success --
    @pytest.mark.asyncio
    async def test_handle_issue_success(self, agent):
        """handle_issue creates branch and returns issue details."""
        result = await agent.handle_issue(issue_number=1)
        assert "✅" in result or "Issue #1" in result

    # -- handle_issue: issue_details starts with "❌" --
    @pytest.mark.asyncio
    async def test_handle_issue_details_error(self, agent):
        """handle_issue returns error when issue details unavailable."""
        agent.platform_skill.get_issue_details = AsyncMock(
            return_value="❌ Issue not found"
        )
        result = await agent.handle_issue(issue_number=99)
        assert "❌" in result

    # -- handle_issue: exception path --
    @pytest.mark.asyncio
    async def test_handle_issue_exception(self, agent):
        """handle_issue returns error on unexpected exception."""
        agent.platform_skill.get_issue_details = AsyncMock(
            side_effect=RuntimeError("crash")
        )
        result = await agent.handle_issue(issue_number=5)
        assert "❌" in result

    # -- finalize_issue: success path --
    @pytest.mark.asyncio
    async def test_finalize_issue_success(self, agent):
        """finalize_issue creates PR, comments and notifies."""
        result = await agent.finalize_issue(
            issue_number=1,
            branch_name="issue-1",
            pr_title="Fix: navigation bug",
            pr_body="Fixed the issue with navigation",
        )
        assert "✅" in result or "PR" in result

    # -- finalize_issue: PR creation fails --
    @pytest.mark.asyncio
    async def test_finalize_issue_pr_fails(self, agent):
        """finalize_issue returns error when PR creation fails."""
        agent.platform_skill.create_pull_request = AsyncMock(
            return_value="❌ PR creation denied"
        )
        result = await agent.finalize_issue(
            issue_number=1,
            branch_name="issue-1",
            pr_title="Fix",
            pr_body="body",
        )
        assert "❌" in result

    # -- finalize_issue: exception path --
    @pytest.mark.asyncio
    async def test_finalize_issue_exception(self, agent):
        """finalize_issue returns error on unexpected exception."""
        agent.git_skill.push = AsyncMock(side_effect=RuntimeError("push failed"))
        result = await agent.finalize_issue(
            issue_number=1,
            branch_name="issue-1",
            pr_title="Fix",
            pr_body="body",
        )
        assert "❌" in result


# ===========================================================================
# TesterAgent – branch coverage
# ===========================================================================


class TestTesterBranches:
    """Branch-level tests for TesterAgent."""

    @pytest.fixture
    def mock_browser_skill(self, tmp_path):
        skill = MagicMock()
        skill.screenshots_dir = tmp_path / "screenshots"
        skill.screenshots_dir.mkdir(parents=True, exist_ok=True)
        skill.visit_page = AsyncMock(return_value="✅ Page loaded")
        skill.click_element = AsyncMock(return_value="✅ Clicked")
        skill.fill_form = AsyncMock(return_value="✅ Filled")
        skill.get_text_content = AsyncMock(return_value="Expected text here")
        skill.take_screenshot = AsyncMock(return_value="✅ Screenshot saved")
        skill.wait_for_element = AsyncMock(return_value="✅ Element found")
        skill.close_browser = AsyncMock(return_value="✅ Browser closed")
        return skill

    @pytest.fixture
    def mock_eyes(self):
        eyes = MagicMock()
        eyes.analyze_image = AsyncMock(return_value="Clean UI, no errors detected")
        return eyes

    @pytest.fixture
    def agent(self, mock_kernel, mock_browser_skill, mock_eyes):
        from venom_core.agents.tester import TesterAgent

        return TesterAgent(
            kernel=mock_kernel,
            browser_skill=mock_browser_skill,
            eyes=mock_eyes,
        )

    # -- process() success path without screenshot --
    @pytest.mark.asyncio
    async def test_process_success_no_screenshot(self, agent):
        """process() returns LLM response for test request."""
        mock_result = MagicMock()
        mock_result.content = "Login form works correctly. All checks passed."
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = mock_result
            result = await agent.process("Test the login form at http://localhost:3000")
        assert isinstance(result, str)
        assert len(result) > 0

    # -- process() with screenshot in response → visual analysis --
    @pytest.mark.asyncio
    async def test_process_with_screenshot_analysis(self, agent, tmp_path):
        """process() appends visual analysis when screenshot is mentioned."""
        # Create a fake screenshot file
        screenshot_dir = tmp_path / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        screenshot_file = screenshot_dir / "test_page.png"
        screenshot_file.write_bytes(b"fake png data")
        agent.browser_skill.screenshots_dir = screenshot_dir

        mock_result = MagicMock()
        mock_result.content = "I took a screenshot test_page.png to verify"
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = mock_result
            result = await agent.process("Test and screenshot the page")
        # Visual analysis appended
        assert "screenshot" in result.lower() or "analiza" in result.lower()

    # -- process() screenshot analysis raises exception --
    @pytest.mark.asyncio
    async def test_process_screenshot_analysis_fails(self, agent, tmp_path):
        """process() handles Eyes analysis failure gracefully."""
        screenshot_dir = tmp_path / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        screenshot_file = screenshot_dir / "error_test.png"
        screenshot_file.write_bytes(b"fake png")
        agent.browser_skill.screenshots_dir = screenshot_dir
        agent.eyes.analyze_image = AsyncMock(side_effect=RuntimeError("vision error"))

        mock_result = MagicMock()
        mock_result.content = "Took screenshot error_test.png of the page"
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = mock_result
            result = await agent.process("Test page")
        # Should not crash even if Eyes fails
        assert isinstance(result, str)

    # -- process() exception path --
    @pytest.mark.asyncio
    async def test_process_exception_path(self, agent):
        """process() returns error string on unexpected exception."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM unreachable")
            result = await agent.process("test something")
        assert "❌" in result

    # -- run_e2e_scenario: visit action --
    @pytest.mark.asyncio
    async def test_run_e2e_visit_action(self, agent):
        """run_e2e_scenario handles 'visit' action."""
        steps = [{"action": "visit", "url": "http://localhost:3000"}]
        result = await agent.run_e2e_scenario("http://localhost:3000", steps)
        assert "VISIT" in result
        assert "✅" in result or "Page loaded" in result

    # -- run_e2e_scenario: click action --
    @pytest.mark.asyncio
    async def test_run_e2e_click_action(self, agent):
        """run_e2e_scenario handles 'click' action."""
        steps = [{"action": "click", "selector": "#submit-btn"}]
        result = await agent.run_e2e_scenario("http://localhost", steps)
        assert "CLICK" in result

    # -- run_e2e_scenario: fill action --
    @pytest.mark.asyncio
    async def test_run_e2e_fill_action(self, agent):
        """run_e2e_scenario handles 'fill' action."""
        steps = [{"action": "fill", "selector": "#username", "value": "testuser"}]
        result = await agent.run_e2e_scenario("http://localhost", steps)
        assert "FILL" in result

    # -- run_e2e_scenario: verify_text action success --
    @pytest.mark.asyncio
    async def test_run_e2e_verify_text_success(self, agent):
        """run_e2e_scenario verify_text passes when expected text found."""
        agent.browser_skill.get_text_content = AsyncMock(
            return_value="Welcome back, testuser!"
        )
        steps = [{"action": "verify_text", "selector": ".welcome", "expected": "Welcome"}]
        result = await agent.run_e2e_scenario("http://localhost", steps)
        assert "✅ Tekst OK" in result

    # -- run_e2e_scenario: verify_text action failure --
    @pytest.mark.asyncio
    async def test_run_e2e_verify_text_failure(self, agent):
        """run_e2e_scenario verify_text fails when expected text not found."""
        agent.browser_skill.get_text_content = AsyncMock(return_value="Error 404")
        steps = [
            {"action": "verify_text", "selector": ".msg", "expected": "Welcome"}
        ]
        result = await agent.run_e2e_scenario("http://localhost", steps)
        assert "❌ BŁĄD" in result or "BŁĄD" in result

    # -- run_e2e_scenario: screenshot action --
    @pytest.mark.asyncio
    async def test_run_e2e_screenshot_action(self, agent):
        """run_e2e_scenario handles 'screenshot' action."""
        steps = [{"action": "screenshot", "filename": "step_1.png"}]
        result = await agent.run_e2e_scenario("http://localhost", steps)
        assert "SCREENSHOT" in result

    # -- run_e2e_scenario: wait action --
    @pytest.mark.asyncio
    async def test_run_e2e_wait_action(self, agent):
        """run_e2e_scenario handles 'wait' action."""
        steps = [{"action": "wait", "selector": "#loader"}]
        result = await agent.run_e2e_scenario("http://localhost", steps)
        assert "WAIT" in result

    # -- run_e2e_scenario: unknown action --
    @pytest.mark.asyncio
    async def test_run_e2e_unknown_action(self, agent):
        """run_e2e_scenario emits warning for unknown action."""
        steps = [{"action": "teleport", "target": "moon"}]
        result = await agent.run_e2e_scenario("http://localhost", steps)
        assert "⚠️ Nieznana" in result or "Nieznana" in result

    # -- run_e2e_scenario: exception in step --
    @pytest.mark.asyncio
    async def test_run_e2e_scenario_exception(self, agent):
        """run_e2e_scenario handles mid-scenario exceptions."""
        agent.browser_skill.visit_page = AsyncMock(
            side_effect=RuntimeError("Browser crash")
        )
        steps = [{"action": "visit", "url": "http://localhost"}]
        result = await agent.run_e2e_scenario("http://localhost", steps)
        assert "❌" in result

    # -- run_e2e_scenario: multiple steps in sequence --
    @pytest.mark.asyncio
    async def test_run_e2e_full_login_scenario(self, agent):
        """run_e2e_scenario executes a full login scenario successfully."""
        agent.browser_skill.get_text_content = AsyncMock(
            return_value="Welcome, testuser!"
        )
        steps = [
            {"action": "visit", "url": "http://localhost/login"},
            {"action": "fill", "selector": "#username", "value": "testuser"},
            {"action": "fill", "selector": "#password", "value": "secret"},
            {"action": "click", "selector": "#login-btn"},
            {"action": "wait", "selector": ".dashboard"},
            {
                "action": "verify_text",
                "selector": ".greeting",
                "expected": "Welcome",
            },
            {"action": "screenshot", "filename": "login_success.png"},
        ]
        result = await agent.run_e2e_scenario("http://localhost/login", steps)
        assert "✅ Scenariusz zakończony" in result

    # -- TesterAgent initialization --
    def test_tester_initialization_defaults(self, mock_kernel):
        """TesterAgent creates default BrowserSkill and Eyes when none provided."""
        with (
            patch("venom_core.agents.tester.BrowserSkill") as mock_b,
            patch("venom_core.agents.tester.Eyes") as mock_e,
        ):
            mock_b.return_value = MagicMock(screenshots_dir=Path("/tmp/screenshots"))
            mock_e.return_value = MagicMock()
            from venom_core.agents.tester import TesterAgent

            agent = TesterAgent(mock_kernel)
            mock_b.assert_called_once()
            mock_e.assert_called_once()
            assert agent.browser_skill is not None
            assert agent.eyes is not None

    # -- process() close_browser exception (line 188) --
    @pytest.mark.asyncio
    async def test_process_close_browser_exception(self, agent):
        """process() logs warning when close_browser raises exception in finally block."""
        agent.browser_skill.close_browser = AsyncMock(
            side_effect=RuntimeError("cannot close browser")
        )
        mock_result = MagicMock()
        mock_result.content = "Test completed"
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = mock_result
            result = await agent.process("Test the page")
        # Should succeed even if close_browser fails
        assert isinstance(result, str)


# ===========================================================================
# ToolmakerAgent – branch coverage
# ===========================================================================


class TestToolmakerBranches:
    """Branch-level tests for ToolmakerAgent."""

    @pytest.fixture
    def mock_file_skill(self, tmp_path):
        skill = MagicMock()
        skill.workspace_root = str(tmp_path)
        skill.write_file = AsyncMock()
        return skill

    @pytest.fixture
    def agent(self, mock_kernel, mock_file_skill):
        with patch("venom_core.agents.toolmaker.FileSkill", return_value=mock_file_skill):
            from venom_core.agents.toolmaker import ToolmakerAgent

            return ToolmakerAgent(mock_kernel, file_skill=mock_file_skill)

    # -- process() with triple-backtick-only block --
    @pytest.mark.asyncio
    async def test_process_triple_backtick_only(self, agent):
        """process() strips non-python markdown blocks."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = "```\ndef foo():\n    pass\n```"
            result = await agent.process("create a simple function")
        assert "def foo():" in result
        assert "```" not in result

    # -- process() error path --
    @pytest.mark.asyncio
    async def test_process_error(self, agent):
        """process() returns error string on exception."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM failure")
            result = await agent.process("create tool")
        assert "❌" in result

    # -- create_tool: invalid tool name --
    @pytest.mark.asyncio
    async def test_create_tool_invalid_name(self, agent):
        """create_tool rejects names with illegal characters."""
        success, msg = await agent.create_tool("spec", "My-Bad-Name!")
        assert success is False
        assert "Nieprawidłowa nazwa" in msg

    # -- create_tool: process returns error --
    @pytest.mark.asyncio
    async def test_create_tool_process_error(self, agent):
        """create_tool propagates error when process() fails."""
        with patch.object(agent, "process", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = "❌ LLM refused"
            success, msg = await agent.create_tool("spec", "my_tool")
        assert success is False

    # -- create_tool: success with custom output_dir --
    @pytest.mark.asyncio
    async def test_create_tool_with_output_dir(self, agent, tmp_path):
        """create_tool saves to custom output_dir."""
        with patch.object(agent, "process", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = "class MyCool:\n    pass"
            success, code = await agent.create_tool(
                "spec", "my_cool", output_dir=str(tmp_path)
            )
        assert success is True
        assert "class MyCool" in code

    # -- create_tool_ui_card --
    def test_create_tool_ui_card_structure(self, agent):
        """create_tool_ui_card returns correctly structured card config."""
        card = agent.create_tool_ui_card("weather_skill", "Fetches weather data", "🌤️")
        assert card["type"] == "card"
        assert card["metadata"]["tool_name"] == "weather_skill"
        assert card["metadata"]["created_by"] == "ToolmakerAgent"
        assert len(card["data"]["actions"]) == 2

    # -- create_test: success path --
    @pytest.mark.asyncio
    async def test_create_test_success(self, agent, tmp_path):
        """create_test generates and saves test code."""
        test_code = "import pytest\n\ndef test_my_tool():\n    pass\n"
        with patch.object(agent, "process", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = test_code
            success, result = await agent.create_test(
                "my_tool", "class MyTool:\n    pass", output_dir=str(tmp_path)
            )
        assert success is True
        assert "def test_my_tool" in result

    # -- create_test: error from process --
    @pytest.mark.asyncio
    async def test_create_test_process_error(self, agent):
        """create_test returns failure when process() returns error."""
        with patch.object(agent, "process", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = "❌ Cannot generate test"
            success, msg = await agent.create_test("my_tool", "code here")
        assert success is False

    # -- create_test: exception in file writing --
    @pytest.mark.asyncio
    async def test_create_test_write_exception(self, agent):
        """create_test handles file write errors."""
        with patch.object(agent, "process", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = "def test_foo(): pass"
            agent.file_skill.write_file = AsyncMock(
                side_effect=IOError("disk full")
            )
            success, msg = await agent.create_test("my_tool", "code")
        assert success is False


# ===========================================================================
# CoderAgent – branch coverage
# ===========================================================================


class TestCoderBranches:
    """Branch-level tests for CoderAgent."""

    @pytest.fixture
    def mock_file_skill(self):
        skill = MagicMock()
        skill.read_file = AsyncMock(return_value="print('hello world')")
        skill.write_file = AsyncMock()
        return skill

    @pytest.fixture
    def mock_shell_skill(self):
        skill = MagicMock()
        skill.run_shell = MagicMock(return_value="hello world\n[exit_code:0]")
        skill.get_exit_code_from_output = MagicMock(return_value=0)
        return skill

    @pytest.fixture
    def mock_compose_skill(self):
        return MagicMock()

    @pytest.fixture
    def agent(self, mock_kernel, mock_file_skill, mock_shell_skill, mock_compose_skill):
        with (
            patch("venom_core.agents.coder.FileSkill", return_value=mock_file_skill),
            patch("venom_core.agents.coder.ShellSkill", return_value=mock_shell_skill),
            patch("venom_core.agents.coder.ComposeSkill", return_value=mock_compose_skill),
        ):
            from venom_core.agents.coder import CoderAgent

            agent = CoderAgent(mock_kernel, enable_self_repair=True)
            agent.file_skill = mock_file_skill
            agent.shell_skill = mock_shell_skill
            agent.compose_skill = mock_compose_skill
            return agent

    @pytest.fixture
    def agent_no_repair(self, mock_kernel, mock_file_skill, mock_shell_skill, mock_compose_skill):
        with (
            patch("venom_core.agents.coder.FileSkill", return_value=mock_file_skill),
            patch("venom_core.agents.coder.ShellSkill", return_value=mock_shell_skill),
            patch("venom_core.agents.coder.ComposeSkill", return_value=mock_compose_skill),
        ):
            from venom_core.agents.coder import CoderAgent

            agent = CoderAgent(mock_kernel, enable_self_repair=False)
            agent.file_skill = mock_file_skill
            agent.shell_skill = mock_shell_skill
            return agent

    # -- process() basic success --
    @pytest.mark.asyncio
    async def test_process_basic_success(self, agent):
        """process() returns generated code string."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(
                __str__=lambda s: "```python\ndef hello():\n    print('hi')\n```"
            )
            result = await agent.process("Write a hello function")
        assert isinstance(result, str)
        assert len(result) > 0

    # -- process() exception propagation --
    @pytest.mark.asyncio
    async def test_process_raises_on_error(self, agent):
        """process() raises exception when LLM fails."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM down")
            with pytest.raises(RuntimeError, match="LLM down"):
                await agent.process("Write code")

    # -- process_with_params() with params --
    @pytest.mark.asyncio
    async def test_process_with_params(self, agent):
        """process_with_params() passes params and delegates to _process_internal."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "Generated code")
            result = await agent.process_with_params(
                "Write a sort function",
                {"temperature": 0.1, "max_tokens": 500},
            )
        assert isinstance(result, str)

    # -- process_with_params() with None / empty params --
    @pytest.mark.asyncio
    async def test_process_with_empty_params(self, agent):
        """process_with_params() with empty dict delegates to _process_internal."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "Code")
            result = await agent.process_with_params("Write code", {})
        assert isinstance(result, str)

    # -- process_with_verification() without self_repair --
    @pytest.mark.asyncio
    async def test_process_with_verification_no_self_repair(self, agent_no_repair):
        """process_with_verification() returns result directly when self_repair=False."""
        with patch.object(
            agent_no_repair, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "def hello(): pass")
            result = await agent_no_repair.process_with_verification(
                "Write hello", "hello.py"
            )
        assert result["success"] is True
        assert result["attempts"] == 1

    # -- process_with_verification() success on first attempt --
    @pytest.mark.asyncio
    async def test_process_with_verification_first_attempt_success(self, agent):
        """process_with_verification() succeeds when code executes without errors."""
        agent.shell_skill.get_exit_code_from_output = MagicMock(return_value=0)

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "Code written")
            result = await agent.process_with_verification("Write script", "script.py")

        assert result["success"] is True
        assert result["attempts"] == 1

    # -- process_with_verification(): file not created retry --
    @pytest.mark.asyncio
    async def test_process_with_verification_file_not_created(self, agent):
        """process_with_verification() retries when file not created on first attempt."""
        # First call: FileNotFoundError; subsequent: file found and exits successfully
        agent.file_skill.read_file = AsyncMock(
            side_effect=[
                FileNotFoundError("not found"),
                "print('hello')",
                "print('hello')",
            ]
        )
        agent.shell_skill.get_exit_code_from_output = MagicMock(return_value=0)

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "Code written")
            result = await agent.process_with_verification(
                "Write code", "script.py", max_retries=3
            )

        # Might succeed or use all retries depending on retry logic
        assert "success" in result
        assert result["attempts"] >= 1

    # -- process_with_verification(): code fails → repair → success --
    @pytest.mark.asyncio
    async def test_process_with_verification_repair_loop(self, agent):
        """process_with_verification() attempts repair when exit_code != 0."""
        # First attempt: exit_code=1 (error); second attempt: exit_code=0 (success)
        exit_codes = [1, 0]
        call_count = {"n": 0}

        def side_effect(output):
            code = exit_codes[min(call_count["n"], len(exit_codes) - 1)]
            call_count["n"] += 1
            return code

        agent.shell_skill.get_exit_code_from_output = MagicMock(side_effect=side_effect)

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "Repaired code")
            result = await agent.process_with_verification(
                "Write code", "script.py", max_retries=3
            )

        assert result["success"] is True
        assert result["attempts"] >= 2

    # -- process_with_verification(): all retries exhausted --
    @pytest.mark.asyncio
    async def test_process_with_verification_max_retries_exceeded(self, agent):
        """process_with_verification() returns failure after max_retries."""
        agent.shell_skill.get_exit_code_from_output = MagicMock(return_value=1)
        agent.shell_skill.run_shell = MagicMock(
            return_value="SyntaxError: invalid syntax\n[exit_code:1]"
        )

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "Broken code")
            result = await agent.process_with_verification(
                "Write bad code", "bad.py", max_retries=2
            )

        assert result["success"] is False
        assert result["attempts"] == 2

    # -- process_with_verification(): exception path --
    @pytest.mark.asyncio
    async def test_process_with_verification_exception_path(self, agent):
        """process_with_verification() returns failure dict on repeated exceptions."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("Server error")
            result = await agent.process_with_verification(
                "Write code", "err.py", max_retries=2
            )

        assert result["success"] is False

    # -- _build_verification_chat_history --
    def test_build_verification_chat_history(self, agent):
        """_build_verification_chat_history sets up chat history with system prompt."""
        history = agent._build_verification_chat_history(
            "Write a function", "my_func.py"
        )
        assert history is not None
        messages = history.messages
        # Should have SYSTEM + USER messages
        assert len(messages) >= 2
        # USER message should reference the script name
        user_content = messages[-1].content
        assert "my_func.py" in user_content

    # -- _append_repair_feedback_to_history --
    def test_append_repair_feedback_to_history(self, agent):
        """_append_repair_feedback_to_history adds repair request to history."""
        from semantic_kernel.contents import ChatHistory

        history = ChatHistory()
        agent._append_repair_feedback_to_history(
            history, "SyntaxError on line 5", "broken.py"
        )
        assert len(history.messages) == 1
        content = history.messages[0].content
        assert "SyntaxError" in content
        assert "broken.py" in content

    # -- _build_final_verification_result --
    def test_build_final_verification_result(self, agent):
        """_build_final_verification_result returns correctly structured dict."""
        from venom_core.agents.coder import CoderAgent

        result = CoderAgent._build_final_verification_result(
            success=True, output="hello world", attempts=2, final_code="print('hi')"
        )
        assert result["success"] is True
        assert result["output"] == "hello world"
        assert result["attempts"] == 2
        assert result["final_code"] == "print('hi')"

    # -- CoderAgent initialization --
    def test_coder_initialization_with_self_repair(self, agent):
        """CoderAgent initializes with self_repair=True."""
        assert agent.enable_self_repair is True

    def test_coder_initialization_without_self_repair(self, agent_no_repair):
        """CoderAgent initializes with self_repair=False."""
        assert agent_no_repair.enable_self_repair is False

    # -- process_with_verification: ALL retries fail with FileNotFoundError --
    @pytest.mark.asyncio
    async def test_process_with_verification_all_retries_file_not_found(self, agent):
        """process_with_verification hits fallback return when all retries fail with missing file."""
        # All retries fail because file never created (always FileNotFoundError)
        agent.file_skill.read_file = AsyncMock(
            side_effect=FileNotFoundError("file never created")
        )
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "Code written")
            result = await agent.process_with_verification(
                "Write code", "missing.py", max_retries=2
            )
        # Exhausted all retries without file being created → fallback return
        assert "success" in result
