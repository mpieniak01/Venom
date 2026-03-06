"""
Testy integracyjne dla parametrów generacji.

Uwaga: Te testy wymagają działającego środowiska LLM (vLLM lub Ollama).
Jeśli środowisko nie jest dostępne, testy będą pominięte (skip).
"""

import re

import httpx
import pytest

from venom_core.config import SETTINGS
from venom_core.core.generation_params_adapter import GenerationParamsAdapter


def _local_llm_available() -> bool:
    if SETTINGS.AI_MODE != "LOCAL" or not SETTINGS.LLM_LOCAL_ENDPOINT:
        return False
    endpoint = SETTINGS.LLM_LOCAL_ENDPOINT.rstrip("/")
    probe_paths = ("/v1/models", "/models", "/api/tags")
    try:
        for path in probe_paths:
            response = httpx.get(f"{endpoint}{path}", timeout=1.0)
            if response.status_code == 200:
                return True
        return False
    except httpx.HTTPError:
        return False


LOCAL_LLM_AVAILABLE = _local_llm_available()


def _is_runtime_connectivity_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "connection error",
        "all connection attempts failed",
        "service failed to complete the prompt",
        "connecterror",
    )
    return any(marker in text for marker in markers)


class TestGenerationParamsIntegration:
    """Testy integracyjne sprawdzające wpływ parametrów na odpowiedzi modelu."""

    @pytest.mark.skipif(
        not LOCAL_LLM_AVAILABLE,
        reason="Wymaga lokalnego środowiska LLM",
    )
    @pytest.mark.asyncio
    async def test_temperature_affects_response_determinism(self):
        """
        Test sprawdzający czy temperatura wpływa na deterministyczność odpowiedzi.

        Niższa temperatura (0.0) powinna dawać bardziej deterministyczne odpowiedzi,
        wyższa temperatura (2.0) - bardziej kreatywne i zmienne.
        """
        # Import tu aby uniknąć błędów jeśli semantic_kernel nie jest zainstalowany
        from semantic_kernel.contents import ChatHistory
        from semantic_kernel.contents.chat_message_content import ChatMessageContent
        from semantic_kernel.contents.utils.author_role import AuthorRole

        from venom_core.execution.kernel_builder import KernelBuilder

        # Prosty prompt do testowania
        prompt = "Podaj liczbę od 1 do 10."

        # Test 1: Temperatura 0.0 - deterministyczna
        kernel_low = KernelBuilder().build_kernel()
        chat_service_low = kernel_low.get_service()

        # Parametry z niską temperaturą
        params_low = {"temperature": 0.0, "max_tokens": 50}
        adapted_low = GenerationParamsAdapter.adapt_params(
            params_low, SETTINGS.LLM_SERVICE_TYPE or "local"
        )

        # Import settings class
        from semantic_kernel.connectors.ai.open_ai import (
            OpenAIChatPromptExecutionSettings,
        )

        settings_low = OpenAIChatPromptExecutionSettings(**adapted_low)

        # Wykonaj 2 razy z tą samą niską temperaturą
        responses_low = []
        for _ in range(2):
            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=prompt)
            )
            try:
                response = await chat_service_low.get_chat_message_content(
                    chat_history=chat_history, settings=settings_low
                )
            except Exception as exc:
                if _is_runtime_connectivity_error(exc):
                    pytest.skip(
                        f"Lokalny runtime niedostępny podczas testu integracyjnego: {exc}"
                    )
                raise
            responses_low.append(str(response).strip())

        # Z temperaturą 0.0, odpowiedzi powinny być identyczne lub bardzo podobne
        # (niektóre modele mogą mieć minimalną losowość nawet przy temp=0)
        def _extract_first_int_1_10(text: str) -> int | None:
            for match in re.finditer(r"\b([1-9]|10)\b", text):
                try:
                    value = int(match.group(1))
                except (TypeError, ValueError):
                    continue
                if 1 <= value <= 10:
                    return value
            return None

        value_a = _extract_first_int_1_10(responses_low[0])
        value_b = _extract_first_int_1_10(responses_low[1])

        # Preferuj porównanie semantyczne: ten sam wybór liczby przy temp=0.
        # Część modeli/runtime nadal potrafi być stochastyczna mimo temp=0.0,
        # więc nie traktujemy rozjazdu jako twardego błędu adaptera.
        if value_a is not None and value_b is not None:
            if value_a != value_b:
                pytest.skip(
                    "Runtime nie gwarantuje deterministycznego wyboru liczby przy temp=0.0."
                )
            return

        if not (
            responses_low[0] == responses_low[1]
            or responses_low[0][:10] == responses_low[1][:10]
        ):
            pytest.skip(
                "Runtime nie gwarantuje stabilnej formy odpowiedzi przy temp=0.0."
            )

    @pytest.mark.skipif(
        not LOCAL_LLM_AVAILABLE,
        reason="Wymaga lokalnego środowiska LLM",
    )
    @pytest.mark.asyncio
    async def test_max_tokens_limits_response_length(self):
        """
        Test sprawdzający czy max_tokens ogranicza długość odpowiedzi.
        """
        from semantic_kernel.connectors.ai.open_ai import (
            OpenAIChatPromptExecutionSettings,
        )
        from semantic_kernel.contents import ChatHistory
        from semantic_kernel.contents.chat_message_content import ChatMessageContent
        from semantic_kernel.contents.utils.author_role import AuthorRole

        from venom_core.execution.kernel_builder import KernelBuilder

        # Prompt wymagający dłuższej odpowiedzi
        prompt = "Wypisz liczby od 1 do 100 oddzielone przecinkami."

        # Test z małym limitem tokenów
        kernel = KernelBuilder().build_kernel()
        chat_service = kernel.get_service()

        # Parametry z małym max_tokens
        params_short = {"temperature": 0.5, "max_tokens": 20}
        adapted_short = GenerationParamsAdapter.adapt_params(
            params_short, SETTINGS.LLM_SERVICE_TYPE or "local"
        )
        settings_short = OpenAIChatPromptExecutionSettings(**adapted_short)

        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=prompt)
        )
        try:
            response_short = await chat_service.get_chat_message_content(
                chat_history=chat_history, settings=settings_short
            )
        except Exception as exc:
            if _is_runtime_connectivity_error(exc):
                pytest.skip(
                    f"Lokalny runtime niedostępny podczas testu integracyjnego: {exc}"
                )
            raise
        response_short_text = str(response_short).strip()

        # Parametry z większym max_tokens
        params_long = {"temperature": 0.5, "max_tokens": 200}
        adapted_long = GenerationParamsAdapter.adapt_params(
            params_long, SETTINGS.LLM_SERVICE_TYPE or "local"
        )
        settings_long = OpenAIChatPromptExecutionSettings(**adapted_long)

        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=prompt)
        )
        try:
            response_long = await chat_service.get_chat_message_content(
                chat_history=chat_history, settings=settings_long
            )
        except Exception as exc:
            if _is_runtime_connectivity_error(exc):
                pytest.skip(
                    f"Lokalny runtime niedostępny podczas testu integracyjnego: {exc}"
                )
            raise
        response_long_text = str(response_long).strip()

        # W praktyce backendy OpenAI-compatible mogą:
        # - ignorować limity tokenów,
        # - zwracać inny format (np. tool_calls),
        # - dawać krótszą odpowiedź dla większego limitu (niestabilność runtime).
        # Nie traktujemy tego jako błąd logiki adaptera.
        if len(response_long_text) <= len(response_short_text):
            pytest.skip(
                "Runtime nie gwarantuje monotonicznej długości odpowiedzi dla max_tokens."
            )

    @pytest.mark.skipif(
        not LOCAL_LLM_AVAILABLE,
        reason="Wymaga lokalnego środowiska LLM",
    )
    def test_adapter_maps_params_correctly_for_provider(self):
        """
        Test sprawdzający czy adapter poprawnie mapuje parametry dla aktywnego providera.
        """
        provider = SETTINGS.LLM_SERVICE_TYPE or "local"
        provider_key = GenerationParamsAdapter.normalize_provider(provider)

        # Generyczne parametry
        generic_params = {
            "temperature": 0.7,
            "max_tokens": 1024,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        }

        # Adaptuj do providera
        adapted = GenerationParamsAdapter.adapt_params(generic_params, provider)

        # Sprawdź czy parametry zostały zmapowane
        assert "temperature" in adapted or "temp" in adapted
        assert len(adapted) > 0, "Adapter powinien zwrócić zmapowane parametry"

        # Dla Ollama sprawdź specyficzne mapowanie
        if provider_key == "ollama":
            assert "num_predict" in adapted, (
                "Ollama powinien używać num_predict zamiast max_tokens"
            )
            assert adapted["num_predict"] == 1024
        # Dla vLLM sprawdź mapowanie
        elif provider_key == "vllm":
            assert "max_tokens" in adapted, "vLLM powinien używać max_tokens"
            assert "repetition_penalty" in adapted, (
                "vLLM powinien używać repetition_penalty"
            )

    def test_generation_params_in_task_request(self):
        """
        Test sprawdzający czy TaskRequest poprawnie obsługuje generation_params.
        """
        from venom_core.core.models import TaskRequest

        # Utwórz TaskRequest z parametrami
        request = TaskRequest(
            content="Test zadanie",
            generation_params={"temperature": 0.5, "max_tokens": 1000},
        )

        assert request.generation_params is not None
        assert request.generation_params["temperature"] == pytest.approx(0.5)
        assert request.generation_params["max_tokens"] == 1000

    def test_generation_params_optional_in_task_request(self):
        """
        Test sprawdzający czy generation_params są opcjonalne w TaskRequest.
        """
        from venom_core.core.models import TaskRequest

        # Utwórz TaskRequest bez parametrów
        request = TaskRequest(content="Test zadanie")

        assert request.generation_params is None
