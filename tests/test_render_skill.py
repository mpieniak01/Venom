"""Testy jednostkowe dla RenderSkill."""

import pytest

import venom_core.execution.skills.render_skill as render_skill_module
from venom_core.execution.skills.render_skill import RenderSkill
from venom_core.ui.component_engine import ComponentEngine, WidgetType


@pytest.fixture
def render_skill():
    """Fixture dla RenderSkill z nowym ComponentEngine."""
    return RenderSkill()


def test_render_skill_initialization():
    """Test inicjalizacji RenderSkill."""
    skill = RenderSkill()
    assert skill.component_engine is not None


def test_render_skill_with_engine():
    """Test inicjalizacji RenderSkill z istniejącym ComponentEngine."""
    engine = ComponentEngine()
    skill = RenderSkill(component_engine=engine)
    assert skill.component_engine == engine


def test_sanitize_html():
    """Test sanityzacji HTML."""
    skill = RenderSkill()

    # Bezpieczny HTML
    safe_html = '<div class="test">Hello</div>'
    sanitized = skill._sanitize_html(safe_html)
    assert "<div" in sanitized
    assert "Hello" in sanitized

    # Niebezpieczny HTML (script tag)
    dangerous_html = '<script>alert("XSS")</script><div>Safe</div>'
    sanitized = skill._sanitize_html(dangerous_html)
    assert "<script>" not in sanitized
    assert "Safe" in sanitized


def test_sanitize_html_fallback_strips_attributes(monkeypatch):
    """Test fallback sanitizera bez bleach - atrybuty nie powinny przejść."""
    monkeypatch.setattr(render_skill_module, "BLEACH_AVAILABLE", False)
    monkeypatch.setattr(render_skill_module, "bleach", None)

    skill = RenderSkill()
    html = '<div class="x" onclick="alert(1)">Safe</div>'
    sanitized = skill._sanitize_html(html)

    assert "<div>" in sanitized
    assert "Safe" in sanitized
    assert "onclick" not in sanitized
    assert 'class="' not in sanitized


def test_render_chart(render_skill):
    """Test renderowania wykresu."""
    result = render_skill.render_chart(
        chart_type="bar",
        labels="A,B,C",
        values="1,2,3",
        dataset_label="Test",
        title="Test Chart",
    )

    assert "Utworzono wykres" in result
    widgets = render_skill.component_engine.list_widgets()
    assert len(widgets) == 1
    assert widgets[0].type == WidgetType.CHART


def test_render_chart_invalid_data(render_skill):
    """Test renderowania wykresu z nieprawidłowymi danymi."""
    result = render_skill.render_chart(
        chart_type="bar",
        labels="A,B",
        values="1,2,3",  # Niezgodna liczba wartości
        dataset_label="Test",
    )

    assert "Błąd" in result


def test_render_table(render_skill):
    """Test renderowania tabeli."""
    result = render_skill.render_table(
        headers="Name,Age", rows_data="John,30;Jane,25", title="Test Table"
    )

    assert "Utworzono tabelę" in result
    widgets = render_skill.component_engine.list_widgets()
    assert len(widgets) == 1
    assert widgets[0].type == WidgetType.TABLE


def test_render_dashboard_widget(render_skill):
    """Test renderowania niestandardowego widgetu HTML."""
    html = '<div class="custom">Custom Widget</div>'
    result = render_skill.render_dashboard_widget(html)

    assert "Utworzono widget HTML" in result
    widgets = render_skill.component_engine.list_widgets()
    assert len(widgets) == 1
    assert widgets[0].type == WidgetType.CUSTOM_HTML


def test_create_input_form(render_skill):
    """Test tworzenia formularza."""
    result = render_skill.create_input_form(
        form_title="Bug Report",
        fields="title:text:Title*;description:textarea:Description",
        submit_intent="create_issue",
    )

    assert "Utworzono formularz" in result
    widgets = render_skill.component_engine.list_widgets()
    assert len(widgets) == 1
    assert widgets[0].type == WidgetType.FORM


