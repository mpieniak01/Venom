"""Testy jednostkowe dla modułu operator (OperatorAgent)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from semantic_kernel.contents.chat_history import ChatHistory

import venom_core.agents.operator as op_module
from venom_core.agents.operator import (
    OperatorAgent,
    _build_voice_context_message,
    _build_voice_retry_history,
    _coerce_float,
    _coerce_int,
    _extract_text_payload,
    _normalize_voice_response,
    _ollama_extra_body,
    _ollama_native_call,
    _sanitize_voice_response,
)
from venom_core.infrastructure.hardware_pi import HardwareBridge


class TestOperatorAgent:
    """Testy dla OperatorAgent."""

    @pytest.fixture
    def mock_kernel(self):
        """Mock Semantic Kernel."""
        kernel = MagicMock()
        kernel.get_service = MagicMock()
        return kernel

    @pytest.fixture
    def mock_hardware_bridge(self):
        """Mock HardwareBridge."""
        bridge = MagicMock(spec=HardwareBridge)
        bridge.connected = True
        return bridge

    def test_initialization(self, mock_kernel):
        """Test inicjalizacji OperatorAgent."""
        agent = OperatorAgent(kernel=mock_kernel, hardware_bridge=None)

        assert agent.kernel == mock_kernel
        assert agent.hardware_bridge is None
        assert agent.chat_history is not None
        assert len(agent.chat_history.messages) == 1  # System prompt

    def test_initialization_with_hardware_bridge(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test inicjalizacji z hardware bridge."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        assert agent.hardware_bridge == mock_hardware_bridge

    def test_resolve_chat_service_id_prefers_chat_then_local_and_fallback(
        self, mock_kernel
    ):
        """_resolve_chat_service_id should prefer chat, then local, then fallback."""
        agent = OperatorAgent(kernel=mock_kernel)

        mock_kernel.services = {"chat": MagicMock(), "local": MagicMock()}
        assert agent._resolve_chat_service_id() == "chat"

        mock_kernel.services = {"local": MagicMock()}
        assert agent._resolve_chat_service_id() == "local"

        mock_kernel.services = {}
        assert agent._resolve_chat_service_id() == "chat"

    def test_voice_prompt_coercion_helpers(self):
        assert _coerce_int("12", 0) == 12
        assert _coerce_int(object(), 7) == 7
        assert _coerce_float("0.5", 0.1) == pytest.approx(0.5)
        assert _coerce_float(object(), 0.1) == pytest.approx(0.1)

    def test_build_voice_context_message_handles_empty_and_disabled_fields(self):
        assert _build_voice_context_message(None) is None
        assert (
            _build_voice_context_message(
                {
                    "reasoning_summary": "x",
                    "reasoning_summary_enabled": False,
                    "emotion_label": "curious",
                    "emotion_detection_enabled": False,
                }
            )
            is None
        )

    def test_build_voice_context_message_includes_all_enabled_sections(self):
        message = _build_voice_context_message(
            {
                "reasoning_summary": "pipeline=gemma | mode=summary",
                "reasoning_summary_enabled": True,
                "emotion_label": "frustrated",
                "emotion_confidence": 0.74,
                "emotion_detection_enabled": True,
                "emotion_response_style_enabled": True,
                "raw_thinking_available": True,
            }
        )

        assert message is not None
        assert "Kontekst reasoning: pipeline=gemma | mode=summary" in message
        assert "Emocja użytkownika: frustrated (pewność 74%)" in message
        assert "Dopasuj ton odpowiedzi do emocji użytkownika" in message
        assert "Model może emitować blok reasoning" in message

    def test_is_hardware_command_true(self, mock_kernel):
        """Test rozpoznawania komend sprzętowych."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Komendy sprzętowe
        assert agent._is_hardware_command("status Rider-Pi") is True
        assert agent._is_hardware_command("włącz GPIO 17") is True
        assert agent._is_hardware_command("wyłącz pin 4") is True
        assert agent._is_hardware_command("jaka jest temperatura?") is True
        assert agent._is_hardware_command("procedura awaryjna reset") is True

    def test_is_hardware_command_false(self, mock_kernel):
        """Test rozpoznawania komend niesprzętowych."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Komendy niesprzętowe
        assert agent._is_hardware_command("jaki jest status repozytorium?") is False
        assert agent._is_hardware_command("napisz kod w Python") is False
        assert agent._is_hardware_command("zrób research o AI") is False

    def test_low_level_hardware_command_detectors(self, mock_kernel):
        """Low-level helpers should classify GPIO/emergency commands correctly."""
        agent = OperatorAgent(kernel=mock_kernel)

        assert agent._is_gpio_disable_command("wyłącz gpio 21") is True
        assert agent._is_gpio_disable_command("włącz gpio 21") is False
        assert agent._is_emergency_command("procedura awaryjna reset gpio") is True
        assert agent._is_emergency_command("zwykła komenda") is False
        assert agent._extract_gpio_pin("wyłącz gpio 17") == 17
        assert agent._extract_gpio_pin("wyłącz pin bez numeru") is None

    @pytest.mark.asyncio
    async def test_handle_hardware_command_no_bridge(self, mock_kernel):
        """Test obsługi komendy sprzętowej bez hardware bridge."""
        agent = OperatorAgent(kernel=mock_kernel, hardware_bridge=None)

        response = await agent._handle_hardware_command("status Rider-Pi")
        assert "nie jest podłączony" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_hardware_command_status(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy statusu Rider-Pi."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock get_system_info
        mock_hardware_bridge.get_system_info = AsyncMock(
            return_value={
                "cpu_temp": 45.5,
                "memory_usage_percent": 42.0,
            }
        )

        response = await agent._handle_hardware_command("status Rider-Pi")
        assert "45.5" in response
        assert "42" in response

    @pytest.mark.asyncio
    async def test_handle_hardware_command_temperature(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy temperatury."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock read_sensor
        mock_hardware_bridge.read_sensor = AsyncMock(return_value=47.3)

        response = await agent._handle_hardware_command("jaka jest temperatura?")
        assert "47.3" in response
        assert "stopni" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_hardware_command_gpio_on(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy włączenia GPIO."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock set_gpio
        mock_hardware_bridge.set_gpio = AsyncMock(return_value=True)

        response = await agent._handle_hardware_command("włącz GPIO 17")
        assert "17" in response
        assert "włączony" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_hardware_command_gpio_off(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy wyłączenia GPIO."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock set_gpio
        mock_hardware_bridge.set_gpio = AsyncMock(return_value=True)

        response = await agent._handle_hardware_command("wyłącz GPIO 4")
        assert "4" in response
        assert "wyłączony" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_hardware_command_emergency(
        self, mock_kernel, mock_hardware_bridge
    ):
        """Test komendy procedury awaryjnej."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        # Mock emergency_procedure
        mock_hardware_bridge.emergency_procedure = AsyncMock(return_value=True)

        response = await agent._handle_hardware_command("procedura awaryjna reset GPIO")
        assert "procedura" in response.lower()

    @pytest.mark.asyncio
    async def test_process_hardware_command(self, mock_kernel, mock_hardware_bridge):
        """Test przetwarzania komendy sprzętowej przez process()."""
        agent = OperatorAgent(
            kernel=mock_kernel,
            hardware_bridge=mock_hardware_bridge,
        )

        mock_hardware_bridge.read_sensor = AsyncMock(return_value=45.0)

        response = await agent.process("temperatura")
        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_summarize_for_voice(self, mock_kernel):
        """Test streszczania dla głosu."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Mock chat service
        mock_chat_service = MagicMock()
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: "Krótkie streszczenie."
        mock_chat_service.get_chat_message_content = AsyncMock(
            return_value=mock_response
        )
        mock_kernel.get_service.return_value = mock_chat_service

        long_text = """
        To jest bardzo długi tekst z wieloma szczegółami technicznymi.
        Zawiera kod:
        ```python
        def hello():
            print("Hello, world!")
        ```
        I wiele innych informacji które nie są potrzebne w odpowiedzi głosowej.
        """

        summary = await agent.summarize_for_voice(long_text)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_clear_history(self, mock_kernel):
        """Test czyszczenia historii."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Dodaj kilka wiadomości
        agent.chat_history.add_user_message("Test 1")
        agent.chat_history.add_assistant_message("Response 1")

        initial_count = len(agent.chat_history.messages)
        assert initial_count > 1

        # Wyczyść historię
        agent.clear_history()

        # Powinna pozostać tylko system message
        assert len(agent.chat_history.messages) == 1

    @pytest.mark.asyncio
    async def test_process_non_hardware_command(self, mock_kernel):
        """Test przetwarzania komendy niesprzętowej."""
        agent = OperatorAgent(kernel=mock_kernel)

        # Mock chat service
        mock_chat_service = MagicMock()
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: "Odpowiedź na pytanie."
        mock_chat_service.get_chat_message_content = AsyncMock(
            return_value=mock_response
        )
        mock_kernel.get_service.return_value = mock_chat_service

        response = await agent.process("Jaki jest status repozytorium?")
        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_generate_voice_response_filters_system_messages_and_uses_mode(
        self, mock_kernel
    ):
        """_generate_voice_response should filter historical system messages."""
        agent = OperatorAgent(kernel=mock_kernel)
        mock_kernel.services = {"local": MagicMock()}
        agent.chat_history.add_user_message("historia user")
        agent.chat_history.add_assistant_message("historia assistant")
        agent.chat_history.add_system_message("system-only-history")
        agent.chat_history.messages.append(
            SimpleNamespace(
                role=SimpleNamespace(name="SYSTEM"),
                content="system-object-role",
            )
        )

        captured = {}

        async def fake_invoke_chat_with_fallbacks(
            *, chat_service, chat_history, settings, enable_functions
        ):
            captured["service"] = chat_service
            captured["messages"] = [
                getattr(message, "role", None) for message in chat_history.messages
            ]
            captured["tokens"] = settings.max_tokens
            captured["temperature"] = settings.temperature
            captured["enable_functions"] = enable_functions
            return "Odpowiedź głosowa."

        mock_chat_service = MagicMock()
        mock_kernel.get_service.return_value = mock_chat_service
        agent._invoke_chat_with_fallbacks = AsyncMock(
            side_effect=fake_invoke_chat_with_fallbacks
        )

        response = await agent._generate_voice_response("co dalej?", mode="summary")

        assert response == "Odpowiedź głosowa."
        assert captured["service"] is mock_chat_service
        assert captured["enable_functions"] is False
        assert captured["tokens"] == 100
        assert captured["temperature"] == pytest.approx(0.5)
        assert captured["messages"].count("system") == 2

    @pytest.mark.asyncio
    async def test_generate_voice_response_truncates_history_to_10_messages(
        self, mock_kernel
    ):
        agent = OperatorAgent(kernel=mock_kernel)
        mock_kernel.services = {"chat": MagicMock()}
        mock_kernel.get_service.return_value = MagicMock()
        agent._invoke_chat_with_fallbacks = AsyncMock(return_value="ok")

        for idx in range(5):
            agent.chat_history.add_user_message(f"u{idx}")
            agent.chat_history.add_assistant_message(f"a{idx}")
        assert len(agent.chat_history.messages) == 11

        response = await agent._generate_voice_response("nowa wiadomość")

        assert response == "ok"
        assert len(agent.chat_history.messages) == 10
        assert (
            "system" in str(getattr(agent.chat_history.messages[0], "role", "")).lower()
        )


