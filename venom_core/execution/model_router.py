"""
Moduł: model_router - Hybrydowy router modeli AI (Local First + Cloud Options).

Router zarządza ruchem zapytań między lokalnym LLM a chmurą,
priorytetyzując prywatność i zerowy koszt operacyjny.
"""

from enum import Enum
from pathlib import Path

from venom_core.config import SETTINGS
from venom_core.core.token_economist import TokenEconomist
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TaskType(str, Enum):
    """Typy zadań określające routing."""

    STANDARD = "STANDARD"  # Standardowe zadania (chat, proste pytania)
    CHAT = "CHAT"  # Rozmowy
    CODING_SIMPLE = "CODING_SIMPLE"  # Proste zadania kodowania
    CODING_COMPLEX = "CODING_COMPLEX"  # Złożone zadania kodowania (>5 plików)
    SENSITIVE = "SENSITIVE"  # Wrażliwe dane (hasła, klucze) - ZAWSZE local
    ANALYSIS = "ANALYSIS"  # Analiza danych
    GENERATION = "GENERATION"  # Generowanie treści
    RESEARCH = "RESEARCH"  # Badania, wyszukiwanie w Internecie


class AIMode(str, Enum):
    """Tryby pracy systemu AI."""

    LOCAL = "LOCAL"  # Tylko lokalne, chmura zablokowana
    HYBRID = "HYBRID"  # Lokalne do prostych zadań, chmura do trudnych
    CLOUD = "CLOUD"  # Wszystko w chmurze


