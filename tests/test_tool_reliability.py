"""Integration Suite for Tool Reliability (Toolchain Check)."""

import tempfile
from pathlib import Path

import pytest

from venom_core.core.permission_guard import permission_guard
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.shell_skill import ShellSkill
from venom_core.execution.skills.test_skill import TestSkill


@pytest.fixture(autouse=True)
def _allow_toolchain_operations():
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(40)
    try:
        yield
    finally:
        permission_guard.set_level(previous_level)


@pytest.mark.asyncio
async def test_toolchain_reliability():
    """
    Verify the entire toolchain works together in the current environment:
    1. FileSkill: Create a python script.
    2. ShellSkill: Execute the script.
    3. TestSkill: Run tests for it.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Initialize Skills
        file_skill = FileSkill(workspace_root=str(workspace))
        shell_skill = ShellSkill(use_sandbox=False)  # Local execution
        test_skill = TestSkill(allow_local_execution=True)

        # 1. FileSkill: Create a script and a test
        script_content = """
def add(a, b):
    return a + b

if __name__ == "__main__":
    print(add(2, 3))
"""
        test_content = """
from script import add

def test_add():
    assert add(2, 3) == 5
"""
        await file_skill.write_file("script.py", script_content)
        await file_skill.write_file("test_script.py", test_content)

        assert (workspace / "script.py").exists()

        # 2. ShellSkill: Run the script
        # We need to run it in the temp dir context
        import shlex
        import sys

        # Use sys.executable to ensure we use the correct python interpreter (with pytest installed)
        # Quote paths to handle spaces properly
        safe_tmpdir = shlex.quote(str(tmpdir))
        cmd = f"cd {safe_tmpdir} && {sys.executable} script.py"
        shell_result = shell_skill.run_shell(cmd)

        assert "5" in shell_result
        assert "pomyślnie" in shell_result.lower() or "exit_code=0" in shell_result

        # 3. TestSkill: Run the test
        # TestSkill.run_pytest uses 'python -m pytest path'
        # For pytest to import 'script', we need to set PYTHONPATH to include tmpdir.
        # Since TestSkill runs pytest as a subprocess, we'll set PYTHONPATH env var.

        import os

        # Save original PYTHONPATH
        original_pythonpath = os.environ.get("PYTHONPATH", "")

        try:
            # Add tmpdir to PYTHONPATH so pytest can import 'script'
            if original_pythonpath:
                os.environ["PYTHONPATH"] = f"{tmpdir}{os.pathsep}{original_pythonpath}"
            else:
                os.environ["PYTHONPATH"] = str(tmpdir)

            test_path = str(workspace / "test_script.py")
            pass_test_result = await test_skill.run_pytest(test_path=test_path)
        finally:
            # Restore original PYTHONPATH
            if original_pythonpath:
                os.environ["PYTHONPATH"] = original_pythonpath
            else:
                os.environ.pop("PYTHONPATH", None)

        # Check results
        if "ModuleNotFoundError" in pass_test_result:
            pytest.fail(
                f"TestSkill failed to resolve imports in generated code: {pass_test_result}"
            )

        assert "✅" in pass_test_result or "passed" in pass_test_result.lower()
        assert "Failed: 0" in pass_test_result
