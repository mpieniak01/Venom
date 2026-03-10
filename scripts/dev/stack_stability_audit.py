#!/usr/bin/env python3
"""Manual stack stability diagnostics for web/API runtime."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PidStatus:
    pid_file: str
    pid: int | None
    running: bool
    process_name: str | None
    error: str | None = None


def _read_pid_file(path: Path) -> tuple[int | None, str | None]:
    if not path.exists():
        return None, None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None, "empty_pid_file"
    if not raw.isdigit():
        return None, "invalid_pid_value"
    return int(raw), None


def _process_name(pid: int) -> str | None:
    comm = Path(f"/proc/{pid}/comm")
    if not comm.exists():
        return None
    try:
        return comm.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _pid_status(root: Path, pid_file: str) -> PidStatus:
    path = root / pid_file
    pid, err = _read_pid_file(path)
    if pid is None:
        return PidStatus(
            pid_file=pid_file, pid=None, running=False, process_name=None, error=err
        )
    running = os.path.exists(f"/proc/{pid}")
    return PidStatus(
        pid_file=pid_file,
        pid=pid,
        running=running,
        process_name=_process_name(pid) if running else None,
        error=err,
    )


def _port_pids(root: Path, port: int) -> list[int]:
    script = root / "scripts" / "dev" / "port_pids.sh"
    if not script.exists():
        return []
    result = subprocess.run(
        [str(script), str(port)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        text = line.strip()
        if text.isdigit():
            pids.append(int(text))
    return sorted(set(pids))


def _pid_and_descendant_pids(root_pid: int) -> set[int]:
    """Return root pid and all descendants.

    Primary strategy: recursive `pgrep -P`.
    Fallback strategy: /proc parent map.
    """
    descendants: set[int] = {root_pid}
    queue = [root_pid]
    while queue:
        parent = queue.pop()
        try:
            result = subprocess.run(
                ["pgrep", "-P", str(parent)],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            result = None
        if result is not None and result.returncode in (0, 1):
            for line in result.stdout.splitlines():
                text = line.strip()
                if not text.isdigit():
                    continue
                child = int(text)
                if child not in descendants:
                    descendants.add(child)
                    queue.append(child)

    if len(descendants) > 1:
        return descendants

    parent_to_children: dict[int, set[int]] = {}
    try:
        proc_entries = list(Path("/proc").iterdir())
    except OSError:
        return descendants
    for proc_entry in proc_entries:
        if not proc_entry.name.isdigit():
            continue
        stat_path = proc_entry / "stat"
        try:
            payload = stat_path.read_text(encoding="utf-8")
        except OSError:
            continue
        parts = payload.split()
        if len(parts) < 5:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[3])
        except ValueError:
            continue
        parent_to_children.setdefault(ppid, set()).add(pid)

    queue = [root_pid]
    while queue:
        parent = queue.pop()
        for child in parent_to_children.get(parent, set()):
            if child not in descendants:
                descendants.add(child)
                queue.append(child)
    return descendants


def _pid_group_id(pid: int) -> int | None:
    try:
        result = subprocess.run(
            ["ps", "-o", "pgid=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return int(text) if text.isdigit() else None


def _pid_context_matches_port(pid: int, port_pids: list[int]) -> bool:
    if not port_pids:
        return False
    if pid in port_pids:
        return True
    descendants = _pid_and_descendant_pids(pid)
    if descendants.intersection(port_pids):
        return True
    root_pgid = _pid_group_id(pid)
    if root_pgid is None:
        return False
    for port_pid in port_pids:
        if _pid_group_id(port_pid) == root_pgid:
            return True
    return False


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _resolve_optional_modules(root: Path, env_values: dict[str, str]) -> dict[str, Any]:
    raw = env_values.get("API_OPTIONAL_MODULES", "")
    manifests: list[dict[str, Any]] = []
    for item in [part.strip() for part in raw.split(",") if part.strip()]:
        if not item.startswith("manifest:"):
            manifests.append(
                {"entry": item, "valid": False, "reason": "unsupported_entry"}
            )
            continue
        manifest_path = Path(item[len("manifest:") :]).expanduser()
        if not manifest_path.is_absolute():
            manifest_path = (root / manifest_path).resolve()
        exists = manifest_path.exists()
        manifests.append(
            {
                "entry": item,
                "path": str(manifest_path),
                "exists": exists,
                "valid": exists,
                "reason": None if exists else "missing_manifest",
            }
        )
    return {"configured": raw, "manifests": manifests}


def run_audit(
    root: Path, env_file: Path, backend_port: int, web_port: int
) -> dict[str, Any]:
    api = _pid_status(root, ".venom.pid")
    web = _pid_status(root, ".web-next.pid")
    api_port_pids = _port_pids(root, backend_port)
    web_port_pids = _port_pids(root, web_port)
    env_values = _load_env_file(env_file)
    optional_modules = _resolve_optional_modules(root, env_values)

    issues: list[str] = []
    if api.pid is not None and not api.running:
        issues.append("api_pid_file_stale")
    if web.pid is not None and not web.running:
        issues.append("web_pid_file_stale")
    if api.running and api.pid is not None and api_port_pids:
        if not _pid_context_matches_port(api.pid, api_port_pids):
            issues.append("api_pid_not_bound_to_expected_port")
    if web.running and web.pid is not None and web_port_pids:
        if not _pid_context_matches_port(web.pid, web_port_pids):
            issues.append("web_pid_not_bound_to_expected_port")
    if not api.running and api_port_pids:
        issues.append("api_port_busy_without_pid_file_process")
    if not web.running and web_port_pids:
        issues.append("web_port_busy_without_pid_file_process")
    for manifest in optional_modules["manifests"]:
        if not manifest.get("valid", False):
            issues.append(f"optional_module_invalid:{manifest.get('entry', '')}")

    return {
        "root": str(root),
        "env_file": str(env_file),
        "api": asdict(api),
        "web": asdict(web),
        "api_port": {"port": backend_port, "pids": api_port_pids},
        "web_port": {"port": web_port, "pids": web_port_pids},
        "optional_modules": optional_modules,
        "issues": issues,
        "ok": len(issues) == 0,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual stack stability diagnostics for web/API."
    )
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument(
        "--env-file", default=".env.dev", help="Environment file to inspect."
    )
    parser.add_argument(
        "--backend-port", type=int, default=8000, help="Expected API port."
    )
    parser.add_argument("--web-port", type=int, default=3000, help="Expected web port.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Exit with code 1 when issues are detected.",
    )
    return parser.parse_args()


def _print_text(report: dict[str, Any]) -> None:
    print("Stack stability audit")
    print(f"- env_file: {report['env_file']}")
    print(f"- api pid: {report['api']['pid']} running={report['api']['running']}")
    print(f"- web pid: {report['web']['pid']} running={report['web']['running']}")
    print(f"- api port pids: {report['api_port']['pids']}")
    print(f"- web port pids: {report['web_port']['pids']}")
    manifests = report["optional_modules"]["manifests"]
    print(f"- optional modules manifests: {len(manifests)}")
    if manifests:
        for item in manifests:
            print(f"  * {item.get('entry')} => valid={item.get('valid')}")
    if report["issues"]:
        print("- issues:")
        for issue in report["issues"]:
            print(f"  * {issue}")
    else:
        print("- issues: none")


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (root / env_file).resolve()
    report = run_audit(
        root=root,
        env_file=env_file,
        backend_port=args.backend_port,
        web_port=args.web_port,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        _print_text(report)
    if args.fail_on_issues and report["issues"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
