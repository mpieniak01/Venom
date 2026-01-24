"""Persistent store for per-session chat history and summaries."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.utils.boot_id import BOOT_ID
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class SessionStore:
    """Stores chat history/summary per session_id with optional persistence."""

    def __init__(self, store_path: Optional[str] = None, max_entries: int = 500):
        self._lock = Lock()
        resolved = store_path or str(Path(SETTINGS.MEMORY_ROOT) / "session_store.json")
        self._store_path = Path(resolved)
        self._max_entries = max_entries
        self._sessions: Dict[str, Dict[str, object]] = {}
        self._load()

    def _load(self) -> None:
        if not self._store_path.exists():
            return
        try:
            with self._store_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if data.get("boot_id") != BOOT_ID:
                logger.info(
                    "SessionStore boot_id mismatch - clearing persisted sessions"
                )
                self._sessions = {}
                self._save()
                return
            sessions = data.get("sessions", {}) or {}
            if isinstance(sessions, dict):
                self._sessions = sessions
            else:
                self._sessions = {}
        except Exception as exc:
            logger.warning(f"Nie udało się wczytać SessionStore: {exc}")
            self._sessions = {}

    def _save(self) -> None:
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"boot_id": BOOT_ID, "sessions": self._sessions}
            with self._store_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning(f"Nie udało się zapisać SessionStore: {exc}")

    def append_message(self, session_id: str, entry: Dict[str, object]) -> None:
        if not session_id:
            return
        with self._lock:
            session = self._sessions.setdefault(session_id, {})
            history: List[Dict[str, object]] = []
            history_raw = session.get("history")
            if isinstance(history_raw, list):
                history = [item for item in history_raw if isinstance(item, dict)]
            history.append(entry)
            if self._max_entries and len(history) > self._max_entries:
                history = history[-self._max_entries :]
            session["history"] = history
            session["updated_at"] = datetime.now().isoformat()
            self._sessions[session_id] = session
            self._save()

    def get_history(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, object]]:
        if not session_id:
            return []
        with self._lock:
            session = self._sessions.get(session_id, {})
            history: List[Dict[str, object]] = []
            history_raw = session.get("history")
            if isinstance(history_raw, list):
                history = [item for item in history_raw if isinstance(item, dict)]
        if limit is not None:
            return history[-limit:]
        return history

    def set_summary(self, session_id: str, summary: str) -> None:
        if not session_id:
            return
        with self._lock:
            session = self._sessions.setdefault(session_id, {})
            session["summary"] = summary
            session["updated_at"] = datetime.now().isoformat()
            self._sessions[session_id] = session
            self._save()

    def get_summary(self, session_id: str) -> Optional[str]:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id, {})
            summary = session.get("summary")
        return summary if isinstance(summary, str) else None

    def clear_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        with self._lock:
            existed = session_id in self._sessions
            if existed:
                self._sessions.pop(session_id, None)
                self._save()
            return existed

    def clear_all(self) -> None:
        with self._lock:
            self._sessions = {}
            self._save()
