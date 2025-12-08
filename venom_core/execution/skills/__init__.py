"""Moduł: skills - zestawienie wszystkich umiejętności Venom."""

# Import only when needed to avoid circular dependencies
__all__ = [
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


def __getattr__(name):
    """Lazy import for skills to avoid import errors."""
    if name == "BrowserSkill":
        from venom_core.execution.skills.browser_skill import BrowserSkill

        return BrowserSkill
    elif name == "CoreSkill":
        from venom_core.execution.skills.core_skill import CoreSkill

        return CoreSkill
    elif name == "DocsSkill":
        from venom_core.execution.skills.docs_skill import DocsSkill

        return DocsSkill
    elif name == "FileSkill":
        from venom_core.execution.skills.file_skill import FileSkill

        return FileSkill
    elif name == "GitSkill":
        from venom_core.execution.skills.git_skill import GitSkill

        return GitSkill
    elif name == "InputSkill":
        from venom_core.execution.skills.input_skill import InputSkill

        return InputSkill
    elif name == "MediaSkill":
        from venom_core.execution.skills.media_skill import MediaSkill

        return MediaSkill
    elif name == "PlatformSkill":
        from venom_core.execution.skills.platform_skill import PlatformSkill

        return PlatformSkill
    elif name == "ShellSkill":
        from venom_core.execution.skills.shell_skill import ShellSkill

        return ShellSkill
    elif name == "TestSkill":
        from venom_core.execution.skills.test_skill import TestSkill

        return TestSkill
    elif name == "WebSearchSkill":
        from venom_core.execution.skills.web_skill import WebSearchSkill

        return WebSearchSkill
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
