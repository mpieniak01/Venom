import os
import subprocess
import time
from pathlib import Path

import pytest

from venom_core.jobs.scheduler import (
    _delete_stale_empty_dir,
    _delete_stale_file,
    _is_target_scannable,
    _load_tracked_repo_files,
    _resolve_retention_targets,
    _runtime_retention_marker_path,
    check_health,
    cleanup_runtime_files,
    consolidate_memory,
    should_run_runtime_retention_now,
)


def _touch_with_age(path: Path, *, age_days: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    now = int(time.time())
    timestamp = now - (age_days * 86400)
    os.utime(path, (timestamp, timestamp))


def test_cleanup_runtime_files_removes_old_files_only(tmp_path: Path) -> None:
    _touch_with_age(tmp_path / "logs" / "old.log", age_days=8)
    _touch_with_age(tmp_path / "logs" / "recent.log", age_days=1)
    _touch_with_age(tmp_path / "data" / "nested" / "old.json", age_days=9)
    _touch_with_age(tmp_path / "data" / "nested" / "recent.json", age_days=2)

    stats = cleanup_runtime_files(
        retention_days=7,
        target_dirs=["logs", "data"],
        base_dir=tmp_path,
    )

    assert stats["targets_scanned"] == 2
    assert stats["deleted_files"] == 2
    assert (tmp_path / "logs" / "old.log").exists() is False
    assert (tmp_path / "data" / "nested" / "old.json").exists() is False
    assert (tmp_path / "logs" / "recent.log").exists() is True
    assert (tmp_path / "data" / "nested" / "recent.json").exists() is True


def test_cleanup_runtime_files_skips_targets_outside_repo(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    outside_dir = tmp_path / "outside"
    repo_dir.mkdir(parents=True, exist_ok=True)
    _touch_with_age(outside_dir / "old.log", age_days=10)

    stats = cleanup_runtime_files(
        retention_days=7,
        target_dirs=["../outside"],
        base_dir=repo_dir,
    )

    assert stats["targets_scanned"] == 0
    assert stats["deleted_files"] == 0
    assert (outside_dir / "old.log").exists() is True


def test_cleanup_runtime_files_skips_when_retention_non_positive(
    tmp_path: Path,
) -> None:
    _touch_with_age(tmp_path / "logs" / "old.log", age_days=10)

    stats = cleanup_runtime_files(
        retention_days=0,
        target_dirs=["logs"],
        base_dir=tmp_path,
    )

    assert stats["skipped"] is True
    assert stats["deleted_files"] == 0
    assert (tmp_path / "logs" / "old.log").exists() is True


def test_cleanup_runtime_files_writes_retention_marker(tmp_path: Path) -> None:
    _touch_with_age(tmp_path / "logs" / "old.log", age_days=10)

    cleanup_runtime_files(
        retention_days=7,
        target_dirs=["logs"],
        base_dir=tmp_path,
    )

    marker = _runtime_retention_marker_path(base_dir=tmp_path.resolve())
    assert marker.exists() is True


def test_should_run_runtime_retention_now_respects_marker_interval(
    tmp_path: Path,
) -> None:
    marker = _runtime_retention_marker_path(base_dir=tmp_path.resolve())
    marker.parent.mkdir(parents=True, exist_ok=True)

    marker.write_text(str(time.time()), encoding="utf-8")
    assert (
        should_run_runtime_retention_now(
            min_interval_minutes=1440,
            base_dir=tmp_path,
        )
        is False
    )

    marker.write_text(str(time.time() - (2 * 3600)), encoding="utf-8")
    assert (
        should_run_runtime_retention_now(
            min_interval_minutes=60,
            base_dir=tmp_path,
        )
        is True
    )


def test_cleanup_runtime_files_skips_git_tracked_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked_file = tmp_path / "data" / "prompts" / "tracked.yaml"
    _touch_with_age(tracked_file, age_days=10)
    monkeypatch.setattr(
        "venom_core.jobs.scheduler._load_tracked_repo_files",
        lambda **_: {"data/prompts/tracked.yaml"},
    )

    stats = cleanup_runtime_files(
        retention_days=7,
        target_dirs=["data"],
        base_dir=tmp_path,
    )

    assert stats["deleted_files"] == 0
    assert tracked_file.exists() is True


def test_should_run_runtime_retention_now_returns_true_for_invalid_marker(
    tmp_path: Path,
) -> None:
    marker = _runtime_retention_marker_path(base_dir=tmp_path.resolve())
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("invalid", encoding="utf-8")
    assert should_run_runtime_retention_now(min_interval_minutes=60, base_dir=tmp_path)


def test_resolve_retention_targets_filters_duplicates_and_escape(
    tmp_path: Path,
) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    targets = _resolve_retention_targets(
        base_dir=base,
        target_dirs=["logs", " logs ", "", "../outside", "logs", str(base / "data")],
    )
    assert (base / "logs").resolve() in targets
    assert (base / "data").resolve() in targets
    assert len(targets) == 2


def test_load_tracked_repo_files_returns_empty_on_subprocess_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args, **_kwargs):
        raise subprocess.SubprocessError("boom")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert _load_tracked_repo_files(repo_root=tmp_path) == set()


def test_load_tracked_repo_files_skips_undecodable_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyResult:
        stdout = b"good.py\x00\xff\xfe\x00nested/test.py\x00"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: DummyResult())
    tracked = _load_tracked_repo_files(repo_root=tmp_path)
    assert "good.py" in tracked
    assert "nested/test.py" in tracked


