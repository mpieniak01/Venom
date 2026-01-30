"""Moduł: routes/system_storage - Endpointy monitoringu storage."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from venom_core.utils.logger import get_logger
from venom_core.utils.ttl_cache import TTLCache

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_storage_cache = TTLCache[dict](ttl_seconds=60.0)


@router.get("/system/storage")
async def get_storage_snapshot():
    """
    Zwraca snapshot użycia dysku oraz największe katalogi (whitelist).
    """
    try:
        cached = _storage_cache.get()
        if cached is not None:
            return cached

        disk_physical_mount = Path("/usr/lib/wsl/drivers")
        if not disk_physical_mount.exists():
            disk_physical_mount = PROJECT_ROOT
        total_physical, used_physical, free_physical = shutil.disk_usage(
            disk_physical_mount
        )

        disk_root_mount = Path("/")
        total_root, used_root, free_root = shutil.disk_usage(disk_root_mount)
        entries = [
            {"name": "Modele LLM", "path": "models", "kind": "models"},
            {"name": "Modele cache", "path": "models_cache", "kind": "cache"},
            {"name": "Logi", "path": "logs", "kind": "logs"},
            {"name": "Dane: timelines", "path": "data/timelines", "kind": "data"},
            {"name": "Dane: memory", "path": "data/memory", "kind": "data"},
            {"name": "Dane: audio", "path": "data/audio", "kind": "data"},
            {"name": "Dane: learning", "path": "data/learning", "kind": "data"},
            {
                "name": "MCP: Repozytoria narzędzi",
                "path": "workspace/venom_core/skills/mcp/_repos",
                "kind": "mcp",
            },
            {
                "name": "MCP: Wygenerowane skille",
                "path": "workspace/venom_core/skills/custom",
                "kind": "mcp",
            },
            {
                "name": "Build: web-next/.next",
                "path": "web-next/.next",
                "kind": "build",
            },
            {
                "name": "Deps: web-next/node_modules",
                "path": "web-next/node_modules",
                "kind": "deps",
            },
        ]
        sizes = []
        for entry in entries:
            size = _dir_size_bytes_fast(PROJECT_ROOT / entry["path"], timeout_sec=5.0)
            if size == 0:
                try:
                    size = _dir_size_bytes(PROJECT_ROOT / entry["path"])
                except Exception as exc:
                    logger.warning(
                        "Nie udało się policzyć rozmiaru %s: %s", entry["path"], exc
                    )
                    size = 0
            sizes.append(size)

        dreams_size = 0
        timelines_path = PROJECT_ROOT / "data/timelines"
        if timelines_path.exists():
            try:
                for child in timelines_path.iterdir():
                    if child.is_dir() and child.name.startswith("dream_"):
                        dreams_size += _dir_size_bytes_fast(child)
            except Exception as e:
                logger.warning(f"Błąd podczas liczenia rozmiaru snów: {e}")

        items = []
        total_items_size = 0
        for entry, size in zip(entries, sizes):
            if isinstance(size, Exception):
                logger.warning(
                    "Nie udało się policzyć rozmiaru %s: %s", entry["path"], size
                )
                size_bytes = 0
            else:
                size_bytes = size

            if entry["name"] == "Dane: timelines" and dreams_size > 0:
                size_bytes = max(0, size_bytes - dreams_size)
                entry["name"] = "Dane: timelines (user/core)"

            total_items_size += size_bytes
            items.append(
                {
                    "name": entry["name"],
                    "path": str(PROJECT_ROOT / entry["path"]),
                    "size_bytes": size_bytes,
                    "kind": entry["kind"],
                }
            )

        if dreams_size > 0:
            total_items_size += dreams_size
            items.append(
                {
                    "name": "Dane: dreaming (timelines)",
                    "path": str(timelines_path / "dream_*"),
                    "size_bytes": dreams_size,
                    "kind": "data",
                }
            )

        items.insert(
            0,
            {
                "name": "Katalog venom (repo)",
                "path": str(PROJECT_ROOT),
                "size_bytes": total_items_size,
                "kind": "project",
            },
        )
        code_size = _dir_size_code(
            PROJECT_ROOT,
            skip_top={
                "models",
                "models_cache",
                "logs",
                "data",
                "web-next/.next",
                "web-next/node_modules",
                ".git",
                "node_modules",
                "htmlcov",
            },
        )
        items.insert(
            1,
            {
                "name": "Kod (repo, bez modeli/deps/build/logs/data)",
                "path": str(PROJECT_ROOT),
                "size_bytes": code_size,
                "kind": "code",
            },
        )
        items.sort(key=lambda item: item["size_bytes"], reverse=True)
        res = {
            "status": "success",
            "refreshed_at": datetime.now().isoformat(),
            "disk": {
                "total_bytes": total_physical,
                "used_bytes": used_physical,
                "free_bytes": free_physical,
                "mount": str(disk_physical_mount),
            },
            "disk_root": {
                "total_bytes": total_root,
                "used_bytes": used_root,
                "free_bytes": free_root,
                "mount": str(disk_root_mount),
            },
            "items": items,
        }
        _storage_cache.set(res)
        return res
    except Exception as e:
        logger.exception("Błąd podczas pobierania snapshotu storage")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


def _dir_size_bytes(path: Path) -> int:
    """Suma rozmiarów plików w katalogu (bez podążania za symlinkami)."""
    if not path.exists():
        return 0
    total = 0
    for root, _, files in os.walk(path, followlinks=False):
        for name in files:
            file_path = os.path.join(root, name)
            try:
                if os.path.islink(file_path):
                    continue
                total += os.path.getsize(file_path)
            except OSError:
                continue
    return total


def _dir_size_bytes_fast(path: Path, timeout_sec: float = 3.0) -> int:
    """
    Szybki rozmiar katalogu przy użyciu `du -sb` z timeoutem.
    """
    if not path.exists():
        return 0
    try:
        result = subprocess.run(
            ["du", "-sb", str(path)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        if result.returncode != 0:
            return 0
        output = result.stdout.split()
        if not output:
            return 0
        return int(output[0])
    except Exception:
        return 0


def _dir_size_code(path: Path, skip_top: set[str] | None = None) -> int:
    """Policz rozmiar kodu z pominięciem katalogów i danych."""
    if not path.exists():
        return 0
    skip_top = skip_top or set()
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        root_path = Path(root)
        if root_path == path:
            dirs[:] = [d for d in dirs if d not in skip_top]
        for name in files:
            file_path = root_path / name
            try:
                if file_path.is_symlink():
                    continue
                total += file_path.stat().st_size
            except OSError:
                continue
    return total
