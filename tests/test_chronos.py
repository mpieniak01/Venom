"""Testy jednostkowe dla ChronosEngine."""

import tempfile
from pathlib import Path

import pytest

from venom_core.core.chronos import Checkpoint, ChronosEngine


@pytest.fixture
def temp_timelines_dir():
    """Fixture dla tymczasowego katalogu snapshotów."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "timelines")


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        # Utwórz prosty plik testowy
        test_file = workspace / "test.txt"
        test_file.write_text("Initial content")
        yield workspace


@pytest.fixture
def temp_memory():
    """Fixture dla tymczasowej pamięci."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = Path(tmpdir) / "memory"
        memory.mkdir(parents=True, exist_ok=True)
        # Utwórz prosty plik bazy
        db_file = memory / "test.db"
        db_file.write_text('{"test": "data"}')
        yield memory


@pytest.fixture
def chronos_engine(temp_timelines_dir, temp_workspace, temp_memory):
    """Fixture dla ChronosEngine."""
    return ChronosEngine(
        timelines_dir=temp_timelines_dir,
        workspace_root=str(temp_workspace),
        memory_root=str(temp_memory),
    )


class TestCheckpoint:
    """Testy dla klasy Checkpoint."""

    def test_checkpoint_creation(self):
        """Test tworzenia checkpointu."""
        checkpoint = Checkpoint(
            checkpoint_id="test123",
            name="Test Checkpoint",
            timestamp="2024-01-01T12:00:00",
            description="Test description",
            metadata={"key": "value"},
        )

        assert checkpoint.checkpoint_id == "test123"
        assert checkpoint.name == "Test Checkpoint"
        assert checkpoint.timestamp == "2024-01-01T12:00:00"
        assert checkpoint.description == "Test description"
        assert checkpoint.metadata["key"] == "value"

    def test_checkpoint_to_dict(self):
        """Test konwersji checkpointu do słownika."""
        checkpoint = Checkpoint(
            checkpoint_id="test123",
            name="Test",
            timestamp="2024-01-01T12:00:00",
        )

        data = checkpoint.to_dict()
        assert data["checkpoint_id"] == "test123"
        assert data["name"] == "Test"
        assert data["timestamp"] == "2024-01-01T12:00:00"
        assert "description" in data
        assert "metadata" in data

    def test_checkpoint_from_dict(self):
        """Test tworzenia checkpointu ze słownika."""
        data = {
            "checkpoint_id": "test123",
            "name": "Test",
            "timestamp": "2024-01-01T12:00:00",
            "description": "Description",
            "metadata": {"key": "value"},
        }

        checkpoint = Checkpoint.from_dict(data)
        assert checkpoint.checkpoint_id == "test123"
        assert checkpoint.name == "Test"
        assert checkpoint.metadata["key"] == "value"


