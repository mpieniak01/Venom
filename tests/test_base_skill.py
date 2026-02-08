import pytest

from venom_core.execution.skills.base_skill import (
    BaseSkill,
    SecurityError,
    async_safe_action,
    safe_action,
)


# Helper class to test decorators and inheritance
class BaseSkillTester(BaseSkill):
    @safe_action
    def risky_method(self, should_fail=False):
        if should_fail:
            raise ValueError("Intentional failure")
        return "Success"

    @async_safe_action
    def risky_method_async(self, should_fail=False):
        if should_fail:
            raise ValueError("Intentional async failure")
        return "Async Success"


@pytest.fixture
def workspace_root(tmp_path):
    return tmp_path


def test_base_skill_initialization(workspace_root):
    skill = BaseSkill(workspace_root=str(workspace_root))
    assert skill.workspace_root == workspace_root.resolve()
    assert skill.logger is not None


def test_validate_path_valid(workspace_root):
    skill = BaseSkill(workspace_root=str(workspace_root))

    # Simple file
    path = skill.validate_path("test.txt")
    assert path == (workspace_root / "test.txt").resolve()

    # Subdirectory
    path = skill.validate_path("subdir/test.txt")
    assert path == (workspace_root / "subdir/test.txt").resolve()


def test_validate_path_security_error(workspace_root):
    skill = BaseSkill(workspace_root=str(workspace_root))

    # Parent directory traversal
    with pytest.raises(SecurityError):
        skill.validate_path("../outside.txt")

    # Absolute path outside workspace
    with pytest.raises(SecurityError):
        skill.validate_path("/etc/passwd")


def test_safe_action_decorator(workspace_root):
    skill = BaseSkillTester(workspace_root=str(workspace_root))

    # Success case
    assert skill.risky_method(should_fail=False) == "Success"

    # Failure case (should return string error, not raise)
    result = skill.risky_method(should_fail=True)
    assert isinstance(result, str)
    assert "❌ Wystąpił błąd: Intentional failure" in result


@pytest.mark.asyncio
async def test_async_safe_action_decorator(workspace_root):
    skill = BaseSkillTester(workspace_root=str(workspace_root))

    # Success case
    assert await skill.risky_method_async(should_fail=False) == "Async Success"

    # Failure case
    result = await skill.risky_method_async(should_fail=True)
    assert isinstance(result, str)
    assert "❌ Wystąpił błąd: Intentional async failure" in result
