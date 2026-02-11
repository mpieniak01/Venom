import asyncio
import os
import sys

# Ensure venom_core is in path
sys.path.append(os.getcwd())

from venom_core.core.permission_guard import permission_guard
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.shell_skill import ShellSkill


async def test_autonomy_bypass():
    print("--- Autonomy Bypass Test ---")

    # Setup mock workspace
    os.makedirs("./workspace", exist_ok=True)

    # 1. Set Autonomy to ISOLATED (Level 0)
    print(f"Current Level: {permission_guard.get_current_level()}")
    print("Setting Autonomy Level to 0 (ISOLATED)...")
    permission_guard.set_level(0)

    # 2. Try ShellSkill
    print("\n[Attempting Shell Execution]")
    shell_skill = ShellSkill(use_sandbox=False)

    try:
        # We expect this to FAIL with PermissionError
        result = shell_skill.run_shell("echo 'VULNERABLE'")
        print(f"Result: {result}")
        if "VULNERABLE" in result:
            print("❌ SECURITY FAILURE: Shell command executed!")
        else:
            print("❓ RESULT: " + result)
    except Exception as e:
        print(f"✅ BLOCKED: {e}")

    # 3. Try FileSkill
    print("\n[Attempting File Write]")
    file_skill = FileSkill(workspace_root="/tmp/venom_test")
    try:
        result = await file_skill.write_file("pwn.txt", "VULNERABLE")
        print(f"Result: {result}")
        print("❌ SECURITY FAILURE: File written!")
    except Exception as e:
        print(f"✅ BLOCKED: {e}")


if __name__ == "__main__":
    asyncio.run(test_autonomy_bypass())
