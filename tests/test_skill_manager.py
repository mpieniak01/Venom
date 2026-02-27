"""Testy dla SkillManager - dynamiczne zarządzanie umiejętnościami."""

import ast
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import venom_core.execution.skill_manager as skill_manager_module
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.execution.skill_manager import SkillManager, SkillValidationError


@pytest.fixture
def kernel():
    """Fixture: Kernel do testów."""
    builder = KernelBuilder()
    return builder.build_kernel()


@pytest.fixture
def temp_skills_dir():
    """Fixture: Tymczasowy katalog na skills."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def skill_manager(kernel, temp_skills_dir):
    """Fixture: SkillManager z tymczasowym katalogiem."""
    return SkillManager(kernel, custom_skills_dir=temp_skills_dir)


def test_skill_manager_initialization(skill_manager, temp_skills_dir):
    """Test inicjalizacji SkillManager."""
    assert skill_manager.kernel is not None
    assert str(skill_manager.custom_skills_dir) == temp_skills_dir
    assert skill_manager.loaded_skills == {}


def test_custom_skills_directory_creation(temp_skills_dir):
    """Test tworzenia katalogu custom skills."""
    skills_dir = Path(temp_skills_dir) / "custom"
    assert not skills_dir.exists()

    # Katalog powinien być utworzony przez SkillManager
    builder = KernelBuilder()
    kernel = builder.build_kernel()
    SkillManager(kernel, custom_skills_dir=str(skills_dir))

    assert skills_dir.exists()


def test_validate_skill_valid(skill_manager, temp_skills_dir):
    """Test walidacji poprawnego skill."""
    # Stwórz poprawny skill
    skill_code = '''"""Test skill."""
from typing import Annotated
from semantic_kernel.functions import kernel_function

class TestSkill:
    @kernel_function(name="test_func", description="Test")
    def test_func(self, param: Annotated[str, "param"]) -> str:
        return f"Result: {param}"
'''

    skill_file = Path(temp_skills_dir) / "test_skill.py"
    skill_file.write_text(skill_code)

    # Walidacja powinna przejść
    result = skill_manager.validate_skill(str(skill_file))
    assert result is True


def test_validate_skill_no_class(skill_manager, temp_skills_dir):
    """Test walidacji skill bez klasy."""
    skill_code = '''"""Test skill without class."""
def some_function():
    return "test"
'''

    skill_file = Path(temp_skills_dir) / "bad_skill.py"
    skill_file.write_text(skill_code)

    # Walidacja powinna nie przejść
    with pytest.raises(SkillValidationError, match="nie zawiera żadnej klasy"):
        skill_manager.validate_skill(str(skill_file))


def test_validate_skill_no_kernel_function(skill_manager, temp_skills_dir):
    """Test walidacji skill bez @kernel_function."""
    skill_code = '''"""Test skill without decorator."""
class TestSkill:
    def test_func(self):
        return "test"
'''

    skill_file = Path(temp_skills_dir) / "bad_skill.py"
    skill_file.write_text(skill_code)

    # Walidacja powinna nie przejść
    with pytest.raises(
        SkillValidationError, match="nie ma dekoratora @kernel_function"
    ):
        skill_manager.validate_skill(str(skill_file))


def test_validate_skill_dangerous_code(skill_manager, temp_skills_dir):
    """Test walidacji skill z niebezpiecznym kodem."""
    skill_code = '''"""Dangerous skill."""
from typing import Annotated
from semantic_kernel.functions import kernel_function

class DangerousSkill:
    @kernel_function(name="eval_func", description="Dangerous")
    def eval_func(self, code: Annotated[str, "code"]) -> str:
        return eval(code)
'''

    skill_file = Path(temp_skills_dir) / "dangerous_skill.py"
    skill_file.write_text(skill_code)

    # Walidacja powinna nie przejść
    with pytest.raises(SkillValidationError, match="niebezpieczne funkcje"):
        skill_manager.validate_skill(str(skill_file))


def test_load_skills_from_empty_dir(skill_manager):
    """Test ładowania skills z pustego katalogu."""
    loaded = skill_manager.load_skills_from_dir()
    assert loaded == []
    assert len(skill_manager.loaded_skills) == 0


def test_load_valid_skill(skill_manager, temp_skills_dir):
    """Test ładowania poprawnego skill."""
    # Stwórz poprawny skill
    skill_code = '''"""Calculator skill."""
from typing import Annotated
from semantic_kernel.functions import kernel_function

class CalculatorSkill:
    @kernel_function(name="add", description="Dodaje dwie liczby")
    def add(self, a: Annotated[int, "pierwsza liczba"], b: Annotated[int, "druga liczba"]) -> str:
        result = a + b
        return f"Wynik: {result}"
'''

    skill_file = Path(temp_skills_dir) / "calculator_skill.py"
    skill_file.write_text(skill_code)

    # Załaduj skills
    loaded = skill_manager.load_skills_from_dir()

    assert "calculator_skill" in loaded
    assert "calculator_skill" in skill_manager.loaded_skills


def test_get_loaded_skills(skill_manager, temp_skills_dir):
    """Test pobierania listy załadowanych skills."""
    # Stwórz kilka skills
    for i in range(3):
        skill_code = f'''"""Skill {i}."""
from typing import Annotated
from semantic_kernel.functions import kernel_function

class Skill{i}:
    @kernel_function(name="func{i}", description="Test")
    def func{i}(self) -> str:
        return "test"
'''
        skill_file = Path(temp_skills_dir) / f"skill_{i}.py"
        skill_file.write_text(skill_code)

    # Załaduj skills
    skill_manager.load_skills_from_dir()

    loaded = skill_manager.get_loaded_skills()
    assert len(loaded) == 3
    assert "skill_0" in loaded
    assert "skill_1" in loaded
    assert "skill_2" in loaded


def test_unload_skill(skill_manager, temp_skills_dir):
    """Test usuwania skill z rejestru."""
    # Stwórz i załaduj skill
    skill_code = '''"""Test skill."""
from typing import Annotated
from semantic_kernel.functions import kernel_function

class TestSkill:
    @kernel_function(name="test", description="Test")
    def test(self) -> str:
        return "test"
'''
    skill_file = Path(temp_skills_dir) / "test_skill.py"
    skill_file.write_text(skill_code)
    skill_manager.load_skills_from_dir()

    assert "test_skill" in skill_manager.loaded_skills

    # Usuń skill
    result = skill_manager.unload_skill("test_skill")
    assert result is True
    assert "test_skill" not in skill_manager.loaded_skills

    # Próba usunięcia nieistniejącego skill
    result = skill_manager.unload_skill("nonexistent")
    assert result is False


def test_load_skill_ignores_init_and_underscore(skill_manager, temp_skills_dir):
    """Test że SkillManager ignoruje __init__.py i pliki zaczynające się od _."""
    # Stwórz pliki do zignorowania
    init_file = Path(temp_skills_dir) / "__init__.py"
    init_file.write_text("# init")

    private_file = Path(temp_skills_dir) / "_private.py"
    private_file.write_text("# private")

    # Stwórz poprawny skill
    skill_code = '''"""Valid skill."""
from semantic_kernel.functions import kernel_function

class ValidSkill:
    @kernel_function(name="test", description="Test")
    def test(self) -> str:
        return "test"
'''
    skill_file = Path(temp_skills_dir) / "valid_skill.py"
    skill_file.write_text(skill_code)

    # Załaduj
    loaded = skill_manager.load_skills_from_dir()

    # Tylko valid_skill powinien być załadowany
    assert len(loaded) == 1
    assert "valid_skill" in loaded


def test_reload_skill_returns_false_for_missing_file(skill_manager):
    assert skill_manager.reload_skill("missing_skill") is False


def test_reload_skill_returns_false_when_reload_raises(
    skill_manager, temp_skills_dir, monkeypatch
):
    skill_code = '''"""Reloadable skill."""
from semantic_kernel.functions import kernel_function

class ReloadableSkill:
    @kernel_function(name="test", description="Test")
    def test(self) -> str:
        return "ok"
'''
    skill_file = Path(temp_skills_dir) / "reloadable.py"
    skill_file.write_text(skill_code)
    assert "reloadable" in skill_manager.load_skills_from_dir()

    def _raise_reload(_module):
        raise RuntimeError("reload failed")

    monkeypatch.setattr(skill_manager_module.importlib, "reload", _raise_reload)
    assert skill_manager.reload_skill("reloadable") is False


@pytest.mark.asyncio
async def test_broadcast_skill_event_success_and_failure(kernel, temp_skills_dir):
    broadcaster = MagicMock()
    broadcaster.broadcast_event = AsyncMock(return_value=None)
    manager = SkillManager(
        kernel, custom_skills_dir=temp_skills_dir, event_broadcaster=broadcaster
    )

    await manager.broadcast_skill_event("SKILL_STARTED", "docs", action="generate")
    broadcaster.broadcast_event.assert_awaited_once()

    broadcaster.broadcast_event = AsyncMock(side_effect=RuntimeError("ws down"))
    await manager.broadcast_skill_event("SKILL_FAILED", "docs", action="build")


def test_decorator_name_variants(skill_manager):
    name_node = ast.Name(id="kernel_function")
    call_node = ast.Call(func=ast.Name(id="kernel_function"), args=[], keywords=[])
    attr_node = ast.Attribute(value=ast.Name(id="x"), attr="y")

    assert skill_manager._decorator_name(name_node) == "kernel_function"
    assert skill_manager._decorator_name(call_node) == "kernel_function"
    assert skill_manager._decorator_name(attr_node) is None


def test_register_skill_in_kernel_skips_foreign_classes(temp_skills_dir):
    manager = SkillManager(MagicMock(), custom_skills_dir=temp_skills_dir)
    plugin_cls = type("Plugin", (), {"__module__": "venom_custom_demo"})
    foreign_cls = type("Foreign", (), {"__module__": "external.mod"})
    module = SimpleNamespace(Plugin=plugin_cls, Foreign=foreign_cls)

    manager._register_skill_in_kernel("demo", module)

    added = [
        call.kwargs.get("plugin_name") for call in manager.kernel.add_plugin.mock_calls
    ]
    assert "Plugin" in added
    assert "Foreign" not in added


class _DummyMcpAdapter:
    def __init__(self, result="ok", should_fail=False):
        self._result = result
        self._should_fail = should_fail

    def list_tools(self):
        return [SimpleNamespace(name="tool_a")]

    async def invoke_tool(self, tool_name, arguments):
        if self._should_fail:
            raise RuntimeError("tool failed")
        return f"{tool_name}:{arguments.get('x', self._result)}"


def test_register_mcp_adapter_rejects_missing_interface(skill_manager):
    with pytest.raises(ValueError, match="list_tools"):
        skill_manager.register_mcp_adapter("broken", object())


def test_list_mcp_tools_for_single_adapter(skill_manager):
    skill_manager.register_mcp_adapter(
        "dummy", _DummyMcpAdapter(), skill_name="FileSkill"
    )

    tools = skill_manager.list_mcp_tools("dummy")
    assert "dummy" in tools
    assert tools["dummy"][0].name == "tool_a"


@pytest.mark.asyncio
async def test_invoke_mcp_tool_success_emits_started_and_completed(
    kernel, temp_skills_dir, monkeypatch
):
    broadcaster = MagicMock()
    broadcaster.broadcast_event = AsyncMock(return_value=None)
    manager = SkillManager(
        kernel, custom_skills_dir=temp_skills_dir, event_broadcaster=broadcaster
    )
    manager.register_mcp_adapter("dummy", _DummyMcpAdapter(), skill_name="FileSkill")

    monkeypatch.setattr(
        skill_manager_module.permission_guard, "check_permission", lambda _name: True
    )

    result = await manager.invoke_mcp_tool("dummy", "tool_a", {"x": "ok"})
    assert result == "tool_a:ok"
    assert broadcaster.broadcast_event.await_count == 2
    event_types = [
        call.kwargs["event_type"]
        for call in broadcaster.broadcast_event.await_args_list
    ]
    assert event_types == ["SKILL_STARTED", "SKILL_COMPLETED"]
    completed_data = broadcaster.broadcast_event.await_args_list[1].kwargs["data"]
    assert "duration_ms" in completed_data
    assert isinstance(completed_data["duration_ms"], int)


@pytest.mark.asyncio
async def test_invoke_mcp_tool_permission_denied_emits_failed(
    kernel, temp_skills_dir, monkeypatch
):
    broadcaster = MagicMock()
    broadcaster.broadcast_event = AsyncMock(return_value=None)
    manager = SkillManager(
        kernel, custom_skills_dir=temp_skills_dir, event_broadcaster=broadcaster
    )
    manager.register_mcp_adapter("dummy", _DummyMcpAdapter(), skill_name="GitSkill")

    def _deny(_name):
        raise RuntimeError("denied")

    monkeypatch.setattr(
        skill_manager_module.permission_guard, "check_permission", _deny
    )

    with pytest.raises(RuntimeError, match="denied"):
        await manager.invoke_mcp_tool("dummy", "tool_a", {})

    assert broadcaster.broadcast_event.await_count == 1
    assert broadcaster.broadcast_event.await_args.kwargs["event_type"] == "SKILL_FAILED"
    failed_data = broadcaster.broadcast_event.await_args.kwargs["data"]
    assert failed_data["error_class"] == "PermissionDenied"
    assert "duration_ms" in failed_data


@pytest.mark.asyncio
async def test_invoke_mcp_tool_tool_error_emits_failed(
    kernel, temp_skills_dir, monkeypatch
):
    broadcaster = MagicMock()
    broadcaster.broadcast_event = AsyncMock(return_value=None)
    manager = SkillManager(
        kernel, custom_skills_dir=temp_skills_dir, event_broadcaster=broadcaster
    )
    manager.register_mcp_adapter(
        "dummy", _DummyMcpAdapter(should_fail=True), skill_name="FileSkill"
    )

    monkeypatch.setattr(
        skill_manager_module.permission_guard, "check_permission", lambda _name: True
    )

    with pytest.raises(RuntimeError, match="tool failed"):
        await manager.invoke_mcp_tool("dummy", "tool_a", {})

    assert broadcaster.broadcast_event.await_count == 2
    event_types = [
        call.kwargs["event_type"]
        for call in broadcaster.broadcast_event.await_args_list
    ]
    assert event_types == ["SKILL_STARTED", "SKILL_FAILED"]
    failed_data = broadcaster.broadcast_event.await_args_list[1].kwargs["data"]
    assert failed_data["error_class"] == "RuntimeError"
    assert "duration_ms" in failed_data
