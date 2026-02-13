"""Testy dla TokenEconomist."""

import pytest
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.core.token_economist import TokenEconomist


class TestTokenEconomist:
    """Testy dla klasy TokenEconomist."""

    def test_initialization(self):
        """Test inicjalizacji ekonomisty."""
        economist = TokenEconomist()
        assert economist.enable_compression is True

    def test_estimate_tokens(self):
        """Test estymacji liczby tokenów."""
        economist = TokenEconomist()

        # Krótki tekst
        tokens = economist.estimate_tokens("Hello world")
        assert tokens > 0

        # Długi tekst
        long_text = "x" * 1000
        tokens = economist.estimate_tokens(long_text)
        assert tokens > 200  # ~1000 / 4 = 250

    def test_compress_context_below_limit(self):
        """Test kompresji gdy historia jest poniżej limitu."""
        economist = TokenEconomist()

        history = ChatHistory()
        history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content="System prompt")
        )
        history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content="User message")
        )

        # Historia krótka - nie powinna być kompresowana
        compressed = economist.compress_context(history, max_tokens=10000)
        assert len(compressed.messages) == len(history.messages)

    def test_compress_context_above_limit(self):
        """Test kompresji gdy historia przekracza limit."""
        economist = TokenEconomist()

        history = ChatHistory()
        history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content="System prompt")
        )

        # Dodaj wiele długich wiadomości
        for i in range(20):
            history.add_message(
                ChatMessageContent(
                    role=AuthorRole.USER, content=f"Long user message {i}" * 50
                )
            )
            history.add_message(
                ChatMessageContent(
                    role=AuthorRole.ASSISTANT,
                    content=f"Long assistant response {i}" * 50,
                )
            )

        # Historia długa - powinna być skompresowana
        compressed = economist.compress_context(history, max_tokens=500)
        assert len(compressed.messages) < len(history.messages)

        # System prompt powinien być zachowany
        assert compressed.messages[0].role == AuthorRole.SYSTEM

    def test_compress_context_preserves_system_message(self):
        """Test czy kompresja zachowuje system message."""
        economist = TokenEconomist()

        history = ChatHistory()
        system_content = "Important system prompt"
        history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content=system_content)
        )

        for i in range(10):
            history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content="X" * 200)
            )

        compressed = economist.compress_context(history, max_tokens=300)

        # System message powinien być pierwszy
        assert compressed.messages[0].role == AuthorRole.SYSTEM
        assert str(compressed.messages[0].content) == system_content

    def test_compress_context_disabled(self):
        """Test wyłączonej kompresji."""
        economist = TokenEconomist(enable_compression=False)

        history = ChatHistory()
        for i in range(10):
            history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content="X" * 500)
            )

        # Kompresja wyłączona - historia nie powinna być zmieniona
        compressed = economist.compress_context(history, max_tokens=100)
        assert len(compressed.messages) == len(history.messages)

    def test_calculate_cost_gpt35(self):
        """Test kalkulacji kosztu dla GPT-3.5."""
        economist = TokenEconomist()

        usage = {"input_tokens": 1000, "output_tokens": 500}
        cost_info = economist.calculate_cost(usage, "gpt-3.5-turbo")

        assert cost_info["input_tokens"] == 1000
        assert cost_info["output_tokens"] == 500
        assert cost_info["total_tokens"] == 1500
        assert cost_info["input_cost_usd"] > 0
        assert cost_info["output_cost_usd"] > 0
        assert cost_info["total_cost_usd"] > 0
        assert cost_info["model"] == "gpt-3.5-turbo"

    def test_calculate_cost_gpt4o(self):
        """Test kalkulacji kosztu dla GPT-4o."""
        economist = TokenEconomist()

        usage = {"input_tokens": 1000, "output_tokens": 500}
        cost_info = economist.calculate_cost(usage, "gpt-4o")

        # GPT-4o jest droższy niż GPT-3.5
        gpt35_cost = economist.calculate_cost(usage, "gpt-3.5-turbo")
        assert cost_info["total_cost_usd"] > gpt35_cost["total_cost_usd"]

    def test_calculate_cost_local_model(self):
        """Test kalkulacji kosztu dla lokalnego modelu."""
        economist = TokenEconomist()

        usage = {"input_tokens": 1000, "output_tokens": 500}
        cost_info = economist.calculate_cost(usage, "local")

        # Lokalny model powinien być darmowy
        assert cost_info["total_cost_usd"] == 0
        assert cost_info["input_cost_usd"] == 0
        assert cost_info["output_cost_usd"] == 0

    def test_calculate_cost_phi3(self):
        """Test kalkulacji kosztu dla Phi-3 (lokalny)."""
        economist = TokenEconomist()

        usage = {"input_tokens": 1000, "output_tokens": 500}
        cost_info = economist.calculate_cost(usage, "phi3:latest")

        # Phi-3 jest lokalny - powinien być darmowy
        assert cost_info["total_cost_usd"] == 0

    def test_estimate_request_cost(self):
        """Test estymacji kosztu przed requestem."""
        economist = TokenEconomist()

        prompt = "This is a test prompt"
        cost_estimate = economist.estimate_request_cost(
            prompt, expected_output_tokens=300, model_name="gpt-3.5-turbo"
        )

        assert "input_tokens" in cost_estimate
        assert "output_tokens" in cost_estimate
        assert cost_estimate["output_tokens"] == 300
        assert cost_estimate["total_cost_usd"] > 0

    def test_get_token_statistics(self):
        """Test statystyk tokenów dla historii."""
        economist = TokenEconomist()

        history = ChatHistory()
        history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content="System prompt")
        )
        history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content="User message 1")
        )
        history.add_message(
            ChatMessageContent(role=AuthorRole.ASSISTANT, content="Assistant response")
        )
        history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content="User message 2")
        )

        stats = economist.get_token_statistics(history)

        assert stats["total_messages"] == 4
        assert stats["messages_by_role"]["system"] == 1
        assert stats["messages_by_role"]["user"] == 2
        assert stats["messages_by_role"]["assistant"] == 1
        assert stats["total_tokens"] > 0
        assert "compression_needed" in stats

    def test_get_token_statistics_empty_history(self):
        """Test statystyk dla pustej historii."""
        economist = TokenEconomist()

        history = ChatHistory()
        stats = economist.get_token_statistics(history)

        assert stats["total_messages"] == 0
        assert stats["total_tokens"] == 0

    def test_pricing_for_unknown_model(self):
        """Test cennika dla nieznanego modelu."""
        economist = TokenEconomist()

        usage = {"input_tokens": 1000, "output_tokens": 500}
        cost_info = economist.calculate_cost(usage, "unknown-model-xyz")

        # Powinien użyć fallback (GPT-3.5)
        assert cost_info["total_cost_usd"] > 0

    def test_summarize_messages(self):
        """Test sumaryzacji wiadomości."""
        economist = TokenEconomist()

        messages = [
            ChatMessageContent(role=AuthorRole.USER, content="Question 1"),
            ChatMessageContent(role=AuthorRole.ASSISTANT, content="Answer 1"),
            ChatMessageContent(role=AuthorRole.USER, content="Question 2"),
            ChatMessageContent(role=AuthorRole.ASSISTANT, content="Answer 2"),
        ]

        summary = economist._summarize_messages(messages)

        # Summary nie powinno być puste
        assert len(summary) > 0
        assert isinstance(summary, str)

    def test_load_pricing_default_path(self):
        """Test wczytywania cennika z domyślnej ścieżki."""
        economist = TokenEconomist()
        pricing = economist.load_pricing()

        # Sprawdź czy cennik został wczytany
        if pricing:
            assert "models" in pricing
            assert "tools" in pricing
            assert "local" in pricing["models"]

    def test_estimate_task_cost(self):
        """Test estymacji kosztu zadania."""
        economist = TokenEconomist()

        # Test dla modelu lokalnego (darmowy)
        local_cost = economist.estimate_task_cost("local", 100)
        assert local_cost["service_id"] == "local"
        assert local_cost["estimated_cost_usd"] == pytest.approx(0.0)
        assert local_cost["is_free"] is True

        # Test dla modelu płatnego
        gpt_cost = economist.estimate_task_cost("gpt-4o", 1000)
        assert gpt_cost["service_id"] == "gpt-4o"
        assert gpt_cost["estimated_cost_usd"] > 0
        assert gpt_cost["is_free"] is False
        assert gpt_cost["input_tokens"] > 0
        assert gpt_cost["output_tokens"] > 0

    def test_compare_providers(self):
        """Test porównania kosztów między providerami."""
        economist = TokenEconomist()

        prompt = "Write a simple hello world function"
        results = economist.compare_providers(prompt)

        # Powinny być wyniki dla wszystkich providerów
        assert len(results) > 0

        # Pierwszy (najtańszy) powinien być local (koszt 0)
        assert results[0]["provider"] == "local"
        assert results[0]["cost"] == pytest.approx(0.0)
        assert results[0]["is_free"] is True

        # Wyniki powinny być posortowane rosnąco po koszcie
        for i in range(len(results) - 1):
            assert results[i]["cost"] <= results[i + 1]["cost"]

    def test_compare_providers_custom_list(self):
        """Test porównania kosztów z niestandardową listą providerów."""
        economist = TokenEconomist()

        prompt = "Test prompt"
        providers = ["local", "gpt-4o-mini"]
        results = economist.compare_providers(prompt, providers)

        assert len(results) == 2
        assert results[0]["provider"] == "local"  # Najtańszy

    def test_estimate_task_cost_with_output_ratio(self):
        """Test estymacji kosztu z niestandardowym output_ratio."""
        economist = TokenEconomist()

        # Output ratio = 1.0 (output taki sam jak input)
        cost_1 = economist.estimate_task_cost("gpt-4o", 1000, output_ratio=1.0)
        # Output ratio = 0.5 (output połowa inputu)
        cost_05 = economist.estimate_task_cost("gpt-4o", 1000, output_ratio=0.5)

        # Koszt z ratio=1.0 powinien być wyższy
        assert cost_1["estimated_cost_usd"] > cost_05["estimated_cost_usd"]
        assert cost_1["output_tokens"] == cost_1["input_tokens"]
        assert cost_05["output_tokens"] == cost_05["input_tokens"] // 2


