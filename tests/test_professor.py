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

    # Sprawdź domyślne wartości (bez dataset_size)
    assert params["lora_rank"] == Professor.DEFAULT_LORA_RANK
    assert params["learning_rate"] == Professor.DEFAULT_LEARNING_RATE
    assert params["num_epochs"] == Professor.DEFAULT_NUM_EPOCHS


def test_professor_select_training_parameters_small_dataset(kernel):
    """Test doboru parametrów dla małego datasetu."""
    professor = Professor(kernel)

    params = professor._select_training_parameters(dataset_size=50)

    # Mały dataset -> mniejszy batch size, więcej epok
    assert params["batch_size"] == 2
    assert params["num_epochs"] == 5


def test_professor_select_training_parameters_medium_dataset(kernel):
    """Test doboru parametrów dla średniego datasetu."""
    professor = Professor(kernel)

    params = professor._select_training_parameters(dataset_size=600)

    # Średni dataset -> średni batch size
    assert params["batch_size"] == 6
    assert params["num_epochs"] == Professor.DEFAULT_NUM_EPOCHS


def test_professor_select_training_parameters_large_dataset(kernel):
    """Test doboru parametrów dla dużego datasetu."""
    professor = Professor(kernel)

    params = professor._select_training_parameters(dataset_size=1500)

    # Duży dataset -> większy batch size, mniej epok
    assert params["batch_size"] == 8
    assert params["num_epochs"] == 2


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


def test_professor_should_start_training_time_gating(kernel):
    """Test time-gating - zbyt wczesny trening."""
    from datetime import datetime, timedelta

    professor = Professor(kernel, lessons_store=MockLessonsStore())

    # Dodaj ostatni trening który był niedawno (2 godziny temu)
    recent_time = datetime.now() - timedelta(hours=2)
    professor.training_history.append(
        {
            "job_name": "test_job",
            "started_at": recent_time.isoformat(),
            "lessons_count": 150,
        }
    )

    decision = professor.should_start_training()

    assert decision["should_train"] is False
    assert "Zbyt wcześnie" in decision["reason"]


def test_professor_should_start_training_insufficient_new_lessons(kernel):
    """Test - za mało nowych lekcji od ostatniego treningu."""
    from datetime import datetime, timedelta

    professor = Professor(kernel, lessons_store=MockLessonsStore())

    # Dodaj ostatni trening który był dawno (48 godzin temu) ale z podobną liczbą lekcji
    old_time = datetime.now() - timedelta(hours=48)
    professor.training_history.append(
        {
            "job_name": "test_job",
            "started_at": old_time.isoformat(),
            "lessons_count": 140,  # 150 - 140 = 10 nowych lekcji (za mało)
        }
    )

    decision = professor.should_start_training()

    assert decision["should_train"] is False
    assert "Za mało nowych lekcji" in decision["reason"]


def test_professor_should_start_training_ready(kernel):
    """Test - gotowy do treningu po wystarczającym czasie i nowych lekcjach."""
    from datetime import datetime, timedelta

    professor = Professor(kernel, lessons_store=MockLessonsStore())

    # Dodaj ostatni trening który był dawno (48 godzin temu) z mniejszą liczbą lekcji
    old_time = datetime.now() - timedelta(hours=48)
    professor.training_history.append(
        {
            "job_name": "test_job",
            "started_at": old_time.isoformat(),
            "lessons_count": 50,  # 150 - 50 = 100 nowych lekcji (wystarczająco)
        }
    )

    decision = professor.should_start_training()

    assert decision["should_train"] is True
    assert "Gotowy do treningu" in decision["reason"]


def test_professor_check_model_availability(kernel, tmp_path):
    """Test sprawdzania dostępności modelu."""
    professor = Professor(kernel)

    # Utwórz testowy katalog modelu
    model_dir = tmp_path / "test_model"
    model_dir.mkdir()

    assert professor._check_model_availability(str(model_dir)) is True
    assert professor._check_model_availability(str(tmp_path / "nonexistent")) is False


def test_professor_score_response(kernel):
    """Test oceny odpowiedzi modelu."""
    professor = Professor(kernel)

    # Pusta odpowiedź
    score = professor._score_response("", "Napisz funkcję")
    assert score == pytest.approx(1.0)

    # Odpowiedź z kodem
    code_response = "def hello():\n    print('Hello')\n    return True"
    score = professor._score_response(code_response, "Napisz funkcję")
    assert score > 5.0

    # Odpowiedź tekstowa (nie kod)
    text_response = (
        "Rekurencja to technika programistyczna gdzie funkcja wywołuje sama siebie."
    )
    score = professor._score_response(text_response, "Wyjaśnij rekurencję")
    assert score >= 5.0


@pytest.mark.asyncio
async def test_professor_evaluate_model_no_candidate(kernel):
    """Test ewaluacji bez modelu kandydującego."""
    professor = Professor(kernel)

    result = professor._evaluate_model()

    assert "Brak nowego modelu" in result or "❌" in result
