"""Testy jednostkowe dla CreativeDirectorAgent i DevOpsAgent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from semantic_kernel import Kernel

from venom_core.agents.creative_director import CreativeDirectorAgent
from venom_core.agents.devops import DevOpsAgent


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowanego Kernel."""
    kernel = MagicMock(spec=Kernel)
    mock_service = MagicMock()
    kernel.get_service.return_value = mock_service
    return kernel


@pytest.fixture
def creative_director(mock_kernel):
    """Fixture dla CreativeDirectorAgent."""
    return CreativeDirectorAgent(kernel=mock_kernel)


@pytest.fixture
def devops_agent(mock_kernel):
    """Fixture dla DevOpsAgent."""
    return DevOpsAgent(kernel=mock_kernel)


def test_creative_director_initialization(creative_director):
    """Test inicjalizacji Creative Director."""
    assert creative_director.kernel is not None
    assert len(creative_director.chat_history.messages) > 0
    # System prompt powinien być pierwszy
    assert "Creative Director" in creative_director.SYSTEM_PROMPT


def test_devops_agent_initialization(devops_agent):
    """Test inicjalizacji DevOps Agent."""
    assert devops_agent.kernel is not None
    assert len(devops_agent.chat_history.messages) > 0
    # System prompt powinien być pierwszy
    assert "DevOps" in devops_agent.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_creative_director_process(creative_director):
    """Test przetwarzania zadania przez Creative Director."""
    # Mock response z LLM
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: (
        "Logo prompt: 'Minimalist logo for app'\n"
        "Tagline: 'Simple and Clean'\n"
        "Tweet: 'Launching our app! 🚀'"
    )

    mock_service = creative_director.kernel.get_service()
    mock_service.get_chat_message_contents = AsyncMock(return_value=[mock_response])

    result = await creative_director.process("Stwórz branding dla aplikacji pogodowej")

    assert "Logo prompt" in result or "Minimalist" in result
    # Sprawdź czy historia została zaktualizowana
    assert len(creative_director.chat_history.messages) > 1


@pytest.mark.asyncio
async def test_creative_director_error_handling(creative_director):
    """Test obsługi błędów w Creative Director."""
    mock_service = creative_director.kernel.get_service()
    mock_service.get_chat_message_contents = AsyncMock(
        side_effect=Exception("LLM Error")
    )

    result = await creative_director.process("Test task")

    assert "Błąd" in result
    assert "LLM Error" in result


@pytest.mark.asyncio
async def test_devops_process(devops_agent):
    """Test przetwarzania zadania przez DevOps Agent."""
    # Mock response z LLM
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: (
        "1. Sprawdź połączenie SSH\n"
        "2. Zainstaluj Docker\n"
        "3. Deploy aplikacji\n"
        "4. Sprawdź health checks"
    )

    mock_service = devops_agent.kernel.get_service()
    mock_service.get_chat_message_contents = AsyncMock(return_value=[mock_response])

    result = await devops_agent.process("Deploy aplikację na serwer 1.2.3.4")

    assert "Docker" in result or "Deploy" in result
    # Sprawdź czy historia została zaktualizowana
    assert len(devops_agent.chat_history.messages) > 1


@pytest.mark.asyncio
async def test_devops_error_handling(devops_agent):
    """Test obsługi błędów w DevOps Agent."""
    mock_service = devops_agent.kernel.get_service()
    mock_service.get_chat_message_contents = AsyncMock(
        side_effect=Exception("Connection timeout")
    )

    result = await devops_agent.process("Test deployment")

    assert "Błąd" in result
    assert "Connection timeout" in result


def test_creative_director_reset_conversation(creative_director):
    """Test resetowania historii konwersacji Creative Director."""
    # Dodaj kilka wiadomości
    creative_director.chat_history.add_user_message("Test 1")
    creative_director.chat_history.add_assistant_message("Response 1")

    # Reset
    creative_director.reset_conversation()

    # Powinna zostać tylko wiadomość systemowa
    assert len(creative_director.chat_history.messages) == 1
    assert creative_director.chat_history.messages[0].role.value == "system"


def test_devops_reset_conversation(devops_agent):
    """Test resetowania historii konwersacji DevOps Agent."""
    # Dodaj kilka wiadomości
    devops_agent.chat_history.add_user_message("Test 1")
    devops_agent.chat_history.add_assistant_message("Response 1")

    # Reset
    devops_agent.reset_conversation()

    # Powinna zostać tylko wiadomość systemowa
    assert len(devops_agent.chat_history.messages) == 1
    assert devops_agent.chat_history.messages[0].role.value == "system"


def test_creative_director_system_prompt_content(creative_director):
    """Test zawartości system promptu Creative Director."""
    prompt = creative_director.SYSTEM_PROMPT
    
    # Sprawdź czy zawiera kluczowe elementy
    assert "branding" in prompt.lower()
    assert "marketing" in prompt.lower()
    assert "logo" in prompt.lower()
    assert "copywriting" in prompt.lower() or "copy" in prompt.lower()


def test_devops_system_prompt_content(devops_agent):
    """Test zawartości system promptu DevOps Agent."""
    prompt = devops_agent.SYSTEM_PROMPT
    
    # Sprawdź czy zawiera kluczowe elementy
    assert "devops" in prompt.lower() or "infrastructure" in prompt.lower()
    assert "docker" in prompt.lower()
    assert "deployment" in prompt.lower() or "deploy" in prompt.lower()
    assert "ssh" in prompt.lower() or "security" in prompt.lower()


@pytest.mark.asyncio
async def test_creative_director_with_media_context(creative_director):
    """Test Creative Director z kontekstem generowania mediów."""
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: (
        "Używając generate_image wygeneruję:\n"
        "Prompt: 'Modern logo for SaaS platform'\n"
        "Style: minimalist"
    )

    mock_service = creative_director.kernel.get_service()
    mock_service.get_chat_message_contents = AsyncMock(return_value=[mock_response])

    result = await creative_director.process(
        "Stwórz logo dla platformy SaaS i użyj generate_image"
    )

    assert "generate_image" in result or "logo" in result.lower()


@pytest.mark.asyncio
async def test_devops_with_deployment_context(devops_agent):
    """Test DevOps Agent z kontekstem deploymentu."""
    mock_response = MagicMock()
    mock_response.__str__ = lambda self: (
        "Plan deploymentu:\n"
        "1. provision_server - instalacja Docker\n"
        "2. deploy_stack - uruchomienie aplikacji\n"
        "3. check_deployment_health - weryfikacja"
    )

    mock_service = devops_agent.kernel.get_service()
    mock_service.get_chat_message_contents = AsyncMock(return_value=[mock_response])

    result = await devops_agent.process(
        "Przygotuj plan deploymentu aplikacji na nowy serwer"
    )

    assert (
        "provision_server" in result
        or "deploy_stack" in result
        or "deployment" in result.lower()
    )
