"""Moduł: designer - agent projektant interfejsu użytkownika."""

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class DesignerAgent(BaseAgent):
    """
    Agent Projektant (Designer - Frontend Developer & UX Expert).

    Specjalizuje się w:
    - Wizualizacji danych
    - Generowaniu HTML/TailwindCSS/JavaScript
    - Tworzeniu konfiguracji wykresów (Chart.js, ApexCharts)
    - Projektowaniu responsywnych komponentów UI
    """

    SYSTEM_PROMPT = """Jesteś ekspertem UI/UX i Frontend Developerem.

Twoim zadaniem jest wizualizacja danych dostarczonych przez inne agenty oraz
tworzenie estetycznych, responsywnych komponentów interfejsu użytkownika.

KOMPETENCJE:
1. Generowanie kodu HTML/CSS/JavaScript
2. Tworzenie wykresów i wizualizacji danych
3. Projektowanie formularzy i interaktywnych komponentów
4. Używanie TailwindCSS do stylizacji
5. Konfiguracja bibliotek wykresów (Chart.js, ApexCharts)
6. Tworzenie diagramów Mermaid

ZASADY PROJEKTOWANIA:
1. Wszystkie komponenty muszą być responsywne
2. Używaj ciemnego motywu (#1e1e1e tło, białe teksty)
3. Używaj TailwindCSS utility classes
4. Kod JavaScript musi być bezpieczny (no eval, no innerHTML z niezaufanych źródeł)
5. Formularze muszą mieć walidację
6. Wykresy muszą mieć czytelne legendy i opisy

DOSTĘPNE TYPY KOMPONENTÓW:
- chart: Wykresy (bar, line, pie, doughnut, radar)
- table: Tabele danych z sortowaniem
- form: Formularze z JSON Schema
- markdown: Treści Markdown
- mermaid: Diagramy Mermaid
- card: Karty informacyjne z akcjami
- custom-html: Dowolny HTML (tylko gdy inne typy nie wystarczą)

PRZYKŁAD WYKRESU (Chart.js):
```json
{
  "type": "chart",
  "data": {
    "chartType": "bar",
    "chartData": {
      "labels": ["Poniedziałek", "Wtorek", "Środa"],
      "datasets": [{
        "label": "Commity",
        "data": [12, 19, 3],
        "backgroundColor": "rgba(59, 130, 246, 0.5)"
      }]
    },
    "title": "Aktywność commitów"
  }
}
```

PRZYKŁAD FORMULARZA (JSON Schema):
```json
{
  "type": "form",
  "data": {
    "schema": {
      "type": "object",
      "properties": {
        "title": {"type": "string", "title": "Tytuł"},
        "description": {"type": "string", "title": "Opis"}
      },
      "required": ["title"]
    },
    "title": "Zgłoś błąd"
  },
  "events": {
    "submit": "create_github_issue"
  }
}
```

PRZYKŁAD DIAGRAMU MERMAID:
```json
{
  "type": "mermaid",
  "data": {
    "diagram": "graph TD\\n  A[Start] --> B[Process]\\n  B --> C[End]",
    "title": "Diagram przepływu"
  }
}
```

BEZPIECZEŃSTWO:
- NIE generuj innerHTML z niezaufanych danych
- Zawsze escapuj dane użytkownika
- Używaj textContent zamiast innerHTML dla danych tekstowych
- Formularze muszą walidować input

Twoje odpowiedzi powinny być w formacie JSON z konfiguracją widgetu.
Jeśli użytkownik prosi o wizualizację, wybierz najlepszy typ komponentu
i wygeneruj odpowiednią konfigurację."""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja DesignerAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)
        self.chat_service = kernel.get_service()
        logger.info("DesignerAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza żądanie wizualizacji i generuje konfigurację UI.

        Args:
            input_text: Opis danych do wizualizacji lub żądanie UI

        Returns:
            JSON z konfiguracją widgetu lub odpowiedź tekstowa
        """
        try:
            # Tworzenie historii czatu
            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
            )
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=input_text)
            )

            # Ustawienia wykonania
            settings = OpenAIChatPromptExecutionSettings(
                temperature=0.7, max_tokens=2000
            )

            # Wywołanie modelu
            response = await self.chat_service.get_chat_message_content(
                chat_history=chat_history, settings=settings
            )

            result = str(response)
            logger.info(f"Designer wygenerował odpowiedź: {len(result)} znaków")

            return result

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania przez DesignerAgent: {e}")
            return f"Błąd projektanta: {str(e)}"

    async def create_visualization(self, data_description: str, data: dict) -> dict:
        """
        Tworzy wizualizację na podstawie opisu i danych.

        Args:
            data_description: Opis co wizualizować
            data: Dane do wizualizacji

        Returns:
            Konfiguracja widgetu w formacie dict
        """
        prompt = f"""Dane: {data}

Zadanie: {data_description}

Wygeneruj konfigurację widgetu w formacie JSON. Odpowiedz TYLKO JSONem, bez dodatkowego tekstu."""

        result = await self.process(prompt)

        # Próba wyekstrahowania JSON z odpowiedzi
        import json
        import re

        # Szukaj JSON w odpowiedzi
        json_match = re.search(r"\{.*\}", result, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                logger.warning("Nie udało się sparsować JSON z odpowiedzi")

        return {"type": "markdown", "data": {"content": result}}

    async def create_chart(self, chart_type: str, data: dict, title: str = "") -> dict:
        """
        Tworzy konfigurację wykresu.

        Args:
            chart_type: Typ wykresu (bar, line, pie, etc.)
            data: Dane dla wykresu
            title: Tytuł wykresu

        Returns:
            Konfiguracja widgetu wykresu
        """
        prompt = f"""Utwórz wykres typu {chart_type} z następującymi danymi:
{data}

Tytuł: {title}

Wygeneruj konfigurację Chart.js w formacie JSON."""

        return await self.create_visualization(prompt, data)

    async def create_form(self, form_description: str, fields: list) -> dict:
        """
        Tworzy konfigurację formularza.

        Args:
            form_description: Opis celu formularza
            fields: Lista pól formularza

        Returns:
            Konfiguracja widgetu formularza
        """
        prompt = f"""Utwórz formularz: {form_description}

Pola: {fields}

Wygeneruj JSON Schema formularza z walidacją."""

        return await self.create_visualization(prompt, {"fields": fields})

    async def create_dashboard_card(
        self, title: str, data: dict, icon: str = ""
    ) -> dict:
        """
        Tworzy kartę dashboardu dla narzędzia.

        Args:
            title: Tytuł karty
            data: Dane do wyświetlenia
            icon: Emoji lub ikona

        Returns:
            Konfiguracja widgetu karty
        """
        prompt = f"""Utwórz kartę dashboardu:
Tytuł: {title}
Ikona: {icon}
Dane: {data}

Wygeneruj estetyczną kartę z przyciskami akcji jeśli potrzeba."""

        return await self.create_visualization(prompt, data)
