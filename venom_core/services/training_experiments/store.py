"""Atomic on-disk run records and a recoverable SQLite index."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from venom_core.services.remote_training.lifecycle import atomic_json, validate_run_id
from venom_core.services.remote_training.paths import operator_path

from .profiles import read_json


class RunStore:
    def __init__(self, root: Path):
        self.root = operator_path(root)

    def directory(self, run_id: str) -> Path:
        validate_run_id(run_id)
        return operator_path(self.root / "runs" / run_id)

    def read(self, run_id: str) -> dict:
        return read_json(self.directory(run_id) / "state.json")

    def save(self, state: dict) -> None:
        directory = self.directory(state["run_id"])
        atomic_json(directory / "state.json", state)
        database = operator_path(self.root / "runs.sqlite3")
        fd = os.open(database, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(database, timeout=5)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS run_index "
                "(id TEXT PRIMARY KEY, status TEXT NOT NULL, updated REAL NOT NULL)"
            )
            db.execute(
                "INSERT OR REPLACE INTO run_index VALUES (?, ?, ?)",
                (state["run_id"], state["status"], state["updated_at"]),
            )

    def ids(self) -> list[str]:
        # State files also recover entries committed just before a database failure.
        records = operator_path(self.root / "runs")
        if not records.is_dir():
            return []
        names = {
            directory.name
            for directory in records.iterdir()
            if not directory.is_symlink() and (directory / "state.json").is_file()
        }
        database = operator_path(self.root / "runs.sqlite3")
        if database.is_file():
            try:
                uri = database.as_uri() + "?mode=ro"
                with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
                    indexed = [
                        row[0]
                        for row in db.execute(
                            "SELECT id FROM run_index ORDER BY updated DESC"
                        )
                        if row[0] in names
                    ]
                return [*indexed, *sorted(names.difference(indexed))]
            except sqlite3.Error:
                pass
        return sorted(names)
