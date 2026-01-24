"""Moduł: component_engine - silnik dynamicznych komponentów UI."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class WidgetType(str, Enum):
    """Typy widgetów UI."""

    CHART = "chart"
    TABLE = "table"
    FORM = "form"
    MARKDOWN = "markdown"
    CUSTOM_HTML = "custom-html"
    MERMAID = "mermaid"
    CARD = "card"


class Widget(BaseModel):
    """Model widgetu UI."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: WidgetType
    data: Dict[str, Any]
    events: Optional[Dict[str, str]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    model_config = ConfigDict(use_enum_values=True)


class ComponentEngine:
    """
    Silnik zarządzający dynamicznymi komponentami UI.

    Odpowiada za:
    - Rejestrowanie widgetów
    - Aktualizacje live poprzez WebSocket
    - Walidację i sanityzację contentu
    """

    def __init__(self):
        """Inicjalizacja ComponentEngine."""
        self.widgets: Dict[str, Widget] = {}
        logger.info("ComponentEngine zainicjalizowany")

    def create_widget(
        self,
        widget_type: WidgetType,
        data: Dict[str, Any],
        events: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Widget:
        """
        Tworzy nowy widget UI.

        Args:
            widget_type: Typ widgetu
            data: Dane do wyświetlenia
            events: Mapowanie zdarzeń UI na intencje
            metadata: Dodatkowe metadane

        Returns:
            Utworzony widget
        """
        widget = Widget(
            type=widget_type, data=data, events=events or {}, metadata=metadata or {}
        )

        self.widgets[widget.id] = widget
        logger.info(f"Utworzono widget {widget.id} typu {widget_type}")

        return widget

    def get_widget(self, widget_id: str) -> Optional[Widget]:
        """
        Pobiera widget po ID.

        Args:
            widget_id: ID widgetu

        Returns:
            Widget lub None jeśli nie istnieje
        """
        return self.widgets.get(widget_id)

    def update_widget(self, widget_id: str, data: Dict[str, Any]) -> bool:
        """
        Aktualizuje dane widgetu (Live Update).

        Args:
            widget_id: ID widgetu do aktualizacji
            data: Nowe dane

        Returns:
            True jeśli sukces, False jeśli widget nie istnieje
        """
        widget = self.widgets.get(widget_id)
        if not widget:
            logger.warning(f"Próba aktualizacji nieistniejącego widgetu: {widget_id}")
            return False

        widget.data = data
        logger.info(f"Zaktualizowano widget {widget_id}")
        return True

    def remove_widget(self, widget_id: str) -> bool:
        """
        Usuwa widget z silnika.

        Args:
            widget_id: ID widgetu do usunięcia

        Returns:
            True jeśli sukces, False jeśli widget nie istnieje
        """
        if widget_id in self.widgets:
            del self.widgets[widget_id]
            logger.info(f"Usunięto widget {widget_id}")
            return True

        logger.warning(f"Próba usunięcia nieistniejącego widgetu: {widget_id}")
        return False

    def list_widgets(self) -> List[Widget]:
        """
        Zwraca listę wszystkich aktywnych widgetów.

        Returns:
            Lista widgetów
        """
        return list(self.widgets.values())

    def clear_widgets(self):
        """Usuwa wszystkie widgety."""
        count = len(self.widgets)
        self.widgets.clear()
        logger.info(f"Wyczyszczono {count} widgetów")

    def create_chart_widget(
        self, chart_type: str, chart_data: Dict[str, Any], title: str = ""
    ) -> Widget:
        """
        Tworzy widget wykresu.

        Args:
            chart_type: Typ wykresu (bar, line, pie, etc.)
            chart_data: Dane dla wykresu (labels, datasets)
            title: Tytuł wykresu

        Returns:
            Widget wykresu
        """
        data = {"chartType": chart_type, "chartData": chart_data, "title": title}

        return self.create_widget(WidgetType.CHART, data)

    def create_table_widget(
        self, headers: List[str], rows: List[List[Any]], title: str = ""
    ) -> Widget:
        """
        Tworzy widget tabeli.

        Args:
            headers: Nagłówki kolumn
            rows: Wiersze danych
            title: Tytuł tabeli

        Returns:
            Widget tabeli
        """
        data = {"headers": headers, "rows": rows, "title": title}

        return self.create_widget(WidgetType.TABLE, data)

    def create_form_widget(
        self, schema: Dict[str, Any], submit_intent: str, title: str = ""
    ) -> Widget:
        """
        Tworzy widget formularza.

        Args:
            schema: JSON Schema formularza
            submit_intent: Intencja wywoływana po submit
            title: Tytuł formularza

        Returns:
            Widget formularza
        """
        data = {"schema": schema, "title": title}
        events = {"submit": submit_intent}

        return self.create_widget(WidgetType.FORM, data, events)

    def create_markdown_widget(self, content: str) -> Widget:
        """
        Tworzy widget Markdown.

        Args:
            content: Treść w formacie Markdown

        Returns:
            Widget Markdown
        """
        data = {"content": content}

        return self.create_widget(WidgetType.MARKDOWN, data)

    def create_mermaid_widget(self, diagram: str, title: str = "") -> Widget:
        """
        Tworzy widget diagramu Mermaid.

        Args:
            diagram: Kod Mermaid
            title: Tytuł diagramu

        Returns:
            Widget Mermaid
        """
        data = {"diagram": diagram, "title": title}

        return self.create_widget(WidgetType.MERMAID, data)

    def create_card_widget(
        self,
        title: str,
        content: str,
        icon: str = "",
        actions: Optional[List[Dict[str, str]]] = None,
    ) -> Widget:
        """
        Tworzy widget karty (Card).

        Args:
            title: Tytuł karty
            content: Zawartość karty
            icon: Emoji lub ikona
            actions: Lista akcji (przycisków) z intencjami

        Returns:
            Widget karty
        """
        data: Dict[str, Any] = {"title": title, "content": content, "icon": icon}

        events: Dict[str, str] = {}
        if actions:
            data["actions"] = actions
            for action in actions:
                if "intent" in action and "id" in action:
                    events[action["id"]] = action["intent"]

        return self.create_widget(WidgetType.CARD, data, events)
