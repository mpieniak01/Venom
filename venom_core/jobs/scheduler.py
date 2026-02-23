"""Moduł: scheduler - Funkcje zadań w tle (background jobs)."""

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable

from venom_core.api.stream import EventType
from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
RUNTIME_RETENTION_MARKER_DIR = ".venom_runtime"
RUNTIME_RETENTION_MARKER_FILE = "runtime_retention.last_run"


async def consolidate_memory(event_broadcaster=None):
    """Konsolidacja pamięci - analiza logów i zapis wniosków (PLACEHOLDER)."""
    logger.info("Uruchamiam konsolidację pamięci (placeholder)...")
    if event_broadcaster:
        await event_broadcaster.broadcast_event(
            event_type=EventType.BACKGROUND_JOB_STARTED,
            message="Memory consolidation started (placeholder)",
            data={"job": "consolidate_memory"},
        )

    try:
        # PLACEHOLDER: W przyszłości tutaj będzie analiza logów i zapis do GraphRAG
        logger.debug("Konsolidacja pamięci - placeholder, brak implementacji")

        if event_broadcaster:
            await event_broadcaster.broadcast_event(
                event_type=EventType.MEMORY_CONSOLIDATED,
                message="Memory consolidation completed (placeholder)",
                data={"job": "consolidate_memory"},
            )

    except Exception as e:
        logger.error(f"Błąd podczas konsolidacji pamięci: {e}")
        if event_broadcaster:
            await event_broadcaster.broadcast_event(
                event_type=EventType.BACKGROUND_JOB_FAILED,
                message=f"Memory consolidation failed: {e}",
                data={"job": "consolidate_memory", "error": str(e)},
            )


async def check_health(event_broadcaster=None):
    """Sprawdzenie zdrowia systemu (PLACEHOLDER)."""
    logger.debug("Sprawdzanie zdrowia systemu (placeholder)...")

    try:
        # Placeholder: W przyszłości tutaj będzie sprawdzanie Docker, LLM endpoints, etc.
        health_status = {"status": "ok", "timestamp": datetime.now().isoformat()}

        if event_broadcaster:
            await event_broadcaster.broadcast_event(
                event_type=EventType.BACKGROUND_JOB_COMPLETED,
                message="Health check completed",
                data={"job": "check_health", "status": health_status},
            )

    except Exception as e:
        logger.error(f"Błąd podczas sprawdzania zdrowia: {e}")
        if event_broadcaster:
            await event_broadcaster.broadcast_event(
                event_type=EventType.BACKGROUND_JOB_FAILED,
                message=f"Health check failed: {e}",
                data={"job": "check_health", "error": str(e)},
            )


def _resolve_retention_targets(
    *, base_dir: Path, target_dirs: Iterable[str]
) -> list[Path]:
    """Resolve and validate retention targets, preventing path escape outside base_dir."""
    resolved_base = base_dir.resolve()
    targets: list[Path] = []
    seen: set[Path] = set()

    for target in target_dirs:
        raw = str(target).strip()
        if not raw:
            continue

        candidate = Path(raw)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (resolved_base / candidate).resolve()
        )

        try:
            resolved.relative_to(resolved_base)
        except ValueError:
            logger.warning(
                "Pomijam katalog retencji poza repo: target=%s resolved=%s",
                raw,
                resolved,
            )
            continue

        if resolved in seen:
            continue
        seen.add(resolved)
        targets.append(resolved)

    return targets