def test_should_run_runtime_retention_now_short_circuits_when_non_positive(
    tmp_path: Path,
) -> None:
    assert should_run_runtime_retention_now(min_interval_minutes=0, base_dir=tmp_path)


def test_should_run_runtime_retention_now_returns_true_when_marker_missing(
    tmp_path: Path,
) -> None:
    assert should_run_runtime_retention_now(min_interval_minutes=30, base_dir=tmp_path)


def test_is_target_scannable_handles_missing_and_non_directory(tmp_path: Path) -> None:
    assert _is_target_scannable(tmp_path / "missing") is False
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    assert _is_target_scannable(file_path) is False


def test_delete_stale_file_returns_zero_on_unlink_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale_file = tmp_path / "data" / "old.log"
    _touch_with_age(stale_file, age_days=9)

    original_unlink = Path.unlink

    def _unlink_raise(self, *args, **kwargs):
        if self == stale_file:
            raise OSError("nope")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink_raise)
    deleted, freed = _delete_stale_file(
        file_path=stale_file,
        repo_root=tmp_path.resolve(),
        cutoff_timestamp=time.time() - (7 * 86400),
        tracked_repo_files=set(),
    )
    assert deleted == 0
    assert freed == 0


def test_delete_stale_empty_dir_returns_zero_when_rmdir_fails(tmp_path: Path) -> None:
    stale_dir = tmp_path / "logs" / "stale"
    stale_dir.mkdir(parents=True, exist_ok=True)
    # Keep directory non-empty so rmdir fails and branch returns 0.
    (stale_dir / "keep.txt").write_text("x", encoding="utf-8")
    old_ts = int(time.time()) - (10 * 86400)
    os.utime(stale_dir, (old_ts, old_ts))

    assert (
        _delete_stale_empty_dir(
            dir_path=stale_dir,
            cutoff_timestamp=time.time() - (7 * 86400),
        )
        == 0
    )


def test_cleanup_runtime_files_skips_non_scannable_target(tmp_path: Path) -> None:
    stats = cleanup_runtime_files(
        retention_days=7,
        target_dirs=["logs", "missing"],
        base_dir=tmp_path,
    )
    assert stats["targets_scanned"] == 0
    assert stats["deleted_files"] == 0


def test_cleanup_runtime_files_handles_marker_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "venom_core.jobs.scheduler._mark_runtime_retention_run",
        lambda **_: (_ for _ in ()).throw(OSError("marker-fail")),
    )
    stats = cleanup_runtime_files(
        retention_days=7,
        target_dirs=["logs"],
        base_dir=tmp_path,
    )
    assert stats["skipped"] is False


@pytest.mark.asyncio
async def test_consolidate_memory_emits_started_and_completed_events() -> None:
    class Broadcaster:
        def __init__(self):
            self.calls = []

        async def broadcast_event(self, **kwargs):
            self.calls.append(kwargs["event_type"])

    broadcaster = Broadcaster()
    await consolidate_memory(event_broadcaster=broadcaster)
    assert len(broadcaster.calls) == 2


@pytest.mark.asyncio
async def test_consolidate_memory_emits_failed_event_on_exception() -> None:
    class Broadcaster:
        def __init__(self):
            self.calls = 0

        async def broadcast_event(self, **kwargs):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("boom")

    broadcaster = Broadcaster()
    await consolidate_memory(event_broadcaster=broadcaster)
    assert broadcaster.calls >= 3


@pytest.mark.asyncio
async def test_check_health_emits_failed_event_on_exception() -> None:
    class Broadcaster:
        def __init__(self):
            self.calls = 0

        async def broadcast_event(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom")

    broadcaster = Broadcaster()
    await check_health(event_broadcaster=broadcaster)
    assert broadcaster.calls >= 2
