"""Testy dla StrategistAgent."""

from unittest.mock import Mock

import pytest

from venom_core.agents.strategist import StrategistAgent
from venom_core.ops.work_ledger import TaskComplexity, WorkLedger


class TestStrategistAgent:
    """Testy dla klasy StrategistAgent."""

    @pytest.fixture
    def mock_kernel(self):
        """Mock Semantic Kernel."""
        kernel = Mock()
        kernel.add_plugin = Mock()
        return kernel

    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Tymczasowy plik storage."""
        return str(tmp_path / "test_strategist_ledger.json")

    @pytest.fixture
    def agent(self, mock_kernel, temp_storage):
        """Instancja StrategistAgent."""
        work_ledger = WorkLedger(storage_path=temp_storage)
        return StrategistAgent(kernel=mock_kernel, work_ledger=work_ledger)

    def test_initialization(self, agent):
        """Test inicjalizacji Strategist Agent."""
        assert agent is not None
        assert agent.work_ledger is not None
        assert agent.complexity_skill is not None

    @pytest.mark.asyncio
    async def test_analyze_task_simple(self, agent):
        """Test analizy prostego zadania."""
        task_desc = "Napisz funkcję sumującą dwie liczby"

        result = await agent.analyze_task(task_desc, task_id="test_001")

        assert "STRATEGIST ANALYSIS" in result
        assert "test_001" in result
        assert "ZŁOŻONOŚĆ" in result
        assert "SZACOWANIE CZASU" in result

        # Sprawdź czy zadanie zostało zalogowane
        task = agent.work_ledger.get_task("test_001")
        assert task is not None

    @pytest.mark.asyncio
    async def test_analyze_task_complex(self, agent):
        """Test analizy złożonego zadania."""
        task_desc = "Zaprojektuj architekturę mikroserwisów z Kubernetes"

        result = await agent.analyze_task(task_desc, task_id="test_002")

        assert "HIGH" in result or "EPIC" in result
        assert "SUGEROWANY PODZIAŁ" in result

    def test_monitor_task_nonexistent(self, agent):
        """Test monitorowania nieistniejącego zadania."""
        result = agent.monitor_task("nonexistent")

        assert "❌" in result
        assert "nie istnieje" in result.lower()

    def test_monitor_task_in_progress(self, agent):
        """Test monitorowania zadania w trakcie."""
        # Dodaj zadanie
        agent.work_ledger.log_task(
            "test_001", "Test Task", "Description", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("test_001")
        agent.work_ledger.update_progress("test_001", 30, actual_minutes=20)

        result = agent.monitor_task("test_001")

        assert "MONITORING" in result
        assert "test_001" in result or "Test Task" in result
        assert "30" in result  # Progress percent

    def test_monitor_task_overrun(self, agent):
        """Test monitorowania zadania z overrun."""
        agent.work_ledger.log_task(
            "test_001", "Test Task", "Description", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("test_001")
        # 50% po 60 minutach = prognoza 120 minut (overrun!)
        agent.work_ledger.update_progress("test_001", 50, actual_minutes=60)

        result = agent.monitor_task("test_001")

        assert "OSTRZEŻENIE" in result or "⚠️" in result

    def test_generate_report_empty(self, agent):
        """Test generowania raportu bez zadań."""
        result = agent.generate_report()

        assert "OPERATIONS DASHBOARD" in result
        assert "0" in result or "Brak" in result

    def test_generate_report_with_tasks(self, agent):
        """Test generowania raportu z zadaniami."""
        # Dodaj kilka zadań
        agent.work_ledger.log_task("test_001", "Task 1", "Desc", 30, TaskComplexity.LOW)
        agent.work_ledger.start_task("test_001")
        agent.work_ledger.complete_task("test_001", 28)

        agent.work_ledger.log_task(
            "test_002", "Task 2", "Desc", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("test_002")

        result = agent.generate_report()

        assert "2" in result  # Total tasks
        assert "1" in result  # Completed
        assert "Breakdown" in result

    def test_check_api_usage_default_limits(self, agent):
        """Test sprawdzania użycia API."""
        result = agent.check_api_usage()

        assert "API USAGE REPORT" in result
        assert "openai" in result.lower()

    def test_check_api_usage_with_usage(self, agent):
        """Test sprawdzania użycia API z danymi."""
        # Dodaj zadanie używające API
        agent.work_ledger.log_task(
            "test_001", "API Task", "Desc", 30, TaskComplexity.LOW
        )
        agent.work_ledger.record_api_usage("test_001", "openai", tokens=5000, ops=10)

        result = agent.check_api_usage("openai")

        assert "openai" in result.lower()
        assert "10" in result  # Calls
        assert "5000" in result  # Tokens

    def test_check_api_usage_warning_thresholds(self, agent):
        # 95%+ powinno zwrócić status alarmowy
        limits = {"calls": 100, "tokens": 1000}
        block = agent._format_provider_limit_block("openai", limits, 96, 960)
        assert "🚨 OPENAI" in block
        assert "OSTRZEŻENIE" in block

        # 75-90% powinno zwrócić warning monitoringu
        warn_block = agent._format_provider_limit_block("openai", limits, 81, 760)
        assert "⚠️ OPENAI" in warn_block
        assert "Wysokie zużycie - monitoruj" in warn_block

    def test_calculate_provider_usage_helper(self, agent):
        agent.work_ledger.log_task(
            "test_api", "API Task", "Desc", 30, TaskComplexity.LOW
        )
        agent.work_ledger.record_api_usage("test_api", "openai", tokens=1234, ops=7)

        calls, tokens = agent._calculate_provider_usage("openai")
        assert calls == 7
        assert tokens == 1234

    def test_suggest_local_fallback_images(self, agent):
        """Test sugestii lokalnych fallbacków dla obrazów."""
        result = agent.suggest_local_fallback("Generowanie obrazów przez DALL-E")

        assert "Stable Diffusion" in result or "lokalny" in result.lower()

    def test_suggest_local_fallback_embeddings(self, agent):
        """Test sugestii lokalnych fallbacków dla embeddingów."""
        result = agent.suggest_local_fallback(
            "Wektoryzacja tekstów przez embedding API"
        )

        assert "sentence-transformers" in result or "lokalny" in result.lower()

    def test_suggest_local_fallback_no_suggestions(self, agent):
        """Test sugestii fallbacków gdy brak rekomendacji."""
        result = agent.suggest_local_fallback("Prosta funkcja pomocnicza")

        assert "✅" in result or "Brak" in result

    def test_should_pause_task_normal(self, agent):
        """Test decyzji o pauzowaniu - zadanie normalne."""
        agent.work_ledger.log_task(
            "test_001", "Task", "Desc", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("test_001")
        agent.work_ledger.update_progress("test_001", 30, actual_minutes=20)

        should_pause = agent.should_pause_task("test_001")

        assert should_pause is False

    def test_should_pause_task_major_overrun(self, agent):
        """Test decyzji o pauzowaniu - duże przekroczenie."""
        agent.work_ledger.log_task("test_001", "Task", "Desc", 30, TaskComplexity.LOW)
        agent.work_ledger.start_task("test_001")
        # 25% po 30 minutach = prognoza 120 minut (400% overrun!)
        agent.work_ledger.update_progress("test_001", 25, actual_minutes=30)

        should_pause = agent.should_pause_task("test_001")

        assert should_pause is True

    def test_should_pause_task_many_risks(self, agent):
        """Test decyzji o pauzowaniu - wiele ryzyk."""
        agent.work_ledger.log_task(
            "test_001", "Task", "Desc", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("test_001")

        # Dodaj wiele ryzyk
        for i in range(5):
            agent.work_ledger.add_risk("test_001", f"Ryzyko {i}")

        should_pause = agent.should_pause_task("test_001")

        assert should_pause is True

    @pytest.mark.asyncio
    async def test_process_analyze_command(self, agent):
        """Test przetwarzania komendy analyze."""
        result = await agent.process("analyze:Napisz funkcję testową")

        assert "STRATEGIST ANALYSIS" in result

    @pytest.mark.asyncio
    async def test_process_monitor_command(self, agent):
        """Test przetwarzania komendy monitor."""
        agent.work_ledger.log_task("test_001", "Task", "Desc", 30, TaskComplexity.LOW)

        result = await agent.process("monitor:test_001")

        assert "MONITORING" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_process_report_command(self, agent):
        """Test przetwarzania komendy report."""
        result = await agent.process("report")

        assert "OPERATIONS DASHBOARD" in result

    @pytest.mark.asyncio
    async def test_process_check_api_command(self, agent):
        """Test przetwarzania komendy check_api."""
        result = await agent.process("check_api:openai")

        assert "API USAGE" in result

    def test_extract_time_from_new_json_format(self, agent):
        """Test parsowania czasu z nowego formatu JSON."""
        time_result = '{"estimated_minutes": 45, "complexity": "MEDIUM"}\n\nOszacowany czas: 45 minut'

        extracted = agent._extract_time(time_result)

        assert extracted == pytest.approx(45.0)

    def test_extract_time_from_old_json_format(self, agent):
        """Test parsowania czasu ze starego formatu JSON."""
        time_result = '{"minutes": 60}\n\nOszacowany czas: 60 minut'

        extracted = agent._extract_time(time_result)

        assert extracted == pytest.approx(60.0)

    def test_extract_time_from_text_fallback(self, agent):
        """Test parsowania czasu z tekstu (fallback)."""
        time_result = "Oszacowany czas: 120 minut (2.0h)"

        extracted = agent._extract_time(time_result)

        assert extracted == pytest.approx(120.0)

    def test_extract_time_default_on_error(self, agent):
        """Test domyślnej wartości gdy parsowanie się nie uda."""
        time_result = "Niepoprawny format bez liczb"

        extracted = agent._extract_time(time_result)

        assert extracted == pytest.approx(30.0)  # Domyślna wartość

    def test_extract_time_with_multiline_json(self, agent):
        """Test parsowania JSON z wieloliniowego wyniku."""
        time_result = """

{"estimated_minutes": 75, "complexity": "HIGH"}

Oszacowany czas: 75 minut (1.3h)
Złożoność: HIGH
"""

        extracted = agent._extract_time(time_result)

        assert extracted == pytest.approx(75.0)

    def test_extract_time_zero_minutes(self, agent):
        """Test parsowania JSON gdy estimated_minutes wynosi 0 (edge case)."""
        time_result = '{"estimated_minutes": 0, "complexity": "TRIVIAL"}\n\nOszacowany czas: 0 minut'

        extracted = agent._extract_time(time_result)

        # Powinno zwrócić 0, a nie fallback do "minutes"
        assert extracted == pytest.approx(0.0)
