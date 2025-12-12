"""Moduł: token_economist - optymalizacja kontekstu i kalkulacja kosztów."""

from pathlib import Path
from typing import Dict, List

import yaml
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TokenEconomist:
    """Optymalizator kontekstu i kalkulator kosztów tokenów."""

    # Cennik tokenów (USD za 1M tokenów) - aktualizowany 2025-12-07
    PRICING = {
        "_updated": "2025-12-07",  # Data ostatniej aktualizacji cennika
        "gpt-4o": {"input": 5.0, "output": 15.0},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
        "claude-opus": {"input": 15.0, "output": 75.0},
        "claude-sonnet": {"input": 3.0, "output": 15.0},
        "gemini-pro": {"input": 0.5, "output": 1.5},
        "local": {"input": 0.0, "output": 0.0},  # Lokalny model jest darmowy
    }

    def __init__(self, enable_compression: bool = True, pricing_file: str = None):
        """
        Inicjalizacja Token Economist.

        Args:
            enable_compression: Czy włączyć kompresję kontekstu (domyślnie True)
            pricing_file: Ścieżka do pliku YAML z cennikiem (opcjonalne)
        """
        self.enable_compression = enable_compression
        self.pricing_file = pricing_file
        self.external_pricing = None

        # Wczytaj cennik z pliku YAML jeśli podano
        if pricing_file:
            self.load_pricing(pricing_file)

        logger.info(
            f"TokenEconomist zainicjalizowany (compression={enable_compression}, "
            f"pricing_file={'loaded' if self.external_pricing else 'not loaded'})"
        )

    def estimate_tokens(self, text: str) -> int:
        """
        Estymuje liczbę tokenów w tekście (heurystyka).

        Uwaga: To jest uproszczona estymacja. W produkcji użyj tiktoken.

        Args:
            text: Tekst do estymacji

        Returns:
            Przybliżona liczba tokenów
        """
        # Uproszczona heurystyka: zawsze ~4 znaki na token (oparta na angielskim),
        # NIE rozróżnia języka tekstu. Dla polskiego i tekstów mieszanych może zaniżać liczbę tokenów.
        # W produkcji użyj tiktoken lub detekcji języka i innego przelicznika.
        return max(1, len(text) // 4)

    def compress_context(
        self, history: ChatHistory, max_tokens: int = 4000, reserve_tokens: int = None
    ) -> ChatHistory:
        """
        Kompresuje historię czatu jeśli przekracza limit tokenów.

        Strategia:
        1. Zachowaj message SYSTEM (pierwsza wiadomość)
        2. Zachowaj ostatnich N wiadomości USER/ASSISTANT
        3. Starsze wiadomości zsumuj w jedno podsumowanie

        Args:
            history: Historia czatu do skompresowania
            max_tokens: Maksymalna liczba tokenów (domyślnie 4000)
            reserve_tokens: Tokeny zarezerwowane na podsumowanie (domyślnie z SETTINGS)

        Returns:
            Skompresowana historia czatu
        """
        if reserve_tokens is None:
            reserve_tokens = SETTINGS.RESERVE_TOKENS_FOR_SUMMARY

        if not self.enable_compression:
            logger.debug("Kompresja wyłączona, zwracam oryginalną historię")
            return history

        # Estymuj obecną liczbę tokenów
        total_tokens = sum(
            self.estimate_tokens(str(msg.content)) for msg in history.messages
        )

        if total_tokens <= max_tokens:
            logger.debug(
                f"Historia czatu mieści się w limicie ({total_tokens}/{max_tokens} tokenów)"
            )
            return history

        logger.info(
            f"Historia czatu przekracza limit ({total_tokens}/{max_tokens}), kompresuję..."
        )

        # Nowa skompresowana historia
        compressed_history = ChatHistory()

        # Zachowaj message SYSTEM (jeśli istnieje)
        if history.messages and history.messages[0].role == AuthorRole.SYSTEM:
            compressed_history.add_message(history.messages[0])
            remaining_messages = history.messages[1:]
        else:
            remaining_messages = history.messages

        # Ile tokenów mamy na pozostałe wiadomości
        system_tokens = (
            self.estimate_tokens(str(history.messages[0].content))
            if history.messages and history.messages[0].role == AuthorRole.SYSTEM
            else 0
        )
        available_tokens = max_tokens - system_tokens - reserve_tokens

        # Zachowaj ostatnie N wiadomości
        messages_to_keep = []
        tokens_count = 0

        for msg in reversed(remaining_messages):
            msg_tokens = self.estimate_tokens(str(msg.content))
            if tokens_count + msg_tokens <= available_tokens:
                messages_to_keep.insert(0, msg)
                tokens_count += msg_tokens
            else:
                break

        # Jeśli są starsze wiadomości, zsumuj je
        older_messages = (
            remaining_messages[: -len(messages_to_keep)]
            if messages_to_keep
            else remaining_messages
        )
        if older_messages:
            summary = self._summarize_messages(older_messages)
            compressed_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.ASSISTANT,
                    content=f"[PODSUMOWANIE WCZEŚNIEJSZEJ ROZMOWY]\n{summary}",
                )
            )

        # Dodaj zachowane wiadomości
        for msg in messages_to_keep:
            compressed_history.add_message(msg)

        new_total_tokens = sum(
            self.estimate_tokens(str(msg.content))
            for msg in compressed_history.messages
        )

        logger.info(
            f"Kompresja zakończona: {total_tokens} -> {new_total_tokens} tokenów "
            f"({len(history.messages)} -> {len(compressed_history.messages)} wiadomości)"
        )

        return compressed_history

    def _summarize_messages(self, messages: List[ChatMessageContent]) -> str:
        """
        Tworzy podsumowanie starszych wiadomości.

        Args:
            messages: Lista wiadomości do podsumowania

        Returns:
            Podsumowanie w formie tekstu
        """
        # Uproszczone podsumowanie - w produkcji użyj LLM do sumaryzacji
        summary_parts = []

        user_questions = []
        assistant_responses = []

        for msg in messages:
            content = str(msg.content)[:200]  # Ogranicz długość
            if msg.role == AuthorRole.USER:
                user_questions.append(content)
            elif msg.role == AuthorRole.ASSISTANT:
                assistant_responses.append(content)

        if user_questions:
            summary_parts.append(f"Użytkownik pytał o: {', '.join(user_questions[:3])}")

        if assistant_responses:
            summary_parts.append(
                f"Asystent odpowiedział na tematy: {', '.join(assistant_responses[:3])}"
            )

        return (
            " | ".join(summary_parts)
            if summary_parts
            else "Brak treści do podsumowania"
        )

    def calculate_cost(
        self,
        usage: dict,
        model_name: str = "gpt-3.5-turbo",
    ) -> dict:
        """
        Kalkuluje koszt użycia modelu.

        Args:
            usage: Dict z kluczami 'input_tokens' i 'output_tokens'
            model_name: Nazwa modelu (dla określenia ceny)

        Returns:
            Dict z kosztami i szczegółami
        """
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        # Znajdź cennik dla modelu
        pricing = self._get_pricing(model_name)

        # Oblicz koszty
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_cost_usd": round(input_cost, 6),
            "output_cost_usd": round(output_cost, 6),
            "total_cost_usd": round(total_cost, 6),
            "model": model_name,
        }

    def _get_pricing(self, model_name: str) -> dict:
        """
        Pobiera cennik dla modelu.

        Args:
            model_name: Nazwa modelu

        Returns:
            Dict z cenami input/output
        """
        # Normalizuj nazwę modelu
        model_name_lower = model_name.lower()

        # Sprawdź czy to lokalny model (używając patterns z config)
        for pattern in SETTINGS.LOCAL_MODEL_PATTERNS:
            if pattern in model_name_lower:
                return self.PRICING["local"]

        # Sprawdź predefiniowane modele
        for key, pricing in self.PRICING.items():
            if key in model_name_lower:
                return pricing

        # Domyślnie użyj ceny GPT-3.5 (konwersatywna estymacja)
        logger.warning(
            f"Nieznany model {model_name}, używam cennika GPT-3.5 jako fallback"
        )
        return self.PRICING["gpt-3.5-turbo"]

    def estimate_request_cost(
        self,
        prompt: str,
        expected_output_tokens: int = 500,
        model_name: str = "gpt-3.5-turbo",
    ) -> dict:
        """
        Estymuje koszt requesta przed jego wykonaniem.

        Args:
            prompt: Treść promptu
            expected_output_tokens: Oczekiwana liczba tokenów odpowiedzi
            model_name: Nazwa modelu

        Returns:
            Dict z estymowanymi kosztami
        """
        input_tokens = self.estimate_tokens(prompt)

        usage = {
            "input_tokens": input_tokens,
            "output_tokens": expected_output_tokens,
        }

        return self.calculate_cost(usage, model_name)

    def get_token_statistics(self, history: ChatHistory) -> dict:
        """
        Zwraca statystyki tokenów dla historii czatu.

        Args:
            history: Historia czatu

        Returns:
            Dict ze statystykami
        """
        total_tokens = 0
        messages_by_role = {"system": 0, "user": 0, "assistant": 0}
        tokens_by_role = {"system": 0, "user": 0, "assistant": 0}

        for msg in history.messages:
            tokens = self.estimate_tokens(str(msg.content))
            total_tokens += tokens

            role = msg.role.value.lower()
            if role in messages_by_role:
                messages_by_role[role] += 1
                tokens_by_role[role] += tokens

        return {
            "total_tokens": total_tokens,
            "total_messages": len(history.messages),
            "messages_by_role": messages_by_role,
            "tokens_by_role": tokens_by_role,
            "compression_needed": total_tokens > 4000,
        }

    def load_pricing(self, pricing_file: str = None) -> Dict:
        """
        Wczytuje cennik z pliku YAML.

        Args:
            pricing_file: Ścieżka do pliku YAML (domyślnie data/config/pricing.yaml)

        Returns:
            Dict z cennikiem lub None jeśli wczytanie się nie powiodło
        """
        if pricing_file is None:
            # Domyślna ścieżka do pricing.yaml
            project_root = Path(__file__).parent.parent.parent
            pricing_file = project_root / "data" / "config" / "pricing.yaml"
        else:
            pricing_file = Path(pricing_file)

        if not pricing_file.exists():
            logger.warning(f"Plik cennika nie istnieje: {pricing_file}")
            return None

        try:
            with open(pricing_file, "r", encoding="utf-8") as f:
                pricing_data = yaml.safe_load(f)

            self.external_pricing = pricing_data
            logger.info(f"Wczytano cennik z pliku: {pricing_file}")
            return pricing_data
        except Exception as e:
            logger.error(f"Błąd podczas wczytywania cennika: {e}")
            return None

    def estimate_task_cost(
        self, service_id: str, prompt_length: int, output_ratio: float = 0.5
    ) -> Dict:
        """
        Estymuje koszt wykonania zadania przed jego wykonaniem.

        Args:
            service_id: Identyfikator serwisu/modelu (np. 'gpt-4o', 'local', 'gemini-1.5-flash')
            prompt_length: Długość promptu (liczba znaków)
            output_ratio: Stosunek długości outputu do inputu (domyślnie 0.5 = 50%)

        Returns:
            Dict z estymowanym kosztem i szczegółami:
            - service_id: nazwa serwisu
            - input_tokens: liczba tokenów wejściowych
            - output_tokens: estymowana liczba tokenów wyjściowych
            - estimated_cost_usd: estymowany koszt w USD
            - is_free: czy model jest darmowy (lokalny)
        """
        # Oblicz liczbę tokenów w prompcie (heurystyka: ~4 znaki na token)
        input_tokens = max(1, prompt_length // 4)

        # Estymuj output (pesymistycznie - zakładamy output_ratio)
        output_tokens = int(input_tokens * output_ratio)

        # Pobierz cennik
        pricing = self._get_pricing_for_service(service_id)

        # Oblicz koszty (ceny per 1K tokenów)
        input_cost = (input_tokens / 1_000) * pricing["input"]
        output_cost = (output_tokens / 1_000) * pricing["output"]
        total_cost = input_cost + output_cost

        is_free = total_cost == 0.0

        logger.debug(
            f"Estymacja kosztu dla {service_id}: "
            f"{input_tokens} in + {output_tokens} out = ${total_cost:.6f}"
        )

        return {
            "service_id": service_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(total_cost, 6),
            "is_free": is_free,
        }

    def compare_providers(self, prompt: str, providers: List[str] = None) -> List[Dict]:
        """
        Porównuje koszty wykonania zadania między różnymi providerami.

        Args:
            prompt: Treść promptu
            providers: Lista providerów do porównania (domyślnie: local, gpt-4o-mini, gpt-4o, gemini-1.5-flash)

        Returns:
            Lista dict posortowana od najtańszego do najdroższego:
            - provider: nazwa providera
            - cost: estymowany koszt
            - input_tokens: liczba tokenów wejściowych
            - output_tokens: estymowana liczba tokenów wyjściowych
            - is_free: czy provider jest darmowy
        """
        if providers is None:
            providers = ["local", "gpt-4o-mini", "gpt-4o", "gemini-1.5-flash"]

        results = []
        prompt_length = len(prompt)

        for provider in providers:
            estimate = self.estimate_task_cost(provider, prompt_length)
            results.append(
                {
                    "provider": provider,
                    "cost": estimate["estimated_cost_usd"],
                    "input_tokens": estimate["input_tokens"],
                    "output_tokens": estimate["output_tokens"],
                    "is_free": estimate["is_free"],
                }
            )

        # Sortuj od najtańszego do najdroższego
        results.sort(key=lambda x: x["cost"])

        if results:
            logger.info(
                f"Porównanie providerów: Najtańszy={results[0]['provider']} "
                f"(${results[0]['cost']:.6f}), Najdroższy={results[-1]['provider']} "
                f"(${results[-1]['cost']:.6f})"
            )
        else:
            logger.info("Nie udało się oszacować kosztów dla żadnego providera.")

        return results

    def _get_pricing_for_service(self, service_id: str) -> Dict:
        """
        Pobiera cennik dla danego serwisu z pliku YAML lub fallback do PRICING.

        Args:
            service_id: Identyfikator serwisu

        Returns:
            Dict z cenami input/output per 1K tokenów
        """
        service_id_lower = service_id.lower()

        # Najpierw sprawdź external_pricing (z YAML)
        if self.external_pricing:
            models_pricing = self.external_pricing.get("models", {})
            if service_id_lower in models_pricing:
                yaml_pricing = models_pricing[service_id_lower]
                # YAML ma ceny per 1K tokenów, zwracamy bezpośrednio
                return {
                    "input": yaml_pricing.get("input_cost_per_1k", 0.0),
                    "output": yaml_pricing.get("output_cost_per_1k", 0.0),
                }

        # Fallback do statycznego cennika PRICING (ceny per 1M)
        # Konwertuj per 1M na per 1K (podziel przez 1000)
        pricing_1m = self._get_pricing(service_id)
        return {
            "input": pricing_1m["input"] / 1000,
            "output": pricing_1m["output"] / 1000,
        }