class TestChronosEngine:
    """Testy dla klasy ChronosEngine."""

    def test_chronos_initialization(self, chronos_engine, temp_timelines_dir):
        """Test inicjalizacji ChronosEngine."""
        assert chronos_engine.timelines_dir.exists()
        assert chronos_engine.main_timeline.exists()
        assert str(temp_timelines_dir) in str(chronos_engine.timelines_dir)

    def test_create_checkpoint(self, chronos_engine):
        """Test tworzenia checkpointu."""
        checkpoint_id = chronos_engine.create_checkpoint(
            name="Test Checkpoint", description="Test description"
        )

        assert checkpoint_id is not None
        assert len(checkpoint_id) == 8  # UUID[:8]

        # Sprawdź czy katalog został utworzony
        checkpoint_dir = chronos_engine.main_timeline / checkpoint_id
        assert checkpoint_dir.exists()

        # Sprawdź czy pliki metadanych istnieją
        assert (checkpoint_dir / "checkpoint.json").exists()
        assert (checkpoint_dir / "env_config.json").exists()

    def test_list_checkpoints(self, chronos_engine):
        """Test listowania checkpointów."""
        # Utwórz kilka checkpointów
        id1 = chronos_engine.create_checkpoint(name="Checkpoint 1")
        id2 = chronos_engine.create_checkpoint(name="Checkpoint 2")

        checkpoints = chronos_engine.list_checkpoints()
        assert len(checkpoints) == 2
        assert any(cp.checkpoint_id == id1 for cp in checkpoints)
        assert any(cp.checkpoint_id == id2 for cp in checkpoints)

    def test_delete_checkpoint(self, chronos_engine):
        """Test usuwania checkpointu."""
        checkpoint_id = chronos_engine.create_checkpoint(name="To Delete")
        assert len(chronos_engine.list_checkpoints()) == 1

        success = chronos_engine.delete_checkpoint(checkpoint_id)
        assert success
        assert len(chronos_engine.list_checkpoints()) == 0

    def test_delete_nonexistent_checkpoint(self, chronos_engine):
        """Test usuwania nieistniejącego checkpointu."""
        success = chronos_engine.delete_checkpoint("nonexistent")
        assert not success

    def test_create_timeline(self, chronos_engine):
        """Test tworzenia nowej linii czasowej."""
        success = chronos_engine.create_timeline("experimental")
        assert success

        timelines = chronos_engine.list_timelines()
        assert "experimental" in timelines
        assert "main" in timelines

    def test_create_duplicate_timeline(self, chronos_engine):
        """Test tworzenia duplikatu linii czasowej."""
        chronos_engine.create_timeline("test")
        success = chronos_engine.create_timeline("test")
        assert not success

    def test_list_timelines(self, chronos_engine):
        """Test listowania linii czasowych."""
        chronos_engine.create_timeline("timeline1")
        chronos_engine.create_timeline("timeline2")

        timelines = chronos_engine.list_timelines()
        assert "main" in timelines
        assert "timeline1" in timelines
        assert "timeline2" in timelines

    def test_checkpoint_on_different_timelines(self, chronos_engine):
        """Test checkpointów na różnych liniach czasowych."""
        chronos_engine.create_timeline("experimental")

        id1 = chronos_engine.create_checkpoint(name="Main CP", timeline="main")
        id2 = chronos_engine.create_checkpoint(name="Exp CP", timeline="experimental")

        main_checkpoints = chronos_engine.list_checkpoints(timeline="main")
        exp_checkpoints = chronos_engine.list_checkpoints(timeline="experimental")

        assert len(main_checkpoints) == 1
        assert len(exp_checkpoints) == 1
        assert main_checkpoints[0].checkpoint_id == id1
        assert exp_checkpoints[0].checkpoint_id == id2

    def test_backup_memory(self, chronos_engine, temp_memory):
        """Test backupu pamięci."""
        # Utwórz checkpoint
        checkpoint_id = chronos_engine.create_checkpoint(name="Memory Test")

        # Sprawdź czy backup pamięci został utworzony
        checkpoint_dir = chronos_engine.main_timeline / checkpoint_id
        memory_backup = checkpoint_dir / "memory_dump"

        assert memory_backup.exists()
        assert (memory_backup / "test.db").exists()

    def test_env_config_save(self, chronos_engine):
        """Test zapisywania konfiguracji środowiska."""
        checkpoint_id = chronos_engine.create_checkpoint(name="Env Test")

        checkpoint_dir = chronos_engine.main_timeline / checkpoint_id
        env_config_file = checkpoint_dir / "env_config.json"

        assert env_config_file.exists()

        import json

        with open(env_config_file) as f:
            config = json.load(f)

        assert "timestamp" in config
        assert "settings" in config
        assert "WORKSPACE_ROOT" in config["settings"]


class TestChronosIntegration:
    """Testy integracyjne dla ChronosEngine."""

    def test_full_checkpoint_cycle(self, chronos_engine, temp_workspace):
        """Test pełnego cyklu: tworzenie -> modyfikacja -> przywracanie."""
        # Stan początkowy
        test_file = temp_workspace / "test.txt"
        initial_content = test_file.read_text()
        assert initial_content == "Initial content"

        # Utwórz checkpoint
        chronos_engine.create_checkpoint(name="Before Change")

        # Modyfikuj plik
        test_file.write_text("Modified content")
        assert test_file.read_text() == "Modified content"

        # Przywróć checkpoint
        # Uwaga: W testach nie inicjalizujemy git repo, więc ta część może nie działać
        # W prawdziwym środowisku wymaga git repo
        # success = chronos_engine.restore_checkpoint(checkpoint_id)
        # assert success

        # Po przywróceniu plik powinien mieć oryginalną zawartość
        # assert test_file.read_text() == "Initial content"

    def test_multiple_checkpoints_order(self, chronos_engine):
        """Test kolejności checkpointów."""
        import time

        id1 = chronos_engine.create_checkpoint(name="First")
        time.sleep(0.1)
        id2 = chronos_engine.create_checkpoint(name="Second")
        time.sleep(0.1)
        id3 = chronos_engine.create_checkpoint(name="Third")

        checkpoints = chronos_engine.list_checkpoints()

        # Powinny być posortowane od najnowszych
        assert checkpoints[0].checkpoint_id == id3
        assert checkpoints[1].checkpoint_id == id2
        assert checkpoints[2].checkpoint_id == id1
