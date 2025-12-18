"""
Adapter parametrów generacji - mapowanie generycznych parametrów na specyfikę vLLM/Ollama.

Umożliwia przekazywanie parametrów generacji (temperature, max_tokens, etc.) 
do różnych backendów LLM z uwzględnieniem ich specyficznych wymagań.
"""

from typing import Any, Dict, Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class GenerationParamsAdapter:
    """
    Adapter mapujący generyczne parametry generacji na format specyficzny dla danego providera.
    """

    # Mapowanie nazw parametrów dla różnych providerów
    PARAM_MAPPINGS = {
        "ollama": {
            "max_tokens": "num_predict",  # Ollama używa num_predict zamiast max_tokens
            "temperature": "temperature",
            "top_p": "top_p",
            "top_k": "top_k",
            "repeat_penalty": "repeat_penalty",
        },
        "vllm": {
            # vLLM używa standardowych nazw OpenAI API
            "max_tokens": "max_tokens",
            "temperature": "temperature",
            "top_p": "top_p",
            "top_k": "top_k",
            "repeat_penalty": "repetition_penalty",  # vLLM używa repetition_penalty
        },
        "openai": {
            # OpenAI API - standardowe nazwy
            "max_tokens": "max_tokens",
            "temperature": "temperature",
            "top_p": "top_p",
            # OpenAI nie wspiera top_k i repeat_penalty
        },
    }

    @classmethod
    def adapt_params(
        cls,
        generation_params: Optional[Dict[str, Any]],
        provider: str = "local",
    ) -> Dict[str, Any]:
        """
        Adaptuje parametry generacji do formatu specyficznego dla providera.

        Args:
            generation_params: Słownik z generycznymi parametrami generacji
            provider: Typ providera ("ollama", "vllm", "openai", "local")

        Returns:
            Słownik z parametrami w formacie zrozumiałym dla providera

        Examples:
            >>> params = {"temperature": 0.5, "max_tokens": 1024}
            >>> adapted = GenerationParamsAdapter.adapt_params(params, "ollama")
            >>> adapted
            {"temperature": 0.5, "num_predict": 1024}
        """
        if not generation_params:
            logger.debug("Brak parametrów generacji do adaptacji")
            return {}

        # Wykryj rzeczywisty provider na podstawie heurystyk
        provider_key = cls._detect_provider(provider)
        logger.debug(f"Wykryto provider: {provider_key} (oryginalnie: {provider})")

        # Pobierz mapowanie dla providera
        param_mapping = cls.PARAM_MAPPINGS.get(provider_key, {})

        adapted = {}
        for generic_name, value in generation_params.items():
            # Mapuj nazwę parametru
            provider_name = param_mapping.get(generic_name, generic_name)

            # Pomiń parametry nieobsługiwane przez providera
            if provider_key == "openai" and generic_name in ["top_k", "repeat_penalty"]:
                logger.debug(
                    f"Pomijam parametr '{generic_name}' - nieobsługiwany przez OpenAI"
                )
                continue

            adapted[provider_name] = value
            if provider_name != generic_name:
                logger.debug(
                    f"Zmapowano parametr: {generic_name} -> {provider_name} = {value}"
                )

        logger.info(
            f"Zaadaptowano {len(adapted)} parametrów dla providera '{provider_key}'"
        )
        return adapted

    @classmethod
    def _detect_provider(cls, provider: str) -> str:
        """
        Wykrywa rzeczywisty provider na podstawie podanej wartości.

        Args:
            provider: Wartość providera z konfiguracji

        Returns:
            Klucz providera do użycia w mapowaniu
        """
        provider_lower = provider.lower()

        if "ollama" in provider_lower:
            return "ollama"
        elif "vllm" in provider_lower:
            return "vllm"
        elif "openai" in provider_lower or "azure" in provider_lower:
            return "openai"
        elif provider_lower == "local":
            # Dla lokalnego providera spróbuj wykryć z runtime info
            try:
                from venom_core.utils.llm_runtime import get_active_llm_runtime

                runtime = get_active_llm_runtime()
                detected = runtime.provider.lower()
                if detected in ["ollama", "vllm", "openai"]:
                    logger.debug(
                        f"Wykryto provider z runtime: {detected} (dla 'local')"
                    )
                    return detected
            except Exception as e:
                logger.debug(f"Nie udało się wykryć providera z runtime: {e}")

            # Fallback do vLLM (najczęstszy w projekcie)
            logger.debug("Używam domyślnego mapowania vLLM dla providera 'local'")
            return "vllm"
        else:
            # Domyślnie zwróć oryginalną wartość
            logger.warning(
                f"Nieznany provider '{provider}', używam mapowania domyślnego"
            )
            return provider_lower

    @classmethod
    def merge_with_defaults(
        cls,
        generation_params: Optional[Dict[str, Any]],
        default_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Łączy parametry użytkownika z domyślnymi parametrami.

        Args:
            generation_params: Parametry od użytkownika
            default_params: Domyślne parametry (opcjonalne)

        Returns:
            Połączony słownik parametrów
        """
        if default_params is None:
            default_params = {}

        if not generation_params:
            return default_params.copy()

        # Parametry użytkownika nadpisują domyślne
        merged = default_params.copy()
        merged.update(generation_params)

        logger.debug(f"Połączono parametry: {len(merged)} parametrów łącznie")
        return merged
