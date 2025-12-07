"""Testy jednostkowe dla Professor Agent."""

import pytest
from pydantic_settings import BaseSettings

from venom_core.agents.professor import Professor
from venom_core.execution.kernel_builder import KernelBuilder


class MockSettings(BaseSettings):
    """Mockowa konfiguracja do testów."""

    LLM_SERVICE_TYPE: str = "local"
    LLM_LOCAL_ENDPOINT: str = "http://localhost:11434/v1"
    LLM_MODEL_NAME: str = "phi3:latest"
    LLM_LOCAL_API_KEY: str = "venom-local"
    OPENAI_API_KEY: str = ""


@pytest.fixture
def kernel():
    """Fixture dla kernela."""
    settings = MockSettings()
    builder = KernelBuilder(settings=settings)
    return builder.build_kernel()


def test_professor_initialization(kernel):
    """Test inicjalizacji Profesora."""
    professor = Professor(kernel)

    assert professor.kernel is not None
    assert professor.dataset_curator is None
    assert professor.gpu_habitat is None
    assert professor.lessons_store is None
    assert len(professor.training_history) == 0


@pytest.mark.asyncio
async def test_professor_process_help(kernel):
    """Test domyślnej odpowiedzi Profesora."""
    professor = Professor(kernel)

    result = await professor.process("help")

    assert "Profesor" in result
    assert "nauki" in result.lower()


def test_professor_should_start_training_without_lessons_store(kernel):
    """Test decyzji o treningu bez LessonsStore."""
    professor = Professor(kernel)

    decision = professor.should_start_training()

    assert decision["should_train"] is False
    assert "LessonsStore" in decision["reason"]


def test_professor_select_training_parameters(kernel):
    """Test doboru parametrów treningowych."""
    professor = Professor(kernel)

    params = professor._select_training_parameters()

    assert "base_model" in params
    assert "lora_rank" in params
    assert "learning_rate" in params
    assert "num_epochs" in params
    assert "max_seq_length" in params
    assert "batch_size" in params

    # Sprawdź domyślne wartości
    assert params["lora_rank"] == Professor.DEFAULT_LORA_RANK
    assert params["learning_rate"] == Professor.DEFAULT_LEARNING_RATE
    assert params["num_epochs"] == Professor.DEFAULT_NUM_EPOCHS


def test_professor_get_learning_status_without_lessons_store(kernel):
    """Test statusu bez LessonsStore."""
    professor = Professor(kernel)

    status = professor._get_learning_status()

    assert "niedostępny" in status.lower()


class MockLessonsStore:
    """Mock LessonsStore dla testów."""

    def get_statistics(self):
        return {
            "total_lessons": 150,
            "unique_tags": 10,
        }


def test_professor_should_start_training_with_lessons(kernel):
    """Test decyzji o treningu z wystarczającą liczbą lekcji."""
    professor = Professor(kernel, lessons_store=MockLessonsStore())

    decision = professor.should_start_training()

    assert decision["should_train"] is True
    assert "150" in decision["reason"]


def test_professor_get_learning_status_with_lessons(kernel):
    """Test statusu z LessonsStore."""
    professor = Professor(kernel, lessons_store=MockLessonsStore())

    status = professor._get_learning_status()

    assert "150" in status
    assert "lekcji" in status.lower()


class MockLessonsStoreInsufficient:
    """Mock LessonsStore z niewystarczającą liczbą lekcji."""

    def get_statistics(self):
        return {
            "total_lessons": 50,
            "unique_tags": 5,
        }


def test_professor_should_start_training_insufficient_lessons(kernel):
    """Test decyzji o treningu z niewystarczającą liczbą lekcji."""
    professor = Professor(kernel, lessons_store=MockLessonsStoreInsufficient())

    decision = professor.should_start_training()

    assert decision["should_train"] is False
    assert "Za mało lekcji" in decision["reason"]
