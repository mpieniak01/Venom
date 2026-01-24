"""Integration Suite for Tool Reliability (Toolchain Check)."""

import tempfile
from pathlib import Path

import pytest

from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.shell_skill import ShellSkill
from venom_core.execution.skills.test_skill import TestSkill


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
        import sys

        # Use sys.executable to ensure we use the correct python interpreter (with pytest installed)
        cmd = f"cd {tmpdir} && {sys.executable} script.py"
        shell_result = shell_skill.run_shell(cmd)

        assert "5" in shell_result
        assert "pomyślnie" in shell_result.lower() or "exit_code=0" in shell_result

        # 3. TestSkill: Run the test
        # We pass absolute path or ensure pytest runs in tmpdir
        # TestSkill.run_pytest uses 'python -m pytest path'
        # Since 'script.py' is in tmpdir, we need to make sure pytest finds it.
        # Simplest way: execute pytest on the absolute path of the test file.

        test_path = str(workspace / "test_script.py")

        # NOTE: For pytest to import 'script', the directory must be in PYTHONPATH
        # or we rely on pytest's automatic path addition.
        # Let's set PYTHONPATH for the subprocess in TestSkill?
        # TestSkill currently uses the env of the parent process.
        # We might need to modify sys.path temporarily or trust pytest.

        # Hack: ensure PYTHONPATH includes the tmpdir for this test execution?
        # Actually, python -m pytest adds the current dir to sys.path if run from there.
        # But TestSkill runs from CWD.
        # Let's see if it works naturally due to pytest magic.

        # If imports fail, this reliability test correctly identifies a gap in Toolchain
        # (Handling PYTHONPATH for generated code).

        # Workaround for test reliability: use --rootdir or rely on python modules
        pass_test_result = await test_skill.run_pytest(test_path=test_path)

        # Check results
        if "ModuleNotFoundError" in pass_test_result:
            pytest.fail(
                f"TestSkill failed to resolve imports in generated code: {pass_test_result}"
            )

        assert "✅" in pass_test_result or "passed" in pass_test_result.lower()
        assert "Failed: 0" in pass_test_result
