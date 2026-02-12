"""Testy dla Docker cleanup w MirrorWorld (Phase 132C)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from venom_core.infrastructure.mirror_world import MirrorWorld, InstanceInfo


@pytest.fixture
def mirror_world(tmp_path):
    """Fixture: MirrorWorld z tymczasowym workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return MirrorWorld(workspace_root=str(workspace))


class TestDockerContainerCleanup:
    """Testy dla funkcjonalności zatrzymywania i usuwania kontenerów Docker (PR-132C)."""

    @pytest.mark.asyncio
    async def test_stop_and_remove_container_success(self, mirror_world):
        """Test pomyślnego zatrzymania i usunięcia kontenera."""
        # Mock Docker client
        mock_container = MagicMock()
        mock_container.stop = MagicMock()
        mock_container.remove = MagicMock()
        
        mock_client = MagicMock()
        mock_client.containers.get = MagicMock(return_value=mock_container)
        
        mirror_world._docker_client = mock_client
        
        # Wywołaj metodę
        result = await mirror_world._stop_and_remove_container("test-container")
        
        # Sprawdź że kontener został zatrzymany i usunięty
        assert result is True
        mock_container.stop.assert_called_once_with(timeout=10)
        mock_container.remove.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_stop_and_remove_container_not_found(self, mirror_world):
        """Test gdy kontener już nie istnieje - powinien zwrócić True (idempotencja)."""
        # Mock Docker client - symuluj NotFound
        mock_client = MagicMock()
        
        with patch('venom_core.infrastructure.mirror_world.docker') as mock_docker_module:
            mock_docker_module.errors.NotFound = Exception
            mock_client.containers.get.side_effect = Exception("Container not found")
            mirror_world._docker_client = mock_client
            
            result = await mirror_world._stop_and_remove_container("nonexistent")
            
            # Powinno zwrócić True - kontener nie istnieje = cel osiągnięty
            assert result is True

    @pytest.mark.asyncio
    async def test_stop_and_remove_container_force_kill(self, mirror_world):
        """Test wymuszenia kill gdy graceful stop nie działa."""
        # Mock Docker client
        mock_container = MagicMock()
        mock_container.stop = MagicMock(side_effect=Exception("Stop timeout"))
        mock_container.kill = MagicMock()
        mock_container.remove = MagicMock()
        
        mock_client = MagicMock()
        mock_client.containers.get = MagicMock(return_value=mock_container)
        
        mirror_world._docker_client = mock_client
        
        # Wywołaj z force=True (domyślnie)
        result = await mirror_world._stop_and_remove_container("stubborn-container")
        
        # Sprawdź że użyto kill jako fallback
        assert result is True
        mock_container.stop.assert_called_once()
        mock_container.kill.assert_called_once()
        mock_container.remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_and_remove_container_docker_unavailable(self, mirror_world):
        """Test gdy Docker SDK nie jest dostępne."""
        # Wymuszamy _docker_client = None (symulacja braku Docker)
        mirror_world._docker_client = None
        
        # Mock _get_docker_client żeby zwracał None
        mirror_world._get_docker_client = MagicMock(return_value=None)
        
        result = await mirror_world._stop_and_remove_container("any-container")
        
        # Powinno zwrócić False - operacja niemożliwa bez Docker
        assert result is False

    @pytest.mark.asyncio
    async def test_destroy_instance_calls_docker_cleanup(self, mirror_world, tmp_path):
        """Test że destroy_instance wywołuje cleanup kontenera Docker."""
        # Przygotuj instancję z kontenerem
        instance_id = "test-instance"
        workspace_path = tmp_path / "instance_workspace"
        workspace_path.mkdir()
        
        instance_info = InstanceInfo(
            instance_id=instance_id,
            port=8080,
            branch_name="test-branch",
            workspace_path=workspace_path,
            container_name="venom-shadow-test",
            status="running",
        )
        
        mirror_world.instances[instance_id] = instance_info
        
        # Mock _stop_and_remove_container
        mirror_world._stop_and_remove_container = AsyncMock(return_value=True)
        
        # Wywołaj destroy_instance
        result = await mirror_world.destroy_instance(instance_id, cleanup=True)
        
        # Sprawdź że kontener został zatrzymany
        assert result is True
        mirror_world._stop_and_remove_container.assert_called_once_with(
            "venom-shadow-test", timeout=10, force=True
        )

    @pytest.mark.asyncio
    async def test_destroy_instance_without_container(self, mirror_world, tmp_path):
        """Test destroy_instance gdy instancja nie ma kontenera."""
        # Przygotuj instancję bez kontenera
        instance_id = "test-instance-no-container"
        workspace_path = tmp_path / "instance_workspace2"
        workspace_path.mkdir()
        
        instance_info = InstanceInfo(
            instance_id=instance_id,
            port=8080,
            branch_name="test-branch",
            workspace_path=workspace_path,
            container_name=None,  # Brak kontenera
            status="running",
        )
        
        mirror_world.instances[instance_id] = instance_info
        
        # Mock _stop_and_remove_container (nie powinno być wywołane)
        mirror_world._stop_and_remove_container = AsyncMock()
        
        # Wywołaj destroy_instance
        result = await mirror_world.destroy_instance(instance_id, cleanup=True)
        
        # Sprawdź że kontener cleanup nie został wywołany
        assert result is True
        mirror_world._stop_and_remove_container.assert_not_called()

    def test_get_docker_client_lazy_init(self, mirror_world):
        """Test lazy initialization Docker client."""
        # Początkowo None
        assert mirror_world._docker_client is None
        
        # Mock docker.from_env
        with patch('venom_core.infrastructure.mirror_world.docker') as mock_docker_module:
            mock_client = MagicMock()
            mock_docker_module.from_env = MagicMock(return_value=mock_client)
            
            # Pierwsze wywołanie - inicjalizacja
            client1 = mirror_world._get_docker_client()
            assert client1 is mock_client
            mock_docker_module.from_env.assert_called_once()
            
            # Drugie wywołanie - użycie cached client
            client2 = mirror_world._get_docker_client()
            assert client2 is mock_client
            # Nie powinno wywołać from_env ponownie
            assert mock_docker_module.from_env.call_count == 1

    def test_get_docker_client_unavailable(self, mirror_world):
        """Test gdy Docker SDK nie jest dostępne."""
        # Mock _DOCKER_AVAILABLE = False
        with patch('venom_core.infrastructure.mirror_world._DOCKER_AVAILABLE', False):
            client = mirror_world._get_docker_client()
            
            # Powinno zwrócić None
            assert client is None
