"""Architecture guardrails for API routes side-effect imports."""

from __future__ import annotations

import ast
from pathlib import Path

ROUTES_DIR = Path("venom_core/api/routes")
FORBIDDEN_IMPORTS = {"subprocess", "httpx", "threading"}
FORBIDDEN_LAYER_PREFIXES = ("venom_core.core", "venom_core.infrastructure")

# Current exceptions are explicit and bounded. Adding a new file here should be
# a conscious architectural decision in review.
ALLOWED_FORBIDDEN_IMPORTS: dict[str, set[str]] = {
    "venom_core/api/routes/academy_models.py": {"subprocess"},
    "venom_core/api/routes/git.py": {"subprocess"},
    "venom_core/api/routes/system_storage.py": {"subprocess"},
    "venom_core/api/routes/providers.py": {"httpx"},
    "venom_core/api/routes/system_llm.py": {"httpx"},
    "venom_core/api/routes/models_remote.py": {"threading"},
    "venom_core/api/routes/llm_simple.py": {"threading"},
}

# Existing layer exceptions are a temporary baseline from refactor wave 181/182.
# The test blocks any new direct imports in routes and forces explicit review.
ALLOWED_LAYER_IMPORTS: dict[str, set[str]] = {
    "venom_core/api/routes/agents.py": {"venom_core.core.models"},
    "venom_core/api/routes/feedback.py": {"venom_core.core", "venom_core.core.models"},
    "venom_core/api/routes/learning.py": {
        "venom_core.core.hidden_prompts",
        "venom_core.core.learning_log",
    },
    "venom_core/api/routes/llm_simple.py": {
        "venom_core.core.metrics",
        "venom_core.core.tracer",
    },
    "venom_core/api/routes/memory.py": {
        "venom_core.core.environment_policy",
        "venom_core.core.orchestrator.constants",
    },
    "venom_core/api/routes/models_config.py": {
        "venom_core.core",
        "venom_core.core.generation_params_adapter",
        "venom_core.core.model_registry",
    },
    "venom_core/api/routes/models_install.py": {"venom_core.core.model_manager"},
    "venom_core/api/routes/models_registry.py": {"venom_core.core.model_registry"},
    "venom_core/api/routes/models_registry_ops.py": {"venom_core.core.model_registry"},
    "venom_core/api/routes/providers.py": {
        "venom_core.core.admin_audit",
        "venom_core.core.error_mappings",
        "venom_core.core.metrics",
        "venom_core.core.provider_observability",
    },
    "venom_core/api/routes/queue.py": {"venom_core.core.environment_policy"},
    "venom_core/api/routes/system_governance.py": {"venom_core.core.permission_guard"},
    "venom_core/api/routes/system_metrics.py": {"venom_core.core"},
    "venom_core/api/routes/traffic_control.py": {
        "venom_core.infrastructure.traffic_control"
    },
}


def _collect_top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def _collect_import_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_api_routes_forbidden_imports_are_explicitly_whitelisted() -> None:
    violations: list[str] = []

    for route_file in sorted(ROUTES_DIR.glob("*.py")):
        rel = str(route_file)
        imported = _collect_top_level_imports(route_file)
        forbidden_used = imported & FORBIDDEN_IMPORTS
        if not forbidden_used:
            continue

        allowed = ALLOWED_FORBIDDEN_IMPORTS.get(rel, set())
        unexpected = forbidden_used - allowed
        if unexpected:
            violations.append(
                f"{rel}: forbidden imports {sorted(unexpected)}; allowed={sorted(allowed)}"
            )

    assert not violations, "\n".join(violations)


def test_api_routes_layer_imports_are_explicitly_whitelisted() -> None:
    violations: list[str] = []

    for route_file in sorted(ROUTES_DIR.glob("*.py")):
        rel = str(route_file)
        imported_modules = _collect_import_modules(route_file)
        layer_imports = {
            module
            for module in imported_modules
            if module.startswith(FORBIDDEN_LAYER_PREFIXES)
        }
        if not layer_imports:
            continue

        allowed = ALLOWED_LAYER_IMPORTS.get(rel, set())
        unexpected = layer_imports - allowed
        if unexpected:
            violations.append(
                f"{rel}: direct core/infrastructure imports {sorted(unexpected)}; "
                f"allowed={sorted(allowed)}"
            )

    assert not violations, "\n".join(violations)
