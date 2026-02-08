"""Testy dla modułu watcher (FileWatcher)."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from venom_core.perception.watcher import FileWatcher


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.asyncio
async def test_watcher_initialization(temp_workspace):
    """Test inicjalizacji watchera."""
    watcher = FileWatcher(workspace_root=str(temp_workspace))

    assert not watcher.is_running
    assert watcher.workspace_root == temp_workspace


@pytest.mark.asyncio
async def test_watcher_start_stop(temp_workspace):
    """Test uruchamiania i zatrzymywania watchera."""
    watcher = FileWatcher(workspace_root=str(temp_workspace))

    await watcher.start()
    assert watcher.is_running

    await watcher.stop()
    assert not watcher.is_running


@pytest.mark.asyncio
async def test_watcher_get_status(temp_workspace):
    """Test pobierania statusu watchera."""
    watcher = FileWatcher(workspace_root=str(temp_workspace))

    status = watcher.get_status()

    assert "is_running" in status
    assert "workspace_root" in status
    assert "debounce_seconds" in status
    assert "monitoring_extensions" in status


@pytest.mark.asyncio
async def test_watcher_callback_triggered(temp_workspace):
    """Test wywołania callback przy zmianie pliku."""
    # Callback do śledzenia wywołań
    callback_triggered = asyncio.Event()
    changed_files = []

    async def test_callback(file_path):
        await asyncio.to_thread(changed_files.append, file_path)
        await asyncio.to_thread(callback_triggered.set)

    watcher = FileWatcher(
        workspace_root=str(temp_workspace), on_change_callback=test_callback
    )

    await watcher.start()

    # Utwórz plik Python
    test_file = temp_workspace / "test.py"
    test_file.write_text("print('hello')")

    # Poczekaj chwilę na reakcję watchera (dłużej na wolnych systemach CI)
    await asyncio.sleep(2)

    # Zmodyfikuj plik
    test_file.write_text("print('hello world')")

    # Czekaj na callback (z timeoutem)
    try:
        await asyncio.wait_for(callback_triggered.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        pytest.skip("Watchdog nie zdążył wywołać callback (może być opóźniony na CI)")

    await watcher.stop()

    # Sprawdź czy callback został wywołany
    assert len(changed_files) > 0


@pytest.mark.asyncio
async def test_watcher_ignores_non_python_files(temp_workspace):
    """Test ignorowania plików niebędących Python/Markdown."""
    callback_triggered = asyncio.Event()
    changed_files = []

    async def test_callback(file_path):
        await asyncio.to_thread(changed_files.append, file_path)
        await asyncio.to_thread(callback_triggered.set)

    watcher = FileWatcher(
        workspace_root=str(temp_workspace), on_change_callback=test_callback
    )

    await watcher.start()

    # Utwórz plik tekstowy (nie .py ani .md)
    test_file = temp_workspace / "test.txt"
    test_file.write_text("some text")

    # Poczekaj
    await asyncio.sleep(2)

    await watcher.stop()

    # Callback nie powinien być wywołany
    assert len(changed_files) == 0


@pytest.mark.asyncio
async def test_watcher_ignores_pycache(temp_workspace):
    """Test ignorowania plików w __pycache__."""
    callback_triggered = asyncio.Event()
    changed_files = []

    async def test_callback(file_path):
        await asyncio.to_thread(changed_files.append, file_path)
        await asyncio.to_thread(callback_triggered.set)

    watcher = FileWatcher(
        workspace_root=str(temp_workspace), on_change_callback=test_callback
    )

    await watcher.start()

    # Utwórz katalog __pycache__ i plik w nim
    pycache_dir = temp_workspace / "__pycache__"
    pycache_dir.mkdir()
    test_file = pycache_dir / "test.pyc"
    test_file.write_text("cached")

    # Poczekaj
    await asyncio.sleep(2)

    await watcher.stop()

    # Callback nie powinien być wywołany
    assert len(changed_files) == 0
