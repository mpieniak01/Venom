"""Test integracyjny dla FileSkill - zapis i odczyt przez Orchestrator."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.helpers.url_fixtures import LOCALHOST_11434_V1, MOCK_HTTP, local_runtime_id
from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.utils.llm_runtime import LLMRuntimeInfo


@pytest.fixture
def mock_runtime_info():
    """Mock dla get_active_llm_runtime."""
    return LLMRuntimeInfo(
        provider="local",
        model_name="mock-model",
        endpoint=MOCK_HTTP,
        service_type="local",
        mode="LOCAL",
        config_hash="abc123456789",
        runtime_id=local_runtime_id(MOCK_HTTP),
    )


@pytest.fixture(autouse=True)
def patch_runtime(mock_runtime_info):
    """Automatycznie patchuje runtime dla wszystkich testów."""
    with (
        patch(
            "venom_core.utils.llm_runtime.get_active_llm_runtime",
            return_value=mock_runtime_info,
        ),
    ):
        with (
            patch("venom_core.config.SETTINGS") as mock_settings,
            patch(
                "venom_core.core.orchestrator.orchestrator_dispatch.SETTINGS",
                new=mock_settings,
            ),
        ):
            mock_settings.LLM_CONFIG_HASH = "abc123456789"
            yield


@pytest.fixture
def temp_state_file():
    """Fixture dla tymczasowego pliku stanu."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.mark.asyncio
async def test_file_skill_direct_integration(temp_workspace):
    """Test bezpośredniej integracji FileSkill - zapis i odczyt."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Test 1: Zapis pliku
    write_result = await skill.write_file("test.py", "print('Hello World')")
    assert "pomyślnie zapisany" in write_result

    # Weryfikacja fizycznego zapisu
    file_path = Path(temp_workspace) / "test.py"
    assert file_path.exists()
    assert file_path.read_text() == "print('Hello World')"

    # Test 2: Odczyt pliku
    read_result = await skill.read_file("test.py")
    assert read_result == "print('Hello World')"

    # Test 3: Lista plików
    list_result = skill.list_files(".")
    assert "test.py" in list_result

    # Test 4: Sprawdzenie istnienia
    exists_result = skill.file_exists("test.py")
    assert exists_result == "True"

    nonexists_result = skill.file_exists("nonexistent.py")
    assert nonexists_result == "False"


@pytest.mark.asyncio
async def test_orchestrator_with_file_operations(temp_state_file, temp_workspace):
    """Test integracyjny Orchestrator z operacjami plikowymi."""
    # Mock konfiguracji workspace
    with patch("venom_core.config.SETTINGS") as mock_settings:
        mock_settings.WORKSPACE_ROOT = temp_workspace
        mock_settings.STATE_FILE_PATH = temp_state_file
        mock_settings.LLM_SERVICE_TYPE = "local"
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.LLM_MODEL_NAME = "phi3:latest"
        mock_settings.LLM_LOCAL_API_KEY = "venom-local"
        mock_settings.OPENAI_API_KEY = ""

        # Utwórz StateManager i Orchestrator
        state_manager = StateManager(state_file_path=temp_state_file)

        # Mock IntentManager
        with patch(
            "venom_core.core.orchestrator.orchestrator_core.IntentManager"
        ) as mock_intent_cls:
            mock_intent_manager = MagicMock()
            mock_intent_manager.classify_intent = AsyncMock(
                return_value="FILE_OPERATION"
            )
            mock_intent_cls.return_value = mock_intent_manager

            # Mock TaskDispatcher - symuluj operację zapisu pliku
            with patch(
                "venom_core.core.orchestrator.orchestrator_core.TaskDispatcher"
            ) as mock_disp_cls:
                mock_dispatcher = MagicMock()
                # Symuluj odpowiedź agenta po zapisie pliku
                mock_dispatcher.dispatch = AsyncMock(
                    return_value="Plik 'test.py' został pomyślnie zapisany (20 znaków)"
                )
                mock_disp_cls.return_value = mock_dispatcher

                orchestrator = Orchestrator(state_manager)

                # Test submit_task
                request = TaskRequest(content="Stwórz plik test.py z funkcją print")
                response = await orchestrator.submit_task(request)

                assert response.task_id is not None
                assert response.status == "PENDING"

                # Poczekaj na wykonanie zadania
                import asyncio

                await asyncio.sleep(0.5)

                # Sprawdź status zadania
                task = state_manager.get_task(response.task_id)
                assert task is not None
                from venom_core.core.models import TaskStatus

                assert task.status in [
                    TaskStatus.COMPLETED,
                    TaskStatus.PENDING,
                    TaskStatus.PROCESSING,
                ]
