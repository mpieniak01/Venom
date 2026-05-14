"""Audit current multi_runtime request flow for 217DA phase 0."""

from __future__ import annotations

import ast
import json
from pathlib import Path


def _function_calls(module_path: Path, function_name: str) -> list[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.ClassDef):
            stack.extend(node.body)
            continue
        if (
            isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
            and node.name == function_name
        ):
            calls: list[str] = []
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    func = inner.func
                    if isinstance(func, ast.Name):
                        calls.append(func.id)
                    elif isinstance(func, ast.Attribute):
                        calls.append(func.attr)
            return sorted(set(calls))
    return []


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    main_py = repo_root / "services" / "multi_runtime" / "main.py"
    engine_py = repo_root / "services" / "multi_runtime" / "engine.py"

    respond_calls = _function_calls(main_py, "respond")
    engine_calls = _function_calls(engine_py, "respond")

    report = {
        "phase": "217DA/F0",
        "request_flow": [
            "request",
            "parse",
            "route",
            "infer",
            "response",
            "status",
        ],
        "main.respond.calls": respond_calls,
        "engine.respond.calls": engine_calls,
        "notes": [
            "Pipeline orchestration should stay outside heavy model loader internals.",
            "Model infer call remains delegated to engine.respond.",
        ],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
