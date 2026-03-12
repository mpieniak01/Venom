# The Apprentice - Visual Imitation Learning Guide

## Przegląd

**The Apprentice** to rewolucyjna funkcja Venoma umożliwiająca uczenie się nowych umiejętności poprzez obserwację działań użytkownika. Zamiast ręcznie programować skrypty automatyzacji, operator wykonuje zadanie a Venom "patrzy i uczy się".

## Architektura

System składa się z czterech głównych komponentów:

### 1. Demonstration Recorder (`venom_core/perception/recorder.py`)

Rejestrator nagrywa demonstracje użytkownika:
- **Zrzuty ekranu** - wykonywane w momentach akcji (mss library)
- **Zdarzenia myszy** - kliknięcia, pozycje (pynput)
- **Zdarzenia klawiatury** - wpisany tekst, skróty (pynput)

Dane są zapisywane jako sesja (`session.json` + katalog ze zrzutami).

```python
from venom_core.perception.recorder import DemonstrationRecorder

recorder = DemonstrationRecorder()

# Rozpocznij nagrywanie
session_id = recorder.start_recording(session_name="my_workflow")

# [Użytkownik wykonuje akcje]

# Zatrzymaj nagrywanie
session_path = recorder.stop_recording()
```

### 2. Demonstration Analyzer (`venom_core/learning/demonstration_analyzer.py`)

Analizator zamienia surowe dane na semantyczne akcje:
- Transformuje współrzędne pikseli → opisy elementów UI
- Rozpoznaje sekwencje klawiszy (tekst vs skróty)
- Wykrywa wrażliwe dane (hasła)
- Generuje `ActionIntent` (semantyczne kroki)

```python
from venom_core.learning.demonstration_analyzer import DemonstrationAnalyzer

analyzer = DemonstrationAnalyzer()

# Analizuj sesję
session = recorder.load_session(session_id)
actions = await analyzer.analyze_session(session)

# actions to lista ActionIntent z opisami semantycznymi
```

### 3. Apprentice Agent (`venom_core/agents/apprentice.py`)

Agent zarządza całym cyklem uczenia:
- Kontroluje nagrywanie (REC/STOP)
- Analizuje demonstracje
- Generuje skrypty Python
- Parametryzuje workflow
- Zapisuje do `custom_skills/`

```python
from venom_core.agents.apprentice import ApprenticeAgent

apprentice = ApprenticeAgent(kernel)

# Rozpocznij nagrywanie
await apprentice.process("Rozpocznij nagrywanie nazwany login_workflow")

# [Demonstracja]

# Zatrzymaj i analizuj
await apprentice.process("Zatrzymaj nagrywanie")
await apprentice.process("Analizuj sesję login_workflow")

# Generuj skill
await apprentice.process("Generuj skill login_to_app")
```

### 4. Workflow Store (`venom_core/memory/workflow_store.py`)

Magazyn przechowuje i zarządza workflow:
- Zapisywanie/ładowanie workflow (JSON)
- CRUD operacje na krokach
- Eksport do Python
- Wyszukiwanie workflow

```python
from venom_core.memory.workflow_store import WorkflowStore

store = WorkflowStore()

# Lista workflow
workflows = store.list_workflows()

# Załaduj workflow
workflow = store.load_workflow("my_workflow")

# Edytuj krok
store.update_step("my_workflow", step_id=1, updates={"enabled": False})

# Eksportuj do Python
python_file = store.export_to_python("my_workflow")
```

## Workflow Użytkownika

### Krok 1: Demonstracja

```
Użytkownik: "Venom, patrz jak wysyłam raport na Slacka"
Venom: "🔴 Rozpoczęto nagrywanie demonstracji (sesja: send_report_slack)"

[Użytkownik]:
1. Otwiera Slack
2. Klika kanał #general
3. Klika ikonę spinacza (attach)
4. Wybiera plik report.pdf
5. Klika "Send"

Użytkownik: "Zrobione"
Venom: "⬛ Zakończono nagrywanie (5 akcji, 32 sekundy)"
```

### Krok 2: Analiza

```
Venom: "Analizuję demonstrację..."
Venom: "Zrozumiałem workflow składający się z 5 kroków:
  1. Click Slack icon on taskbar
  2. Click #general channel
  3. Click attachment button (paperclip icon)
  4. Select file: report.pdf
  5. Click Send button
"
```

### Krok 3: Parametryzacja

```
Venom: "Zauważyłem wartość 'report.pdf'. Czy to ma być parametr?"
Użytkownik: "Tak, nazwij to 'filename'"
Venom: "OK, utworzę parametr 'filename' z domyślną wartością 'report.pdf'"
```

