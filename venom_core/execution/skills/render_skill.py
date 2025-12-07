"""Moduł: render_skill - umiejętność wizualizacji i renderowania UI."""

from typing import Annotated, Any, Dict, List, Optional

import bleach
from semantic_kernel.functions import kernel_function

from venom_core.ui.component_engine import ComponentEngine, WidgetType
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class RenderSkill:
    """
    Skill do wizualizacji danych i renderowania komponentów UI.

    Umożliwia agentom:
    - Tworzenie wykresów i wizualizacji
    - Wstrzykiwanie widgetów do dashboardu
    - Generowanie formularzy interaktywnych
    - Renderowanie diagramów Mermaid
    """

    # Dozwolone tagi HTML dla sanityzacji
    ALLOWED_TAGS = [
        "div",
        "span",
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "strong",
        "em",
        "ul",
        "ol",
        "li",
        "a",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "br",
        "code",
        "pre",
    ]

    ALLOWED_ATTRIBUTES = {
        "a": ["href", "title"],
        "div": ["class"],
        "span": ["class"],
        "p": ["class"],
        "table": ["class"],
    }

    def __init__(self, component_engine: Optional[ComponentEngine] = None):
        """
        Inicjalizacja RenderSkill.

        Args:
            component_engine: Silnik komponentów UI (jeśli None, tworzy nowy)
        """
        self.component_engine = component_engine or ComponentEngine()
        logger.info("RenderSkill zainicjalizowany")

    def _sanitize_html(self, html: str) -> str:
        """
        Sanityzuje HTML aby zapobiec XSS.

        Args:
            html: Surowy HTML

        Returns:
            Czysty HTML
        """
        return bleach.clean(
            html, tags=self.ALLOWED_TAGS, attributes=self.ALLOWED_ATTRIBUTES, strip=True
        )

    @kernel_function(
        name="render_chart",
        description="Renderuje wykres na dashboardzie. Używaj do wizualizacji danych liczbowych.",
    )
    def render_chart(
        self,
        chart_type: Annotated[
            str,
            "Typ wykresu: bar (słupkowy), line (liniowy), pie (kołowy), doughnut, radar",
        ],
        labels: Annotated[str, "Etykiety dla osi X, oddzielone przecinkami"],
        values: Annotated[str, "Wartości dla danych, oddzielone przecinkami"],
        dataset_label: Annotated[str, "Nazwa datasetu"] = "Dane",
        title: Annotated[str, "Tytuł wykresu"] = "",
    ) -> str:
        """
        Renderuje wykres na dashboardzie.

        Args:
            chart_type: Typ wykresu
            labels: Etykiety (CSV)
            values: Wartości (CSV)
            dataset_label: Nazwa datasetu
            title: Tytuł wykresu

        Returns:
            ID widgetu lub komunikat o błędzie
        """
        try:
            # Parsowanie danych
            labels_list = [label.strip() for label in labels.split(",")]
            values_list = [float(value.strip()) for value in values.split(",")]

            if len(labels_list) != len(values_list):
                return "Błąd: Liczba etykiet i wartości musi być taka sama"

            # Tworzenie danych wykresu
            chart_data = {
                "labels": labels_list,
                "datasets": [
                    {
                        "label": dataset_label,
                        "data": values_list,
                        "backgroundColor": "rgba(59, 130, 246, 0.5)",
                        "borderColor": "rgba(59, 130, 246, 1)",
                        "borderWidth": 2,
                    }
                ],
            }

            # Utworzenie widgetu
            widget = self.component_engine.create_chart_widget(
                chart_type=chart_type, chart_data=chart_data, title=title
            )

            logger.info(f"Utworzono wykres {chart_type} z ID: {widget.id}")
            return f"Utworzono wykres: {widget.id}"

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wykresu: {e}")
            return f"Błąd tworzenia wykresu: {str(e)}"

    @kernel_function(
        name="render_table",
        description="Renderuje tabelę danych na dashboardzie. Używaj do wyświetlania danych tabelarycznych.",
    )
    def render_table(
        self,
        headers: Annotated[str, "Nagłówki kolumn, oddzielone przecinkami"],
        rows_data: Annotated[
            str,
            "Wiersze danych, każdy wiersz oddzielony średnikiem, komórki przecinkiem",
        ],
        title: Annotated[str, "Tytuł tabeli"] = "",
    ) -> str:
        """
        Renderuje tabelę na dashboardzie.

        Args:
            headers: Nagłówki kolumn (CSV)
            rows_data: Dane wierszy (format: row1_col1,row1_col2;row2_col1,row2_col2)
            title: Tytuł tabeli

        Returns:
            ID widgetu lub komunikat o błędzie
        """
        try:
            # Parsowanie nagłówków
            headers_list = [h.strip() for h in headers.split(",")]

            # Parsowanie wierszy
            rows = []
            for row_str in rows_data.split(";"):
                if row_str.strip():
                    row = [cell.strip() for cell in row_str.split(",")]
                    rows.append(row)

            # Utworzenie widgetu
            widget = self.component_engine.create_table_widget(
                headers=headers_list, rows=rows, title=title
            )

            logger.info(f"Utworzono tabelę z ID: {widget.id}")
            return f"Utworzono tabelę: {widget.id}"

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia tabeli: {e}")
            return f"Błąd tworzenia tabeli: {str(e)}"

    @kernel_function(
        name="render_dashboard_widget",
        description="Wstrzykuje niestandardowy widget HTML do dashboardu. Używaj tylko gdy inne metody nie wystarczą.",
    )
    def render_dashboard_widget(
        self,
        html: Annotated[
            str, "Kod HTML widgetu (zostanie automatycznie zesanityzowany)"
        ],
    ) -> str:
        """
        Wstrzykuje customowy HTML jako widget.

        Args:
            html: Kod HTML (będzie zesanityzowany)

        Returns:
            ID widgetu lub komunikat o błędzie
        """
        try:
            # Sanityzacja HTML
            clean_html = self._sanitize_html(html)

            # Utworzenie widgetu
            widget = self.component_engine.create_widget(
                widget_type=WidgetType.CUSTOM_HTML, data={"html": clean_html}
            )

            logger.info(f"Utworzono custom widget z ID: {widget.id}")
            return f"Utworzono widget HTML: {widget.id}"

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia custom widgetu: {e}")
            return f"Błąd tworzenia widgetu: {str(e)}"

    @kernel_function(
        name="create_input_form",
        description="Tworzy interaktywny formularz na dashboardzie do zbierania danych od użytkownika.",
    )
    def create_input_form(
        self,
        form_title: Annotated[str, "Tytuł formularza"],
        fields: Annotated[
            str,
            "Pola formularza w formacie: name:type:label, oddzielone średnikiem (type: text, number, email, textarea)",
        ],
        submit_intent: Annotated[
            str, "Intencja wywoływana po submit (np. create_github_issue)"
        ],
    ) -> str:
        """
        Tworzy formularz z dynamicznymi polami.

        Args:
            form_title: Tytuł formularza
            fields: Definicja pól (format: name:type:label;name2:type2:label2)
            submit_intent: Intencja po submit

        Returns:
            ID widgetu lub komunikat o błędzie
        """
        try:
            # Parsowanie pól
            properties = {}
            required = []

            for field_str in fields.split(";"):
                if field_str.strip():
                    parts = field_str.split(":")
                    if len(parts) >= 3:
                        name, field_type, label = (
                            parts[0].strip(),
                            parts[1].strip(),
                            parts[2].strip(),
                        )

                        clean_name = name.rstrip("*")

                        # Mapowanie typów
                        json_type = "string"
                        if field_type in ["number", "integer"]:
                            json_type = "number"

                        properties[clean_name] = {"type": json_type, "title": label}

                        # Jeśli pole kończy się *, jest wymagane
                        if name.endswith("*"):
                            required.append(clean_name)

            # Tworzenie JSON Schema
            schema = {
                "type": "object",
                "properties": properties,
                "required": required if required else [],
            }

            # Utworzenie widgetu
            widget = self.component_engine.create_form_widget(
                schema=schema, submit_intent=submit_intent, title=form_title
            )

            logger.info(f"Utworzono formularz z ID: {widget.id}")
            return f"Utworzono formularz: {widget.id}"

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia formularza: {e}")
            return f"Błąd tworzenia formularza: {str(e)}"

    @kernel_function(
        name="render_markdown",
        description="Renderuje treść w formacie Markdown na dashboardzie.",
    )
    def render_markdown(
        self,
        content: Annotated[str, "Treść w formacie Markdown"],
    ) -> str:
        """
        Renderuje Markdown.

        Args:
            content: Treść Markdown

        Returns:
            ID widgetu lub komunikat o błędzie
        """
        try:
            widget = self.component_engine.create_markdown_widget(content=content)

            logger.info(f"Utworzono widget Markdown z ID: {widget.id}")
            return f"Utworzono Markdown: {widget.id}"

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia Markdown: {e}")
            return f"Błąd tworzenia Markdown: {str(e)}"

    @kernel_function(
        name="render_mermaid_diagram",
        description="Renderuje diagram Mermaid (flowchart, sequence, class diagram, etc.) na dashboardzie.",
    )
    def render_mermaid_diagram(
        self,
        diagram_code: Annotated[str, "Kod diagramu Mermaid"],
        title: Annotated[str, "Tytuł diagramu"] = "",
    ) -> str:
        """
        Renderuje diagram Mermaid.

        Args:
            diagram_code: Kod Mermaid
            title: Tytuł diagramu

        Returns:
            ID widgetu lub komunikat o błędzie
        """
        try:
            widget = self.component_engine.create_mermaid_widget(
                diagram=diagram_code, title=title
            )

            logger.info(f"Utworzono diagram Mermaid z ID: {widget.id}")
            return f"Utworzono diagram Mermaid: {widget.id}"

        except Exception as e:
            logger.error(f"Błąd podczas tworzenia diagramu Mermaid: {e}")
            return f"Błąd tworzenia diagramu: {str(e)}"

    @kernel_function(
        name="update_widget",
        description="Aktualizuje dane istniejącego widgetu (live update).",
    )
    def update_widget(
        self,
        widget_id: Annotated[str, "ID widgetu do aktualizacji"],
        new_data: Annotated[str, "Nowe dane w formacie JSON"],
    ) -> str:
        """
        Aktualizuje widget.

        Args:
            widget_id: ID widgetu
            new_data: Nowe dane (JSON string)

        Returns:
            Komunikat o sukcesie lub błędzie
        """
        try:
            import json

            data_dict = json.loads(new_data)
            success = self.component_engine.update_widget(widget_id, data_dict)

            if success:
                logger.info(f"Zaktualizowano widget {widget_id}")
                return f"Zaktualizowano widget: {widget_id}"
            else:
                return f"Nie znaleziono widgetu: {widget_id}"

        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji widgetu: {e}")
            return f"Błąd aktualizacji widgetu: {str(e)}"

    @kernel_function(
        name="remove_widget",
        description="Usuwa widget z dashboardu.",
    )
    def remove_widget(
        self,
        widget_id: Annotated[str, "ID widgetu do usunięcia"],
    ) -> str:
        """
        Usuwa widget.

        Args:
            widget_id: ID widgetu

        Returns:
            Komunikat o sukcesie lub błędzie
        """
        try:
            success = self.component_engine.remove_widget(widget_id)

            if success:
                logger.info(f"Usunięto widget {widget_id}")
                return f"Usunięto widget: {widget_id}"
            else:
                return f"Nie znaleziono widgetu: {widget_id}"

        except Exception as e:
            logger.error(f"Błąd podczas usuwania widgetu: {e}")
            return f"Błąd usuwania widgetu: {str(e)}"

    def get_widget(self, widget_id: str) -> Optional[Dict[str, Any]]:
        """
        Pobiera widget jako dict.

        Args:
            widget_id: ID widgetu

        Returns:
            Widget jako dict lub None
        """
        widget = self.component_engine.get_widget(widget_id)
        if widget:
            return widget.model_dump()
        return None

    def list_all_widgets(self) -> List[Dict[str, Any]]:
        """
        Zwraca listę wszystkich widgetów jako dict.

        Returns:
            Lista widgetów
        """
        widgets = self.component_engine.list_widgets()
        return [w.model_dump() for w in widgets]
