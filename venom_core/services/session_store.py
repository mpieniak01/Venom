"""Persistent store for per-session chat history and summaries."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.utils.boot_id import BOOT_ID
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class SessionStore:
    """Stores chat history/summary per session_id with optional persistence."""

    def __init__(self, store_path: Optional[str] = None, max_entries: int = 1000):
        self._lock = Lock()
        self._store_path = self._resolve_store_path(store_path)
        self._max_entries = max_entries
        self._sessions: Dict[str, Dict[str, object]] = {}
        self._load()

    @staticmethod
    def _is_within(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def _resolve_store_path(self, store_path: Optional[str]) -> Path:
        default_path = (
            Path(SETTINGS.MEMORY_ROOT).resolve() / "session_store.json"
        ).resolve()
        if not store_path:
            return default_path

        candidate = Path(store_path).expanduser()
        if not candidate.is_absolute():
            candidate = (Path(SETTINGS.MEMORY_ROOT).resolve() / candidate).resolve()
        else:
            candidate = candidate.resolve()

        memory_root = Path(SETTINGS.MEMORY_ROOT).resolve()
        tmp_root = Path("/tmp").resolve()
        if self._is_within(candidate, memory_root) or self._is_within(
            candidate, tmp_root
        ):
            return candidate

        logger.warning(
            "Odrzucono store_path poza dozwolonym zakresem (MEMORY_ROOT,/tmp): %s; używam domyślnej ścieżki",
            candidate,
        )
        return default_path

    def _load(self) -> None:
        if not self._store_path.exists():
            return
        try:
            with self._store_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if data.get("boot_id") != BOOT_ID:
                logger.debug(
                    "SessionStore boot_id mismatch - updating boot_id while preserving sessions"
                )
                # Nie czyścimy sesji, po prostu pozwalamy mechanizmowi _save zapisać nowy boot_id później
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
            session["updated_at"] = get_utc_now_iso()
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
            session["updated_at"] = get_utc_now_iso()
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