### Krok 4: Generowanie Skill

```
Venom: "Generuję skill 'send_report_slack'..."
Venom: "✅ Skill wygenerowany: workspace/custom_skills/send_report_slack.py"
```

### Krok 5: Wykonanie

```
Użytkownik: "Venom, wyślij raport na Slacka"
Venom: "Wykonuję workflow send_report_slack..."
[GhostAgent wykonuje wygenerowany kod]
Venom: "✅ Raport wysłany pomyślnie"
```

## Przykłady Użycia

### Przykład 1: Login do Aplikacji

```python
# 1. Nagraj demonstrację
await apprentice.process("Rozpocznij nagrywanie nazwany bank_login")

# Użytkownik:
# - Otwiera przeglądarkę
# - Wpisuje URL
# - Klika pole username
# - Wpisuje nazwę użytkownika
# - Klika pole password
# - Wpisuje hasło
# - Klika przycisk Login

await apprentice.process("Zatrzymaj nagrywanie")

# 2. Analizuj i generuj
await apprentice.process("Analizuj sesję bank_login")
await apprentice.process("Generuj skill bank_login_skill")

# 3. Wygenerowany kod (workspace/custom_skills/bank_login_skill.py):
"""
async def bank_login_skill(ghost_agent: GhostAgent, **kwargs):
    username = kwargs.get("username", "user@example.com")
    password = kwargs.get("password", "")

    await ghost_agent.vision_click(description="browser icon")
    await ghost_agent.input_skill.keyboard_type(text="https://bank.example.com")
    await ghost_agent.input_skill.keyboard_hotkey(["enter"])

    await ghost_agent.vision_click(description="username field")
    await ghost_agent.input_skill.keyboard_type(text=username)

    await ghost_agent.vision_click(description="password field")
    await ghost_agent.input_skill.keyboard_type(text=password)

    await ghost_agent.vision_click(description="login button")
"""
```

### Przykład 2: Eksport Danych

```python
# Demonstracja:
# 1. Otwórz Excel
# 2. File → Export → CSV
# 3. Wybierz lokalizację
# 4. Zapisz

await apprentice.process("Rozpocznij nagrywanie nazwany excel_export")
# [Demonstracja]
await apprentice.process("Zatrzymaj nagrywanie")
await apprentice.process("Generuj skill excel_to_csv")

# Użycie:
await ghost.process("Wykonaj skill excel_to_csv")
```

## Zaawansowane Funkcje

### Edycja Workflow

Po wygenerowaniu, workflow można edytować:

```python
from venom_core.memory.workflow_store import WorkflowStore, WorkflowStep

store = WorkflowStore()

# Dodaj krok (wait)
new_step = WorkflowStep(
    step_id=0,
    action_type="wait",
    description="Wait 2 seconds for page to load",
    params={"duration": 2.0},
)
store.add_step("my_workflow", new_step, position=3)

# Wyłącz krok
store.update_step("my_workflow", step_id=5, updates={"enabled": False})

# Zmień opis
store.update_step("my_workflow", step_id=2, updates={
    "description": "Click UPDATED button"
})
```

### Wyszukiwanie Workflow

```python
# Wyszukaj po nazwie/opisie
results = store.search_workflows("login")

# Wynik: lista workflow zawierających "login" w nazwie lub opisie
```

### Parametryzacja

System automatycznie wykrywa:
- **Stałe wartości** (URL, ścieżki) → hardcoded
- **Zmienne wartości** (dane użytkownika) → parametry z domyślnymi wartościami
- **Wrażliwe dane** (hasła) → parametry wymagane (bez domyślnej wartości)

```python
# Heurystyka wykrywania haseł:
# - Brak spacji
# - Zawiera cyfry
# - Zawiera znaki specjalne
# - Krótki tekst (< 20 znaków)
```

## Bezpieczeństwo i Prywatność

### Zamazywanie Haseł

System automatycznie wykrywa prawdopodobne hasła:

```python
# W demonstracji:
# Użytkownik wpisuje: "MyP@ssw0rd!"

# W analizie:
action = ActionIntent(
    action_type="type",
    description="Type text: ***",  # Zamazane
    params={
        "text": "MyP@ssw0rd!",
        "is_sensitive": True  # Oznaczony jako wrażliwy
    }
)

# W wygenerowanym kodzie:
# password = kwargs.get("password", "")  # Brak domyślnej wartości
```

### Prywatność Zrzutów Ekranu

Zrzuty ekranu przechowywane lokalnie w `workspace/demonstrations/`.
Można je ręcznie usunąć po wygenerowaniu skill.

