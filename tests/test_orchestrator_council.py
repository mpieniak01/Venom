"""Testy jednostkowe dla logiki decyzyjnej Orchestratora (Council mode)."""

from unittest.mock import MagicMock, patch

from venom_core.core.orchestrator import (
    COUNCIL_COLLABORATION_KEYWORDS,
    COUNCIL_TASK_THRESHOLD,
    Orchestrator,
)


class TestOrchestratorCouncilDecision:
    """Testy dla metody _should_use_council()."""

    def setup_method(self):
        """Setup przed każdym testem."""
        # Mock dependencies
        self.state_manager = MagicMock()
        self.orchestrator = Orchestrator(state_manager=self.state_manager)

    def test_should_use_council_disabled(self):
        """Test: Council wyłączony przez flagę."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", False):
            result = self.orchestrator._should_use_council(
                context="Długie zadanie wymagające współpracy", intent="CODE_GENERATION"
            )
            assert result is False

    def test_should_use_council_complex_planning_intent(self):
        """Test: COMPLEX_PLANNING intent zawsze aktywuje Council."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", True):
            result = self.orchestrator._should_use_council(
                context="Krótkie zadanie", intent="COMPLEX_PLANNING"
            )
            assert result is True

    def test_should_use_council_short_task_no_keywords(self):
        """Test: Krótkie zadanie bez słów kluczowych - nie aktywuje Council."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", True):
            short_context = "x" * (COUNCIL_TASK_THRESHOLD - 1)
            result = self.orchestrator._should_use_council(
                context=short_context, intent="CODE_GENERATION"
            )
            assert result is False

    def test_should_use_council_long_task_with_keyword(self):
        """Test: Długie zadanie ze słowem kluczowym - aktywuje Council."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", True):
            long_context = "x" * (COUNCIL_TASK_THRESHOLD + 1) + " stwórz projekt"
            result = self.orchestrator._should_use_council(
                context=long_context, intent="CODE_GENERATION"
            )
            assert result is True

    def test_should_use_council_long_task_without_keyword(self):
        """Test: Długie zadanie bez słowa kluczowego - nie aktywuje Council."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", True):
            long_context = "x" * (COUNCIL_TASK_THRESHOLD + 1)
            result = self.orchestrator._should_use_council(
                context=long_context, intent="CODE_GENERATION"
            )
            assert result is False

    def test_should_use_council_all_keywords(self):
        """Test: Sprawdź że wszystkie słowa kluczowe są rozpoznawane."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", True):
            for keyword in COUNCIL_COLLABORATION_KEYWORDS:
                long_context = "x" * (COUNCIL_TASK_THRESHOLD + 1) + f" {keyword}"
                result = self.orchestrator._should_use_council(
                    context=long_context, intent="CODE_GENERATION"
                )
                fail_msg = f"Słowo kluczowe '{keyword}' nie aktywowało Council"
                assert result is True, fail_msg

    def test_should_use_council_case_insensitive(self):
        """Test: Sprawdzanie słów kluczowych jest case-insensitive."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", True):
            long_context = "x" * (COUNCIL_TASK_THRESHOLD + 1) + " PROJEKT APLIKACJA"
            result = self.orchestrator._should_use_council(
                context=long_context, intent="CODE_GENERATION"
            )
            assert result is True

    def test_should_use_council_exactly_threshold(self):
        """Test: Zadanie dokładnie na progu (edge case)."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", True):
            # Dokładnie threshold znaków BEZ słowa kluczowego - nie powinno aktywować
            exact_threshold = "x" * COUNCIL_TASK_THRESHOLD
            result = self.orchestrator._should_use_council(
                context=exact_threshold, intent="CODE_GENERATION"
            )
            # len == 100, warunek wymaga > 100, więc False
            assert result is False

            # Dokładnie threshold + 1 znak BEZ słowa kluczowego - też nie aktywuje
            just_over_threshold = "x" * (COUNCIL_TASK_THRESHOLD + 1)
            result2 = self.orchestrator._should_use_council(
                context=just_over_threshold, intent="CODE_GENERATION"
            )
            # len == 101 > 100, ale brak słowa kluczowego, więc False
            assert result2 is False

            # Dokładnie threshold + 1 znak ZE słowem kluczowym - powinno aktywować
            just_over_with_keyword = "x" * (COUNCIL_TASK_THRESHOLD + 1) + " projekt"
            result3 = self.orchestrator._should_use_council(
                context=just_over_with_keyword, intent="CODE_GENERATION"
            )
            # len > 100 i ma słowo kluczowe, więc True
            assert result3 is True

    def test_should_use_council_empty_context(self):
        """Test: Puste zadanie - nie aktywuje Council."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", True):
            result = self.orchestrator._should_use_council(
                context="", intent="CODE_GENERATION"
            )
            assert result is False

    def test_should_use_council_other_intents(self):
        """Test: Inne intencje nie aktywują Council (bez słów kluczowych)."""
        with patch("venom_core.core.orchestrator.ENABLE_COUNCIL_MODE", True):
            intents = [
                "CODE_GENERATION",
                "GENERAL_CHAT",
                "KNOWLEDGE_SEARCH",
                "CODE_REVIEW",
            ]
            for intent in intents:
                result = self.orchestrator._should_use_council(
                    context="Krótkie zadanie", intent=intent
                )
                fail_msg = f"Intencja '{intent}' błędnie aktywowała Council"
                assert result is False, fail_msg