class TestTokenEconomistPerModelTracking:
    """Testy dla funkcjonalności śledzenia per-model w TokenEconomist (PR-132A)."""

    def test_initialization_with_tracking(self):
        """Test inicjalizacji z licznikami per-model."""
        economist = TokenEconomist()
        assert economist.model_usage == {}
        assert economist.total_usage == {"input_tokens": 0, "output_tokens": 0}

    def test_record_usage_single_model(self):
        """Test rejestrowania użycia dla pojedynczego modelu."""
        economist = TokenEconomist()

        # Zarejestruj użycie dla gpt-4o
        economist.record_usage("gpt-4o", 100, 50)

        assert "gpt-4o" in economist.model_usage
        assert economist.model_usage["gpt-4o"]["input_tokens"] == 100
        assert economist.model_usage["gpt-4o"]["output_tokens"] == 50
        assert economist.total_usage["input_tokens"] == 100
        assert economist.total_usage["output_tokens"] == 50

    def test_record_usage_multiple_models(self):
        """Test rejestrowania użycia dla wielu modeli."""
        economist = TokenEconomist()

        # Zarejestruj użycie dla różnych modeli
        economist.record_usage("gpt-4o", 100, 50)
        economist.record_usage("gpt-3.5-turbo", 200, 100)
        economist.record_usage("local", 500, 300)

        assert len(economist.model_usage) == 3
        assert economist.total_usage["input_tokens"] == 800
        assert economist.total_usage["output_tokens"] == 450

    def test_record_usage_accumulation(self):
        """Test akumulacji użycia dla tego samego modelu."""
        economist = TokenEconomist()

        # Wielokrotne użycie tego samego modelu
        economist.record_usage("gpt-4o", 100, 50)
        economist.record_usage("gpt-4o", 200, 100)
        economist.record_usage("gpt-4o", 50, 25)

        assert economist.model_usage["gpt-4o"]["input_tokens"] == 350
        assert economist.model_usage["gpt-4o"]["output_tokens"] == 175
        assert economist.total_usage["input_tokens"] == 350
        assert economist.total_usage["output_tokens"] == 175

    def test_get_model_breakdown_empty(self):
        """Test pobierania breakdown gdy brak danych."""
        economist = TokenEconomist()

        breakdown = economist.get_model_breakdown()

        assert breakdown["models_breakdown"] == {}
        assert breakdown["total_tokens"] == 0
        assert breakdown["total_cost_usd"] == 0.0

    def test_get_model_breakdown_single_model(self):
        """Test pobierania breakdown dla pojedynczego modelu."""
        economist = TokenEconomist()

        economist.record_usage("gpt-4o", 100, 50)
        breakdown = economist.get_model_breakdown()

        assert "gpt-4o" in breakdown["models_breakdown"]
        model_data = breakdown["models_breakdown"]["gpt-4o"]
        assert model_data["input_tokens"] == 100
        assert model_data["output_tokens"] == 50
        assert model_data["total_tokens"] == 150
        assert model_data["cost_usd"] > 0  # gpt-4o nie jest darmowy

        assert breakdown["total_tokens"] == 150
        assert breakdown["total_cost_usd"] > 0

    def test_get_model_breakdown_multiple_models(self):
        """Test pobierania breakdown dla wielu modeli."""
        economist = TokenEconomist()

        economist.record_usage("gpt-4o", 100, 50)
        economist.record_usage("local", 500, 300)

        breakdown = economist.get_model_breakdown()

        assert len(breakdown["models_breakdown"]) == 2
        assert "gpt-4o" in breakdown["models_breakdown"]
        assert "local" in breakdown["models_breakdown"]

        # Local powinien mieć koszt 0
        assert breakdown["models_breakdown"]["local"]["cost_usd"] == 0.0

        # gpt-4o powinien mieć koszt > 0
        assert breakdown["models_breakdown"]["gpt-4o"]["cost_usd"] > 0

        # Całkowity koszt to tylko koszt gpt-4o
        assert (
            breakdown["total_cost_usd"]
            == breakdown["models_breakdown"]["gpt-4o"]["cost_usd"]
        )

        # Całkowita liczba tokenów to suma
        assert breakdown["total_tokens"] == 950  # 150 + 800

    def test_reset_usage(self):
        """Test resetowania liczników użycia."""
        economist = TokenEconomist()

        # Dodaj dane
        economist.record_usage("gpt-4o", 100, 50)
        economist.record_usage("local", 500, 300)

        # Zresetuj
        economist.reset_usage()

        assert economist.model_usage == {}
        assert economist.total_usage == {"input_tokens": 0, "output_tokens": 0}

        breakdown = economist.get_model_breakdown()
        assert breakdown["total_tokens"] == 0
        assert breakdown["total_cost_usd"] == 0.0

    def test_get_model_breakdown_cost_calculation(self):
        """Test poprawności obliczeń kosztów w breakdown."""
        economist = TokenEconomist()

        # Użyj znanego modelu z znanym cennikiem
        economist.record_usage("gpt-3.5-turbo", 1_000_000, 1_000_000)

        breakdown = economist.get_model_breakdown()
        model_data = breakdown["models_breakdown"]["gpt-3.5-turbo"]

        # Sprawdź czy koszt jest zgodny z cennikiem
        # gpt-3.5-turbo: input=0.5 USD/1M, output=1.5 USD/1M
        expected_cost = (1_000_000 / 1_000_000) * 0.5 + (1_000_000 / 1_000_000) * 1.5
        assert model_data["cost_usd"] == pytest.approx(expected_cost, abs=1e-6)