## Integracja z GhostAgent

Wygenerowane skrypty używają API GhostAgent:

- `vision_click(description, fallback_coords)` - kliknięcie elementu
- `input_skill.keyboard_type(text)` - wpisanie tekstu
- `input_skill.keyboard_hotkey(keys)` - skrót klawiszowy
- `_wait(duration)` - opóźnienie
- `apply_runtime_profile(profile)` - tryb runtime (`desktop_safe` lub `desktop_power`)

### Odporność na Pozycję

Kod używa opisów elementów zamiast sztywnych współrzędnych:

```python
# ❌ Nieodporne (sztywne współrzędne)
await ghost.input_skill.mouse_click(x=500, y=300)

# ✅ Odporne (opis elementu + fallback)
await ghost.vision_click(
    description="blue Submit button",
    fallback_coords=(500, 300)  # Fallback jeśli nie znaleziono
)
```

W profilu `desktop_safe` fallback może zostać zablokowany (fail-closed), jeśli locate nie znajdzie elementu.

## Ograniczenia i Roadmap

### Aktualne Ograniczenia

- Rozpoznawanie elementów UI wymaga dalszej integracji z Florence-2/LLaVA
- Brak OCR dla automatycznego wykrywania tekstu na przyciskach
- Brak automatycznej walidacji wygenerowanych workflow

### Planowane Funkcje

- **Dashboard UI**: Web interface z przyciskami REC/STOP, timeline, edytor
- **Florence-2 Integration**: Lepsze rozpoznawanie elementów UI
- **OCR**: Automatyczne wykrywanie tekstu na przyciskach
- **Walidacja**: Automatyczne testy wygenerowanych workflow
- **Multi-monitor Support**: Obsługa wielu monitorów
- **Conditional Steps**: Kroki warunkowe (if/else)

## API Reference

### DemonstrationRecorder

```python
recorder = DemonstrationRecorder(workspace_root="./workspace")

# Rozpocznij nagrywanie
session_id = recorder.start_recording(
    session_name="my_session",
    metadata={"description": "Login workflow"}
)

# Zatrzymaj nagrywanie
session_path = recorder.stop_recording()

# Załaduj sesję
session = recorder.load_session(session_id)

# Lista sesji
sessions = recorder.list_sessions()
```

### DemonstrationAnalyzer

```python
analyzer = DemonstrationAnalyzer()

# Analizuj sesję
actions = await analyzer.analyze_session(session)

# Generuj opis
summary = analyzer.generate_workflow_summary(actions)
```

### ApprenticeAgent

```python
apprentice = ApprenticeAgent(kernel, workspace_root="./workspace")

# Przetwarzaj komendy
await apprentice.process("Rozpocznij nagrywanie")
await apprentice.process("Zatrzymaj nagrywanie")
await apprentice.process("Analizuj sesję <session_id>")
await apprentice.process("Generuj skill <skill_name>")
```

### WorkflowStore

```python
store = WorkflowStore(workspace_root="./workspace")

# CRUD
workflow = store.load_workflow(workflow_id)
store.save_workflow(workflow)
store.delete_workflow(workflow_id)

# Operacje na krokach
store.add_step(workflow_id, step, position=None)
store.update_step(workflow_id, step_id, updates)
store.remove_step(workflow_id, step_id)

# Eksport
python_path = store.export_to_python(workflow_id)

# Wyszukiwanie
results = store.search_workflows(query)
```

## Troubleshooting

### Problem: Nagrywanie nie startuje

**Przyczyna**: Brak uprawnień do przechwytywania zdarzeń
**Rozwiązanie**: Uruchom z uprawnieniami administratora (Windows) lub jako sudo (Linux)

### Problem: Zrzuty ekranu są puste

**Przyczyna**: Problem z biblioteką mss w środowisku headless
**Rozwiązanie**: Użyj środowiska z GUI lub zmień backend na PIL.ImageGrab

### Problem: Wygenerowany kod nie działa

**Przyczyna**: Nieodpowiednie opisy elementów
**Rozwiązanie**:
1. Sprawdź logi analizy
2. Ręcznie edytuj workflow w WorkflowStore
3. Dodaj bardziej szczegółowe opisy elementów

## Przykłady

Zobacz pełne przykłady w:
- `examples/apprentice_demo.py` - podstawowe demo
- `examples/apprentice_integration_example.py` - integracja z GhostAgent

## Wsparcie

W razie problemów:
1. Sprawdź logi: `data/logs/venom.log`
2. Uruchom demo: `python examples/apprentice_demo.py`
3. Zgłoś issue na GitHub
