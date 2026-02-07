"""Moduł: routes/system_storage - Endpointy monitoringu storage."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

from fastapi import APIRouter, HTTPException

from venom_core.utils.helpers import get_utc_now
from venom_core.utils.logger import get_logger
from venom_core.utils.ttl_cache import TTLCache

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

STORAGE_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("llm_models", "models", "models"),
    ("llm_cache", "models_cache", "cache"),
    ("logs", "logs", "logs"),
    ("timelines", "data/timelines", "data"),
    ("memory", "data/memory", "data"),
    ("audio", "data/audio", "data"),
    ("learning", "data/learning", "data"),
    ("mcp_repos", "workspace/venom_core/skills/mcp/_repos", "mcp"),
    ("mcp_custom", "workspace/venom_core/skills/custom", "mcp"),
    ("next_build", "web-next/.next", "build"),
    ("node_modules", "web-next/node_modules", "deps"),
)

CODE_SIZE_SKIP_TOP: set[str] = {
    "models",
    "models_cache",
    "logs",
    "data",
    "web-next/.next",
    "web-next/node_modules",
    ".git",
    "node_modules",
    "htmlcov",
}


def _detect_project_root() -> Path:
    """
    Wykrywa root projektu.

    Kolejność:
    1. katalog nadrzędny zawierający pyproject.toml,
    2. /app (runtime Dockera),
    3. bieżący katalog roboczy.
    """
    this_file = Path(__file__).resolve()
    for parent in this_file.parents:
        if (parent / "pyproject.toml").exists():
            return parent

    docker_app = Path("/app")
    if docker_app.exists():
        return docker_app

    return Path.cwd()


PROJECT_ROOT = _detect_project_root()
_storage_cache = TTLCache[dict](ttl_seconds=3600.0)  # Zwiększony TTL do 1h


@router.get("/system/storage")
async def get_storage_snapshot():
    """
    Zwraca snapshot użycia dysku oraz największe katalogi (whitelist).
    """
    try:
        cached = _storage_cache.get()
        if cached is not None:
            return cached

        # Wykonujemy blokujące operacje w osobnym wątku, aby nie blokować event loopa
        res = await asyncio.to_thread(_get_storage_data_sync)

        _storage_cache.set(res)
        return res
    except Exception as e:
        logger.exception("Błąd podczas pobierania snapshotu storage")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


def _item_payload(
    name: str, path: Path, size_bytes: int, kind: str
) -> dict[str, int | str]:
    """Tworzy spójny payload itemu storage."""
    return {
        "name": name,
        "path": str(path),
        "size_bytes": size_bytes,
        "kind": kind,
    }


def _get_storage_data_sync() -> dict:
    """Synchronizowana wersja zbierania danych o storage."""
    disk_physical_mount = Path("/usr/lib/wsl/drivers")
    if not disk_physical_mount.exists():
        disk_physical_mount = PROJECT_ROOT

    # shutil.disk_usage przyjmuje str lub Path, ale niektóre wersje wolą str
    total_physical, used_physical, free_physical = shutil.disk_usage(
        str(disk_physical_mount)
    )

    disk_root_mount = Path("/")
    total_root, used_root, free_root = shutil.disk_usage(str(disk_root_mount))

    items = []
    total_items_size = 0

    # 1. Liczymy base entries
    for name, rel_path, kind in STORAGE_ENTRIES:
        path = PROJECT_ROOT / rel_path
        fast_size = _dir_size_bytes_fast(path, timeout_sec=2.0)
        if fast_size is None and path.exists():
            try:
                # Fallback do wolniejszego ale dokładniejszego walk
                size_bytes = _dir_size_bytes(path)
            except Exception as exc:
                logger.warning("Błąd liczenia %s: %s", rel_path, exc)
                size_bytes = 0
        else:
            # 0 to legalny rozmiar katalogu - fallback tylko przy błędzie fast-path.
            size_bytes = fast_size or 0

        items.append(
            _item_payload(name=name, path=path, size_bytes=size_bytes, kind=kind)
        )
        total_items_size += size_bytes

    # 2. Specyficzne traktowanie "dreaming" wewnątrz timelines
    dreams_size = 0
    timelines_path = PROJECT_ROOT / "data/timelines"
    if timelines_path.exists():
        try:
            for child in timelines_path.iterdir():
                if child.is_dir() and child.name.startswith("dream_"):
                    dream_size = _dir_size_bytes_fast(child, timeout_sec=1.0)
                    dreams_size += dream_size or 0
        except Exception as e:
            logger.warning(f"Błąd podczas liczenia rozmiaru snów: {e}")

    # Aktualizujemy wpisy o sny
    final_items = []
    for item in items:
        if item["name"] == "timelines" and dreams_size > 0:
            # Nie odejmujemy jeśli to by miało dać < 0
            size_val = item.get("size_bytes", 0)
            current_size = int(size_val) if isinstance(size_val, (int, float)) else 0
            item["size_bytes"] = max(0, current_size - dreams_size)
            item["name"] = "timelines_user"
        final_items.append(item)

    if dreams_size > 0:
        final_items.append(
            _item_payload(
                name="dreaming",
                path=timelines_path / "dream_*",
                size_bytes=dreams_size,
                kind="data",
            )
        )

    # 3. Project Root & Code Only
    final_items.insert(
        0,
        _item_payload(
            name="project_root",
            path=PROJECT_ROOT,
            size_bytes=total_items_size,
            kind="project",
        ),
    )

    code_size = _dir_size_code(PROJECT_ROOT, skip_top=CODE_SIZE_SKIP_TOP)
    final_items.insert(
        1,
        _item_payload(
            name="code_only", path=PROJECT_ROOT, size_bytes=code_size, kind="code"
        ),
    )

    final_items.sort(key=lambda x: cast(int, x.get("size_bytes", 0) or 0), reverse=True)

    return {
        "status": "success",
        "refreshed_at": get_utc_now().isoformat(),
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
        "items": final_items,
    }


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


def _dir_size_bytes_fast(path: Path, timeout_sec: float = 3.0) -> int | None:
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
            return None
        output = result.stdout.split()
        if not output:
            return None
        return int(output[0])
    except Exception:
        return None


def _dir_size_code(path: Path, skip_top: set[str] | None = None) -> int:
    """Policz rozmiar kodu z pominięciem katalogów i danych.

    Wspiera dwa typy wpisów w ``skip_top``:
    - nazwa katalogu (np. ``node_modules``) => pomijana globalnie na każdym poziomie,
    - ścieżka względna (np. ``web-next/.next``) => pomijana tylko dla tej gałęzi.
    """
    if not path.exists():
        return 0
    skip_top = skip_top or set()
    global_skip_names = {item for item in skip_top if "/" not in item}
    relative_skip_paths = {item.strip("/") for item in skip_top if "/" in item}
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        root_path = Path(root)
        rel_root = root_path.relative_to(path).as_posix()
        if rel_root == ".":
            rel_root = ""
        filtered_dirs = []
        for d in dirs:
            rel_dir = f"{rel_root}/{d}" if rel_root else d
            if d in global_skip_names:
                continue
            if rel_dir in relative_skip_paths:
                continue
            filtered_dirs.append(d)
        dirs[:] = filtered_dirs
        for name in files:
            file_path = root_path / name
            try:
                if file_path.is_symlink():
                    continue
                total += file_path.stat().st_size
            except OSError:
                continue
    return total
