import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _dir_size_bytes(path: Path) -> int:
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
    except Exception as e:
        print(f"Błąd fast dla {path}: {e}")
        return 0


def _dir_size_code(path: Path, skip_top: set[str] | None = None) -> int:
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


def _disk_usage_with_fallback() -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Zwraca usage dla mounta fizycznego i root."""
    disk_physical_mount = Path("/usr/lib/wsl/drivers")
    if not disk_physical_mount.exists():
        disk_physical_mount = PROJECT_ROOT
    physical = shutil.disk_usage(disk_physical_mount)
    root = shutil.disk_usage(Path("/"))
    return physical, root


def _storage_entries() -> list[dict[str, str]]:
    return [
        {"name": "llm_models", "path": "models", "kind": "models"},
        {"name": "llm_cache", "path": "models_cache", "kind": "cache"},
        {"name": "logs", "path": "logs", "kind": "logs"},
        {"name": "timelines", "path": "data/timelines", "kind": "data"},
        {"name": "memory", "path": "data/memory", "kind": "data"},
        {"name": "audio", "path": "data/audio", "kind": "data"},
        {"name": "learning", "path": "data/learning", "kind": "data"},
        {
            "name": "mcp_repos",
            "path": "workspace/venom_core/skills/mcp/_repos",
            "kind": "mcp",
        },
        {
            "name": "mcp_custom",
            "path": "workspace/venom_core/skills/custom",
            "kind": "mcp",
        },
        {"name": "next_build", "path": "web-next/.next", "kind": "build"},
        {"name": "node_modules", "path": "web-next/node_modules", "kind": "deps"},
    ]


def _measure_entry_sizes(entries: list[dict[str, str]]) -> list[int]:
    sizes: list[int] = []
    for entry in entries:
        print(f"Liczenie {entry['path']}...")
        size = _dir_size_bytes_fast(PROJECT_ROOT / entry["path"], timeout_sec=5.0)
        if size == 0:
            print(f"Fallback dla {entry['path']}...")
            size = _dir_size_bytes(PROJECT_ROOT / entry["path"])
        sizes.append(size)
    return sizes


def _compute_dreams_size(timelines_path: Path) -> int:
    dreams_size = 0
    if timelines_path.exists():
        for child in timelines_path.iterdir():
            if child.is_dir() and child.name.startswith("dream_"):
                dreams_size += _dir_size_bytes_fast(child)
    return dreams_size


def _build_items(
    entries: list[dict[str, str]], sizes: list[int], dreams_size: int
) -> tuple[list[dict[str, str | int]], int]:
    items: list[dict[str, str | int]] = []
    total_items_size = 0
    for entry, size in zip(entries, sizes):
        size_bytes = size
        item_name = entry["name"]
        if item_name == "timelines" and dreams_size > 0:
            size_bytes = max(0, size_bytes - dreams_size)
            item_name = "timelines_user"
        total_items_size += size_bytes
        items.append(
            {
                "name": item_name,
                "path": str(PROJECT_ROOT / entry["path"]),
                "size_bytes": size_bytes,
                "kind": entry["kind"],
            }
        )
    return items, total_items_size


def _insert_project_and_code_entries(
    items: list[dict[str, str | int]], total_items_size: int
) -> None:
    items.insert(
        0,
        {
            "name": "project_root",
            "path": str(PROJECT_ROOT),
            "size_bytes": total_items_size,
            "kind": "project",
        },
    )

    print("Liczenie code_size...")
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
            "name": "code_only",
            "path": str(PROJECT_ROOT),
            "size_bytes": code_size,
            "kind": "code",
        },
    )


def debug_snapshot():
    (total_physical, used_physical, free_physical), (
        total_root,
        used_root,
        free_root,
    ) = _disk_usage_with_fallback()
    print(f"Physical: {total_physical}, {used_physical}, {free_physical}")
    print(f"Root: {total_root}, {used_root}, {free_root}")

    entries = _storage_entries()
    sizes = _measure_entry_sizes(entries)

    timelines_path = PROJECT_ROOT / "data/timelines"
    dreams_size = _compute_dreams_size(timelines_path)
    print(f"Dreams size: {dreams_size}")

    items, total_items_size = _build_items(entries, sizes, dreams_size)
    print(f"Total items size: {total_items_size}")

    if dreams_size > 0:
        items.append(
            {
                "name": "dreaming",
                "path": str(timelines_path / "dream_*"),
                "size_bytes": dreams_size,
                "kind": "data",
            }
        )

    _insert_project_and_code_entries(items, total_items_size)

    items.sort(key=lambda item: item["size_bytes"], reverse=True)
    print("Sukces!")


if __name__ == "__main__":
    try:
        debug_snapshot()
    except Exception:
        import traceback

        traceback.print_exc()
