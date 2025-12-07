"""Moduł: agents - zestawienie wszystkich agentów Venom."""

# Lazy imports to avoid dependency issues in tests
__all__ = [
    "BaseAgent",
    "ArchitectAgent",
    "ChatAgent",
    "CoderAgent",
    "CriticAgent",
    "DocumenterAgent",
    "GardenerAgent",
    "GuardianAgent",
    "IntegratorAgent",
    "LibrarianAgent",
    "Professor",
    "PublisherAgent",
    "ReleaseManagerAgent",
    "ResearcherAgent",
    "SystemEngineerAgent",
    "TesterAgent",
    "ToolmakerAgent",
]


def __getattr__(name):
    """Lazy import agentów."""
    if name == "BaseAgent":
        from venom_core.agents.base import BaseAgent

        return BaseAgent
    elif name == "ArchitectAgent":
        from venom_core.agents.architect import ArchitectAgent

        return ArchitectAgent
    elif name == "ChatAgent":
        from venom_core.agents.chat import ChatAgent

        return ChatAgent
    elif name == "CoderAgent":
        from venom_core.agents.coder import CoderAgent

        return CoderAgent
    elif name == "CriticAgent":
        from venom_core.agents.critic import CriticAgent

        return CriticAgent
    elif name == "DocumenterAgent":
        from venom_core.agents.documenter import DocumenterAgent

        return DocumenterAgent
    elif name == "GardenerAgent":
        from venom_core.agents.gardener import GardenerAgent

        return GardenerAgent
    elif name == "GuardianAgent":
        from venom_core.agents.guardian import GuardianAgent

        return GuardianAgent
    elif name == "IntegratorAgent":
        from venom_core.agents.integrator import IntegratorAgent

        return IntegratorAgent
    elif name == "LibrarianAgent":
        from venom_core.agents.librarian import LibrarianAgent

        return LibrarianAgent
    elif name == "Professor":
        from venom_core.agents.professor import Professor

        return Professor
    elif name == "PublisherAgent":
        from venom_core.agents.publisher import PublisherAgent

        return PublisherAgent
    elif name == "ReleaseManagerAgent":
        from venom_core.agents.release_manager import ReleaseManagerAgent

        return ReleaseManagerAgent
    elif name == "ResearcherAgent":
        from venom_core.agents.researcher import ResearcherAgent

        return ResearcherAgent
    elif name == "SystemEngineerAgent":
        from venom_core.agents.system_engineer import SystemEngineerAgent

        return SystemEngineerAgent
    elif name == "TesterAgent":
        from venom_core.agents.tester import TesterAgent

        return TesterAgent
    elif name == "ToolmakerAgent":
        from venom_core.agents.toolmaker import ToolmakerAgent

        return ToolmakerAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