def test_render_markdown(render_skill):
    """Test renderowania Markdown."""
    content = "# Hello\n\nThis is **bold**"
    result = render_skill.render_markdown(content)

    assert "Utworzono Markdown" in result
    widgets = render_skill.component_engine.list_widgets()
    assert len(widgets) == 1
    assert widgets[0].type == WidgetType.MARKDOWN


def test_render_mermaid_diagram(render_skill):
    """Test renderowania diagramu Mermaid."""
    diagram = "graph TD\n  A --> B"
    result = render_skill.render_mermaid_diagram(diagram, "Test")

    assert "Utworzono diagram Mermaid" in result
    widgets = render_skill.component_engine.list_widgets()
    assert len(widgets) == 1
    assert widgets[0].type == WidgetType.MERMAID


def test_update_widget(render_skill):
    """Test aktualizacji widgetu."""
    # Utwórz widget
    render_skill.render_chart("bar", "A,B", "1,2", "Test")
    widgets = render_skill.component_engine.list_widgets()
    widget_id = widgets[0].id

    # Aktualizuj
    new_data = '{"chartType": "line", "chartData": {"labels": ["X"], "datasets": []}}'
    result = render_skill.update_widget(widget_id, new_data)

    assert "Zaktualizowano widget" in result


def test_update_nonexistent_widget(render_skill):
    """Test aktualizacji nieistniejącego widgetu."""
    result = render_skill.update_widget("nonexistent-id", '{"data": "test"}')

    assert "Nie znaleziono widgetu" in result


def test_remove_widget(render_skill):
    """Test usuwania widgetu."""
    # Utwórz widget
    render_skill.render_chart("bar", "A,B", "1,2", "Test")
    widgets = render_skill.component_engine.list_widgets()
    widget_id = widgets[0].id

    # Usuń
    result = render_skill.remove_widget(widget_id)

    assert "Usunięto widget" in result
    assert len(render_skill.component_engine.list_widgets()) == 0


def test_remove_nonexistent_widget(render_skill):
    """Test usuwania nieistniejącego widgetu."""
    result = render_skill.remove_widget("nonexistent-id")

    assert "Nie znaleziono widgetu" in result


def test_get_widget(render_skill):
    """Test pobierania widgetu jako dict."""
    render_skill.render_chart("bar", "A,B", "1,2", "Test")
    widgets = render_skill.component_engine.list_widgets()
    widget_id = widgets[0].id

    widget_dict = render_skill.get_widget(widget_id)

    assert widget_dict is not None
    assert widget_dict["id"] == widget_id
    assert widget_dict["type"] == "chart"


def test_get_nonexistent_widget(render_skill):
    """Test pobierania nieistniejącego widgetu."""
    widget_dict = render_skill.get_widget("nonexistent-id")

    assert widget_dict is None


def test_list_all_widgets(render_skill):
    """Test listowania wszystkich widgetów jako dict."""
    render_skill.render_chart("bar", "A", "1", "Chart")
    render_skill.render_table("Name", "John", "Table")

    widgets = render_skill.list_all_widgets()

    assert len(widgets) == 2
    assert all(isinstance(w, dict) for w in widgets)
    assert any(w["type"] == "chart" for w in widgets)
    assert any(w["type"] == "table" for w in widgets)


def test_multiple_widgets(render_skill):
    """Test tworzenia wielu widgetów."""
    render_skill.render_chart("bar", "A", "1", "Chart")
    render_skill.render_table("Name", "John", "Table")
    render_skill.render_markdown("# Test")

    widgets = render_skill.component_engine.list_widgets()
    assert len(widgets) == 3


def test_parse_form_fields_ignores_invalid_entries(render_skill):
    properties, required = render_skill._parse_form_fields(
        "name*:text:Name;invalid;amount:number:Amount"
    )
    assert properties["name"]["type"] == "string"
    assert properties["amount"]["type"] == "number"
    assert required == ["name"]
