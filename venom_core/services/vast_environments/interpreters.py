"""Discover existing image environments without installing or modifying packages."""

import shlex

SELECT_SCRIPT = """
import shutil, subprocess, sys
mode = sys.argv[1]
required = ["torch", "vllm"] if mode == "vllm" else ["torch"] if mode == "pytorch" else []
candidates = ["/workspace/venom-vast/worker-venv/bin/python", sys.executable,
              "/venv/main/bin/python", "/opt/venv/bin/python"]
if len(sys.argv) > 2 and sys.argv[2] == "base":
    candidates = candidates[1:]
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
        + " base <<'VENOM_PYTHON'\n"
        + SELECT_SCRIPT
        + "\nVENOM_PYTHON\n)\n"
        + 'test -n "$PYTHON" || PYTHON=python3\n'
    )


WORKER_PATHS_SCRIPT = """
import pathlib, site, subprocess, sys
worker = sys.argv[1]
result = subprocess.run(
    [worker, "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
    text=True, capture_output=True, check=True, timeout=10,
)
destination = pathlib.Path(result.stdout.strip()) / "venom-image-site-packages.pth"
paths = [path for path in site.getsitepackages()
         if pathlib.Path(path).is_absolute() and pathlib.Path(path).is_dir()
         and "\\n" not in path and "\\r" not in path]
destination.write_text("".join(path + "\\n" for path in paths), encoding="utf-8")
"""
