"""Testy integracyjne dla IntegratorAgent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.agents.integrator import IntegratorAgent


@pytest.fixture
def mock_kernel():
    """Mock Semantic Kernel."""
    kernel = MagicMock()
    kernel.add_plugin = MagicMock()

    # Mock chat service
    chat_service = MagicMock()
    chat_service.get_chat_message_content = AsyncMock(
        return_value="Wykonano operację Git"
    )
    kernel.get_service = MagicMock(return_value=chat_service)

    return kernel


@pytest.fixture
def integrator_agent(mock_kernel):
    """Tworzy instancję IntegratorAgent z mock kernel."""
    with patch("venom_core.agents.integrator.GitSkill"), patch(
        "venom_core.agents.integrator.PlatformSkill"
    ):
        agent = IntegratorAgent(mock_kernel)
        return agent


@pytest.mark.asyncio
async def test_integrator_agent_initialization(mock_kernel):
    """Test inicjalizacji IntegratorAgent."""
    with patch("venom_core.agents.integrator.GitSkill") as mock_git_skill, patch(
        "venom_core.agents.integrator.PlatformSkill"
    ) as mock_platform_skill:
        IntegratorAgent(mock_kernel)

        # Sprawdź czy GitSkill i PlatformSkill zostały utworzone
        mock_git_skill.assert_called_once()
        mock_platform_skill.assert_called_once()

        # Sprawdź czy pluginy zostały dodane do kernela
        assert mock_kernel.add_plugin.call_count == 2


@pytest.mark.asyncio
async def test_integrator_agent_process(integrator_agent):
    """Test przetwarzania żądania przez IntegratorAgent."""
    result = await integrator_agent.process("Utwórz nowy branch feat/test")

    # Sprawdź czy wynik jest stringiem
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_generate_commit_message(integrator_agent):
    """Test generowania wiadomości commita."""
    diff = """
diff --git a/test.py b/test.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/test.py
@@ -0,0 +1,5 @@
+def hello():
+    print("Hello, World!")
"""

    result = await integrator_agent.generate_commit_message(diff)

    # Sprawdź czy wynik jest stringiem (wiadomość commita)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_integrator_agent_error_handling(integrator_agent):
    """Test obsługi błędów w IntegratorAgent."""
    # Symuluj błąd w chat service
    integrator_agent.kernel.get_service.side_effect = Exception("Test error")

    result = await integrator_agent.process("Test command")

    # Sprawdź czy błąd został obsłużony
    assert "❌" in result or "Błąd" in result.lower()


@pytest.mark.asyncio
async def test_poll_issues_success(integrator_agent):
    """Test pomyślnego pollowania Issues."""
    # Mock PlatformSkill
    integrator_agent.platform_skill.get_assigned_issues = AsyncMock(
        return_value="Znaleziono 1 Issues:\n\n#42: Test Issue"
    )

    result = await integrator_agent.poll_issues()

    # Sprawdź czy wynik zawiera znalezione Issues
    assert len(result) == 1
    assert "Test Issue" in result[0]


@pytest.mark.asyncio
async def test_poll_issues_empty(integrator_agent):
    """Test pollowania Issues gdy brak nowych."""
    # Mock PlatformSkill
    integrator_agent.platform_skill.get_assigned_issues = AsyncMock(
        return_value="ℹ️ Brak Issues w stanie 'open'"
    )

    result = await integrator_agent.poll_issues()

    # Sprawdź czy wynik jest pustą listą
    assert result == []


@pytest.mark.asyncio
async def test_handle_issue_success(integrator_agent):
    """Test obsługi Issue."""
    # Mock GitSkill i PlatformSkill
    integrator_agent.platform_skill.get_issue_details = AsyncMock(
        return_value="Issue #42: Test Issue\nOpis: Test description"
    )
    integrator_agent.git_skill.checkout = AsyncMock(
        return_value="✅ Utworzono branch issue-42"
    )

    result = await integrator_agent.handle_issue(42)

    # Sprawdź czy Issue zostało obsłużone
    assert "✅" in result
    assert "issue-42" in result
    assert "gotowe do przetworzenia" in result


@pytest.mark.asyncio
async def test_finalize_issue_success(integrator_agent):
    """Test finalizacji Issue (PR + komentarz + powiadomienie)."""
    # Mock wszystkich operacji
    integrator_agent.git_skill.push = AsyncMock(return_value="✅ Pushed to remote")
    integrator_agent.platform_skill.create_pull_request = AsyncMock(
        return_value="✅ Utworzono Pull Request #10"
    )
    integrator_agent.platform_skill.comment_on_issue = AsyncMock(
        return_value="✅ Dodano komentarz"
    )
    integrator_agent.platform_skill.send_notification = AsyncMock(
        return_value="✅ Wysłano powiadomienie"
    )

    result = await integrator_agent.finalize_issue(
        issue_number=42,
        branch_name="issue-42",
        pr_title="fix: resolve issue #42",
        pr_body="Automatic fix for issue #42",
    )

    # Sprawdź czy Issue zostało sfinalizowane
    assert "✅" in result
    assert "sfinalizowane" in result
