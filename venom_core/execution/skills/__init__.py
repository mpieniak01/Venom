"""Moduł: skills - zestawienie wszystkich umiejętności Venom."""

from venom_core.execution.skills.browser_skill import BrowserSkill
from venom_core.execution.skills.docs_skill import DocsSkill
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.execution.skills.shell_skill import ShellSkill
from venom_core.execution.skills.test_skill import TestSkill
from venom_core.execution.skills.web_skill import WebSearchSkill

__all__ = [
    "BrowserSkill",
    "DocsSkill",
    "FileSkill",
    "GitSkill",
    "ShellSkill",
    "TestSkill",
    "WebSearchSkill",
]