def _load_tracked_repo_files(*, repo_root: Path) -> set[str]:
    """Return git-tracked files as repo-relative POSIX paths."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return set()

    tracked: set[str] = set()
    for raw in result.stdout.split(b"\x00"):
        if not raw:
            continue
        try:
            tracked.add(raw.decode("utf-8").replace("\\", "/"))
        except UnicodeDecodeError:
            continue
    return tracked


def _runtime_retention_marker_path(*, base_dir: Path) -> Path:
    return base_dir / RUNTIME_RETENTION_MARKER_DIR / RUNTIME_RETENTION_MARKER_FILE


def should_run_runtime_retention_now(
    *,
    min_interval_minutes: int,
    base_dir: Path | None = None,
) -> bool:
    """Return True when startup retention should execute immediately."""
    if min_interval_minutes <= 0:
        return True

    repo_root = (base_dir or Path(SETTINGS.REPO_ROOT)).resolve()
    marker_path = _runtime_retention_marker_path(base_dir=repo_root)
    if not marker_path.exists():
        return True

    try:
        last_run_timestamp = float(marker_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return True

    elapsed_seconds = datetime.now().timestamp() - last_run_timestamp
    return elapsed_seconds >= (min_interval_minutes * 60)


def _mark_runtime_retention_run(*, base_dir: Path) -> None:
    marker_path = _runtime_retention_marker_path(base_dir=base_dir)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(str(datetime.now().timestamp()), encoding="utf-8")


def _is_target_scannable(target: Path) -> bool:
    if not target.exists():
        logger.debug("Katalog retencji nie istnieje, pomijam: %s", target)
        return False
    if not target.is_dir():
        logger.debug("Ścieżka retencji nie jest katalogiem, pomijam: %s", target)
        return False
    return True


def _is_file_stale_and_untracked(
    *,
    file_path: Path,
    repo_root: Path,
    cutoff_timestamp: float,
    tracked_repo_files: set[str],
) -> tuple[bool, int]:
    try:
        relative_path = file_path.relative_to(repo_root).as_posix()
    except ValueError:
        return False, 0
    if relative_path in tracked_repo_files:
        return False, 0

    try:
        stat = file_path.stat(follow_symlinks=False)
    except (FileNotFoundError, NotADirectoryError):
        return False, 0
    except OSError as exc:
        logger.debug(
            "Pomijam plik podczas retencji (stat error): %s (%s)",
            file_path,
            exc,
        )
        return False, 0

    if not file_path.is_file():
        return False, 0
    if stat.st_mtime >= cutoff_timestamp:
        return False, 0
    return True, int(stat.st_size)


def _delete_stale_file(
    *,
    file_path: Path,
    repo_root: Path,
    cutoff_timestamp: float,
    tracked_repo_files: set[str],
) -> tuple[int, int]:
    should_delete, file_size = _is_file_stale_and_untracked(
        file_path=file_path,
        repo_root=repo_root,
        cutoff_timestamp=cutoff_timestamp,
        tracked_repo_files=tracked_repo_files,
    )
    if not should_delete:
        return 0, 0

    try:
        file_path.unlink()
    except FileNotFoundError:
        return 0, 0
    except OSError as exc:
        logger.debug(
            "Pomijam plik podczas retencji (unlink error): %s (%s)",
            file_path,
            exc,
        )
        return 0, 0
    return 1, file_size


def _delete_stale_empty_dir(*, dir_path: Path, cutoff_timestamp: float) -> int:
    try:
        stat = dir_path.stat(follow_symlinks=False)
    except (FileNotFoundError, NotADirectoryError):
        return 0
    except OSError as exc:
        logger.debug(
            "Pomijam katalog podczas retencji (stat error): %s (%s)",
            dir_path,
            exc,
        )
        return 0

    if stat.st_mtime >= cutoff_timestamp:
        return 0

    try:
        dir_path.rmdir()
    except OSError:
        return 0
    return 1


def _cleanup_target_tree(
    *,
    target: Path,
    repo_root: Path,
    cutoff_timestamp: float,
    tracked_repo_files: set[str],
) -> tuple[int, int, int]:
    deleted_files = 0
    deleted_dirs = 0
    freed_bytes = 0

    for root, dirs, files in os.walk(target, topdown=False, followlinks=False):
        root_path = Path(root)
        for file_name in files:
            file_deleted, file_bytes = _delete_stale_file(
                file_path=root_path / file_name,
                repo_root=repo_root,
                cutoff_timestamp=cutoff_timestamp,
                tracked_repo_files=tracked_repo_files,
            )
            deleted_files += file_deleted
            freed_bytes += file_bytes

        for dir_name in dirs:
            deleted_dirs += _delete_stale_empty_dir(
                dir_path=root_path / dir_name,
                cutoff_timestamp=cutoff_timestamp,
            )

    return deleted_files, deleted_dirs, freed_bytes


def cleanup_runtime_files(
    *,
    retention_days: int = 7,
    target_dirs: Iterable[str] | None = None,
    base_dir: Path | None = None,
) -> dict[str, int | bool]:
    """
    Usuń pliki starsze niż retention_days z katalogów runtime (domyślnie logs/data).
    Usuwane są wyłącznie pliki; puste podkatalogi starsze niż cutoff są usuwane opcjonalnie.
    """
    if retention_days <= 0:
        logger.info(
            "Czyszczenie runtime pominięte: retention_days=%s (<=0)", retention_days
        )
        return {
            "deleted_files": 0,
            "deleted_dirs": 0,
            "freed_bytes": 0,
            "targets_scanned": 0,
            "skipped": True,
        }

    repo_root = (base_dir or Path(SETTINGS.REPO_ROOT)).resolve()
    configured_targets = list(target_dirs or SETTINGS.RUNTIME_RETENTION_TARGETS)
    targets = _resolve_retention_targets(
        base_dir=repo_root,
        target_dirs=configured_targets,
    )
    tracked_repo_files = _load_tracked_repo_files(repo_root=repo_root)
    cutoff_timestamp = (datetime.now().timestamp()) - (retention_days * 86400)

    deleted_files = 0
    deleted_dirs = 0
    freed_bytes = 0
    targets_scanned = 0

    for target in targets:
        if not _is_target_scannable(target):
            continue
        targets_scanned += 1
        target_deleted_files, target_deleted_dirs, target_freed_bytes = (
            _cleanup_target_tree(
                target=target,
                repo_root=repo_root,
                cutoff_timestamp=cutoff_timestamp,
                tracked_repo_files=tracked_repo_files,
            )
        )
        deleted_files += target_deleted_files
        deleted_dirs += target_deleted_dirs
        freed_bytes += target_freed_bytes

    if targets_scanned == 0:
        logger.debug("Brak dostępnych katalogów do retencji runtime.")
    else:
        logger.info(
            "Retention runtime zakończony: dni=%s, katalogi=%s, usunięte_pliki=%s, usunięte_katalogi=%s, odzyskane_bajty=%s",
            retention_days,
            targets_scanned,
            deleted_files,
            deleted_dirs,
            freed_bytes,
        )
    try:
        _mark_runtime_retention_run(base_dir=repo_root)
    except OSError as exc:
        logger.debug("Nie udało się zapisać markera retencji runtime: %s", exc)

    return {
        "deleted_files": deleted_files,
        "deleted_dirs": deleted_dirs,
        "freed_bytes": freed_bytes,
        "targets_scanned": targets_scanned,
        "skipped": False,
    }