class TestOllamaExtraBody:
    """Tests for the _ollama_extra_body() helper."""

    def test_returns_think_false_when_local_and_think_disabled(self, monkeypatch):
        mock_settings = MagicMock()
        mock_settings.LLM_SERVICE_TYPE = "local"
        mock_settings.OLLAMA_ENABLE_THINK = False
        monkeypatch.setattr(op_module, "SETTINGS", mock_settings)
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="vllm"),
        )

        result = _ollama_extra_body()

        assert result == {"think": False}

    def test_returns_none_when_not_local(self, monkeypatch):
        mock_settings = MagicMock()
        mock_settings.LLM_SERVICE_TYPE = "openai"
        mock_settings.OLLAMA_ENABLE_THINK = False
        monkeypatch.setattr(op_module, "SETTINGS", mock_settings)
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="vllm"),
        )

        result = _ollama_extra_body()

        assert result is None

    def test_returns_think_false_for_ollama_runtime(self, monkeypatch):
        mock_settings = MagicMock()
        mock_settings.LLM_SERVICE_TYPE = "openai"
        mock_settings.OLLAMA_ENABLE_THINK = False
        monkeypatch.setattr(op_module, "SETTINGS", mock_settings)
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="ollama"),
        )

        result = _ollama_extra_body()

        assert result == {"think": False}

    def test_returns_none_when_think_enabled(self, monkeypatch):
        mock_settings = MagicMock()
        mock_settings.LLM_SERVICE_TYPE = "local"
        mock_settings.OLLAMA_ENABLE_THINK = True
        monkeypatch.setattr(op_module, "SETTINGS", mock_settings)
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="ollama"),
        )

        result = _ollama_extra_body()

        assert result is None


