"""Private atomic journal, protected by an inter-process lock on Linux."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import (
    EnvironmentPlan,
    EnvironmentRecord,
)


class Journal:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, plan_id: str, suffix: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", plan_id):
            raise VastError("vast.invalid_plan_id")
        return self.root / (plan_id + suffix)

    @contextmanager
    def lock(self, plan_id: str) -> Iterator[None]:
        import fcntl

        target = self.path(plan_id, ".lock")
        fd = os.open(target, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise VastError("vast.plan_busy") from None
            yield
        finally:
            os.close(fd)

    def write(self, path: Path, data: dict) -> None:
        fd, name = tempfile.mkstemp(prefix=".vast-", dir=self.root)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def save_plan(self, plan: EnvironmentPlan) -> None:
        self.write(self.path(plan.plan_id, ".plan.json"), plan.model_dump(mode="json"))

    def plan(self, plan_id: str) -> EnvironmentPlan:
        plan = EnvironmentPlan.model_validate_json(
            self.path(plan_id, ".plan.json").read_text()
        )
        if plan.plan_id != plan_id or plan.calculate_checksum() != plan.checksum:
            raise VastError("vast.plan_changed")
        return plan

    def record(self, plan_id: str) -> EnvironmentRecord:
        path = self.path(plan_id, ".record.json")
        if not path.exists():
            return EnvironmentRecord(plan_id=plan_id)
        record = EnvironmentRecord.model_validate_json(path.read_text())
        if record.plan_id != plan_id:
            raise VastError("vast.record_mismatch")
        return record

    def save_record(self, record: EnvironmentRecord) -> None:
        self.write(
            self.path(record.plan_id, ".record.json"), record.model_dump(mode="json")
        )
