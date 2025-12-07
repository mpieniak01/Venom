"""Testy dla TokenEconomist."""

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
