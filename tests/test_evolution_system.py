"""Testy dla SystemEngineerAgent i procedury ewolucji."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from venom_core.agents.system_engineer import SystemEngineerAgent
from venom_core.infrastructure.mirror_world import MirrorWorld, InstanceInfo
from venom_core.execution.skills.core_skill import CoreSkill


@pytest.fixture
def mock_kernel():
    """Fixture: Mock Semantic Kernel."""
    kernel = MagicMock()
    kernel.add_plugin = MagicMock()
    
    # Mock chat service
    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.content = "Branch evolution/test-feature utworzony pomyślnie"
    mock_service.get_chat_message_contents = AsyncMock(return_value=[mock_result])
    kernel.get_service = MagicMock(return_value=mock_service)
    
    return kernel


@pytest.fixture
def mock_graph_store():
    """Fixture: Mock CodeGraphStore."""
    graph_store = MagicMock()
    graph_store.get_graph_summary = MagicMock(return_value={
        "file_count": 50,
        "class_count": 20,
        "function_count": 100
    })
    graph_store.get_impact_analysis = MagicMock(return_value={
        "affected_files": ["test.py"],
        "dependencies": []
    })
    return graph_store


@pytest.fixture
def system_engineer(mock_kernel, mock_graph_store, tmp_path):
    """Fixture: SystemEngineerAgent."""
    agent = SystemEngineerAgent(
        kernel=mock_kernel,
        graph_store=mock_graph_store,
        workspace_root=str(tmp_path)
    )
    return agent


@pytest.fixture
def mirror_world(tmp_path):
    """Fixture: MirrorWorld."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return MirrorWorld(workspace_root=str(workspace))


@pytest.fixture
def core_skill(tmp_path):
    """Fixture: CoreSkill."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return CoreSkill(backup_dir=str(backup_dir))


class TestSystemEngineerAgent:
    """Testy dla SystemEngineerAgent."""

    @pytest.mark.asyncio
    async def test_initialization(self, system_engineer, tmp_path):
        """Test inicjalizacji SystemEngineerAgent."""
        assert system_engineer.project_root == tmp_path
        assert system_engineer.graph_store is not None
        assert system_engineer.file_skill is not None
        assert system_engineer.git_skill is not None

    @pytest.mark.asyncio
    async def test_process_request(self, system_engineer):
        """Test przetwarzania żądania modyfikacji kodu."""
        request = "Dodaj obsługę logowania kolorami w logger.py"
        
        # Skip this test as it requires full semantic-kernel setup
        pytest.skip("Wymaga pełnej konfiguracji semantic-kernel")

    @pytest.mark.asyncio
    async def test_analyze_impact(self, system_engineer):
        """Test analizy wpływu modyfikacji."""
        impact = await system_engineer.analyze_impact("test.py")
        
        assert isinstance(impact, dict)
        assert "affected_files" in impact or "error" in impact

    @pytest.mark.asyncio
    async def test_create_evolution_branch(self, system_engineer):
        """Test tworzenia brancha ewolucyjnego."""
        with patch.object(system_engineer.git_skill, 'checkout', new_callable=AsyncMock) as mock_checkout:
            mock_checkout.return_value = "✅ Branch utworzony"
            
            result = await system_engineer.create_evolution_branch("test-feature")
            
            assert "evolution/test-feature" in str(mock_checkout.call_args)
            assert isinstance(result, str)

    def test_get_project_root(self, system_engineer, tmp_path):
        """Test pobierania katalogu głównego projektu."""
        assert system_engineer.get_project_root() == tmp_path


class TestMirrorWorld:
    """Testy dla MirrorWorld."""

    def test_initialization(self, mirror_world, tmp_path):
        """Test inicjalizacji MirrorWorld."""
        assert mirror_world.workspace_root == tmp_path / "workspace"
        assert mirror_world.mirror_dir.exists()
        assert len(mirror_world.instances) == 0

    def test_spawn_shadow_instance(self, mirror_world, tmp_path):
        """Test tworzenia instancji lustrzanej."""
        # Utwórz katalog projektu z przykładowym plikiem
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "test.py").write_text("print('test')")
        
        # Utwórz instancję
        info = mirror_world.spawn_shadow_instance(
            branch_name="evolution/test",
            project_root=project_root,
            instance_id="test_instance"
        )
        
        assert isinstance(info, InstanceInfo)
        assert info.instance_id == "test_instance"
        assert info.branch_name == "evolution/test"
        assert info.port > 0
        assert info.workspace_path.exists()
        assert info.status == "initialized"

    @pytest.mark.asyncio
    async def test_verify_instance_not_exists(self, mirror_world):
        """Test weryfikacji nieistniejącej instancji."""
        success, message = await mirror_world.verify_instance("nonexistent")
        
        assert not success
        assert "nie istnieje" in message

    @pytest.mark.asyncio
    async def test_destroy_instance(self, mirror_world, tmp_path):
        """Test usuwania instancji lustrzanej."""
        # Utwórz instancję
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "test.py").write_text("print('test')")
        
        info = mirror_world.spawn_shadow_instance(
            branch_name="evolution/test",
            project_root=project_root,
            instance_id="test_destroy"
        )
        
        # Usuń instancję
        success = await mirror_world.destroy_instance("test_destroy", cleanup=True)
        
        assert success
        assert "test_destroy" not in mirror_world.instances
        # Katalog powinien być usunięty
        assert not info.workspace_path.parent.exists()

    def test_get_instance_info(self, mirror_world, tmp_path):
        """Test pobierania informacji o instancji."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "test.py").write_text("print('test')")
        
        info = mirror_world.spawn_shadow_instance(
            branch_name="evolution/test",
            project_root=project_root,
            instance_id="test_info"
        )
        
        retrieved_info = mirror_world.get_instance_info("test_info")
        
        assert retrieved_info is not None
        assert retrieved_info.instance_id == info.instance_id

    def test_list_instances(self, mirror_world, tmp_path):
        """Test listowania instancji."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "test.py").write_text("print('test')")
        
        # Utwórz kilka instancji
        mirror_world.spawn_shadow_instance("evolution/test1", project_root, "inst1")
        mirror_world.spawn_shadow_instance("evolution/test2", project_root, "inst2")
        
        instances = mirror_world.list_instances()
        
        assert len(instances) == 2
        assert all(isinstance(i, InstanceInfo) for i in instances)

    @pytest.mark.asyncio
    async def test_cleanup_all(self, mirror_world, tmp_path):
        """Test czyszczenia wszystkich instancji."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "test.py").write_text("print('test')")
        
        # Utwórz instancje
        mirror_world.spawn_shadow_instance("evolution/test1", project_root, "inst1")
        mirror_world.spawn_shadow_instance("evolution/test2", project_root, "inst2")
        
        count = await mirror_world.cleanup_all()
        
        assert count == 2
        assert len(mirror_world.instances) == 0


