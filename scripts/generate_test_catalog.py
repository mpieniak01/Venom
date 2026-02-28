#!/usr/bin/env python3
"""Generate canonical test catalog used by dynamic lane selection."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

LEGACY_TARGETED_RE = re.compile(
    r"(coverage|wave|hotfix|blocker|phase|new_code|fixes?|pr[_-]?gate|ipt)",
    re.IGNORECASE,
)

DEFAULT_OUTPUT = Path("config/testing/test_catalog.json")

ALLOWED_DOMAINS = [
    "academy",
    "agents",
    "api",
    "architecture",
    "audit",
    "bootstrap",
    "control_plane",
    "core",
    "docker",
    "environment",
    "governance",
    "knowledge",
    "memory",
    "models",
    "nodes",
    "orchestrator",
    "performance",
    "providers",
    "runtime",
    "security",
    "skills",
    "system",
    "tasks",
    "testing_tooling",
    "translation",
    "workflow",
    "misc",
]

ALLOWED_TEST_TYPES = [
    "unit",
    "route_contract",
    "service_contract",
    "integration",
    "perf",
    "gate",
]

ALLOWED_INTENTS = [
    "regression",
    "contract",
    "gate",
    "integration",
    "performance",
    "security",
    "legacy_coverage",
]

_TOKEN_TO_DOMAIN = {
    "academy": "academy",
    "agent": "agents",
    "agents": "agents",
    "api": "api",
    "architecture": "architecture",
    "audit": "audit",
    "autonomy": "governance",
    "bootstrap": "bootstrap",
    "compose": "environment",
    "config": "environment",
    "control_plane": "control_plane",
    "docker": "docker",
    "env": "environment",
    "environment": "environment",
    "governance": "governance",
    "graph": "knowledge",
    "knowledge": "knowledge",
    "lane": "testing_tooling",
    "lesson": "knowledge",
    "llm": "runtime",
    "memory": "memory",
    "model": "models",
    "module_registry": "models",
    "node": "nodes",
    "onnx": "runtime",
    "orchestrator": "orchestrator",
    "policy": "governance",
    "preprod": "environment",
    "provider": "providers",
    "queue": "tasks",
    "resolve_sonar": "testing_tooling",
    "runtime": "runtime",
    "scheduler": "tasks",
    "security": "security",
    "service": "core",
    "skill": "skills",
    "sonar": "testing_tooling",
    "system": "system",
    "task": "tasks",
    "test_intelligence": "testing_tooling",
    "traffic_control": "control_plane",
    "translation": "translation",
    "workflow": "workflow",
}


def _read_group(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line)
    return out


def _extract_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _path_tokens(path: str) -> list[str]:
    stem = Path(path).stem
    normalized = stem.replace("test_", "").replace("-", "_").lower()
    tokens = [tok for tok in re.split(r"[_/\.]+", normalized) if tok]
    return tokens


def _normalize_domain_token(token: str) -> str | None:
    if token in _TOKEN_TO_DOMAIN:
        return _TOKEN_TO_DOMAIN[token]
    return None


def _infer_domain(path: str, imports: list[str]) -> str:
    path_obj = Path(path)
    if "perf" in path_obj.parts:
        return "performance"
    if "security" in path_obj.parts:
        return "security"
    if "api" in path_obj.parts:
        return "api"

    for token in _path_tokens(path):
        normalized = _normalize_domain_token(token)
        if normalized:
            return normalized

    for imp in imports:
        if "venom_core.api.routes." in imp:
            route_token = imp.rsplit(".", 1)[-1]
            normalized = _normalize_domain_token(route_token)
            if normalized:
                return normalized
            return "api"
        for token in re.split(r"[_/\.]+", imp.lower()):
            normalized = _normalize_domain_token(token)
            if normalized:
                return normalized

    return "misc"


def _is_integration(path: str, imports: list[str], text: str) -> bool:
    lower = path.lower()
    if "integration" in lower:
        return True
    if "pytest.mark.integration" in text:
        return True
    return any("integration" in imp for imp in imports)


def _is_perf(path: str, text: str) -> bool:
    lower = path.lower()
    if "/perf/" in lower or "tests/perf/" in lower:
        return True
    return "pytest.mark.performance" in text


def _is_gate(path: str, imports: list[str]) -> bool:
    lower = path.lower()
    script_tokens = (
        "check_new_code_coverage",
        "run_new_code_coverage_gate",
        "resolve_sonar_new_code_tests",
        "update_sonar_new_code_group",
        "test_lane_contracts_guard",
        "architecture_contracts_guard",
        "file_coverage_floor_check",
        "test_intelligence_report",
        "audit_lite_deps",
    )
    if any(token in lower for token in script_tokens):
        return True
    return any("scripts." in imp for imp in imports)


def _infer_test_type(path: str, imports: list[str], text: str) -> str:
    if _is_perf(path, text):
        return "perf"
    if _is_gate(path, imports):
        return "gate"
    if _is_integration(path, imports, text):
        return "integration"
    if "venom_core.api.routes" in text or "/api/" in path.lower():
        return "route_contract"
    if "_service" in path.lower() or "venom_core.services." in text:
        return "service_contract"
    return "unit"


def _infer_intent(test_type: str, legacy_targeted: bool, domain: str) -> str:
    if test_type == "perf":
        return "performance"
    if test_type == "integration":
        return "integration"
    if test_type == "gate":
        return "gate"
    if domain == "security":
        return "security"
    if test_type in {"route_contract", "service_contract"}:
        return "contract"
    if legacy_targeted:
        return "legacy_coverage"
    return "regression"


def _lane_assignment(
    path: str,
    *,
    ci_lite: set[str],
    sonar_new_code: set[str],
    long_lane: set[str],
    heavy_lane: set[str],
) -> tuple[str, list[str]]:
    in_ci = path in ci_lite
    in_new = path in sonar_new_code
    in_release = path in long_lane or path in heavy_lane

    if in_ci and in_new:
        return "ci-lite", ["ci-lite", "new-code", "release"]
    if in_ci:
        return "ci-lite", ["ci-lite", "release"]
    if in_new:
        return "new-code", ["new-code", "ci-lite", "release"]
    if in_release:
        return "release", ["release"]
    return "release", ["release"]


def _default_rationale(test_type: str, primary_lane: str, legacy_targeted: bool) -> str:
    if primary_lane == "ci-lite":
        return "Fast deterministic regression check used by mandatory CI-lite lane."
    if primary_lane == "new-code":
        return "Changed-scope coverage reinforcement for Sonar new-code lane."
    if test_type == "perf":
        return "Performance scenario kept outside fast lanes."
    if test_type == "integration":
        return "Integration-heavy behavior delegated to release lane."
    if legacy_targeted:
        return "Legacy targeted test retained as release fallback until full migration."
    return "Default release-lane regression coverage."


def build_catalog(repo_root: Path) -> dict[str, Any]:
    tests = sorted(
        str(path.relative_to(repo_root)).replace("\\", "/")
        for path in (repo_root / "tests").rglob("test_*.py")
        if path.is_file()
    )

    ci_lite = _read_group(repo_root / "config/pytest-groups/ci-lite.txt")
    sonar_new_code = _read_group(repo_root / "config/pytest-groups/sonar-new-code.txt")
    long_lane = _read_group(repo_root / "config/pytest-groups/long.txt")
    heavy_lane = _read_group(repo_root / "config/pytest-groups/heavy.txt")

    items: list[dict[str, Any]] = []
    for test_path in tests:
        abs_path = repo_root / test_path
        imports = _extract_imports(abs_path)
        try:
            text = abs_path.read_text(encoding="utf-8")
        except Exception:
            text = ""

        domain = _infer_domain(test_path, imports)
        legacy_targeted = bool(LEGACY_TARGETED_RE.search(Path(test_path).name))
        test_type = _infer_test_type(test_path, imports, text)
        intent = _infer_intent(test_type, legacy_targeted, domain)
        primary_lane, allowed_lanes = _lane_assignment(
            test_path,
            ci_lite=ci_lite,
            sonar_new_code=sonar_new_code,
            long_lane=long_lane,
            heavy_lane=heavy_lane,
        )

        items.append(
            {
                "path": test_path,
                "domain": domain if domain in ALLOWED_DOMAINS else "misc",
                "test_type": (test_type if test_type in ALLOWED_TEST_TYPES else "unit"),
                "intent": intent if intent in ALLOWED_INTENTS else "regression",
                "primary_lane": primary_lane,
                "allowed_lanes": allowed_lanes,
                "legacy_targeted": legacy_targeted,
                "rationale": _default_rationale(
                    test_type=test_type,
                    primary_lane=primary_lane,
                    legacy_targeted=legacy_targeted,
                ),
            }
        )

    return {
        "version": 1,
        "meta": {
            "legacy_targeted_pattern": LEGACY_TARGETED_RE.pattern,
            "legacy_targeted_fastlane_max": 17,
        },
        "allowed_domains": ALLOWED_DOMAINS,
        "allowed_test_types": ALLOWED_TEST_TYPES,
        "allowed_intents": ALLOWED_INTENTS,
        "tests": items,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate test catalog.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output catalog path.",
    )
    parser.add_argument(
        "--write",
        type=int,
        choices=(0, 1),
        default=1,
        help="Write output file (1) or print only (0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_catalog(args.repo_root)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if bool(args.write):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(
            f"Generated test catalog with {len(payload.get('tests', []))} tests: {args.output}"
        )
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
