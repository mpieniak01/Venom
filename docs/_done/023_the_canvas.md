# ZADANIE: 023_THE_CANVAS (Dynamic UI Generation & Visual Synthesis) ✅

**Status:** ✅ UKOŃCZONE
**Data realizacji:** 2025-12-07
**Priorytet:** Strategiczny (User Experience & Data Visualization)

---

## 📋 Podsumowanie

THE_CANVAS to system dynamicznego generowania interfejsu użytkownika, który przekształca Venom z czatu w pełnoprawny "System Operacyjny" z graficznym dashboardem. System umożliwia agentom Venom tworzenie interaktywnych widgetów, wykresów, formularzy i diagramów bezpośrednio w interfejsie użytkownika.

---

## 🎯 Zrealizowane Cele

### 1. ✅ Silnik Komponentów (`venom_core/ui/component_engine.py`)
- Utworzono moduł `ComponentEngine` do zarządzania widgetami
- Zaimplementowano model `Widget` z typami:
  - `chart` - wykresy (Chart.js)
  - `table` - tabele danych
  - `form` - formularze z JSON Schema
  - `markdown` - treści Markdown
  - `mermaid` - diagramy Mermaid
  - `card` - karty informacyjne
  - `custom-html` - niestandardowy HTML (z sanityzacją)
- Live Update mechanizm przez WebSocket
- Bezpieczne zarządzanie cyklem życia widgetów

### 2. ✅ Agent Projektant (`venom_core/agents/designer.py`)
- Utworzono `DesignerAgent` jako eksperta UI/UX
- System prompt z kompetencjami:
  - Generowanie HTML/TailwindCSS/JavaScript
  - Konfiguracja wykresów (Chart.js)
  - Projektowanie responsywnych komponentów
  - Tworzenie diagramów Mermaid
- Metody pomocnicze:
  - `create_visualization()` - uniwersalna wizualizacja
  - `create_chart()` - wykresy
  - `create_form()` - formularze
  - `create_dashboard_card()` - karty dla narzędzi

### 3. ✅ Umiejętność Wizualizacji (`venom_core/execution/skills/render_skill.py`)
- Utworzono `RenderSkill` jako plugin dla Semantic Kernel
- Metody dostępne dla agentów:
  - `render_chart()` - renderowanie wykresów
  - `render_table()` - renderowanie tabel
  - `render_dashboard_widget()` - custom HTML
  - `create_input_form()` - interaktywne formularze
  - `render_markdown()` - treści Markdown
  - `render_mermaid_diagram()` - diagramy
  - `update_widget()` - aktualizacja live
  - `remove_widget()` - usuwanie widgetów
- Sanityzacja HTML przez `bleach`

### 4. ✅ Dashboard Frontend 2.0
**HTML (`web/templates/index.html`):**
- Dodano CDN dla bibliotek:
  - Chart.js 4.4.0 - wykresy
  - Mermaid.js 10.6.1 - diagramy
  - DOMPurify 3.0.6 - sanityzacja HTML
  - Marked.js 9.1.6 - rendering Markdown
- Grid Layout container dla widgetów
- Przycisk "Clear Widgets"

**JavaScript (`web/static/js/app.js`):**
- Obsługa zdarzeń `RENDER_WIDGET`, `UPDATE_WIDGET`, `REMOVE_WIDGET`
- Renderowanie widgetów po typach:
  - `renderChartWidget()` - wykresy Chart.js
  - `renderTableWidget()` - tabele
  - `renderFormWidget()` - formularze z walidacją
  - `renderMarkdownWidget()` - Markdown (Marked.js)
  - `renderMermaidWidget()` - diagramy Mermaid
  - `renderCardWidget()` - karty z akcjami
  - `renderCustomHTMLWidget()` - sanityzowany HTML (DOMPurify)
- Zarządzanie instancjami Chart.js
- Inicjalizacja Mermaid z dark theme

**CSS (`web/static/css/app.css`):**
- Style dla `.widgets-grid` - responsywny grid layout
- Style dla każdego typu widgetu
- Dark theme zgodny z dashboardem
- Hover effects i animacje
- Responsywne formularze

