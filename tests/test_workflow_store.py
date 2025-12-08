"""Testy jednostkowe dla WorkflowStore."""

import json
import tempfile
from pathlib import Path

import pytest

from venom_core.memory.workflow_store import Workflow, WorkflowStep, WorkflowStore


class TestWorkflowStep:
    """Testy dla WorkflowStep."""

    def test_workflow_step_initialization(self):
        """Test inicjalizacji WorkflowStep."""
        step = WorkflowStep(
            step_id=1,
            action_type="click",
            description="Click button",
            params={"x": 100, "y": 200},
        )

        assert step.step_id == 1
        assert step.action_type == "click"
        assert step.description == "Click button"
        assert step.params == {"x": 100, "y": 200}
        assert step.enabled is True


class TestWorkflow:
    """Testy dla Workflow."""

    def test_workflow_initialization(self):
        """Test inicjalizacji Workflow."""
        workflow = Workflow(
            workflow_id="test_workflow",
            name="Test Workflow",
            description="Test description",
        )

        assert workflow.workflow_id == "test_workflow"
        assert workflow.name == "Test Workflow"
        assert workflow.description == "Test description"
        assert len(workflow.steps) == 0
        assert workflow.created_at is not None


class TestWorkflowStore:
    """Testy dla WorkflowStore."""

    @pytest.fixture
    def temp_workspace(self):
        """Fixture: tymczasowy katalog workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def workflow_store(self, temp_workspace):
        """Fixture: WorkflowStore."""
        return WorkflowStore(workspace_root=temp_workspace)

    @pytest.fixture
    def sample_workflow(self):
        """Fixture: przykładowy workflow."""
        return Workflow(
            workflow_id="test_workflow",
            name="Test Workflow",
            description="Test description",
            steps=[
                WorkflowStep(
                    step_id=1,
                    action_type="click",
                    description="Click button",
                    params={"element_description": "submit button"},
                ),
                WorkflowStep(
                    step_id=2,
                    action_type="type",
                    description="Type text",
                    params={"text": "Hello World"},
                ),
            ],
        )

    def test_initialization(self, workflow_store, temp_workspace):
        """Test inicjalizacji WorkflowStore."""
        assert workflow_store.workspace_root == Path(temp_workspace)
        assert workflow_store.workflows_dir.exists()
        assert len(workflow_store.workflows_cache) == 0

    def test_save_workflow(self, workflow_store, sample_workflow):
        """Test zapisywania workflow."""
        path = workflow_store.save_workflow(sample_workflow)

        assert path is not None
        assert Path(path).exists()

        # Sprawdź czy jest w cache
        assert sample_workflow.workflow_id in workflow_store.workflows_cache

    def test_load_workflow(self, workflow_store, sample_workflow):
        """Test ładowania workflow."""
        # Zapisz
        workflow_store.save_workflow(sample_workflow)

        # Wyczyść cache
        workflow_store.workflows_cache.clear()

        # Załaduj
        loaded = workflow_store.load_workflow(sample_workflow.workflow_id)

        assert loaded is not None
        assert loaded.workflow_id == sample_workflow.workflow_id
        assert loaded.name == sample_workflow.name
        assert len(loaded.steps) == 2

    def test_load_workflow_from_cache(self, workflow_store, sample_workflow):
        """Test ładowania workflow z cache."""
        # Zapisz (dodaje do cache)
        workflow_store.save_workflow(sample_workflow)

        # Załaduj (powinno użyć cache)
        loaded = workflow_store.load_workflow(sample_workflow.workflow_id)

        assert loaded is sample_workflow  # Ten sam obiekt

    def test_load_nonexistent_workflow(self, workflow_store):
        """Test ładowania nieistniejącego workflow."""
        loaded = workflow_store.load_workflow("nonexistent")
        assert loaded is None

    def test_list_workflows(self, workflow_store, sample_workflow):
        """Test listowania workflow."""
        # Zapisz kilka workflow
        workflow_store.save_workflow(sample_workflow)

        workflow2 = Workflow(
            workflow_id="workflow2",
            name="Second Workflow",
            description="Another workflow",
        )
        workflow_store.save_workflow(workflow2)

        # Listuj
        workflows = workflow_store.list_workflows()

        assert len(workflows) == 2
        assert any(w["workflow_id"] == "test_workflow" for w in workflows)
        assert any(w["workflow_id"] == "workflow2" for w in workflows)

    def test_delete_workflow(self, workflow_store, sample_workflow):
        """Test usuwania workflow."""
        # Zapisz
        workflow_store.save_workflow(sample_workflow)

        # Usuń
        result = workflow_store.delete_workflow(sample_workflow.workflow_id)

        assert result is True
        assert sample_workflow.workflow_id not in workflow_store.workflows_cache

        # Sprawdź czy plik został usunięty
        workflow_file = workflow_store.workflows_dir / f"{sample_workflow.workflow_id}.json"
        assert not workflow_file.exists()

    def test_delete_nonexistent_workflow(self, workflow_store):
        """Test usuwania nieistniejącego workflow."""
        result = workflow_store.delete_workflow("nonexistent")
        assert result is False

    def test_update_step(self, workflow_store, sample_workflow):
        """Test aktualizacji kroku."""
        # Zapisz
        workflow_store.save_workflow(sample_workflow)

        # Aktualizuj krok
        result = workflow_store.update_step(
            sample_workflow.workflow_id,
            1,
            {"description": "Updated description", "enabled": False},
        )

        assert result is True

        # Załaduj i sprawdź
        loaded = workflow_store.load_workflow(sample_workflow.workflow_id)
        step = next(s for s in loaded.steps if s.step_id == 1)
        assert step.description == "Updated description"
        assert step.enabled is False

    def test_update_nonexistent_step(self, workflow_store, sample_workflow):
        """Test aktualizacji nieistniejącego kroku."""
        workflow_store.save_workflow(sample_workflow)

        result = workflow_store.update_step(sample_workflow.workflow_id, 999, {"description": "Test"})

        assert result is False

    def test_add_step(self, workflow_store, sample_workflow):
        """Test dodawania kroku."""
        workflow_store.save_workflow(sample_workflow)

        new_step = WorkflowStep(
            step_id=0,  # Będzie nadpisane
            action_type="wait",
            description="Wait 2 seconds",
            params={"duration": 2.0},
        )

        result = workflow_store.add_step(sample_workflow.workflow_id, new_step)

        assert result is True

        # Załaduj i sprawdź
        loaded = workflow_store.load_workflow(sample_workflow.workflow_id)
        assert len(loaded.steps) == 3
        assert loaded.steps[-1].action_type == "wait"
        assert loaded.steps[-1].step_id == 3  # Auto-increment

    def test_add_step_at_position(self, workflow_store, sample_workflow):
        """Test dodawania kroku na określonej pozycji."""
        workflow_store.save_workflow(sample_workflow)

        new_step = WorkflowStep(
            step_id=0,
            action_type="wait",
            description="Wait 1 second",
            params={"duration": 1.0},
        )

        result = workflow_store.add_step(sample_workflow.workflow_id, new_step, position=1)

        assert result is True

        # Załaduj i sprawdź
        loaded = workflow_store.load_workflow(sample_workflow.workflow_id)
        assert len(loaded.steps) == 3
        assert loaded.steps[1].action_type == "wait"

    def test_remove_step(self, workflow_store, sample_workflow):
        """Test usuwania kroku."""
        workflow_store.save_workflow(sample_workflow)

        result = workflow_store.remove_step(sample_workflow.workflow_id, 1)

        assert result is True

        # Załaduj i sprawdź
        loaded = workflow_store.load_workflow(sample_workflow.workflow_id)
        assert len(loaded.steps) == 1
        assert all(s.step_id != 1 for s in loaded.steps)

    def test_remove_nonexistent_step(self, workflow_store, sample_workflow):
        """Test usuwania nieistniejącego kroku."""
        workflow_store.save_workflow(sample_workflow)

        result = workflow_store.remove_step(sample_workflow.workflow_id, 999)

        assert result is False

    def test_export_to_python(self, workflow_store, sample_workflow, temp_workspace):
        """Test eksportu workflow do Python."""
        workflow_store.save_workflow(sample_workflow)

        output_path = workflow_store.export_to_python(sample_workflow.workflow_id)

        assert output_path is not None
        assert Path(output_path).exists()

        # Sprawdź zawartość
        content = Path(output_path).read_text()
        assert "async def test_workflow" in content
        assert "GhostAgent" in content
        assert "vision_click" in content
        assert "keyboard_type" in content

    def test_export_nonexistent_workflow(self, workflow_store):
        """Test eksportu nieistniejącego workflow."""
        result = workflow_store.export_to_python("nonexistent")
        assert result is None

    def test_search_workflows(self, workflow_store):
        """Test wyszukiwania workflow."""
        # Zapisz kilka workflow
        workflow1 = Workflow(
            workflow_id="login_workflow",
            name="Login Workflow",
            description="Logs into the application",
        )
        workflow_store.save_workflow(workflow1)

        workflow2 = Workflow(
            workflow_id="logout_workflow",
            name="Logout Workflow",
            description="Logs out from the application",
        )
        workflow_store.save_workflow(workflow2)

        workflow3 = Workflow(
            workflow_id="send_email",
            name="Send Email",
            description="Sends an email report",
        )
        workflow_store.save_workflow(workflow3)

        # Wyszukaj "log"
        results = workflow_store.search_workflows("log")
        assert len(results) == 2  # login i logout

        # Wyszukaj "email"
        results = workflow_store.search_workflows("email")
        assert len(results) == 1

    def test_workflow_with_disabled_steps(self, workflow_store):
        """Test workflow z wyłączonymi krokami."""
        workflow = Workflow(
            workflow_id="test_workflow",
            name="Test Workflow",
            description="Test",
            steps=[
                WorkflowStep(
                    step_id=1,
                    action_type="click",
                    description="Step 1",
                    params={},
                    enabled=True,
                ),
                WorkflowStep(
                    step_id=2,
                    action_type="click",
                    description="Step 2",
                    params={},
                    enabled=False,  # Wyłączony
                ),
            ],
        )

        workflow_store.save_workflow(workflow)
        output_path = workflow_store.export_to_python(workflow.workflow_id)

        content = Path(output_path).read_text()
        assert "DISABLED: Krok 2" in content
