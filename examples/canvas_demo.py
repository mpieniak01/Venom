"""Przykład: THE_CANVAS - Dynamiczna generacja UI."""

import asyncio

from venom_core.execution.skills.render_skill import RenderSkill
from venom_core.ui.component_engine import ComponentEngine


async def main():
    """Demo THE_CANVAS - różne typy widgetów."""
    print("🎨 THE_CANVAS Demo - Dynamiczna Generacja UI\n")

    # Inicjalizacja
    component_engine = ComponentEngine()
    render_skill = RenderSkill(component_engine=component_engine)

    print("=" * 60)
    print("1. Wykres Słupkowy - Aktywność Commitów")
    print("=" * 60)

    widget_id = render_skill.render_chart(
        chart_type="bar",
        labels="Pon,Wt,Śr,Czw,Pt,Sob,Ndz",
        values="12,19,3,17,10,5,2",
        dataset_label="Liczba commitów",
        title="Aktywność commitów w tym tygodniu",
    )
    print(f"✅ {widget_id}\n")

    print("=" * 60)
    print("2. Tabela - Status Kontenerów Docker")
    print("=" * 60)

    widget_id = render_skill.render_table(
        headers="Kontener,Status,CPU,Memory",
        rows_data="venom-api,running,5%,128MB;postgres,running,12%,512MB;redis,running,2%,64MB",
        title="Status Kontenerów",
    )
    print(f"✅ {widget_id}\n")

    print("=" * 60)
    print("3. Formularz - Zgłoszenie Błędu")
    print("=" * 60)

    widget_id = render_skill.create_input_form(
        form_title="Zgłoś Błąd",
        fields="title:text:Tytuł*;description:textarea:Opis;priority:text:Priorytet",
        submit_intent="create_github_issue",
    )
    print(f"✅ {widget_id}\n")

    print("=" * 60)
    print("4. Diagram Mermaid - Architektura")
    print("=" * 60)

    diagram_code = """
graph TD
    A[Użytkownik] --> B[Dashboard]
    B --> C[WebSocket]
    C --> D[ComponentEngine]
    D --> E[Widget]
    E --> F[Chart.js]
    E --> G[Mermaid]
    E --> H[Forms]
"""

    widget_id = render_skill.render_mermaid_diagram(
        diagram_code=diagram_code, title="Architektura THE_CANVAS"
    )
    print(f"✅ {widget_id}\n")

    print("=" * 60)
    print("5. Markdown - Dokumentacja")
    print("=" * 60)

    markdown_content = """
# THE_CANVAS

## Funkcjonalności

- **Wykresy**: Chart.js dla wizualizacji danych
- **Tabele**: Responsywne tabele z sortowaniem
- **Formularze**: JSON Schema formularze
- **Diagramy**: Mermaid.js dla diagramów
- **Markdown**: Rich text rendering

## Bezpieczeństwo

✅ Sanityzacja HTML (bleach + DOMPurify)
✅ XSS Protection
✅ Safe rendering
"""

    widget_id = render_skill.render_markdown(content=markdown_content)
    print(f"✅ {widget_id}\n")

    print("=" * 60)
    print("6. Karta - Narzędzie Pogodowe")
    print("=" * 60)

    card_config = component_engine.create_card_widget(
        title="Weather Tool",
        content="Pobierz aktualną pogodę dla dowolnego miasta",
        icon="🌤️",
        actions=[
            {"id": "use_weather", "label": "Sprawdź pogodę", "intent": "use_weather"},
            {"id": "info_weather", "label": "Info", "intent": "tool_info:weather"},
        ],
    )
    print(f"✅ Utworzono kartę: {card_config.id}\n")

    print("=" * 60)
    print("7. Lista Wszystkich Widgetów")
    print("=" * 60)

    widgets = component_engine.list_widgets()
    print(f"\nŁącznie widgetów: {len(widgets)}\n")

    for widget in widgets:
        print(f"  • {widget.type.upper()}: {widget.id}")
        if "title" in widget.data:
            print(f"    Tytuł: {widget.data['title']}")

    print("\n" + "=" * 60)
    print("8. Live Update - Aktualizacja Wykresu")
    print("=" * 60)

    # Pobierz pierwszy widget wykresu
    chart_widgets = [w for w in widgets if w.type == "chart"]
    if chart_widgets:
        chart_id = chart_widgets[0].id
        print(f"\nAktualizacja widgetu: {chart_id}")

        new_data = {
            "chartType": "line",
            "chartData": {
                "labels": ["Week 1", "Week 2", "Week 3", "Week 4"],
                "datasets": [
                    {
                        "label": "Nowe dane",
                        "data": [25, 30, 45, 60],
                        "backgroundColor": "rgba(16, 185, 129, 0.5)",
                    }
                ],
            },
            "title": "Wzrost w czasie",
        }

        success = component_engine.update_widget(chart_id, new_data)
        print(f"✅ Aktualizacja: {'Sukces' if success else 'Błąd'}\n")

    print("=" * 60)
    print("9. Usuwanie Widgetu")
    print("=" * 60)

    if widgets:
        to_remove = widgets[-1].id
        print(f"\nUsuwanie widgetu: {to_remove}")
        success = component_engine.remove_widget(to_remove)
        print(f"✅ Usunięto: {'Sukces' if success else 'Błąd'}")
        print(f"Pozostało widgetów: {len(component_engine.list_widgets())}\n")

    print("=" * 60)
    print("10. Czyszczenie Wszystkich Widgetów")
    print("=" * 60)

    component_engine.clear_widgets()
    print(f"✅ Wyczyszczono. Pozostało widgetów: {len(component_engine.list_widgets())}\n")

    print("=" * 60)
    print("🎉 Demo zakończone!")
    print("=" * 60)
    print(
        "\nAby zobaczyć widgety w dashboardzie, uruchom:\n  python -m venom_core.main\n"
    )
    print("Następnie użyj RenderSkill w kontekście agenta z WebSocket connection.\n")


if __name__ == "__main__":
    asyncio.run(main())
