"""Testy jednostkowe dla IntentManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from semantic_kernel import Kernel

from venom_core.core.intent_manager import IntentManager


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    return kernel


@pytest.fixture
def mock_chat_service():
    """Fixture dla mockowego serwisu chat."""
    service = MagicMock()
    service.get_chat_message_content = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_intent_manager_initialization():
    """Test inicjalizacji IntentManager z własnym kernelem."""
    mock_kernel = MagicMock(spec=Kernel)
    manager = IntentManager(kernel=mock_kernel)
    assert manager.kernel == mock_kernel


@pytest.mark.asyncio
async def test_intent_manager_classify_code_generation(mock_kernel, mock_chat_service):
    """Test klasyfikacji intencji CODE_GENERATION."""
    # Mockuj odpowiedź od LLM
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="CODE_GENERATION")
    mock_chat_service.get_chat_message_content.return_value = mock_response

    mock_kernel.get_service.return_value = mock_chat_service

    manager = IntentManager(kernel=mock_kernel)
    intent = await manager.classify_intent("Napisz funkcję w Pythonie do sortowania")

    assert intent == "CODE_GENERATION"
    assert not mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_intent_manager_classify_knowledge_search(mock_kernel, mock_chat_service):
    """Test klasyfikacji intencji KNOWLEDGE_SEARCH."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="KNOWLEDGE_SEARCH")
    mock_chat_service.get_chat_message_content.return_value = mock_response

    mock_kernel.get_service.return_value = mock_chat_service

    manager = IntentManager(kernel=mock_kernel)
    intent = await manager.classify_intent("Co to jest GraphRAG?")

    assert intent == "KNOWLEDGE_SEARCH"


@pytest.mark.asyncio
async def test_intent_manager_classify_general_chat(mock_kernel, mock_chat_service):
    """Test klasyfikacji intencji GENERAL_CHAT."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="GENERAL_CHAT")
    mock_chat_service.get_chat_message_content.return_value = mock_response

    mock_kernel.get_service.return_value = mock_chat_service

    manager = IntentManager(kernel=mock_kernel)
    intent = await manager.classify_intent("Witaj Venom, jak się masz?")

    assert intent == "GENERAL_CHAT"


@pytest.mark.asyncio
async def test_intent_manager_handles_lowercase_response(
    mock_kernel, mock_chat_service
):
    """Test że manager normalizuje lowercase odpowiedzi."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="code_generation")
    mock_chat_service.get_chat_message_content.return_value = mock_response

    mock_kernel.get_service.return_value = mock_chat_service

    manager = IntentManager(kernel=mock_kernel)
    intent = await manager.classify_intent("Napisz skrypt w Bash")

    assert intent == "CODE_GENERATION"


@pytest.mark.asyncio
async def test_intent_manager_handles_extra_text_in_response(
    mock_kernel, mock_chat_service
):
    """Test że manager radzi sobie z dodatkowymi tekstami w odpowiedzi."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value="Based on the input, the intent is CODE_GENERATION"
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response

    mock_kernel.get_service.return_value = mock_chat_service

    manager = IntentManager(kernel=mock_kernel)
    intent = await manager.classify_intent("Zrefaktoruj ten kod")

    assert intent == "CODE_GENERATION"


@pytest.mark.asyncio
async def test_intent_manager_fallback_on_invalid_response(
    mock_kernel, mock_chat_service
):
    """Test że manager używa GENERAL_CHAT jako fallback dla niepoprawnej odpowiedzi."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="UNKNOWN_INTENT")
    mock_chat_service.get_chat_message_content.return_value = mock_response

    mock_kernel.get_service.return_value = mock_chat_service

    manager = IntentManager(kernel=mock_kernel)
    intent = await manager.classify_intent("Jakieś dziwne wejście")

    assert intent == "UNSUPPORTED_TASK"


@pytest.mark.asyncio
async def test_intent_manager_handles_exception(mock_kernel, mock_chat_service):
    """Test że manager obsługuje wyjątki i zwraca GENERAL_CHAT jako fallback."""
    mock_chat_service.get_chat_message_content.side_effect = Exception(
        "Connection error"
    )
    mock_kernel.get_service.return_value = mock_chat_service

    manager = IntentManager(kernel=mock_kernel)
    intent = await manager.classify_intent("Jakieś wejście")

    # Powinien zwrócić UNSUPPORTED_TASK jako bezpieczny fallback
    assert intent == "UNSUPPORTED_TASK"


@pytest.mark.asyncio
async def test_intent_manager_strips_whitespace(mock_kernel, mock_chat_service):
    """Test że manager usuwa whitespace z odpowiedzi."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="  KNOWLEDGE_SEARCH  \n")
    mock_chat_service.get_chat_message_content.return_value = mock_response

    mock_kernel.get_service.return_value = mock_chat_service

    manager = IntentManager(kernel=mock_kernel)
    intent = await manager.classify_intent("Wyjaśnij mi coś")

    assert intent == "KNOWLEDGE_SEARCH"


@pytest.mark.asyncio
@patch("venom_core.core.intent_manager.KernelBuilder")
async def test_intent_manager_creates_kernel_if_none_provided(mock_builder_class):
    """Test że IntentManager tworzy kernel jeśli nie został przekazany."""
    mock_kernel = MagicMock(spec=Kernel)
    mock_builder_instance = MagicMock()
    mock_builder_instance.build_kernel.return_value = mock_kernel
    mock_builder_class.return_value = mock_builder_instance

    manager = IntentManager(kernel=None)

    # Sprawdź czy KernelBuilder został użyty
    assert mock_builder_class.called
    assert manager.kernel == mock_kernel


@pytest.mark.asyncio
async def test_intent_manager_classify_help_request(mock_kernel, mock_chat_service):
    """Test klasyfikacji intencji HELP_REQUEST."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="HELP_REQUEST")
    mock_chat_service.get_chat_message_content.return_value = mock_response

    mock_kernel.get_service.return_value = mock_chat_service

    manager = IntentManager(kernel=mock_kernel)
    intent = await manager.classify_intent("Co potrafisz?")

    assert intent == "HELP_REQUEST"
    assert not mock_chat_service.get_chat_message_content.called
