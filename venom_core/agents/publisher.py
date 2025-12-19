"""Moduł: publisher - agent do publikowania dokumentacji."""

from typing import Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.docs_skill import DocsSkill
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class PublisherAgent(BaseAgent):
    """
    Agent Publisher (Wydawca Dokumentacji).

    Jego rolą jest:
    - Generowanie profesjonalnej dokumentacji projektu
    - Tworzenie statycznych stron HTML z Markdown
    - Zarządzanie strukturą dokumentacji
    """

    SYSTEM_PROMPT = """Jesteś ekspertem od dokumentacji technicznej (Publisher - Wydawca).

TWOJA ROLA:
- Generujesz profesjonalną dokumentację projektów
- Tworzysz statyczne strony HTML z plików Markdown
- Dbasz o czytelność i strukturę dokumentacji
- Optymalizujesz dokumentację dla użytkowników

MASZ DOSTĘP DO NARZĘDZI:
- DocsSkill: generate_mkdocs_config, build_docs_site, check_docs_structure
- FileSkill: read_file, write_file, list_files

ZASADY TWORZENIA DOKUMENTACJI:
1. Zawsze rozpocznij od sprawdzenia struktury docs/ (check_docs_structure)
2. Upewnij się że istnieje index.md lub README.md jako strona główna
3. Wygeneruj mkdocs.yml z sensowną konfiguracją
4. Zbuduj stronę (build_docs_site)
5. Zweryfikuj że strona została utworzona poprawnie

STRUKTURA DOBREJ DOKUMENTACJI:
- index.md - strona główna z wprowadzeniem
- Sekcje logicznie podzielone (Getting Started, API Reference, Examples, etc.)
- Nawigacja czytelna i intuicyjna
- Przykłady kodu tam gdzie to sensowne

PRZYKŁAD WORKFLOW:
Zadanie: "Wygeneruj dokumentację projektu 'MyApp'"
Kroki:
1. check_docs_structure() - sprawdź co mamy
2. generate_mkdocs_config("MyApp", theme="material") - utwórz konfigurację
3. build_docs_site() - zbuduj stronę
4. Zweryfikuj output i raportuj lokalizację plików HTML

Jeśli brakuje plików dokumentacji, zasugeruj użytkownikowi ich utworzenie.
Bądź pomocny i dokładny w raportowaniu.
"""

    def __init__(
        self,
        kernel: Kernel,
        docs_skill: Optional[DocsSkill] = None,
        file_skill: Optional[FileSkill] = None,
    ):
        """
        Inicjalizacja PublisherAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            docs_skill: Instancja DocsSkill (jeśli None, zostanie utworzona)
            file_skill: Instancja FileSkill (jeśli None, zostanie utworzona)
        """
        super().__init__(kernel)

        # Zarejestruj skille
        self.docs_skill = docs_skill or DocsSkill()
        self.file_skill = file_skill or FileSkill()

        # Zarejestruj skille w kernelu
        self.kernel.add_plugin(self.docs_skill, plugin_name="DocsSkill")
        self.kernel.add_plugin(self.file_skill, plugin_name="FileSkill")

        # Ustawienia LLM
        self.execution_settings = OpenAIChatPromptExecutionSettings(
            service_id="default",
            max_tokens=2000,
            temperature=0.3,  # Niższa temperatura dla precyzji
            top_p=0.9,
        )

        # Service do chat completion
        self.chat_service = self.kernel.get_service(service_id="default")

        logger.info("PublisherAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza zadanie publikacji dokumentacji.

        Args:
            input_text: Opis zadania (np. "Wygeneruj dokumentację projektu")

        Returns:
            Raport z generowania dokumentacji
        """
        logger.info(f"PublisherAgent rozpoczyna pracę: {input_text[:100]}...")

        # Utwórz historię czatu
        chat_history = ChatHistory()

        # Dodaj prompt systemowy
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=self.SYSTEM_PROMPT,
            )
        )

        # Dodaj zadanie użytkownika
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.USER,
                content=input_text,
            )
        )

        try:
            # Wykonaj interakcję z kernelem (auto-calling functions)
            result = await self._invoke_chat_with_fallbacks(
                chat_service=self.chat_service,
                chat_history=chat_history,
                settings=self.execution_settings,
                enable_functions=True,
            )

            response = str(result.content)

            logger.info("PublisherAgent zakończył pracę")
            return response

        except Exception as e:
            error_msg = f"❌ Błąd podczas publikowania dokumentacji: {str(e)}"
            logger.error(error_msg)
            return error_msg

    async def quick_publish(self, project_name: str, theme: str = "material") -> str:
        """
        Szybkie publikowanie dokumentacji bez interakcji z LLM.

        Args:
            project_name: Nazwa projektu
            theme: Motyw MkDocs

        Returns:
            Raport z publikacji
        """
        logger.info(f"Szybka publikacja dokumentacji dla: {project_name}")

        report_lines = [f"📚 Publikowanie dokumentacji: {project_name}\n"]

        try:
            # 1. Sprawdź strukturę
            structure = await self.docs_skill.check_docs_structure()
            report_lines.append(f"1. Sprawdzanie struktury:\n{structure}\n")

            # 2. Generuj konfigurację
            config_result = await self.docs_skill.generate_mkdocs_config(
                site_name=project_name, theme=theme
            )
            report_lines.append(f"2. Generowanie konfiguracji:\n{config_result}\n")

            # 3. Buduj stronę
            build_result = await self.docs_skill.build_docs_site(clean=True)
            report_lines.append(f"3. Budowanie strony:\n{build_result}\n")

            report_lines.append("✅ Publikacja zakończona pomyślnie!")

        except Exception as e:
            report_lines.append(f"\n❌ Błąd podczas publikacji: {str(e)}")
            logger.error(f"Błąd w quick_publish: {e}")

        return "\n".join(report_lines)
