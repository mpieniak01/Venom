import json
from pathlib import Path

from venom_core.services.session_store import SessionStore
from venom_core.utils.boot_id import BOOT_ID


def test_session_store_append_and_get(tmp_path: Path):
    store_path = tmp_path / "session_store.json"
    store = SessionStore(store_path=str(store_path), max_entries=3)

    store.append_message("s1", {"role": "user", "content": "a"})
    store.append_message("s1", {"role": "assistant", "content": "b"})
    store.append_message("s1", {"role": "user", "content": "c"})
    store.append_message("s1", {"role": "assistant", "content": "d"})

    history = store.get_history("s1")
    assert [h["content"] for h in history] == ["b", "c", "d"]


def test_session_store_summary(tmp_path: Path):
    store_path = tmp_path / "session_store.json"
    store = SessionStore(store_path=str(store_path))

    store.set_summary("s1", "summary")
    assert store.get_summary("s1") == "summary"


def test_session_store_clear(tmp_path: Path):
    store_path = tmp_path / "session_store.json"
    store = SessionStore(store_path=str(store_path))

    store.append_message("s1", {"role": "user", "content": "a"})
    assert store.clear_session("s1") is True
    assert store.get_history("s1") == []


def test_session_store_clear_isolated(tmp_path: Path):
    """Czyszczenie jednej sesji nie powinno ruszać innych."""
    store_path = tmp_path / "session_store.json"
    store = SessionStore(store_path=str(store_path))

    store.append_message("s1", {"role": "user", "content": "a"})
    store.append_message("s2", {"role": "user", "content": "b"})
    store.set_summary("s1", "sum-a")
    store.set_summary("s2", "sum-b")

    assert store.clear_session("s1") is True
    assert store.get_history("s1") == []
    assert store.get_summary("s1") is None

    # Sesja s2 pozostaje nienaruszona
    assert [h["content"] for h in store.get_history("s2")] == ["b"]
    assert store.get_summary("s2") == "sum-b"


def test_session_store_preserves_source_labels(tmp_path: Path):
    """Historia powinna zachować oznaczenie źródła (live/history/hidden)."""
    store_path = tmp_path / "session_store.json"
    store = SessionStore(store_path=str(store_path))

    store.append_message(
        "s1", {"role": "assistant", "content": "foo", "source": "live"}
    )
    store.append_message(
        "s1", {"role": "assistant", "content": "bar", "source": "hidden"}
    )
    history = store.get_history("s1")

    assert [h.get("source") for h in history] == ["live", "hidden"]
    assert [h["content"] for h in history] == ["foo", "bar"]


def test_session_store_boot_id_mismatch_clears(tmp_path: Path):
    store_path = tmp_path / "session_store.json"
    payload = {
        "boot_id": "stale-boot-id",
        "sessions": {"s1": {"history": [{"role": "user", "content": "a"}]}},
    }
    store_path.write_text(json.dumps(payload), encoding="utf-8")

    store = SessionStore(store_path=str(store_path))
    assert store.get_history("s1") == []

    saved = json.loads(store_path.read_text(encoding="utf-8"))
    assert saved["boot_id"] == BOOT_ID
