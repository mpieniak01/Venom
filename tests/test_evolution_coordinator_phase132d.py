"""Testy dla Evolution Coordinator - Phase 132D (test execution & merge automation)."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from venom_core.core.evolution_coordinator import EvolutionCoordinator
from venom_core.infrastructure.mirror_world import InstanceInfo


@pytest.fixture
def mock_system_engineer():
    """Mock SystemEngineerAgent."""
    mock = MagicMock()
    mock.process = AsyncMock(return_value="Changes implemented")
    return mock


@pytest.fixture
def mock_mirror_world(tmp_path):
    """Mock MirrorWorld."""
    mock = MagicMock()
    
    # Mock spawn_shadow_instance
    workspace_path = tmp_path / "shadow_workspace"
    workspace_path.mkdir()
    
    instance_info = InstanceInfo(
        instance_id="test-instance",
        port=8080,
        branch_name="test-branch",
        workspace_path=workspace_path,
        container_name="test-container",
        status="running",
    )
    
    mock.spawn_shadow_instance = MagicMock(return_value=instance_info)
    mock.verify_instance = AsyncMock(return_value=(True, "OK"))
    mock.destroy_instance = AsyncMock(return_value=True)
    
    return mock


@pytest.fixture
def mock_core_skill():
    """Mock CoreSkill."""
    mock = MagicMock()
    mock.verify_syntax = AsyncMock(return_value="✅ Syntax OK")
    return mock


@pytest.fixture
def mock_git_skill():
    """Mock GitSkill."""
    mock = MagicMock()
    mock.merge = AsyncMock(return_value="✅ Pomyślnie scalono test-branch do main")
    
    # Mock _get_repo with proper return values
    mock_repo = MagicMock()
    mock_active_branch = MagicMock()
    mock_active_branch.name = "main"
    mock_repo.active_branch = mock_active_branch
    mock_repo.index.unmerged_blobs.return_value = {}
    mock_repo.git.merge = MagicMock()
    mock._get_repo = MagicMock(return_value=mock_repo)
    
    return mock


@pytest.fixture
def mock_tester_agent():
    """Mock TesterAgent."""
    mock = MagicMock()
    mock.process = AsyncMock(
        return_value="✅ Wszystkie testy smoke przeszły pomyślnie. Strona się ładuje, API odpowiada."
    )
    return mock


@pytest.fixture
def coordinator(mock_system_engineer, mock_mirror_world, mock_core_skill, mock_git_skill):
    """Evolution Coordinator z mock dependencies."""
    return EvolutionCoordinator(
        system_engineer=mock_system_engineer,
        mirror_world=mock_mirror_world,
        core_skill=mock_core_skill,
        git_skill=mock_git_skill,
        tester_agent=None,  # Domyślnie None, testy dodają gdy potrzeba
    )


class TestEvolutionCoordinatorTestExecution:
    """Testy dla funkcjonalności uruchamiania testów w Shadow Instance (PR-132D)."""

    @pytest.mark.asyncio
    async def test_verify_shadow_instance_runs_tests_when_tester_available(
        self, coordinator, mock_tester_agent, tmp_path
    ):
        """Test że weryfikacja uruchamia testy gdy TesterAgent jest dostępny."""
        # Dodaj TesterAgent do coordinatora
        coordinator.tester_agent = mock_tester_agent
        
        # Przygotuj instance_info
        workspace_path = tmp_path / "test_workspace"
        workspace_path.mkdir()
        (workspace_path / "test.py").write_text("print('hello')")
        
        instance_info = InstanceInfo(
            instance_id="test-instance",
            port=8080,
            branch_name="test-branch",
            workspace_path=workspace_path,
            status="running",
        )
        
        # Mock verify_instance
        coordinator.mirror_world.verify_instance = AsyncMock(return_value=(True, "OK"))
        
        # Wywołaj weryfikację
        result = await coordinator._verify_shadow_instance(instance_info)
        
        # Sprawdź że testy zostały uruchomione
        assert result["success"] is True
        mock_tester_agent.process.assert_called_once()
        
        # Sprawdź że zadanie testowe zawiera właściwy URL
        call_args = mock_tester_agent.process.call_args[0][0]
        assert "http://localhost:8080" in call_args
        assert "smoke" in call_args.lower()

    @pytest.mark.asyncio
    async def test_verify_shadow_instance_fails_on_test_errors(
        self, coordinator, mock_tester_agent, tmp_path
    ):
        """Test że weryfikacja zawodzi gdy testy wykryją błędy."""
        # Dodaj TesterAgent z błędnym wynikiem
        coordinator.tester_agent = mock_tester_agent
        mock_tester_agent.process = AsyncMock(
            return_value="❌ Błąd: Strona nie odpowiada, timeout po 30s"
        )
        
        # Przygotuj instance_info
        workspace_path = tmp_path / "test_workspace"
        workspace_path.mkdir()
        (workspace_path / "test.py").write_text("print('hello')")
        
        instance_info = InstanceInfo(
            instance_id="test-instance",
            port=8080,
            branch_name="test-branch",
            workspace_path=workspace_path,
            status="running",
        )
        
        coordinator.mirror_world.verify_instance = AsyncMock(return_value=(True, "OK"))
        
        # Wywołaj weryfikację
        result = await coordinator._verify_shadow_instance(instance_info)
        
        # Sprawdź że weryfikacja zawodzi
        assert result["success"] is False
        assert "problemy" in result["reason"].lower() or "błąd" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_verify_shadow_instance_handles_test_timeout(
        self, coordinator, mock_tester_agent, tmp_path
    ):
        """Test że weryfikacja obsługuje timeout testów."""
        import asyncio
        
        # Dodaj TesterAgent który się zawiesza
        coordinator.tester_agent = mock_tester_agent
        
        async def slow_test(*args, **kwargs):
            await asyncio.sleep(200)  # Dłużej niż timeout (120s)
            return "Done"
        
        mock_tester_agent.process = slow_test
        
        # Przygotuj instance_info
        workspace_path = tmp_path / "test_workspace"
        workspace_path.mkdir()
        (workspace_path / "test.py").write_text("print('hello')")
        
        instance_info = InstanceInfo(
            instance_id="test-instance",
            port=8080,
            branch_name="test-branch",
            workspace_path=workspace_path,
            status="running",
        )
        
        coordinator.mirror_world.verify_instance = AsyncMock(return_value=(True, "OK"))
        
        # Wywołaj weryfikację (powinno timeout)
        result = await coordinator._verify_shadow_instance(instance_info)
        
        # Sprawdź że weryfikacja zawodzi z powodu timeout
        assert result["success"] is False
        assert "timeout" in result["reason"].lower() or "limit czasu" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_verify_shadow_instance_without_tester_skips_tests(
        self, coordinator, tmp_path
    ):
        """Test że weryfikacja pomija testy gdy TesterAgent nie jest dostępny."""
        # coordinator.tester_agent jest None
        
        workspace_path = tmp_path / "test_workspace"
        workspace_path.mkdir()
        (workspace_path / "test.py").write_text("print('hello')")
        
        instance_info = InstanceInfo(
            instance_id="test-instance",
            port=8080,
            branch_name="test-branch",
            workspace_path=workspace_path,
            status="running",
        )
        
        coordinator.mirror_world.verify_instance = AsyncMock(return_value=(True, "OK"))
        
        # Wywołaj weryfikację
        result = await coordinator._verify_shadow_instance(instance_info)
        
        # Sprawdź że weryfikacja przechodzi (pomimo braku testów)
        assert result["success"] is True


class TestEvolutionCoordinatorMergeAutomation:
    """Testy dla funkcjonalności automatycznego merge (PR-132D)."""

    @pytest.mark.asyncio
    async def test_merge_changes_success(self, coordinator, mock_git_skill):
        """Test pomyślnego merge."""
        coordinator.git_skill = mock_git_skill
        
        result = await coordinator._merge_changes("feature-branch")
        
        # Sprawdź że merge został wywołany
        assert result["merged"] is True
        assert result["source_branch"] == "feature-branch"
        assert result["target_branch"] == "main"
        mock_git_skill.merge.assert_called_once_with("feature-branch")

    @pytest.mark.asyncio
    async def test_merge_changes_handles_conflicts(self, coordinator, mock_git_skill):
        """Test obsługi konfliktów merge."""
        coordinator.git_skill = mock_git_skill
        
        # Mock konflikt
        mock_git_skill.merge = AsyncMock(
            return_value="⚠️ CONFLICT: Wystąpiły konflikty podczas merge"
        )
        
        # Mock repo dla rollback
        mock_repo = MagicMock()
        mock_repo.git.merge = MagicMock()
        mock_git_skill._get_repo = MagicMock(return_value=mock_repo)
        
        result = await coordinator._merge_changes("conflict-branch")
        
        # Sprawdź że merge zawodzi i rollback został wykonany
        assert result["merged"] is False
        assert "konflikty" in result["reason"].lower()
        mock_repo.git.merge.assert_called_once_with("--abort")

    @pytest.mark.asyncio
    async def test_merge_changes_handles_errors(self, coordinator, mock_git_skill):
        """Test obsługi błędów podczas merge."""
        coordinator.git_skill = mock_git_skill
        
        # Mock błąd
        mock_git_skill.merge = AsyncMock(side_effect=Exception("Git error"))
        
        # Mock repo dla rollback
        mock_repo = MagicMock()
        mock_repo.index.unmerged_blobs.return_value = {}
        mock_repo.git.merge = MagicMock()
        mock_git_skill._get_repo = MagicMock(return_value=mock_repo)
        
        result = await coordinator._merge_changes("error-branch")
        
        # Sprawdź że merge zawodzi
        assert result["merged"] is False
        assert "błąd" in result["reason"].lower() or "error" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_merge_changes_rollback_on_unmerged_blobs(self, coordinator, mock_git_skill):
        """Test rollback gdy są unmerged blobs."""
        coordinator.git_skill = mock_git_skill
        
        # Mock błąd podczas merge
        mock_git_skill.merge = AsyncMock(side_effect=Exception("Merge failed"))
        
        # Mock repo z unmerged blobs
        mock_repo = MagicMock()
        mock_repo.index.unmerged_blobs.return_value = {"file.py": "blob"}
        mock_repo.git.merge = MagicMock()
        mock_git_skill._get_repo = MagicMock(return_value=mock_repo)
        
        result = await coordinator._merge_changes("problematic-branch")
        
        # Sprawdź że rollback został wywołany
        assert result["merged"] is False
        mock_repo.git.merge.assert_called_once_with("--abort")


class TestEvolutionCoordinatorIntegration:
    """Testy integracyjne dla pełnego flow ewolucji z testami i merge (PR-132D)."""

    @pytest.mark.asyncio
    async def test_evolve_with_tests_and_merge_success(
        self, coordinator, mock_tester_agent, mock_git_skill, tmp_path
    ):
        """Test pełnego flow ewolucji z testami i merge."""
        # Dodaj TesterAgent i GitSkill
        coordinator.tester_agent = mock_tester_agent
        coordinator.git_skill = mock_git_skill
        
        # Mock SystemEngineer
        coordinator.system_engineer.process = AsyncMock(
            return_value="Zmiany wprowadzone w branchu test-branch"
        )
        
        # Wywołaj evolve
        task_id = uuid4()
        result = await coordinator.evolve(
            task_id=task_id,
            request="Dodaj nową funkcjonalność",
            project_root=tmp_path,
        )
        
        # Sprawdź że proces zakończył się sukcesem
        assert result["success"] is True
        assert result["phase"] == "completed"
        
        # Sprawdź że testy zostały uruchomione
        mock_tester_agent.process.assert_called_once()
        
        # Sprawdź że merge został wykonany
        mock_git_skill.merge.assert_called_once()

    @pytest.mark.asyncio
    async def test_evolve_fails_on_test_failure_no_merge(
        self, coordinator, mock_tester_agent, mock_git_skill, tmp_path
    ):
        """Test że ewolucja nie wykonuje merge gdy testy zawodzą."""
        # Dodaj TesterAgent który zwraca błąd
        coordinator.tester_agent = mock_tester_agent
        mock_tester_agent.process = AsyncMock(
            return_value="❌ Testy nie przeszły - błąd 500 na endpoint /api/health"
        )
        coordinator.git_skill = mock_git_skill
        
        # Mock SystemEngineer
        coordinator.system_engineer.process = AsyncMock(
            return_value="Zmiany wprowadzone"
        )
        
        # Wywołaj evolve
        task_id = uuid4()
        result = await coordinator.evolve(
            task_id=task_id,
            request="Dodaj nową funkcjonalność",
            project_root=tmp_path,
        )
        
        # Sprawdź że proces zawiódł
        assert result["success"] is False
        assert result["phase"] == "verification_failed"
        
        # Sprawdź że merge NIE został wykonany
        mock_git_skill.merge.assert_not_called()
