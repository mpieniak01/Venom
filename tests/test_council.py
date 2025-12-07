"""Testy dla The Council (AutoGen Integration)."""

import pytest

from venom_core.agents.architect import ArchitectAgent
from venom_core.agents.coder import CoderAgent
from venom_core.agents.critic import CriticAgent
from venom_core.agents.guardian import GuardianAgent
from venom_core.core.council import (
    CouncilConfig,
    CouncilSession,
    create_local_llm_config,
)
from venom_core.core.swarm import create_venom_agent_wrapper
from venom_core.execution.kernel_builder import KernelBuilder


@pytest.fixture
def kernel():
    """Fixture dla Semantic Kernel."""
    builder = KernelBuilder()
    return builder.build_kernel()


@pytest.fixture
def coder_agent(kernel):
    """Fixture dla CoderAgent."""
    return CoderAgent(kernel)


@pytest.fixture
def critic_agent(kernel):
    """Fixture dla CriticAgent."""
    return CriticAgent(kernel)


@pytest.fixture
def architect_agent(kernel):
    """Fixture dla ArchitectAgent."""
    return ArchitectAgent(kernel)


@pytest.fixture
def guardian_agent(kernel):
    """Fixture dla GuardianAgent."""
    return GuardianAgent(kernel)


@pytest.fixture
def llm_config():
    """Fixture dla konfiguracji LLM."""
    return create_local_llm_config(
        base_url="http://localhost:11434/v1",
        model="llama3",
        temperature=0.7,
    )


def test_create_local_llm_config():
    """Test tworzenia konfiguracji lokalnego LLM."""
    config = create_local_llm_config()

    assert "config_list" in config
    assert len(config["config_list"]) > 0
    assert config["config_list"][0]["model"] == "llama3"
    assert config["config_list"][0]["api_key"] == "EMPTY"
    assert config["temperature"] == 0.7


def test_venom_agent_wrapper_creation(coder_agent, llm_config):
    """Test tworzenia wrappera VenomAgent."""
    wrapper = create_venom_agent_wrapper(
        agent=coder_agent,
        name="Coder",
        system_message=coder_agent.SYSTEM_PROMPT,
        llm_config=llm_config,
    )

    assert wrapper.name == "Coder"
    assert wrapper.venom_agent == coder_agent
    assert wrapper.system_message == coder_agent.SYSTEM_PROMPT


def test_venom_agent_wrapper_auto_system_message(coder_agent, llm_config):
    """Test automatycznego pobierania system message z agenta."""
    wrapper = create_venom_agent_wrapper(
        agent=coder_agent,
        name="Coder",
        llm_config=llm_config,
    )

    # System message powinien być automatycznie pobrany z SYSTEM_PROMPT
    assert wrapper.system_message == coder_agent.SYSTEM_PROMPT


def test_council_config_initialization(
    coder_agent, critic_agent, architect_agent, guardian_agent, llm_config
):
    """Test inicjalizacji CouncilConfig."""
    council_config = CouncilConfig(
        coder_agent=coder_agent,
        critic_agent=critic_agent,
        architect_agent=architect_agent,
        guardian_agent=guardian_agent,
        llm_config=llm_config,
    )

    assert council_config.coder_agent == coder_agent
    assert council_config.critic_agent == critic_agent
    assert council_config.architect_agent == architect_agent
    assert council_config.guardian_agent == guardian_agent
    assert council_config.llm_config == llm_config


def test_council_creation(
    coder_agent, critic_agent, architect_agent, guardian_agent, llm_config
):
    """Test tworzenia The Council (Group Chat)."""
    council_config = CouncilConfig(
        coder_agent=coder_agent,
        critic_agent=critic_agent,
        architect_agent=architect_agent,
        guardian_agent=guardian_agent,
        llm_config=llm_config,
    )

    user_proxy, group_chat, manager = council_config.create_council()

    # Sprawdź że utworzono wszystkie komponenty
    assert user_proxy is not None
    assert group_chat is not None
    assert manager is not None

    # Sprawdź liczbę agentów (User + 4 agenty Venom)
    assert len(group_chat.agents) == 5

    # Sprawdź nazwy agentów
    agent_names = [agent.name for agent in group_chat.agents]
    assert "User" in agent_names
    assert "Architect" in agent_names
    assert "Coder" in agent_names
    assert "Critic" in agent_names
    assert "Guardian" in agent_names


def test_council_session_initialization(
    coder_agent, critic_agent, architect_agent, guardian_agent, llm_config
):
    """Test inicjalizacji CouncilSession."""
    council_config = CouncilConfig(
        coder_agent=coder_agent,
        critic_agent=critic_agent,
        architect_agent=architect_agent,
        guardian_agent=guardian_agent,
        llm_config=llm_config,
    )

    user_proxy, group_chat, manager = council_config.create_council()
    session = CouncilSession(user_proxy, group_chat, manager)

    assert session.user_proxy == user_proxy
    assert session.group_chat == group_chat
    assert session.manager == manager
    assert session.get_message_count() == 0
    assert session.get_speakers() == []


# Testy integracyjne z prawdziwym LLM są pomijane w standardowych testach
# (wymagają uruchomionego Ollama z modelem llama3)


@pytest.mark.skip(reason="Wymaga uruchomionego lokalnego LLM (Ollama)")
@pytest.mark.asyncio
async def test_council_session_run_integration(
    coder_agent, critic_agent, architect_agent, guardian_agent, llm_config
):
    """Test integracyjny uruchamiania sesji Council (wymaga lokalnego LLM)."""
    council_config = CouncilConfig(
        coder_agent=coder_agent,
        critic_agent=critic_agent,
        architect_agent=architect_agent,
        guardian_agent=guardian_agent,
        llm_config=llm_config,
    )

    user_proxy, group_chat, manager = council_config.create_council()
    session = CouncilSession(user_proxy, group_chat, manager)

    # Proste zadanie testowe
    task = "Napisz funkcję hello_world() w Pythonie, która zwraca 'Hello World'"

    result = await session.run(task)

    # Sprawdź że dyskusja się odbyła
    assert session.get_message_count() > 0
    assert len(session.get_speakers()) > 0
    assert result is not None
    assert len(result) > 0