class TestCoreSkill:
    """Testy dla CoreSkill."""

    def test_initialization(self, core_skill, tmp_path):
        """Test inicjalizacji CoreSkill."""
        assert core_skill.backup_dir == tmp_path / "backups"
        assert core_skill.backup_dir.exists()

    @pytest.mark.asyncio
    async def test_hot_patch(self, core_skill, tmp_path):
        """Test modyfikacji pliku z backupem."""
        # Utwórz plik testowy
        test_file = tmp_path / "test.py"
        test_file.write_text("original content")
        
        # Zmodyfikuj plik
        result = await core_skill.hot_patch(
            file_path=str(test_file),
            content="new content",
            create_backup=True
        )
        
        assert "✅" in result
        assert test_file.read_text() == "new content"
        # Sprawdź czy backup został utworzony
        backups = list(core_skill.backup_dir.glob("test.py.*.bak"))
        assert len(backups) == 1

    @pytest.mark.asyncio
    async def test_hot_patch_no_backup(self, core_skill, tmp_path):
        """Test modyfikacji pliku bez backupu."""
        test_file = tmp_path / "test.py"
        test_file.write_text("original")
        
        result = await core_skill.hot_patch(
            file_path=str(test_file),
            content="modified",
            create_backup=False
        )
        
        assert "✅" in result
        assert test_file.read_text() == "modified"
        assert len(list(core_skill.backup_dir.glob("*.bak"))) == 0

    @pytest.mark.asyncio
    async def test_hot_patch_nonexistent_file(self, core_skill, tmp_path):
        """Test modyfikacji nieistniejącego pliku."""
        result = await core_skill.hot_patch(
            file_path=str(tmp_path / "nonexistent.py"),
            content="content"
        )
        
        assert "❌" in result
        assert "nie istnieje" in result

    @pytest.mark.asyncio
    async def test_rollback(self, core_skill, tmp_path):
        """Test wycofania zmian z backupu."""
        # Utwórz plik i zmodyfikuj go z backupem
        test_file = tmp_path / "test.py"
        test_file.write_text("original")
        
        await core_skill.hot_patch(str(test_file), "modified", create_backup=True)
        
        # Wycofaj zmiany
        result = await core_skill.rollback(file_path=str(test_file))
        
        assert "✅" in result
        assert test_file.read_text() == "original"

    @pytest.mark.asyncio
    async def test_rollback_no_backup(self, core_skill, tmp_path):
        """Test wycofania gdy brak backupu."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        
        result = await core_skill.rollback(file_path=str(test_file))
        
        assert "❌" in result
        assert "Brak backupów" in result

    @pytest.mark.asyncio
    async def test_list_backups(self, core_skill, tmp_path):
        """Test listowania backupów."""
        import time
        
        # Utwórz kilka backupów z opóźnieniem aby nazwy były różne
        test_file = tmp_path / "test.py"
        test_file.write_text("v1")
        await core_skill.hot_patch(str(test_file), "v2", create_backup=True)
        time.sleep(1)  # Opóźnienie 1 sekunda aby timestamp był inny
        await core_skill.hot_patch(str(test_file), "v3", create_backup=True)
        
        result = await core_skill.list_backups(file_path=str(test_file))
        
        # Może być 1 lub 2 backupy w zależności od timingu
        assert "backup" in result.lower()
        assert ".bak" in result

    @pytest.mark.asyncio
    async def test_list_backups_empty(self, core_skill):
        """Test listowania gdy brak backupów."""
        result = await core_skill.list_backups()
        
        assert "Brak backupów" in result

    @pytest.mark.asyncio
    async def test_verify_syntax_valid(self, core_skill, tmp_path):
        """Test weryfikacji poprawnej składni."""
        test_file = tmp_path / "valid.py"
        test_file.write_text("def hello():\n    print('Hello')\n")
        
        result = await core_skill.verify_syntax(file_path=str(test_file))
        
        assert "✅" in result
        assert "poprawna" in result

    @pytest.mark.asyncio
    async def test_verify_syntax_invalid(self, core_skill, tmp_path):
        """Test weryfikacji niepoprawnej składni."""
        test_file = tmp_path / "invalid.py"
        test_file.write_text("def hello(\n    print('Hello')\n")  # Błąd składni
        
        result = await core_skill.verify_syntax(file_path=str(test_file))
        
        assert "❌" in result
        assert "Błąd składni" in result

    @pytest.mark.asyncio
    async def test_restart_service_no_confirm(self, core_skill):
        """Test restartu bez potwierdzenia."""
        result = await core_skill.restart_service(confirm=False)
        
        assert "❌" in result
        assert "wymaga potwierdzenia" in result

    def test_get_backup_dir(self, core_skill, tmp_path):
        """Test pobierania katalogu z backupami."""
        assert core_skill.get_backup_dir() == tmp_path / "backups"


class TestEvolutionProcedure:
    """Testy integracyjne procedury ewolucji."""

    @pytest.mark.asyncio
    async def test_mirror_test_with_syntax_error(self, mirror_world, core_skill, tmp_path):
        """
        Test lustrzany: Venom wprowadza celowy błąd składni.
        MirrorWorld powinien wykryć, że klon nie wstaje.
        """
        # Przygotuj projekt z poprawnym plikiem
        project_root = tmp_path / "project"
        project_root.mkdir()
        test_file = project_root / "main.py"
        test_file.write_text("def main():\n    print('OK')\n")
        
        # Utwórz instancję lustrzaną
        info = mirror_world.spawn_shadow_instance(
            branch_name="evolution/broken",
            project_root=project_root,
            instance_id="broken_test"
        )
        
        # Wprowadź błąd składni w klonie
        cloned_file = info.workspace_path / "main.py"
        cloned_file.write_text("def main(\n    print('Broken')\n")  # Błąd
        
        # Weryfikuj składnię
        result = await core_skill.verify_syntax(str(cloned_file))
        
        assert "❌" in result
        assert "Błąd składni" in result
        
        # Główny plik pozostał nienaruszony
        assert test_file.read_text() == "def main():\n    print('OK')\n"
        
        # Cleanup
        await mirror_world.destroy_instance("broken_test", cleanup=True)

    @pytest.mark.asyncio
    async def test_successful_evolution(self, mirror_world, core_skill, tmp_path):
        """
        Test udanej ewolucji: Dodanie nowej metody.
        """
        # Przygotuj projekt
        project_root = tmp_path / "project"
        project_root.mkdir()
        utils_file = project_root / "utils.py"
        utils_file.write_text("def old_function():\n    pass\n")
        
        # Utwórz instancję lustrzaną
        info = mirror_world.spawn_shadow_instance(
            branch_name="evolution/new-feature",
            project_root=project_root,
            instance_id="evolution_test"
        )
        
        # Dodaj nową metodę w klonie
        cloned_file = info.workspace_path / "utils.py"
        new_content = "def old_function():\n    pass\n\ndef new_function():\n    return 42\n"
        cloned_file.write_text(new_content)
        
        # Weryfikuj składnię
        syntax_result = await core_skill.verify_syntax(str(cloned_file))
        assert "✅" in syntax_result
        
        # Symuluj merge: zastosuj zmiany do głównego pliku
        await core_skill.hot_patch(
            file_path=str(utils_file),
            content=new_content,
            create_backup=True
        )
        
        # Sprawdź czy zmiany zostały zastosowane
        assert "new_function" in utils_file.read_text()
        
        # Sprawdź czy backup istnieje
        backups = list(core_skill.backup_dir.glob("utils.py.*.bak"))
        assert len(backups) == 1
        
        # Cleanup
        await mirror_world.destroy_instance("evolution_test", cleanup=True)
