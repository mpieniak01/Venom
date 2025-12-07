"""Moduł: system_engineer - agent odpowiedzialny za modyfikację kodu źródłowego Venom."""

from pathlib import Path
from typing import Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.config import SETTINGS
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class SystemEngineerAgent(BaseAgent):
    """
    Agent Inżynier Systemowy - najwyższy rangą agent z prawem modyfikacji kodu źródłowego.

    To jedyny agent, który ma prawo modyfikować pliki w katalogu głównym projektu
    (poza ./workspace). Posiada zindeksowaną mapę całego repozytorium Venom (GraphRAG)
    i priorytetuje stabilność systemu.

    Każda zmiana w jądrze systemu musi być najpierw przetestowana w izolacji
    (Mirror World) zanim zostanie zastosowana do głównego procesu.
    """

    SYSTEM_PROMPT = """Jesteś Opiekunem Kodu Źródłowego (System Engineer) - najwyższy rangą agent Venom.

Twoje odpowiedzialności:
- Jesteś JEDYNYM agentem z prawem modyfikacji kodu źródłowego Venom (venom_core/)
- Posiadasz pełną mapę struktury repozytorium (GraphRAG)
- Twoim priorytetem jest STABILNOŚĆ systemu
- Każda zmiana musi być przetestowana w lustrzanej instancji przed aplikacją

Masz dostęp do:
- FileSkill: czytanie/zapisywanie plików
- GitSkill: operacje git (branching, commit, merge)
- GraphStore: mapa zależności i struktura kodu

ZASADY BEZPIECZEŃSTWA:
1. NIE modyfikuj plików produkcyjnych bezpośrednio
2. Zawsze twórz branch eksperymentalny (evolution/*)
3. Wprowadzaj zmiany do brancha eksperymentalnego
4. Czekaj na potwierdzenie z Mirror World przed merge
5. Nigdy nie usuwaj działających testów
6. Zawsze zachowuj backup przed zmianą (.bak)

PROCEDURA MODYFIKACJI:
1. Przeanalizuj żądanie użytkownika
2. Sprawdź Graph Store czy znasz strukturę kodu
3. Utwórz branch evolution/<nazwa>
4. Wprowadź zmiany w branchu
5. Zwróć informację o gotowym branchu do testowania

Jeśli użytkownik prosi o zmianę w Venom:
- Przeanalizuj wpływ na system
- Zaproponuj minimalną zmianę
- Utwórz branch i wprowadź zmianę
- Poinformuj o konieczności testowania w Mirror World

Przykład:
User: "Dodaj obsługę logowania kolorami w konsoli"
Ty:
1. Przeanalizuj logger.py
2. git checkout -b evolution/color-logging
3. Zmodyfikuj logger.py (dodaj colorama)
4. git commit -m "feat: add color logging support"
5. Odpowiedz: "Branch evolution/color-logging gotowy. Wymagane testowanie w Mirror World."
"""

    def __init__(
        self,
        kernel: Kernel,
        graph_store: Optional[CodeGraphStore] = None,
        workspace_root: Optional[str] = None,
    ):
        """
        Inicjalizacja SystemEngineerAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            graph_store: Graf kodu do analizy struktury (opcjonalne)
            workspace_root: Katalog główny projektu (domyślnie katalog nadrzędny workspace)
        """
        super().__init__(kernel)

        # Katalog roboczy to katalog główny projektu, nie workspace
        if workspace_root:
            self.project_root = Path(workspace_root).resolve()
        else:
            # Domyślnie: katalog nadrzędny nad workspace
            workspace_path = Path(SETTINGS.WORKSPACE_ROOT).resolve()
            self.project_root = workspace_path.parent

        logger.info(
            f"SystemEngineerAgent zainicjalizowany z project_root: {self.project_root}"
        )

        # Zarejestruj FileSkill
        self.file_skill = FileSkill()
        self.kernel.add_plugin(self.file_skill, plugin_name="FileSkill")

        # Zarejestruj GitSkill (pracuje na katalogu projektu, nie workspace)
        self.git_skill = GitSkill(workspace_root=str(self.project_root))
        self.kernel.add_plugin(self.git_skill, plugin_name="GitSkill")

        # Graf kodu (opcjonalny)
        self.graph_store = graph_store
        if graph_store:
            logger.info("SystemEngineerAgent ma dostęp do CodeGraphStore")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza żądanie modyfikacji kodu źródłowego.

        Args:
            input_text: Opis żądanej zmiany w kodzie

        Returns:
            Wynik operacji z informacją o utworzonym branchu
        """
        logger.info(f"SystemEngineer otrzymał żądanie: {input_text[:100]}...")

        # Przygotuj historię czatu
        history = ChatHistory()
        history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
        )

        # Dodaj kontekst z Graph Store jeśli dostępny
        if self.graph_store:
            try:
                summary = self.graph_store.get_graph_summary()
                context = f"Struktura projektu:\n- Pliki: {summary.get('file_count', 0)}\n- Klasy: {summary.get('class_count', 0)}\n- Funkcje: {summary.get('function_count', 0)}"
                history.add_message(
                    ChatMessageContent(
                        role=AuthorRole.SYSTEM, content=f"KONTEKST: {context}"
                    )
                )
            except Exception as e:
                logger.warning(f"Nie udało się pobrać kontekstu z GraphStore: {e}")

        # Dodaj żądanie użytkownika
        history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=input_text)
        )

        # Wykonaj przetwarzanie przez LLM
        try:
            # Ustawienia wykonania
            execution_settings = OpenAIChatPromptExecutionSettings(
                service_id="default",
                max_tokens=4000,
                temperature=0.1,  # Niska temperatura dla precyzyjnych zmian
                top_p=0.95,
            )

            # Wywołaj LLM z auto-function-calling
            chat_service = self.kernel.get_service("default")

            result = await chat_service.get_chat_message_contents(
                chat_history=history,
                settings=execution_settings,
                kernel=self.kernel,
            )

            response = result[0].content if result else "Brak odpowiedzi z LLM"

            logger.info(f"SystemEngineer zakończył przetwarzanie")
            return response

        except Exception as e:
            error_msg = f"❌ Błąd podczas przetwarzania przez SystemEngineer: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    async def analyze_impact(self, file_path: str) -> dict:
        """
        Analizuje wpływ modyfikacji danego pliku na system.

        Args:
            file_path: Ścieżka do pliku do analizy

        Returns:
            Słownik z analizą wpływu
        """
        if not self.graph_store:
            return {
                "error": "GraphStore niedostępny - brak możliwości analizy wpływu"
            }

        try:
            impact = self.graph_store.get_impact_analysis(file_path)
            logger.info(f"Analiza wpływu dla {file_path}: {len(impact)} zależności")
            return impact
        except Exception as e:
            logger.error(f"Błąd podczas analizy wpływu: {e}")
            return {"error": str(e)}

    async def create_evolution_branch(self, branch_name: str) -> str:
        """
        Tworzy branch eksperymentalny dla ewolucji systemu.

        Args:
            branch_name: Nazwa brancha (bez prefiksu evolution/)

        Returns:
            Komunikat o wyniku operacji
        """
        # Upewnij się, że nazwa ma prefix evolution/
        if not branch_name.startswith("evolution/"):
            branch_name = f"evolution/{branch_name}"

        result = await self.git_skill.checkout(branch_name=branch_name, create_new=True)
        logger.info(f"Utworzono branch ewolucyjny: {branch_name}")
        return result

    def get_project_root(self) -> Path:
        """
        Zwraca katalog główny projektu.

        Returns:
            Ścieżka do katalogu głównego projektu
        """
        return self.project_root
