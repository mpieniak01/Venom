#!/usr/bin/env python3
"""Environment audit for dependency hygiene and rebuildable artifacts.

Generates deterministic JSON/Markdown reports and supports a lightweight
policy check mode intended for CI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

REPO_ROOT = Path(__file__).resolve().parents[2]

TARGET_DIRS: tuple[tuple[str, str, str], ...] = (
    (".venv", "deps", "must-keep"),
    ("web-next/node_modules", "deps", "rebuildable"),
    ("web-next/.next", "build", "rebuildable"),
    (".pytest_cache", "cache", "rebuildable"),
    (".mypy_cache", "cache", "rebuildable"),
    (".ruff_cache", "cache", "rebuildable"),
    ("models_cache", "cache", "rebuildable"),
    ("logs", "logs", "rebuildable"),
    ("models", "models", "must-keep"),
    ("data", "data", "user-data"),
)

DEV_HINTS = {
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "pytest-xdist",
    "ruff",
    "mypy",
    "locust",
}

OPTIONAL_HEAVY_HINTS = {
    "onnxruntime",
    "onnxruntime-gpu",
    "onnx",
    "transformers",
    "sentence-transformers",
    "graphrag",
    "lancedb",
    "faster-whisper",
    "piper-tts",
    "opencv-python-headless",
    "timm",
    "torch",
    "torchvision",
    "accelerate",
}

CRITICAL_SHARED_PINS = {
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic-settings",
    "python-dotenv",
    "python-multipart",
    "httpx",
    "aiofiles",
    "loguru",
    "colorama",
    "tqdm",
    "psutil",
    "gitpython",
    "networkx",
    "redis",
    "websockets",
    "pytest",
    "pytest-asyncio",
    "pytest-xdist",
}

NODE_SCRIPT_ONLY = {
    "typescript",
    "tsx",
    "eslint",
    "eslint-config-next",
    "playwright",
    "@playwright/test",
    "@types/node",
    "@types/react",
    "@types/react-dom",
    "@tailwindcss/postcss",
    "tailwindcss",
    "tailwindcss-animate",
}

IMPORT_RE = re.compile(
    r"(?:import\s+(?:type\s+)?(?:[^\"'\n]+?\s+from\s+)?|require\()\s*['\"]([^'\"\n]+)['\"]"
)
IMPORT_DYNAMIC_RE = re.compile(r"import\(\s*['\"]([^'\"\n]+)['\"]\s*\)")

REQ_RE = re.compile(r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?\s*([!<>=~]{1,2}[^;\s]+)?")


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def _to_pkg_key(name: str) -> str:
    return name.lower().replace("_", "-")


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    proc = _run(["du", "-sb", str(path)])
    if proc.returncode == 0 and proc.stdout.strip():
        first = proc.stdout.split()[0]
        try:
            return int(first)
        except ValueError:
            pass

    total = 0
    for root, _, files in os.walk(path, followlinks=False):
        for f in files:
            p = Path(root) / f
            try:
                if p.is_symlink():
                    continue
                total += p.stat().st_size
            except OSError:
                continue
    return total


def _parse_requirements(path: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return entries

    for idx, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = REQ_RE.match(line)
        if not m:
            continue
        name = _to_pkg_key(m.group(1))
        spec = (m.group(3) or "").strip() or "unbounded"
        entries[name] = {
            "name": m.group(1),
            "spec": spec,
            "line": idx,
            "raw": raw_line.strip(),
        }
    return entries


def _classify_python(
    full: dict[str, dict[str, Any]], lite: dict[str, dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    required_runtime: list[dict[str, Any]] = []
    required_dev: list[dict[str, Any]] = []
    optional_heavy: list[dict[str, Any]] = []
    candidate_remove: list[dict[str, Any]] = []

    all_names = sorted(set(full) | set(lite))
    for name in all_names:
        in_full = name in full
        in_lite = name in lite
        spec_full = full.get(name, {}).get("spec")
        spec_lite = lite.get(name, {}).get("spec")

        item = {
            "package": name,
            "in_requirements": in_full,
            "in_requirements_ci_lite": in_lite,
            "spec_requirements": spec_full,
            "spec_requirements_ci_lite": spec_lite,
        }

        if name in OPTIONAL_HEAVY_HINTS or (in_full and not in_lite):
            optional_heavy.append(item)
        elif name in DEV_HINTS or name.startswith("types-"):
            required_dev.append(item)
        elif in_lite:
            required_runtime.append(item)
        else:
            candidate_remove.append(item)

        if in_lite and not in_full:
            candidate_remove.append(
                {
                    "package": name,
                    "reason": "present only in requirements-ci-lite",
                    "spec_requirements": spec_full,
                    "spec_requirements_ci_lite": spec_lite,
                }
            )

    return {
        "required-runtime": sorted(required_runtime, key=lambda x: x["package"]),
        "required-dev": sorted(required_dev, key=lambda x: x["package"]),
        "optional-heavy": sorted(optional_heavy, key=lambda x: x["package"]),
        "candidate-remove": sorted(candidate_remove, key=lambda x: x["package"]),
    }


def _python_pin_conflicts(
    full: dict[str, dict[str, Any]], lite: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    def _is_compatible(spec_a: str, spec_b: str) -> bool:
        if spec_a == spec_b:
            return True
        if spec_a == "unbounded" or spec_b == "unbounded":
            return True

        def _extract_exact(spec: str) -> str | None:
            if not spec.startswith("=="):
                return None
            candidate = spec[2:].strip()
            if not candidate or "*" in candidate:
                return None
            return candidate

        exact_a = _extract_exact(spec_a)
        exact_b = _extract_exact(spec_b)
        try:
            if exact_a is not None:
                return Version(exact_a) in SpecifierSet(spec_b)
            if exact_b is not None:
                return Version(exact_b) in SpecifierSet(spec_a)
        except (InvalidSpecifier, InvalidVersion):
            return False
        return False

    conflicts: list[dict[str, Any]] = []
    for name in sorted(set(full) & set(lite)):
        s1 = full[name]["spec"]
        s2 = lite[name]["spec"]
        if not _is_compatible(s1, s2):
            conflicts.append(
                {
                    "package": name,
                    "requirements": s1,
                    "requirements_ci_lite": s2,
                }
            )
    return conflicts


def _parse_node_lock(lock_path: Path) -> dict[str, set[str]]:
    if not lock_path.exists():
        return {}
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = data.get("packages", {})
    versions: dict[str, set[str]] = {}

    for pkg_path, pkg_data in packages.items():
        if not pkg_path.startswith("node_modules/"):
            continue
        parts = pkg_path.split("/")
        if len(parts) < 2:
            continue
        if parts[1].startswith("@") and len(parts) >= 3:
            name = f"{parts[1]}/{parts[2]}"
        else:
            name = parts[1]
        ver = str(pkg_data.get("version", "unknown"))
        versions.setdefault(name, set()).add(ver)

    return versions


def _normalize_import_root(import_name: str) -> str:
    if import_name.startswith("."):
        return ""
    if import_name.startswith("@"):
        parts = import_name.split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return import_name
    return import_name.split("/")[0]


def _collect_web_imports(web_dir: Path) -> set[str]:
    used: set[str] = set()
    if not web_dir.exists():
        return used
    for ext in ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs"):
        for path in web_dir.rglob(ext):
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in IMPORT_RE.finditer(text):
                root = _normalize_import_root(match.group(1).strip())
                if root:
                    used.add(root)
            for match in IMPORT_DYNAMIC_RE.finditer(text):
                root = _normalize_import_root(match.group(1).strip())
                if root:
                    used.add(root)

    next_config = web_dir / "next.config.ts"
    if next_config.exists():
        text = next_config.read_text(encoding="utf-8", errors="ignore")
        # optimizePackageImports is a valid usage signal even when no direct import exists.
        match = re.search(r"optimizePackageImports\s*:\s*\[([^\]]*)\]", text, re.DOTALL)
        if match:
            for token in re.findall(r"['\"]([^'\"]+)['\"]", match.group(1)):
                root = _normalize_import_root(token.strip())
                if root:
                    used.add(root)
    return used


def _node_audit(root: Path) -> dict[str, Any]:
    package_json_path = root / "web-next" / "package.json"
    lock_path = root / "web-next" / "package-lock.json"
    if not package_json_path.exists():
        return {
            "direct_dependencies": {},
            "transitive_version_duplicates": [],
            "heuristic_unused_direct_dependencies": [],
            "policy_warnings": ["web-next/package.json not found"],
        }

    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    direct_deps = package_json.get("dependencies", {})
    dev_deps = package_json.get("devDependencies", {})

    lock_versions = _parse_node_lock(lock_path)
    duplicates = [
        {"package": pkg, "versions": sorted(versions)}
        for pkg, versions in sorted(lock_versions.items())
        if len(versions) > 1
    ]

    used_imports = _collect_web_imports(root / "web-next")
    direct_all = set(direct_deps) | set(dev_deps)
    unused = sorted(
        dep
        for dep in direct_all
        if dep not in used_imports
        and dep not in NODE_SCRIPT_ONLY
        and dep not in {"next", "react", "react-dom"}
    )

    warnings: list[str] = []
    if lock_path.exists():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        root_pkg = lock.get("packages", {}).get("", {})
        root_deps = root_pkg.get("dependencies", {})
        root_dev_deps = root_pkg.get("devDependencies", {})
        if root_deps != direct_deps:
            warnings.append("package-lock root dependencies differ from package.json")
        if root_dev_deps != dev_deps:
            warnings.append(
                "package-lock root devDependencies differ from package.json"
            )
    else:
        warnings.append("package-lock.json not found")

    return {
        "direct_dependencies": {
            "dependencies": direct_deps,
            "devDependencies": dev_deps,
        },
        "transitive_version_duplicates": duplicates,
        "heuristic_unused_direct_dependencies": unused,
        "policy_warnings": warnings,
    }


def _docker_report() -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "summary": {},
        "venom_images": [],
        "dangling": {},
    }

    info = _run(["docker", "info"])
    if info.returncode != 0:
        result["error"] = (info.stderr or info.stdout).strip() or "docker unavailable"
        return result

    result["available"] = True
    df = _run(["docker", "system", "df", "--format", "{{json .}}"])
    if df.returncode == 0:
        rows = []
        for line in df.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        result["summary"] = {
            row.get("Type", f"type_{idx}"): row for idx, row in enumerate(rows)
        }

    images = _run(
        [
            "docker",
            "images",
            "--format",
            "{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}",
        ]
    )
    if images.returncode == 0:
        for line in images.stdout.splitlines():
            if "venom" in line.lower():
                result["venom_images"].append(line.strip())

    dangling_images = _run(["docker", "images", "-f", "dangling=true", "-q"])
    dangling_volumes = _run(["docker", "volume", "ls", "-qf", "dangling=true"])
    exited = _run(["docker", "ps", "-a", "--filter", "status=exited", "-q"])

    result["dangling"] = {
        "images": len([x for x in dangling_images.stdout.splitlines() if x.strip()])
        if dangling_images.returncode == 0
        else None,
        "volumes": len([x for x in dangling_volumes.stdout.splitlines() if x.strip()])
        if dangling_volumes.returncode == 0
        else None,
        "exited_containers": len([x for x in exited.stdout.splitlines() if x.strip()])
        if exited.returncode == 0
        else None,
    }
    return result


def _artifact_report(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for rel, kind, classification in TARGET_DIRS:
        abs_path = root / rel
        items.append(
            {
                "path": rel,
                "absolute_path": str(abs_path),
                "size_bytes": _dir_size_bytes(abs_path),
                "kind": kind,
                "classification": classification,
                "exists": abs_path.exists(),
            }
        )
    return sorted(items, key=lambda x: x["size_bytes"], reverse=True)


def _human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    val = float(size)
    for unit in units:
        if val < 1024.0 or unit == units[-1]:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{size} B"


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Dev Environment Audit")
    lines.append("")
    lines.append(f"Generated at: `{report['generated_at']}`")
    lines.append("")

    lines.append("## Artifact Footprint")
    lines.append("")
    lines.append("| Path | Size | Kind | Classification |")
    lines.append("|---|---:|---|---|")
    for item in report["artifacts"]["directories"]:
        lines.append(
            f"| `{item['path']}` | {_human_size(item['size_bytes'])} | {item['kind']} | {item['classification']} |"
        )

    lines.append("")
    lines.append("## Python Dependencies")
    lines.append("")
    conflicts = report["dependencies"]["python"]["pin_conflicts"]
    if conflicts:
        lines.append("### Pin conflicts between requirements files")
        for c in conflicts:
            lines.append(
                f"- `{c['package']}`: requirements=`{c['requirements']}` vs ci-lite=`{c['requirements_ci_lite']}`"
            )
    else:
        lines.append("No pin conflicts detected between shared Python packages.")

    lines.append("")
    lines.append("## Node Dependencies")
    lines.append("")
    dups = report["dependencies"]["node"]["transitive_version_duplicates"]
    lines.append(f"- Transitive duplicates: **{len(dups)}**")
    unused = report["dependencies"]["node"]["heuristic_unused_direct_dependencies"]
    lines.append(f"- Heuristic unused direct dependencies: **{len(unused)}**")
    for dep in unused[:20]:
        lines.append(f"  - `{dep}`")

    lines.append("")
    lines.append("## Docker")
    lines.append("")
    docker = report["docker"]
    lines.append(f"- Available: `{docker['available']}`")
    if docker.get("error"):
        lines.append(f"- Error: `{docker['error']}`")
    else:
        dangling = docker.get("dangling", {})
        lines.append(f"- Dangling images: `{dangling.get('images')}`")
        lines.append(f"- Dangling volumes: `{dangling.get('volumes')}`")
        lines.append(f"- Exited containers: `{dangling.get('exited_containers')}`")

    return "\n".join(lines) + "\n"


def _build_report(root: Path) -> dict[str, Any]:
    req = _parse_requirements(root / "requirements.txt")
    req_lite = _parse_requirements(root / "requirements-ci-lite.txt")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "artifacts": {
            "directories": _artifact_report(root),
        },
        "dependencies": {
            "python": {
                "requirements": req,
                "requirements_ci_lite": req_lite,
                "classification": _classify_python(req, req_lite),
                "pin_conflicts": _python_pin_conflicts(req, req_lite),
            },
            "node": _node_audit(root),
        },
        "docker": _docker_report(),
    }
    return report


def _ci_check(report: dict[str, Any]) -> int:
    errors: list[str] = []

    conflicts = report["dependencies"]["python"]["pin_conflicts"]
    for conflict in conflicts:
        if conflict["package"] in CRITICAL_SHARED_PINS:
            errors.append(
                f"critical pin mismatch: {conflict['package']} ({conflict['requirements']} vs {conflict['requirements_ci_lite']})"
            )

    warnings = report["dependencies"]["node"]["policy_warnings"]
    if warnings:
        errors.extend(f"node policy warning: {w}" for w in warnings)

    if errors:
        print("❌ Dependency policy check failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("✅ Dependency policy check passed.")
    return 0


def _default_output_paths(logs_dir: Path) -> tuple[Path, Path]:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return (
        logs_dir / f"diag-env-{ts}.json",
        logs_dir / f"diag-env-{ts}.md",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit dev environment dependencies/artifacts"
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root")
    parser.add_argument(
        "--output-json", type=Path, default=None, help="Output JSON path"
    )
    parser.add_argument(
        "--output-md", type=Path, default=None, help="Output Markdown path"
    )
    parser.add_argument(
        "--stdout-json", action="store_true", help="Print JSON to stdout"
    )
    parser.add_argument(
        "--ci-check", action="store_true", help="Run lightweight policy validation"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    report = _build_report(root)

    if args.ci_check:
        return _ci_check(report)

    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_json, out_md = _default_output_paths(logs_dir)
    if args.output_json:
        out_json = args.output_json
    if args.output_md:
        out_md = args.output_md

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    out_md.write_text(_build_markdown(report), encoding="utf-8")

    print(f"✅ Env audit written: {out_json}")
    print(f"✅ Env audit summary: {out_md}")

    if args.stdout_json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
