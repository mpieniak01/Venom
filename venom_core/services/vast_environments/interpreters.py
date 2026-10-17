"""Discover existing image environments without installing or modifying packages."""

import shlex

SELECT_SCRIPT = """
import shutil, subprocess, sys
mode = sys.argv[1]
required = ["torch", "vllm"] if mode == "vllm" else ["torch"] if mode == "pytorch" else []
candidates = ["/workspace/venom-vast/worker-venv/bin/python", sys.executable,
              "/venv/main/bin/python", "/opt/venv/bin/python"]
seen = set()
for candidate in candidates:
    path = shutil.which(candidate)
    if not path or path in seen:
        continue
    seen.add(path)
    try:
        code = "import importlib.util; assert all(importlib.util.find_spec(n) for n in " + repr(required) + ")"
        result = subprocess.run([path, "-c", code], capture_output=True, timeout=3)
        if result.returncode == 0:
            print(path)
            break
    except (OSError, subprocess.TimeoutExpired):
        pass
else:
    print(sys.executable)
"""


def select_shell(mode: str) -> str:
    return (
        "PYTHON=$(python3 - "
        + shlex.quote(mode)
        + " <<'VENOM_PYTHON'\n"
        + SELECT_SCRIPT
        + "\nVENOM_PYTHON\n)\n"
        + 'test -n "$PYTHON" || PYTHON=python3\n'
    )