### 5. ✅ Integracja WebSocket
- Dodano typy zdarzeń w `EventType`:
  - `RENDER_WIDGET` - renderowanie nowego widgetu
  - `UPDATE_WIDGET` - aktualizacja widgetu
  - `REMOVE_WIDGET` - usunięcie widgetu
- System transmisji widgetów przez WebSocket

### 6. ✅ Bezpieczeństwo
- **Backend:** Sanityzacja HTML przez `bleach` (Python)
  - Whitelist dozwolonych tagów HTML
  - Whitelist dozwolonych atrybutów
  - Automatyczne usuwanie niebezpiecznych tagów
- **Frontend:** Sanityzacja HTML przez `DOMPurify` (JavaScript)
  - Ochrona przed XSS
  - Bezpieczne renderowanie custom HTML
- Bezpieczne renderowanie Markdown (Marked.js)

### 7. ✅ Integracja z Toolmaker
- Dodano metodę `create_tool_ui_card()` w `ToolmakerAgent`
- Automatyczne generowanie UI card dla nowych narzędzi
- Karty zawierają:
  - Nazwę narzędzia
  - Opis
  - Ikonę
  - Przyciski akcji ("Użyj narzędzia", "Info")
  - Metadata (nazwa, kategoria, twórca)

### 8. ✅ Testy
- **test_component_engine.py** - 17 testów ✅
  - Inicjalizacja ComponentEngine
  - CRUD operacje na widgetach
  - Wszystkie typy widgetów
  - Live Update
- **test_render_skill.py** - 18 testów ✅
  - Wszystkie metody renderowania
  - Sanityzacja HTML
  - Błędna obsługa
- **test_designer_agent.py** - 9 testów ✅
  - Tworzenie wizualizacji
  - Generowanie konfiguracji
  - Obsługa błędów

**Łącznie: 44 testy, wszystkie przechodzą ✅**

---

## 📖 Przykłady Użycia

### Przykład 1: Wykres Aktywności Commitów
```python
from venom_core.execution.skills.render_skill import RenderSkill

render_skill = RenderSkill()

# Renderuj wykres słupkowy
render_skill.render_chart(
    chart_type="bar",
    labels="Pon,Wt,Śr,Czw,Pt",
    values="12,19,3,17,10",
    dataset_label="Liczba commitów",
    title="Aktywność commitów w tym tygodniu"
)
```

### Przykład 2: Formularz Zgłoszenia Błędu
```python
render_skill.create_input_form(
    form_title="Zgłoś błąd",
    fields="title:text:Tytuł*;description:textarea:Opis;priority:text:Priorytet",
    submit_intent="create_github_issue"
)
```

### Przykład 3: Diagram Mermaid
```python
diagram_code = """
graph TD
    A[Użytkownik] --> B[Dashboard]
    B --> C[WebSocket]
    C --> D[ComponentEngine]
    D --> E[Widget]
"""

render_skill.render_mermaid_diagram(
    diagram_code=diagram_code,
    title="Architektura THE_CANVAS"
)
```

### Przykład 4: Tabela Danych
```python
render_skill.render_table(
    headers="Kontener,Status,CPU",
    rows_data="venom-api,running,5%;postgres,running,12%;redis,running,2%",
    title="Status Kontenerów Docker"
)
```

### Przykład 5: DesignerAgent
```python
from venom_core.agents.designer import DesignerAgent

designer = DesignerAgent(kernel)

# Wizualizacja danych
config = await designer.create_visualization(
    "Pokaż wykres linowy z temperaturą w ciągu tygodnia",
    {"days": ["Pon", "Wt", "Śr"], "temps": [15, 18, 20]}
)
```

---

## 🔧 Architektura

