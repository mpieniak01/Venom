import os
import time
from pathlib import Path

import pytest

from venom_core.jobs.scheduler import (
    _runtime_retention_marker_path,
    cleanup_runtime_files,
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
