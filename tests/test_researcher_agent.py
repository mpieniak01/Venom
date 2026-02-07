"""Testy jednostkowe dla ResearcherAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.researcher import ResearcherAgent
from venom_core.config import SETTINGS
from venom_core.utils.llm_runtime import get_active_llm_runtime


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)

    # Mock add_plugin aby nie rzucał błędów
    kernel.add_plugin = MagicMock()

    return kernel


@pytest.fixture
def mock_chat_service():
    """Fixture dla mockowego serwisu chat."""
    service = MagicMock()
    service.get_chat_message_content = AsyncMock()
    return service


@pytest.fixture
def researcher_agent(mock_kernel, mock_chat_service):
    """Fixture dla ResearcherAgent."""
    mock_kernel.get_service.return_value = mock_chat_service
    agent = ResearcherAgent(mock_kernel)
    return agent


class TestResearcherAgent:
    """Testy dla ResearcherAgent."""

    def test_initialization(self, mock_kernel):
        """Test inicjalizacji ResearcherAgent."""
        agent = ResearcherAgent(mock_kernel)

        assert agent.kernel == mock_kernel
        # Sprawdź czy dodano pluginy (WebSearchSkill i MemorySkill)
        assert mock_kernel.add_plugin.call_count == 2

    @pytest.mark.asyncio
    async def test_process_success(self, researcher_agent, mock_chat_service):
        """Test udanego przetwarzania zapytania badawczego."""
        # Mock odpowiedzi LLM
        mock_response = MagicMock()
        mock_response.__str__ = lambda x: (
            "Znalazłem informacje o PyGame:\n\nKluczowe punkty:\n• pygame.rect.colliderect() do kolizji"
        )
        mock_chat_service.get_chat_message_content.return_value = mock_response

        result = await researcher_agent.process("Jak obsłużyć kolizje w PyGame?")

        assert "PyGame" in result
        assert "colliderect" in result
        assert mock_chat_service.get_chat_message_content.called

    @pytest.mark.asyncio
    async def test_process_with_error(self, researcher_agent, mock_chat_service):
        """Test obsługi błędu podczas przetwarzania."""
        mock_chat_service.get_chat_message_content.side_effect = Exception("LLM error")

        result = await researcher_agent.process("Test query")

        assert "Wystąpił błąd" in result
        assert "LLM error" in result

    @pytest.mark.asyncio
    async def test_process_uses_correct_prompt(
        self, researcher_agent, mock_chat_service
    ):
        """Test czy używany jest poprawny prompt systemowy."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda x: "Test response"
        mock_chat_service.get_chat_message_content.return_value = mock_response

        await researcher_agent.process("Test query")

        # Sprawdź czy wywołano z historią zawierającą system prompt
        call_args = mock_chat_service.get_chat_message_content.call_args
        chat_history = call_args.kwargs.get("chat_history") or call_args.args[0]

        # Sprawdź czy history zawiera system prompt i user message
        assert len(chat_history.messages) >= 2
        assert "Researcher" in str(chat_history.messages[0].content)

    @pytest.mark.asyncio
    async def test_process_has_token_limit(self, researcher_agent, mock_chat_service):
        """Test czy ustawiony jest limit tokenów."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda x: "Test response"
        mock_chat_service.get_chat_message_content.return_value = mock_response

        await researcher_agent.process("Test query")

        # Sprawdź czy settings zawiera max_tokens
        call_args = mock_chat_service.get_chat_message_content.call_args
        settings = call_args.kwargs.get("settings")

        assert settings is not None
        runtime = get_active_llm_runtime()
        max_tokens = getattr(settings, "max_tokens", None)
        num_predict = getattr(settings, "num_predict", None)
        extension_data = getattr(settings, "extension_data", {}) or {}
        if num_predict is None:
            num_predict = extension_data.get("num_predict")
        if max_tokens is None:
            max_tokens = extension_data.get("max_tokens")

        assert max_tokens is not None or num_predict is not None
        if runtime.provider == "vllm" and SETTINGS.VLLM_MAX_MODEL_LEN:
            safe_cap = max(64, SETTINGS.VLLM_MAX_MODEL_LEN // 4)
            assert max_tokens is not None
            assert max_tokens <= safe_cap
        elif runtime.provider == "ollama":
            assert num_predict == 800
        else:
            assert max_tokens == 800
