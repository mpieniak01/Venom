"""Test integracyjny dla THE_OVERMIND - Background Lifecycle Management."""

import asyncio
import tempfile
from pathlib import Path

import pytest

# Proste testy integracyjne aby sprawdzić czy komponenty mogą współpracować


@pytest.mark.asyncio
async def test_scheduler_watcher_integration():
    """Test integracji scheduler + watcher."""
    pytest.importorskip("apscheduler")
    from venom_core.core.scheduler import BackgroundScheduler
    from venom_core.perception.watcher import FileWatcher

    with tempfile.TemporaryDirectory() as tmpdir:
        # Utwórz scheduler
        scheduler = BackgroundScheduler()
        await scheduler.start()
        assert scheduler.is_running is True

        # Utwórz watcher
        watcher = FileWatcher(workspace_root=tmpdir)
        await watcher.start()
        assert watcher.is_running is True

        # Poczekaj chwilę
        await asyncio.sleep(1)

        # Zatrzymaj
        await watcher.stop()
        await scheduler.stop()
        assert watcher.is_running is False
        assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_documenter_handles_py_files():
    """Test czy DocumenterAgent obsługuje pliki Python."""
    from venom_core.agents.documenter import DocumenterAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DocumenterAgent(workspace_root=tmpdir)

        # Utwórz plik Python
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("def hello(): pass")

        # Wywołaj handler (bez GitSkill, nie będzie commitował)
        await agent.handle_code_change(str(test_file))
        status = agent.get_status()
        assert status["workspace_root"] == str(Path(tmpdir).resolve())
        assert status["processing_files"] == 1


@pytest.mark.asyncio
async def test_gardener_idle_mode_integration():
    """Test integracji GardenerAgent z idle mode."""
    from venom_core.agents.gardener import GardenerAgent
    from venom_core.core.orchestrator import Orchestrator
    from venom_core.core.state_manager import StateManager

    with tempfile.TemporaryDirectory() as tmpdir:
        # Utwórz Orchestrator
        state_file = Path(tmpdir) / "state.json"
        state_manager = StateManager(state_file_path=str(state_file))
        orchestrator = Orchestrator(state_manager)

        # Utwórz GardenerAgent z orchestratorem
        gardener = GardenerAgent(
            workspace_root=tmpdir, orchestrator=orchestrator, scan_interval=300
        )

        # Start i stop
        await gardener.start()
        assert gardener.is_running is True
        await asyncio.sleep(0.5)
        await gardener.stop()
        assert gardener.is_running is False


def test_config_has_background_settings():
    """Test czy config zawiera wszystkie nowe ustawienia."""
    from venom_core.config import SETTINGS

    # Sprawdź czy nowe ustawienia istnieją
    assert hasattr(SETTINGS, "VENOM_PAUSE_BACKGROUND_TASKS")
    assert hasattr(SETTINGS, "ENABLE_AUTO_DOCUMENTATION")
    assert hasattr(SETTINGS, "ENABLE_AUTO_GARDENING")
    assert hasattr(SETTINGS, "WATCHER_DEBOUNCE_SECONDS")
    assert hasattr(SETTINGS, "IDLE_THRESHOLD_MINUTES")
    assert hasattr(SETTINGS, "MEMORY_CONSOLIDATION_INTERVAL_MINUTES")
    assert hasattr(SETTINGS, "HEALTH_CHECK_INTERVAL_MINUTES")

    # Sprawdź typy
    assert isinstance(SETTINGS.VENOM_PAUSE_BACKGROUND_TASKS, bool)
    assert isinstance(SETTINGS.ENABLE_AUTO_DOCUMENTATION, bool)
    assert isinstance(SETTINGS.ENABLE_AUTO_GARDENING, bool)
    assert isinstance(SETTINGS.WATCHER_DEBOUNCE_SECONDS, int)
    assert isinstance(SETTINGS.IDLE_THRESHOLD_MINUTES, int)


def test_event_types_extended():
    """Test czy EventType zawiera nowe typy zdarzeń."""
    from venom_core.api.stream import EventType

    # Sprawdź nowe typy zdarzeń
    assert hasattr(EventType, "CODE_CHANGED")
    assert hasattr(EventType, "BACKGROUND_JOB_STARTED")
    assert hasattr(EventType, "BACKGROUND_JOB_COMPLETED")
    assert hasattr(EventType, "BACKGROUND_JOB_FAILED")
    assert hasattr(EventType, "DOCUMENTATION_UPDATED")
    assert hasattr(EventType, "MEMORY_CONSOLIDATED")
    assert hasattr(EventType, "IDLE_REFACTORING_STARTED")
    assert hasattr(EventType, "IDLE_REFACTORING_COMPLETED")


def test_orchestrator_has_last_activity():
    """Test czy Orchestrator ma tracking last_activity."""
    from venom_core.core.orchestrator import Orchestrator
    from venom_core.core.state_manager import StateManager

    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        state_manager = StateManager(state_file_path=str(state_file))
        orchestrator = Orchestrator(state_manager)

        # Sprawdź czy ma atrybut last_activity
        assert hasattr(orchestrator, "last_activity")
        assert orchestrator.last_activity is None
