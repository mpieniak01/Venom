"""
Moduł: model_router - Hybrydowy router modeli AI (Local First + Cloud Options).

Router zarządza ruchem zapytań między lokalnym LLM a chmurą,
priorytetyzując prywatność i zerowy koszt operacyjny.
"""

from enum import Enum

from venom_core.config import SETTINGS
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

    def __init__(self, settings=None):
        """
        Inicjalizacja routera.

        Args:
            settings: Konfiguracja (domyślnie SETTINGS)
        """
        self.settings = settings or SETTINGS
        self.ai_mode = AIMode(self.settings.AI_MODE.upper())

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
            return self._route_to_cloud(f"Tryb CLOUD - zadanie {task_type.value}")

        # PRIORYTET 4: Tryb HYBRID - inteligentny routing
        return self._hybrid_route(task_type, prompt)

    def _hybrid_route(self, task_type: TaskType, prompt: str) -> dict:
        """
        Routing w trybie hybrydowym.

        Args:
            task_type: Typ zadania
            prompt: Prompt

        Returns:
            Dict z informacjami o routingu
        """
        # Zadania proste -> LOCAL
        if task_type in [TaskType.STANDARD, TaskType.CHAT, TaskType.CODING_SIMPLE]:
            return self._route_to_local(
                f"Tryb HYBRID: proste zadanie {task_type.value} -> LOCAL"
            )
        
        # RESEARCH - routing zależy od paid_mode (będzie sprawdzane przez KernelBuilder)
        # DESIGN NOTE: Router wybiera cloud/local, ale faktyczna decyzja o Google Grounding
        # vs DuckDuckGo jest podejmowana przez KernelBuilder bazując na:
        # 1. state_manager.paid_mode_enabled (sprawdzany przez KernelBuilder)
        # 2. Dostępność GOOGLE_API_KEY
        # 3. Zainstalowana biblioteka google-generativeai
        # Ta separacja pozwala na elastyczną konfigurację bez modyfikacji routera.
        if task_type == TaskType.RESEARCH:
            # Tutaj zawsze zwracamy cloud, ale faktyczna decyzja o grounding
            # będzie podjęta w KernelBuilder na podstawie paid_mode
            if self._has_cloud_access():
                return self._route_to_cloud(
                    f"Tryb HYBRID: zadanie RESEARCH -> CLOUD (Google/DuckDuckGo)"
                )
            else:
                return self._route_to_local(
                    "Tryb HYBRID: zadanie RESEARCH -> LOCAL (DuckDuckGo fallback)"
                )

        # Zadania złożone -> CLOUD (jeśli dostępna konfiguracja)
        if task_type in [
            TaskType.CODING_COMPLEX,
            TaskType.ANALYSIS,
            TaskType.GENERATION,
        ]:
            # Sprawdź czy mamy klucz API dla chmury
            if self._has_cloud_access():
                return self._route_to_cloud(
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
        }

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
