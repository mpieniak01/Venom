"""Testy jednostkowe dla modułów ewolucji (bez zależności zewnętrznych)."""

import pytest

from venom_core.execution.skills.core_skill import CoreSkill
from venom_core.infrastructure.mirror_world import InstanceInfo, MirrorWorld


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


class TestMirrorWorldBasic:
    """Podstawowe testy MirrorWorld bez zależności."""

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
            instance_id="test_instance",
        )

        assert isinstance(info, InstanceInfo)
        assert info.instance_id == "test_instance"
        assert info.branch_name == "evolution/test"
        assert info.port > 0
        assert info.workspace_path.exists()
        assert info.status == "initialized"

    @pytest.mark.asyncio
    async def test_destroy_instance(self, mirror_world, tmp_path):
        """Test usuwania instancji lustrzanej."""
        # Utwórz instancję
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "test.py").write_text("print('test')")

        mirror_world.spawn_shadow_instance(
            branch_name="evolution/test",
            project_root=project_root,
            instance_id="test_destroy",
        )

        # Usuń instancję
        success = await mirror_world.destroy_instance("test_destroy", cleanup=True)

        assert success
        assert "test_destroy" not in mirror_world.instances

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


class TestCoreSkillBasic:
    """Podstawowe testy CoreSkill."""

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
        result = core_skill.hot_patch(
            file_path=str(test_file), content="new content", create_backup=True
        )

        assert "✅" in result
        assert test_file.read_text() == "new content"
        # Sprawdź czy backup został utworzony
        backups = list(core_skill.backup_dir.glob("test.py.*.bak"))
        assert len(backups) == 1

    @pytest.mark.asyncio
    async def test_rollback(self, core_skill, tmp_path):
        """Test wycofania zmian z backupu."""
        # Utwórz plik i zmodyfikuj go z backupem
        test_file = tmp_path / "test.py"
        test_file.write_text("original")

        core_skill.hot_patch(str(test_file), "modified", create_backup=True)

        # Wycofaj zmiany
        result = core_skill.rollback(file_path=str(test_file))

        assert "✅" in result
        assert test_file.read_text() == "original"

    @pytest.mark.asyncio
    async def test_verify_syntax_valid(self, core_skill, tmp_path):
        """Test weryfikacji poprawnej składni."""
        test_file = tmp_path / "valid.py"
        test_file.write_text("def hello():\n    print('Hello')\n")

        result = core_skill.verify_syntax(file_path=str(test_file))

        assert "✅" in result
        assert "poprawna" in result

    @pytest.mark.asyncio
    async def test_verify_syntax_invalid(self, core_skill, tmp_path):
        """Test weryfikacji niepoprawnej składni."""
        test_file = tmp_path / "invalid.py"
        test_file.write_text("def hello(\n    print('Hello')\n")  # Błąd składni

        result = core_skill.verify_syntax(file_path=str(test_file))

        assert "❌" in result
        assert "Błąd składni" in result


class TestEvolutionScenarios:
    """Scenariusze testowe procedury ewolucji."""

    @pytest.mark.asyncio
    async def test_mirror_test_with_syntax_error(
        self, mirror_world, core_skill, tmp_path
    ):
        """
        Test lustrzany: Wprowadzenie błędu składni.
        MirrorWorld wykrywa problem, główny kod pozostaje nienaruszony.
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
            instance_id="broken_test",
        )

        # Wprowadź błąd składni w klonie
        cloned_file = info.workspace_path / "main.py"
        cloned_file.write_text("def main(\n    print('Broken')\n")  # Błąd

        # Weryfikuj składnię
        result = core_skill.verify_syntax(str(cloned_file))

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
        Klon przechodzi testy, zmiany są aplikowane.
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
            instance_id="evolution_test",
        )

        # Dodaj nową metodę w klonie
        cloned_file = info.workspace_path / "utils.py"
        new_content = (
            "def old_function():\n    pass\n\ndef new_function():\n    return 42\n"
        )
        cloned_file.write_text(new_content)

        # Weryfikuj składnię
        syntax_result = core_skill.verify_syntax(str(cloned_file))
        assert "✅" in syntax_result

        # Symuluj merge: zastosuj zmiany do głównego pliku
        core_skill.hot_patch(
            file_path=str(utils_file), content=new_content, create_backup=True
        )

        # Sprawdź czy zmiany zostały zastosowane
        assert "new_function" in utils_file.read_text()

        # Sprawdź czy backup istnieje
        backups = list(core_skill.backup_dir.glob("utils.py.*.bak"))
        assert len(backups) == 1

        # Cleanup
        await mirror_world.destroy_instance("evolution_test", cleanup=True)