class TestOllamaNativeCall:
    """Tests for the _ollama_native_call() async helper."""

    def _make_settings(self, endpoint="http://localhost:11434/v1", model="test-model"):
        mock_settings = MagicMock()
        mock_settings.LLM_LOCAL_ENDPOINT = endpoint
        mock_settings.LLM_MODEL_NAME = model
        return mock_settings

    def _make_mock_client_cls(self, response_data):
        """Build an async context manager mock for httpx.AsyncClient."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=response_data)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        return mock_client_cls, mock_client

    @pytest.mark.asyncio
    async def test_success_returns_content(self, monkeypatch):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings())
        mock_client_cls, _ = self._make_mock_client_cls(
            {"message": {"content": "answer"}}
        )
        monkeypatch.setattr(httpx, "AsyncClient", mock_client_cls)

        chat_history = ChatHistory()
        chat_history.add_user_message("hello")

        result = await _ollama_native_call(
            chat_history, max_tokens=150, temperature=0.7
        )

        assert result == "answer"

    @pytest.mark.asyncio
    async def test_strips_v1_from_endpoint(self, monkeypatch):
        monkeypatch.setattr(
            op_module,
            "SETTINGS",
            self._make_settings(endpoint="http://localhost:11434/v1"),
        )
        captured_urls = []

        async def fake_post(url, **kwargs):
            captured_urls.append(url)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value={"message": {"content": "ok"}})
            return mock_resp

        mock_client = AsyncMock()
        mock_client.post = fake_post

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(httpx, "AsyncClient", mock_client_cls)

        chat_history = ChatHistory()
        chat_history.add_user_message("test")

        await _ollama_native_call(chat_history, max_tokens=100, temperature=0.5)

        assert len(captured_urls) == 1
        assert captured_urls[0] == "http://localhost:11434/api/chat"

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self, monkeypatch):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings())

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock()
            )
        )

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(httpx, "AsyncClient", mock_client_cls)

        chat_history = ChatHistory()
        chat_history.add_user_message("test")

        result = await _ollama_native_call(
            chat_history, max_tokens=100, temperature=0.5
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_on_connection_error(self, monkeypatch):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings())

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(httpx, "AsyncClient", mock_client_cls)

        chat_history = ChatHistory()
        chat_history.add_user_message("test")

        result = await _ollama_native_call(
            chat_history, max_tokens=100, temperature=0.5
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_payload_has_think_false(self, monkeypatch):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings())
        captured_payloads = []

        async def fake_post(url, **kwargs):
            captured_payloads.append(kwargs.get("json", {}))
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value={"message": {"content": "ok"}})
            return mock_resp

        mock_client = AsyncMock()
        mock_client.post = fake_post

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(httpx, "AsyncClient", mock_client_cls)

        chat_history = ChatHistory()
        chat_history.add_user_message("test payload")

        await _ollama_native_call(chat_history, max_tokens=200, temperature=0.8)

        assert len(captured_payloads) == 1
        assert captured_payloads[0]["think"] is False


class TestGenerateVoiceResponseGuards:
    """Tests for the None/empty-list guard and Ollama fallback in _generate_voice_response."""

    @pytest.fixture
    def mock_kernel(self):
        kernel = MagicMock()
        kernel.get_service = MagicMock(return_value=MagicMock())
        kernel.services = {"chat": MagicMock()}
        return kernel

    def _make_settings(self, service_type="openai"):
        mock_settings = MagicMock()
        mock_settings.LLM_SERVICE_TYPE = service_type
        mock_settings.OLLAMA_ENABLE_THINK = False
        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        mock_settings.LLM_MODEL_NAME = "test-model"
        return mock_settings

    @pytest.mark.asyncio
    async def test_none_response_triggers_fallback_message(
        self, mock_kernel, monkeypatch
    ):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings("openai"))
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="vllm"),
        )
        agent = OperatorAgent(kernel=mock_kernel)
        agent._invoke_chat_with_fallbacks = AsyncMock(return_value=None)

        response = await agent._generate_voice_response("test input")

        assert (
            response == "Przepraszam, model nie zwrócił odpowiedzi. Spróbuj ponownie."
        )

    @pytest.mark.asyncio
    async def test_empty_list_response_triggers_fallback_message(
        self, mock_kernel, monkeypatch
    ):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings("openai"))
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="vllm"),
        )
        agent = OperatorAgent(kernel=mock_kernel)
        agent._invoke_chat_with_fallbacks = AsyncMock(return_value=[])

        response = await agent._generate_voice_response("test input")

        assert (
            response == "Przepraszam, model nie zwrócił odpowiedzi. Spróbuj ponownie."
        )

    @pytest.mark.asyncio
    async def test_list_response_uses_first_item(self, mock_kernel, monkeypatch):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings("openai"))
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="vllm"),
        )
        agent = OperatorAgent(kernel=mock_kernel)

        mock_item = SimpleNamespace(content="answer")
        agent._invoke_chat_with_fallbacks = AsyncMock(return_value=[mock_item])

        response = await agent._generate_voice_response("test input")

        assert response == "answer"

    @pytest.mark.asyncio
    async def test_empty_sk_with_local_service_calls_ollama_native(
        self, mock_kernel, monkeypatch
    ):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings("local"))
        agent = OperatorAgent(kernel=mock_kernel)
        agent._invoke_chat_with_fallbacks = AsyncMock(return_value="")
        monkeypatch.setattr(
            op_module, "_ollama_native_call", AsyncMock(return_value="native answer")
        )

        response = await agent._generate_voice_response("test input")

        assert response == "native answer"

    @pytest.mark.asyncio
    async def test_empty_sk_non_local_no_ollama_fallback(
        self, mock_kernel, monkeypatch
    ):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings("openai"))
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="vllm"),
        )
        agent = OperatorAgent(kernel=mock_kernel)
        agent._invoke_chat_with_fallbacks = AsyncMock(return_value="")

        native_mock = AsyncMock(return_value="should not be called")
        monkeypatch.setattr(op_module, "_ollama_native_call", native_mock)

        response = await agent._generate_voice_response("test input")

        assert (
            response == "Przepraszam, model nie zwrócił odpowiedzi. Spróbuj ponownie."
        )
        native_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_sk_with_ollama_runtime_calls_native_fallback(
        self, mock_kernel, monkeypatch
    ):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings("openai"))
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="ollama"),
        )
        agent = OperatorAgent(kernel=mock_kernel)
        agent._invoke_chat_with_fallbacks = AsyncMock(return_value="")
        native_mock = AsyncMock(return_value="native answer")
        monkeypatch.setattr(op_module, "_ollama_native_call", native_mock)

        response = await agent._generate_voice_response("test input")

        assert response == "native answer"
        native_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_prompt_leak_triggers_retry_with_minimal_history(
        self, mock_kernel, monkeypatch
    ):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings("openai"))
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="vllm"),
        )
        agent = OperatorAgent(kernel=mock_kernel)
        agent.chat_history.add_user_message("wcześniejsze pytanie")
        agent.chat_history.add_assistant_message(
            "Oto nowy tryb komunikacji: Tryb 1: Dwie odpowiedzie - Odpowiedzi MUSZĄ być krótkie."
        )

        call_payloads = []
        responses = iter(
            [
                "Oto nowy tryb komunikacji: Tryb 1: Dwie odpowiedzie - Odpowiedzi MUSZĄ być krótkie.",
                "Dwa.",
            ]
        )

        async def fake_invoke_chat_with_fallbacks(
            *, chat_service, chat_history, settings, enable_functions
        ):
            call_payloads.append(
                {
                    "messages": [
                        str(getattr(message, "role", "")).lower()
                        for message in chat_history.messages
                    ],
                    "count": len(chat_history.messages),
                    "enable_functions": enable_functions,
                    "service": chat_service,
                }
            )
            return next(responses)

        mock_chat_service = MagicMock()
        mock_kernel.get_service.return_value = mock_chat_service
        agent._invoke_chat_with_fallbacks = AsyncMock(
            side_effect=fake_invoke_chat_with_fallbacks
        )

        response = await agent._generate_voice_response("Ile to dwa?")

        assert response == "Dwa."
        assert agent._invoke_chat_with_fallbacks.await_count == 2
        assert call_payloads[0]["count"] == 3
        assert "assistant" not in call_payloads[0]["messages"][1:]
        assert call_payloads[1]["count"] == 2
        assert call_payloads[0]["enable_functions"] is False
        assert call_payloads[1]["enable_functions"] is False

    @pytest.mark.asyncio
    async def test_prompt_leak_after_retry_returns_fallback_message(
        self, mock_kernel, monkeypatch
    ):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings("openai"))
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="vllm"),
        )
        agent = OperatorAgent(kernel=mock_kernel)
        agent._invoke_chat_with_fallbacks = AsyncMock(
            side_effect=[
                "Oto nowy tryb komunikacji: Tryb 1: Dwie odpowiedzie.",
                "Tryb 2: NIE używaj markdown.",
            ]
        )

        response = await agent._generate_voice_response("Ile to dwa?")

        assert (
            response == "Przepraszam, model nie zwrócił odpowiedzi. Spróbuj ponownie."
        )

    @pytest.mark.asyncio
    async def test_retry_with_ollama_runtime_uses_native_fallback_when_empty(
        self, mock_kernel, monkeypatch
    ):
        monkeypatch.setattr(op_module, "SETTINGS", self._make_settings("openai"))
        monkeypatch.setattr(
            op_module,
            "get_active_llm_runtime",
            lambda: MagicMock(provider="ollama"),
        )
        agent = OperatorAgent(kernel=mock_kernel)
        agent._invoke_chat_with_fallbacks = AsyncMock(
            side_effect=[
                "Oto nowy tryb komunikacji: Tryb 1: Dwie odpowiedzie.",
                "",
            ]
        )
        native_mock = AsyncMock(return_value="Dwa razy dwa to cztery.")
        monkeypatch.setattr(op_module, "_ollama_native_call", native_mock)

        response = await agent._generate_voice_response("Ile to dwa razy dwa?")

        assert response == "Dwa razy dwa to cztery."
        assert native_mock.await_count == 1


class TestVoiceResponseNormalization:
    def test_extract_text_payload_supports_structures(self):
        payload = {
            "message": {
                "content": [
                    {"text": "Ala"},
                    {"response_text": "ma"},
                    " kota ",
                ]
            }
        }

        result = _extract_text_payload(payload)

        assert result == "Ala ma kota"

    def test_extract_text_payload_supports_object_attrs_and_bytes(self):
        obj = SimpleNamespace(content=b"  tak  ")
        assert _extract_text_payload(obj) == "tak"

    def test_extract_text_payload_supports_generated_text_fields(self):
        payload = {"generated_text": "Wynik 42"}
        assert _extract_text_payload(payload) == "Wynik 42"

        obj = SimpleNamespace(generated_text="Wynik 43")
        assert _extract_text_payload(obj) == "Wynik 43"

    def test_extract_text_payload_supports_mock_and_string_fallback(self):
        mocked = MagicMock()
        assert _extract_text_payload(mocked)
        assert _extract_text_payload(123) == "123"

    def test_extract_text_payload_handles_empty_mapping_message_chain(self):
        payload = {"content": "", "text": "", "response_text": "", "message": None}
        assert _extract_text_payload(payload) == ""

    def test_sanitize_and_normalize_voice_response_filter_instructions(self):
        raw = (
            "Oto nowy tryb komunikacji: Tryb 1.\n"
            "- nie używaj markdown i nie wymieniaj szczegółów.\n"
            "Dwa razy dwa to cztery."
        )
        cleaned = _sanitize_voice_response(raw)
        normalized, needs_retry = _normalize_voice_response(raw)

        assert cleaned == "Dwa razy dwa to cztery."
        assert normalized == "Dwa razy dwa to cztery."
        assert needs_retry is True

    def test_normalize_voice_response_without_leak(self):
        normalized, needs_retry = _normalize_voice_response("Krótka odpowiedź.")
        assert normalized == "Krótka odpowiedź."
        assert needs_retry is False

    def test_build_voice_retry_history_respects_mode_and_context(self):
        history = _build_voice_retry_history(
            input_text="Ile to dwa?",
            mode_prompt={"instruction": "Streść odpowiedź."},
            voice_context={"reasoning_summary": "r", "reasoning_summary_enabled": True},
            mode="summary",
        )

        roles = [str(getattr(msg, "role", "")).lower() for msg in history.messages]
        assert sum("system" in role for role in roles) == 3
        assert "user" in roles[-1]
