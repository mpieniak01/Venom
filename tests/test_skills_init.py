import types

import pytest


def test_skills_lazy_imports(monkeypatch):
    import venom_core.execution.skills as skills

    module_map = {
        "AssistantSkill": "assistant_skill",
        "BrowserSkill": "browser_skill",
        "CoreSkill": "core_skill",
        "DocsSkill": "docs_skill",
        "FileSkill": "file_skill",
        "GitSkill": "git_skill",
        "InputSkill": "input_skill",
        "MediaSkill": "media_skill",
        "PlatformSkill": "platform_skill",
        "ShellSkill": "shell_skill",
        "TestSkill": "test_skill",
        "WebSearchSkill": "web_skill",
    }

    for class_name, module_suffix in module_map.items():
        module_name = f"venom_core.execution.skills.{module_suffix}"
        module = types.ModuleType(module_name)
        dummy_class = type(class_name, (), {})
        setattr(module, class_name, dummy_class)
        monkeypatch.setitem(__import__("sys").modules, module_name, module)

    for class_name in skills.__all__:
        resolved = getattr(skills, class_name)
        assert resolved.__name__ == class_name

    with pytest.raises(AttributeError):
        getattr(skills, "MissingSkill")


def test_skills_resolve_skill_helper(monkeypatch):
    import venom_core.execution.skills as skills

    module_name = "venom_core.execution.skills.assistant_skill"
    module = types.ModuleType(module_name)
    dummy_class = type("AssistantSkill", (), {})
    setattr(module, "AssistantSkill", dummy_class)
    monkeypatch.setitem(__import__("sys").modules, module_name, module)

    resolved = skills._resolve_skill("AssistantSkill")
    assert resolved is dummy_class

    with pytest.raises(AttributeError):
        skills._resolve_skill("DefinitelyMissingSkill")
