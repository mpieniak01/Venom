"""Moduł: skills - zestawienie wszystkich umiejętności Venom."""

from importlib import import_module

# Import only when needed to avoid circular dependencies
__all__ = [
    "AssistantSkill",
    "BrowserSkill",
    "CoreSkill",
    "DocsSkill",
    "FileSkill",
    "GitSkill",
    "InputSkill",
    "MediaSkill",
    "PlatformSkill",
    "ShellSkill",
    "TestSkill",
    "WebSearchSkill",
]


_SKILL_IMPORTS = {
    "AssistantSkill": "venom_core.execution.skills.assistant_skill.AssistantSkill",
    "BrowserSkill": "venom_core.execution.skills.browser_skill.BrowserSkill",
    "CoreSkill": "venom_core.execution.skills.core_skill.CoreSkill",
    "DocsSkill": "venom_core.execution.skills.docs_skill.DocsSkill",
    "FileSkill": "venom_core.execution.skills.file_skill.FileSkill",
    "GitSkill": "venom_core.execution.skills.git_skill.GitSkill",
    "InputSkill": "venom_core.execution.skills.input_skill.InputSkill",
    "MediaSkill": "venom_core.execution.skills.media_skill.MediaSkill",
    "PlatformSkill": "venom_core.execution.skills.platform_skill.PlatformSkill",
    "ShellSkill": "venom_core.execution.skills.shell_skill.ShellSkill",
    "TestSkill": "venom_core.execution.skills.test_skill.TestSkill",
    "WebSearchSkill": "venom_core.execution.skills.web_skill.WebSearchSkill",
}


def _resolve_skill(name):
    target = _SKILL_IMPORTS.get(name)
    if not target:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, class_name = target.rsplit(".", 1)
    module = import_module(module_name)
    return getattr(module, class_name)


def __getattr__(name):
    """Lazy import for skills to avoid import errors."""
    return _resolve_skill(name)
