from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_semantic_kernel_openai_connector_imports_with_openai_199x() -> None:
    """The runtime shim should keep Semantic Kernel imports working through venom_core."""
    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "from venom_core.execution.kernel_builder import KernelBuilder\n"
        "from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings\n"
        "from openai._types import omit\n"
        "print(KernelBuilder.__name__)\n"
        "print(type(omit).__name__)\n"
        "print(OpenAIChatPromptExecutionSettings.__name__)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "KernelBuilder" in result.stdout
    assert "Omit" in result.stdout
    assert "OpenAIChatPromptExecutionSettings" in result.stdout
