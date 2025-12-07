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
    with patch("venom_core.agents.integrator.GitSkill"):
        agent = IntegratorAgent(mock_kernel)
        return agent


@pytest.mark.asyncio
async def test_integrator_agent_initialization(mock_kernel):
    """Test inicjalizacji IntegratorAgent."""
    with patch("venom_core.agents.integrator.GitSkill") as mock_git_skill:
        IntegratorAgent(mock_kernel)

        # Sprawdź czy GitSkill został utworzony
        mock_git_skill.assert_called_once()

        # Sprawdź czy plugin został dodany do kernela
        mock_kernel.add_plugin.assert_called_once()


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
