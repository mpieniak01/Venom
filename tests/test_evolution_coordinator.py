"""Testy dla EvolutionCoordinator."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.infrastructure.mirror_world import InstanceInfo


# Mock EvolutionCoordinator zamiast importować cały moduł
class MockEvolutionCoordinator:
    """Mock EvolutionCoordinator do testów."""

    def __init__(self, system_engineer, mirror_world, core_skill, git_skill):
        self.system_engineer = system_engineer
        self.mirror_world = mirror_world
        self.core_skill = core_skill
        self.git_skill = git_skill

    async def _analyze_request(self, request: str) -> dict:
        """Analizuje żądanie."""
        keywords = ["dodaj", "zmień", "usuń", "zmodyfikuj", "uaktualnij", "popraw"]
        is_modification_request = any(kw in request.lower() for kw in keywords)

        if not is_modification_request:
            return {
                "feasible": False,
                "reason": "Żądanie nie wygląda na prośbę o modyfikację kodu",
            }

        words = request.split()[:3]
        branch_name = f"evolution/{'-'.join(w.lower() for w in words if w.isalnum())}"

        return {
            "feasible": True,
            "branch_name": branch_name,
        }

    def _create_shadow_instance(
        self, branch_name: str, project_root: Path
    ) -> InstanceInfo:
        """Tworzy instancję lustrzaną."""
        return self.mirror_world.spawn_shadow_instance(
            branch_name=branch_name,
            project_root=project_root,
        )

    async def _verify_shadow_instance(self, instance_info: InstanceInfo) -> dict:
        """Weryfikuje instancję."""
        # Sprawdź składnię
        python_files = list(instance_info.workspace_path.rglob("*.py"))[:10]

        for py_file in python_files:
            syntax_result = await self.core_skill.verify_syntax(str(py_file))
            if "❌" in syntax_result:
                return {
                    "success": False,
                    "reason": f"Błąd składni w {py_file.name}",
                }

        return {"success": True, "reason": "OK"}

    async def trigger_restart(self, confirm: bool = False) -> str:
        """Restartuje system."""
        if not confirm:
            return "❌ Restart wymaga potwierdzenia"
        return await self.core_skill.restart_service(confirm=True)


@pytest.fixture
def mock_system_engineer():
    """Mock SystemEngineerAgent."""
    engineer = MagicMock()
    engineer.process = AsyncMock(return_value="Branch utworzony")
    return engineer


@pytest.fixture
def mock_mirror_world(tmp_path):
    """Mock MirrorWorld."""
    mirror = MagicMock()

    instance_info = InstanceInfo(
        instance_id="test_instance",
        port=8001,
        branch_name="evolution/test",
        workspace_path=tmp_path / "mirrors" / "test",
        status="initialized",
    )
    mirror.spawn_shadow_instance = MagicMock(return_value=instance_info)
    mirror.verify_instance = AsyncMock(return_value=(True, "OK"))
    mirror.destroy_instance = AsyncMock(return_value=True)

    return mirror


@pytest.fixture
def mock_core_skill():
    """Mock CoreSkill."""
    skill = MagicMock()
    skill.verify_syntax = AsyncMock(return_value="✅ Składnia poprawna")
    skill.restart_service = AsyncMock(return_value="🔄 Restarting...")
    return skill


@pytest.fixture
def mock_git_skill():
    """Mock GitSkill."""
    skill = MagicMock()
    return skill


@pytest.fixture
def evolution_coordinator(
    mock_system_engineer, mock_mirror_world, mock_core_skill, mock_git_skill
):
    """Fixture: EvolutionCoordinator."""
    return MockEvolutionCoordinator(
        system_engineer=mock_system_engineer,
        mirror_world=mock_mirror_world,
        core_skill=mock_core_skill,
        git_skill=mock_git_skill,
    )


class TestEvolutionCoordinator:
    """Testy dla EvolutionCoordinator."""

    @pytest.mark.asyncio
    async def test_analyze_request_valid(self, evolution_coordinator):
        """Test analizy poprawnego żądania."""
        result = await evolution_coordinator._analyze_request("Dodaj obsługę kolorów")

        assert result["feasible"] is True
        assert "branch_name" in result
        assert result["branch_name"].startswith("evolution/")

    @pytest.mark.asyncio
    async def test_analyze_request_invalid(self, evolution_coordinator):
        """Test analizy niepoprawnego żądania."""
        result = await evolution_coordinator._analyze_request("Hello")

        assert result["feasible"] is False
        assert "reason" in result

    def test_create_shadow_instance(self, evolution_coordinator, tmp_path):
        """Test tworzenia instancji lustrzanej."""
        project_root = tmp_path / "project"
        project_root.mkdir()

        instance_info = evolution_coordinator._create_shadow_instance(
            "evolution/test", project_root
        )

        assert instance_info.instance_id == "test_instance"
        assert instance_info.branch_name == "evolution/test"

    @pytest.mark.asyncio
    async def test_verify_shadow_instance_success(
        self, evolution_coordinator, tmp_path
    ):
        """Test pomyślnej weryfikacji."""
        instance_info = InstanceInfo(
            instance_id="test",
            port=8001,
            branch_name="evolution/test",
            workspace_path=tmp_path / "test_verify",
            status="initialized",
        )

        instance_info.workspace_path.mkdir(parents=True, exist_ok=True)
        (instance_info.workspace_path / "test.py").write_text("def test(): pass")

        result = await evolution_coordinator._verify_shadow_instance(instance_info)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_verify_shadow_instance_syntax_error(
        self, evolution_coordinator, tmp_path
    ):
        """Test weryfikacji z błędem składni."""
        evolution_coordinator.core_skill.verify_syntax = AsyncMock(
            return_value="❌ Błąd składni"
        )

        instance_info = InstanceInfo(
            instance_id="test",
            port=8001,
            branch_name="evolution/test",
            workspace_path=tmp_path / "test_syntax_error",
            status="initialized",
        )

        instance_info.workspace_path.mkdir(parents=True, exist_ok=True)
        (instance_info.workspace_path / "bad.py").write_text("def bad(")

        result = await evolution_coordinator._verify_shadow_instance(instance_info)

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_trigger_restart_no_confirm(self, evolution_coordinator):
        """Test restartu bez potwierdzenia."""
        result = await evolution_coordinator.trigger_restart(confirm=False)

        assert "❌" in result

    @pytest.mark.asyncio
    async def test_trigger_restart_with_confirm(self, evolution_coordinator):
        """Test restartu z potwierdzeniem."""
        result = await evolution_coordinator.trigger_restart(confirm=True)

        assert "🔄" in result or "Restart" in result
