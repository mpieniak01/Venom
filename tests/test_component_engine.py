"""Testy jednostkowe dla ComponentEngine."""

import pytest

from venom_core.ui.component_engine import ComponentEngine, Widget, WidgetType


def test_component_engine_initialization():
    """Test inicjalizacji ComponentEngine."""
    engine = ComponentEngine()
    assert engine is not None
    assert len(engine.widgets) == 0


def test_create_widget():
    """Test tworzenia widgetu."""
    engine = ComponentEngine()
    
    data = {"test": "data"}
    widget = engine.create_widget(WidgetType.CHART, data)
    
    assert widget is not None
    assert widget.type == WidgetType.CHART
    assert widget.data == data
    assert widget.id in engine.widgets


def test_get_widget():
    """Test pobierania widgetu."""
    engine = ComponentEngine()
    
    widget = engine.create_widget(WidgetType.TABLE, {"headers": [], "rows": []})
    retrieved = engine.get_widget(widget.id)
    
    assert retrieved is not None
    assert retrieved.id == widget.id
    assert retrieved.type == WidgetType.TABLE


def test_update_widget():
    """Test aktualizacji widgetu."""
    engine = ComponentEngine()
    
    widget = engine.create_widget(WidgetType.CHART, {"value": 1})
    new_data = {"value": 2}
    
    success = engine.update_widget(widget.id, new_data)
    
    assert success is True
    updated = engine.get_widget(widget.id)
    assert updated.data == new_data


def test_update_nonexistent_widget():
    """Test aktualizacji nieistniejącego widgetu."""
    engine = ComponentEngine()
    
    success = engine.update_widget("nonexistent-id", {"data": "test"})
    
    assert success is False


def test_remove_widget():
    """Test usuwania widgetu."""
    engine = ComponentEngine()
    
    widget = engine.create_widget(WidgetType.MARKDOWN, {"content": "test"})
    success = engine.remove_widget(widget.id)
    
    assert success is True
    assert engine.get_widget(widget.id) is None


def test_remove_nonexistent_widget():
    """Test usuwania nieistniejącego widgetu."""
    engine = ComponentEngine()
    
    success = engine.remove_widget("nonexistent-id")
    
    assert success is False


def test_list_widgets():
    """Test listowania widgetów."""
    engine = ComponentEngine()
    
    widget1 = engine.create_widget(WidgetType.CHART, {"data": 1})
    widget2 = engine.create_widget(WidgetType.TABLE, {"data": 2})
    
    widgets = engine.list_widgets()
    
    assert len(widgets) == 2
    widget_ids = [w.id for w in widgets]
    assert widget1.id in widget_ids
    assert widget2.id in widget_ids


def test_clear_widgets():
    """Test czyszczenia wszystkich widgetów."""
    engine = ComponentEngine()
    
    engine.create_widget(WidgetType.CHART, {"data": 1})
    engine.create_widget(WidgetType.TABLE, {"data": 2})
    
    assert len(engine.widgets) == 2
    
    engine.clear_widgets()
    
    assert len(engine.widgets) == 0


def test_create_chart_widget():
    """Test tworzenia widgetu wykresu."""
    engine = ComponentEngine()
    
    chart_data = {
        "labels": ["A", "B", "C"],
        "datasets": [{"data": [1, 2, 3]}]
    }
    
    widget = engine.create_chart_widget("bar", chart_data, "Test Chart")
    
    assert widget.type == WidgetType.CHART
    assert widget.data["chartType"] == "bar"
    assert widget.data["chartData"] == chart_data
    assert widget.data["title"] == "Test Chart"


def test_create_table_widget():
    """Test tworzenia widgetu tabeli."""
    engine = ComponentEngine()
    
    headers = ["Name", "Age"]
    rows = [["John", 30], ["Jane", 25]]
    
    widget = engine.create_table_widget(headers, rows, "Test Table")
    
    assert widget.type == WidgetType.TABLE
    assert widget.data["headers"] == headers
    assert widget.data["rows"] == rows
    assert widget.data["title"] == "Test Table"


def test_create_form_widget():
    """Test tworzenia widgetu formularza."""
    engine = ComponentEngine()
    
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    submit_intent = "test_intent"
    
    widget = engine.create_form_widget(schema, submit_intent, "Test Form")
    
    assert widget.type == WidgetType.FORM
    assert widget.data["schema"] == schema
    assert widget.data["title"] == "Test Form"
    assert widget.events["submit"] == submit_intent


def test_create_markdown_widget():
    """Test tworzenia widgetu Markdown."""
    engine = ComponentEngine()
    
    content = "# Test\n\nThis is **bold**"
    widget = engine.create_markdown_widget(content)
    
    assert widget.type == WidgetType.MARKDOWN
    assert widget.data["content"] == content


def test_create_mermaid_widget():
    """Test tworzenia widgetu Mermaid."""
    engine = ComponentEngine()
    
    diagram = "graph TD\n  A --> B"
    widget = engine.create_mermaid_widget(diagram, "Test Diagram")
    
    assert widget.type == WidgetType.MERMAID
    assert widget.data["diagram"] == diagram
    assert widget.data["title"] == "Test Diagram"


def test_create_card_widget():
    """Test tworzenia widgetu karty."""
    engine = ComponentEngine()
    
    actions = [{"id": "btn1", "label": "Click", "intent": "test_intent"}]
    widget = engine.create_card_widget("Title", "Content", "🎨", actions)
    
    assert widget.type == WidgetType.CARD
    assert widget.data["title"] == "Title"
    assert widget.data["content"] == "Content"
    assert widget.data["icon"] == "🎨"
    assert widget.data["actions"] == actions
    assert widget.events["btn1"] == "test_intent"


def test_widget_model():
    """Test modelu Widget."""
    widget = Widget(
        type=WidgetType.CHART,
        data={"test": "data"},
        events={"click": "intent"},
        metadata={"author": "test"}
    )
    
    assert widget.id is not None
    assert widget.type == WidgetType.CHART
    assert widget.data == {"test": "data"}
    assert widget.events == {"click": "intent"}
    assert widget.metadata == {"author": "test"}
    assert widget.created_at is not None


def test_widget_type_enum():
    """Test enumeracji typów widgetów."""
    assert WidgetType.CHART == "chart"
    assert WidgetType.TABLE == "table"
    assert WidgetType.FORM == "form"
    assert WidgetType.MARKDOWN == "markdown"
    assert WidgetType.CUSTOM_HTML == "custom-html"
    assert WidgetType.MERMAID == "mermaid"
    assert WidgetType.CARD == "card"
