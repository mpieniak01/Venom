"""Test integracyjny dla The Forge - dynamiczne tworzenie narzędzi."""

import tempfile
from pathlib import Path

import pytest

# Ten test wymaga pełnych dependencies i LLM, więc oznaczamy jako integration test
pytestmark = pytest.mark.integration


def test_skill_manager_hot_reload():
    """Test hot-reload narzędzia bez restartu."""
    from venom_core.execution.maf_runtime import AgentRuntime
    from venom_core.execution.skill_manager import SkillManager

    with tempfile.TemporaryDirectory() as tmpdir:
        kernel = AgentRuntime()
        skill_manager = SkillManager(kernel, custom_skills_dir=tmpdir)

        # Stwórz narzędzie v1
        skill_code_v1 = '''"""Test skill v1."""
from typing import Annotated
from venom_core.execution.agent_contracts import tool_function as kernel_function

class TestSkill:
    @kernel_function(name="greet", description="Pozdrowienie")
    def greet(self, name: Annotated[str, "Imię"]) -> str:
        return f"Hello {name}!"
'''

        skill_file = Path(tmpdir) / "test_skill.py"
        skill_file.write_text(skill_code_v1)

        # Załaduj v1
        loaded = skill_manager.load_skills_from_dir()
        assert "test_skill" in loaded
        assert kernel.plugins["TestSkill"]["greet"]("Ada") == "Hello Ada!"

        # Zmień kod na v2
        skill_code_v2 = '''"""Test skill v2."""
from typing import Annotated
from venom_core.execution.agent_contracts import tool_function as kernel_function

class TestSkill:
    @kernel_function(name="greet", description="Pozdrowienie PL")
    def greet(self, name: Annotated[str, "Imię"]) -> str:
        return f"Witaj {name}!"  # Zmienione z Hello na Witaj
'''

        skill_file.write_text(skill_code_v2)

        # Hot-reload (bez restartu)
        reload_success = skill_manager.reload_skill("test_skill")
        assert reload_success, "Hot-reload nie powiódł się"
        assert kernel.plugins["TestSkill"]["greet"]("Ada") == "Witaj Ada!"

        # Narzędzie powinno być nadal w rejestrze
        assert "test_skill" in skill_manager.get_loaded_skills()

        print("✅ Hot-reload zakończony sukcesem!")
