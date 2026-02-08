"""Moduł: agents - zestawienie wszystkich agentów Venom."""

import importlib

# Lazy imports to avoid dependency issues in tests
__all__ = [
    "BaseAgent",
    "ApprenticeAgent",
    "ArchitectAgent",
    "ChatAgent",
    "CoderAgent",
    "CreativeDirectorAgent",
    "CriticAgent",
    "DevOpsAgent",
    "DocumenterAgent",
    "GardenerAgent",
    "GuardianAgent",
    "IntegratorAgent",
    "LibrarianAgent",
    "Professor",
    "PublisherAgent",
    "ReleaseManagerAgent",
    "ResearcherAgent",
    "SystemStatusAgent",
    "StrategistAgent",
    "SystemEngineerAgent",
    "TesterAgent",
    "ToolmakerAgent",
]

AGENT_IMPORTS = {
    "BaseAgent": ("venom_core.agents.base", "BaseAgent"),
    "ApprenticeAgent": ("venom_core.agents.apprentice", "ApprenticeAgent"),
    "ArchitectAgent": ("venom_core.agents.architect", "ArchitectAgent"),
    "ChatAgent": ("venom_core.agents.chat", "ChatAgent"),
    "CoderAgent": ("venom_core.agents.coder", "CoderAgent"),
    "CreativeDirectorAgent": (
        "venom_core.agents.creative_director",
        "CreativeDirectorAgent",
    ),
    "CriticAgent": ("venom_core.agents.critic", "CriticAgent"),
    "DevOpsAgent": ("venom_core.agents.devops", "DevOpsAgent"),
    "DocumenterAgent": ("venom_core.agents.documenter", "DocumenterAgent"),
    "GardenerAgent": ("venom_core.agents.gardener", "GardenerAgent"),
    "GuardianAgent": ("venom_core.agents.guardian", "GuardianAgent"),
    "IntegratorAgent": ("venom_core.agents.integrator", "IntegratorAgent"),
    "LibrarianAgent": ("venom_core.agents.librarian", "LibrarianAgent"),
    "Professor": ("venom_core.agents.professor", "Professor"),
    "PublisherAgent": ("venom_core.agents.publisher", "PublisherAgent"),
    "ReleaseManagerAgent": (
        "venom_core.agents.release_manager",
        "ReleaseManagerAgent",
    ),
    "ResearcherAgent": ("venom_core.agents.researcher", "ResearcherAgent"),
    "SystemStatusAgent": ("venom_core.agents.system_status", "SystemStatusAgent"),
    "StrategistAgent": ("venom_core.agents.strategist", "StrategistAgent"),
    "SystemEngineerAgent": (
        "venom_core.agents.system_engineer",
        "SystemEngineerAgent",
    ),
    "TesterAgent": ("venom_core.agents.tester", "TesterAgent"),
    "ToolmakerAgent": ("venom_core.agents.toolmaker", "ToolmakerAgent"),
}


def __getattr__(name):
    """Lazy import agentów."""
    module_info = AGENT_IMPORTS.get(name)
    if module_info:
        module_name, symbol_name = module_info
        module = importlib.import_module(module_name)
        return getattr(module, symbol_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