```
┌─────────────────────────────────────────────────────────┐
│                    THE_CANVAS System                     │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐        ┌──────────────┐              │
│  │ DesignerAgent│◄──────►│ComponentEngine│              │
│  └──────┬───────┘        └──────┬───────┘              │
│         │                       │                        │
│         │                       │                        │
│  ┌──────▼───────┐        ┌─────▼────────┐              │
│  │ RenderSkill  │        │   Widgets    │              │
│  │  (SK Plugin) │        │   Storage    │              │
│  └──────┬───────┘        └─────┬────────┘              │
│         │                       │                        │
│         │    WebSocket          │                        │
│         └───────┬───────────────┘                        │
│                 │                                         │
│         ┌───────▼────────┐                               │
│         │  EventBroadcast│                               │
│         └───────┬────────┘                               │
│                 │                                         │
│    ┌────────────▼───────────────┐                       │
│    │    Dashboard Frontend       │                       │
│    │  - Chart.js Rendering       │                       │
│    │  - Mermaid.js Diagrams      │                       │
│    │  - DOMPurify Sanitization   │                       │
│    │  - Grid Layout              │                       │
│    └─────────────────────────────┘                       │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Kluczowe Funkcjonalności

1. **Dynamiczne Tworzenie UI** - Agenci mogą tworzyć interfejs w czasie rzeczywistym
2. **Live Updates** - Widgety aktualizują się bez przeładowania strony
3. **Bezpieczne Renderowanie** - Podwójna sanityzacja (backend + frontend)
4. **Responsywny Design** - Grid layout dostosowuje się do rozmiaru ekranu
5. **Integracja z Narzędziami** - Automatyczne UI dla nowych narzędzi (Toolmaker)
6. **Różnorodność Typów** - 7 typów widgetów + custom HTML
7. **Real-time Communication** - WebSocket dla instant updates

---

## 📊 Metryki

- **Linie kodu:** ~2500+ linii (Python + JavaScript + CSS)
- **Testy:** 44 testy, 100% pass rate
- **Komponenty:** 3 główne moduły (ComponentEngine, DesignerAgent, RenderSkill)
- **Typy widgetów:** 7
- **Biblioteki frontend:** 4 (Chart.js, Mermaid.js, DOMPurify, Marked.js)

---

## 🔒 Bezpieczeństwo

### Backend (Python)
```python
# Bleach sanitization
from bleach import clean

ALLOWED_TAGS = ['div', 'span', 'p', 'h1', 'h2', 'h3', ...]
ALLOWED_ATTRIBUTES = {'a': ['href'], 'div': ['class'], ...}

clean_html = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)
```

### Frontend (JavaScript)
```javascript
// DOMPurify sanitization
if (typeof DOMPurify !== 'undefined') {
    container.innerHTML = DOMPurify.sanitize(widget.data.html);
}
```

---

## 🎨 Style Guide

### Kolory (Dark Theme)
- Background: `#1e1e1e`
- Primary: `#3b82f6` (niebieski)
- Success: `#10b981` (zielony)
- Warning: `#f59e0b` (pomarańczowy)
- Error: `#ef4444` (czerwony)

### Grid Layout
- Auto-fit columns: minimum 300px
- Gap: 1rem
- Responsive breakpoints automatyczne

---

## 📝 TODO (Przyszłe Ulepszenia)

- [ ] Drag & Drop dla widgetów
- [ ] Zapisywanie layoutu dashboardu
- [ ] Eksport widgetów do obrazów
- [ ] Więcej typów wykresów (scatter, bubble, mixed)
- [ ] Real-time collaboration (wiele użytkowników)
- [ ] Widget templates library
- [ ] A/B testing dla UI komponentów
- [ ] Analytics dla interakcji użytkownika

---

## 🔗 Powiązane Zadania

- **014_THE_FORGE** - Toolmaker (integracja UI cards)
- **018_THE_INTEGRATOR** - GitHub integration (formularze issues)
- **006_PERCEPTION** - Dashboard telemetry
- **012_THE_GUARDIAN** - Test results visualization

---

## ✅ Kryteria Akceptacji - Wszystkie Spełnione

1. ✅ Wizualizacja Danych - Wykresy renderują się poprawnie
2. ✅ Interaktywność - Formularze działają z walidacją
3. ✅ Live App - Można generować mini-aplikacje (np. gry)
4. ✅ Estetyka - TailwindCSS + dark theme
5. ✅ Bezpieczeństwo - Podwójna sanityzacja HTML
6. ✅ Testy - 44 testy przechodzą

---

**Realizacja:** @copilot (GitHub Copilot Agent)
**Review:** Pending
**Merge:** Pending PR approval