class HybridModelRouter:
    """
    Hybrydowy router modeli AI.

    Zarządza routingiem zapytań między lokalnym LLM a chmurą,
    priorytetując prywatność i oszczędność kosztów.
    """

    def __init__(self, settings=None, state_manager=None, token_economist=None):
        """
        Inicjalizacja routera.

        Args:
            settings: Konfiguracja (domyślnie SETTINGS)
            state_manager: StateManager dla Cost Guard (opcjonalny)
            token_economist: TokenEconomist do estymacji kosztów (opcjonalny)
        """
        self.settings = settings or SETTINGS
        self.ai_mode = AIMode(self.settings.AI_MODE.upper())
        self.state_manager = state_manager  # Opcjonalna integracja z Cost Guard
        
        # Inicjalizuj TokenEconomist z plikiem cennika
        if token_economist:
            self.token_economist = token_economist
        else:
            pricing_file = Path(__file__).parent.parent.parent / "data" / "config" / "pricing.yaml"
            self.token_economist = TokenEconomist(pricing_file=str(pricing_file))

        logger.info(
            f"HybridModelRouter zainicjalizowany (mode={self.ai_mode.value}, "
            f"provider={self.settings.HYBRID_CLOUD_PROVIDER})"
        )

    def route_task(self, task_type: TaskType, prompt: str = "") -> dict:
        """
        Określa routing dla zadania.

        Args:
            task_type: Typ zadania
            prompt: Opcjonalny prompt (dla dodatkowej analizy)

        Returns:
            Dict z informacjami o routingu:
            - target: 'local' lub 'cloud'
            - model_name: nazwa modelu
            - provider: 'local', 'google', 'openai'
            - reason: uzasadnienie decyzji
            - is_paid: czy to płatny model (boolean)
        """
        # PRIORYTET 1: Dane wrażliwe ZAWSZE idą do lokalnego modelu
        if task_type == TaskType.SENSITIVE or (
            self.settings.SENSITIVE_DATA_LOCAL_ONLY
            and self._is_sensitive_content(prompt)
        ):
            return self._route_to_local(
                "Wrażliwe dane - HARD BLOCK na wyjście do sieci"
            )

        # PRIORYTET 2: Tryb LOCAL - wszystko lokalnie
        if self.ai_mode == AIMode.LOCAL:
            return self._route_to_local(f"Tryb LOCAL - zadanie {task_type.value}")

        # PRIORYTET 3: Tryb CLOUD - wszystko do chmury (jeśli nie wrażliwe)
        if self.ai_mode == AIMode.CLOUD:
            if task_type == TaskType.SENSITIVE:
                return self._route_to_local(
                    "Dane wrażliwe - wymuszenie lokalnego modelu"
                )
            # GLOBAL COST GUARD: Sprawdź czy tryb płatny jest włączony
            return self._route_to_cloud_with_guard(
                f"Tryb CLOUD - zadanie {task_type.value}"
            )

        # PRIORYTET 4: Tryb HYBRID - inteligentny routing
        return self._hybrid_route(task_type, prompt)

    def _hybrid_route(self, task_type: TaskType, prompt: str) -> dict:
        """
        Routing w trybie hybrydowym z logiką "Low-Cost".

        Args:
            task_type: Typ zadania
            prompt: Prompt

        Returns:
            Dict z informacjami o routingu
        """
        # Oblicz złożoność zadania (0-10)
        complexity = self.calculate_complexity(prompt, task_type)
        
        # LOW-COST ROUTING: Jeśli złożoność < 5 (proste) -> zawsze LOCAL
        if complexity < 5:
            logger.info(f"[Low-Cost Routing] Complexity={complexity} -> LOCAL")
            return self._route_to_local(
                f"Tryb HYBRID: niski complexity={complexity} -> LOCAL (oszczędność)"
            )
        
        # Zadania proste -> LOCAL
        if task_type in [TaskType.STANDARD, TaskType.CHAT, TaskType.CODING_SIMPLE]:
            return self._route_to_local(
                f"Tryb HYBRID: proste zadanie {task_type.value} -> LOCAL"
            )

        # RESEARCH - routing zależy od paid_mode
        # Router sprawdza paid_mode_enabled i decyduje o użyciu Google Grounding vs DuckDuckGo
        if task_type == TaskType.RESEARCH:
            # Sprawdź czy paid mode jest włączony
            paid_mode_enabled = False
            if self.state_manager:
                paid_mode_enabled = self.state_manager.is_paid_mode_enabled()

            if paid_mode_enabled and self._has_cloud_access():
                # Paid mode ON + API key available -> Google Grounding
                logger.info("[Router] Research mode: GROUNDING (Paid)")
                return self._route_to_cloud(
                    "Tryb HYBRID: zadanie RESEARCH -> CLOUD (Google Grounding)"
                )
            else:
                # Paid mode OFF or no API key -> DuckDuckGo
                logger.info("[Router] Research mode: DUCKDUCKGO (Free)")
                return self._route_to_local(
                    "Tryb HYBRID: zadanie RESEARCH -> LOCAL (DuckDuckGo)"
                )

        # Zadania złożone -> CLOUD (jeśli dostępna konfiguracja + Cost Guard)
        # LOW-COST ROUTING: Sprawdź estymowany koszt przed użyciem CLOUD_HIGH
        if task_type in [
            TaskType.CODING_COMPLEX,
            TaskType.ANALYSIS,
            TaskType.GENERATION,
        ]:
            # Sprawdź czy mamy klucz API dla chmury
            if self._has_cloud_access():
                # Estymuj koszt dla CLOUD_HIGH (np. GPT-4o)
                cloud_high_model = self.settings.HYBRID_CLOUD_MODEL
                cost_estimate = self.token_economist.estimate_task_cost(
                    cloud_high_model, len(prompt)
                )
                
                # Próg bezpieczeństwa: $0.01
                COST_THRESHOLD = 0.01
                
                if cost_estimate["estimated_cost_usd"] > COST_THRESHOLD:
                    logger.warning(
                        f"[Low-Cost Guard] Koszt {cloud_high_model}: "
                        f"${cost_estimate['estimated_cost_usd']:.4f} > ${COST_THRESHOLD} -> "
                        f"Fallback do CLOUD_FAST"
                    )
                    # Fallback do CLOUD_FAST (np. GPT-4o-mini)
                    return self._route_to_cloud_fast(
                        f"Tryb HYBRID: koszt zbyt wysoki -> CLOUD_FAST (oszczędność)"
                    )
                
                logger.info(
                    f"[Low-Cost Guard] Koszt {cloud_high_model}: "
                    f"${cost_estimate['estimated_cost_usd']:.4f} <= ${COST_THRESHOLD} -> OK"
                )
                
                return self._route_to_cloud_with_guard(
                    f"Tryb HYBRID: złożone zadanie {task_type.value} -> CLOUD"
                )
            else:
                return self._route_to_local(
                    "Tryb HYBRID: brak dostępu do chmury -> LOCAL (fallback)"
                )

        # Domyślnie -> LOCAL
        return self._route_to_local("Tryb HYBRID: domyślny routing -> LOCAL")

    def _route_to_local(self, reason: str) -> dict:
        """
        Tworzy routing do lokalnego modelu.

        Args:
            reason: Uzasadnienie decyzji

        Returns:
            Dict z informacjami o routingu
        """
        logger.debug(f"Routing do LOCAL: {reason}")
        return {
            "target": "local",
            "model_name": self.settings.HYBRID_LOCAL_MODEL
            or self.settings.LLM_MODEL_NAME,
            "provider": "local",
            "endpoint": self.settings.LLM_LOCAL_ENDPOINT,
            "reason": reason,
            "is_paid": False,  # Model lokalny = darmowy
        }

    def _route_to_cloud(self, reason: str) -> dict:
        """
        Tworzy routing do chmury.

        Args:
            reason: Uzasadnienie decyzji

        Returns:
            Dict z informacjami o routingu
        """
        logger.debug(f"Routing do CLOUD: {reason}")

        provider = self.settings.HYBRID_CLOUD_PROVIDER.lower()
        model_name = self.settings.HYBRID_CLOUD_MODEL

        return {
            "target": "cloud",
            "model_name": model_name,
            "provider": provider,
            "endpoint": None,  # Endpoint jest domyślny dla providera
            "reason": reason,
            "is_paid": True,  # Model chmurowy = płatny
        }

    def _route_to_cloud_with_guard(self, reason: str) -> dict:
        """
        Tworzy routing do chmury z Global Cost Guard.

        Sprawdza czy tryb płatny jest włączony. Jeśli nie, wykonuje fallback do lokalnego modelu.

        Args:
            reason: Uzasadnienie decyzji

        Returns:
            Dict z informacjami o routingu
        """
        # Sprawdź czy Cost Guard jest aktywny
        if self._is_cost_guard_blocking():
            logger.warning(
                f"🔒 COST GUARD: Zablokowano dostęp do Cloud API. "
                f"Fallback do LOCAL. Powód: {reason}"
            )
            return self._route_to_local(
                f"COST GUARD: Paid Mode wyłączony - fallback do LOCAL. "
                f"Pierwotny powód: {reason}"
            )

        # Tryb płatny włączony lub brak state_manager - przepuść do chmury
        return self._route_to_cloud(reason)

    def _is_cost_guard_blocking(self) -> bool:
        """
        Sprawdza czy Cost Guard blokuje dostęp do chmury.

        Returns:
            True jeśli dostęp zablokowany, False jeśli dozwolony
        """
        # Jeśli brak state_manager - nie blokuj (backward compatibility)
        if not self.state_manager:
            return False

        # Jeśli paid_mode wyłączony - blokuj
        return not self.state_manager.is_paid_mode_enabled()

    def _has_cloud_access(self) -> bool:
        """
        Sprawdza czy system ma dostęp do chmury.

        Returns:
            True jeśli mamy klucz API do chmury
        """
        provider = self.settings.HYBRID_CLOUD_PROVIDER.lower()

        if provider == "google":
            return bool(self.settings.GOOGLE_API_KEY)
        elif provider == "openai":
            return bool(self.settings.OPENAI_API_KEY)
        else:
            logger.warning(f"Nieznany cloud provider: {provider}")
            return False

    def _is_sensitive_content(self, text: str) -> bool:
        """
        Sprawdza czy tekst zawiera wrażliwe dane.

        Args:
            text: Tekst do analizy

        Returns:
            True jeśli wykryto wrażliwe treści
        """
        if not text:
            return False

        # Proste heurystyki (można rozszerzyć)
        sensitive_keywords = [
            "password",
            "hasło",
            "token",
            "klucz",
            "key",
            "secret",
            "api_key",
            "apikey",
            "credentials",
            "uwierzytelnienie",
        ]

        text_lower = text.lower()
        for keyword in sensitive_keywords:
            if keyword in text_lower:
                logger.warning(f"Wykryto wrażliwe słowo kluczowe: {keyword}")
                return True

        return False

    def calculate_complexity(self, prompt: str, task_type: TaskType) -> int:
        """
        Oblicza złożoność zadania na skali 0-10.

        Args:
            prompt: Treść promptu
            task_type: Typ zadania

        Returns:
            Ocena złożoności (0-10)
        """
        complexity = 0

        # Bazowa złożoność na podstawie task_type
        task_type_complexity = {
            TaskType.STANDARD: 1,
            TaskType.CHAT: 1,
            TaskType.CODING_SIMPLE: 2,
            TaskType.CODING_COMPLEX: 7,
            TaskType.SENSITIVE: 1,  # Zawsze local, niska złożoność
            TaskType.ANALYSIS: 6,
            TaskType.GENERATION: 5,
            TaskType.RESEARCH: 4,
        }
        complexity += task_type_complexity.get(task_type, 3)

        # Dodaj punkty na podstawie długości promptu
        prompt_length = len(prompt)
        if prompt_length > 1000:
            complexity += 2
        elif prompt_length > 500:
            complexity += 1

        # Ogranicz do skali 0-10
        complexity = max(0, min(10, complexity))

        logger.debug(f"Obliczona złożoność: {complexity} (task={task_type.value}, len={prompt_length})")
        return complexity

    def _route_to_cloud_fast(self, reason: str) -> dict:
        """
        Tworzy routing do szybkiego (tańszego) modelu chmurowego.

        Args:
            reason: Uzasadnienie decyzji

        Returns:
            Dict z informacjami o routingu
        """
        logger.debug(f"Routing do CLOUD_FAST: {reason}")

        provider = self.settings.HYBRID_CLOUD_PROVIDER.lower()
        
        # Wybierz tańszy model w zależności od providera
        if provider == "openai":
            model_name = "gpt-4o-mini"
        elif provider == "google":
            model_name = "gemini-1.5-flash"
        else:
            # Fallback
            model_name = "gpt-4o-mini"

        return {
            "target": "cloud",
            "model_name": model_name,
            "provider": provider,
            "endpoint": None,
            "reason": reason,
            "is_paid": True,
            "tier": "fast",  # Oznacz jako fast tier
        }

    def get_routing_decision(
        self, prompt: str, task_type: TaskType = TaskType.STANDARD
    ) -> dict:
        """
        Określa decyzję routingu dla zadania (nie wykonuje faktycznego wywołania LLM).

        UWAGA: Ta metoda tylko decyduje o routingu. Faktyczne wywołanie LLM
        powinno być wykonane przez KernelBuilder z użyciem informacji o routingu.

        Args:
            prompt: Prompt do analizy
            task_type: Typ zadania

        Returns:
            Dict z informacjami o routingu:
            - target: 'local' lub 'cloud'
            - model_name: nazwa modelu
            - provider: 'local', 'google', 'openai'
            - endpoint: endpoint (jeśli dotyczy)
            - reason: uzasadnienie decyzji
        """
        routing_info = self.route_task(task_type, prompt)

        logger.info(
            f"[{task_type.value}] Routing decision: {routing_info['provider']} "
            f"({routing_info['model_name']}) - {routing_info['reason']}"
        )

        return routing_info

    def get_routing_info_for_task(self, task_type: TaskType, prompt: str = "") -> dict:
        """
        Pobiera informacje o routingu bez wykonywania zadania.

        Args:
            task_type: Typ zadania
            prompt: Opcjonalny prompt

        Returns:
            Dict z informacjami o routingu
        """
        return self.route_task(task_type, prompt)
