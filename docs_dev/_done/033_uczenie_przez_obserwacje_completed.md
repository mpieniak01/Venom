# ZADANIE: 033_THE_APPRENTICE (Visual Imitation Learning & Workflow Synthesis)

**Status:** ✅ IMPLEMENTACJA ZAKOŃCZONA - Moduły Core
**Priorytet:** Rewolucyjny (Automatyzacja poprzez Demonstrację)
**Kontekst:** Warstwa Uczenia i Percepcji

---

## Zaimplementowano:

### ✅ A. Rejestrator Demonstracji (`venom_core/perception/recorder.py`)
- Synchroniczne nagrywanie zrzutów ekranu (mss) i zdarzeń wejścia (pynput)
- Logowanie zdarzeń myszy (kliknięcia, ruchy) i klawiatury (tekst, skróty)
- Zapis sesji do JSON + katalog ze zrzutami
- Buforowanie zrzutów dla wydajności

### ✅ B. Analizator Behawioralny (`venom_core/learning/demonstration_analyzer.py`)
- Analiza sekwencji zdarzeń z sesji demonstracyjnej
- Transformacja współrzędnych pikseli na opisy semantyczne
- Wykrywanie sekwencji klawiszy (tekst vs skróty)
- Heurystyka rozpoznawania haseł (dla prywatności)
- Generowanie ActionIntent (semantyczne kroki)

### ✅ C. Agent Czeladnik (`venom_core/agents/apprentice.py`)
- Zarządzanie cyklem życia demonstracji (REC/STOP)
- Generowanie skryptów Python z analizy
- Parametryzacja workflow (zmienne vs stałe)
- Integracja z GhostAgent API
- Zapis do custom_skills

### ✅ D. Magazyn Procedur (`venom_core/memory/workflow_store.py`)
- Przechowywanie workflow w JSON
- CRUD operacje na workflow i krokach
- Eksport workflow do Python
- Wyszukiwanie workflow
- Cache w pamięci

### ✅ F. Testy jednostkowe
- `test_recorder.py` - 100% pokrycie DemonstrationRecorder
- `test_apprentice_agent.py` - testy ApprenticeAgent
- `test_workflow_store.py` - testy WorkflowStore

### ✅ G. Demo i dokumentacja
- `examples/apprentice_demo.py` - interaktywne demo

---

## Do zrobienia:

### E. Dashboard Update: "Teaching Studio"
- Integracja z web UI (przyciski REC/STOP)
- Timeline z miniaturkami zrzutów
- Edytor workflow (wizualna edycja kroków)
- Preview wygenerowanego kodu

### Integracja z głównym systemem
- Rejestracja ApprenticeAgent w orchestratorze
- Integracja z DesignerAgent (edycja workflow)
- Integracja z GhostAgent (wykonywanie workflow)

### Zaawansowane funkcje
- Integracja z Florence-2 dla lepszego rozpoznawania UI
- OCR dla wykrywania tekstu na przyciskach
- Detekcja kolorów i kształtów elementów
- Automatyczna walidacja workflow

---

## Użycie:

```python
from venom_core.agents.apprentice import ApprenticeAgent
from venom_core.execution.kernel_builder import KernelBuilder

# Inicjalizacja
kernel = KernelBuilder().build_kernel()
apprentice = ApprenticeAgent(kernel)

# Rozpocznij nagrywanie
await apprentice.process("Rozpocznij nagrywanie nazwany login_workflow")

# [Użytkownik wykonuje akcje]

# Zatrzymaj nagrywanie
await apprentice.process("Zatrzymaj nagrywanie")

# Analizuj
await apprentice.process("Analizuj sesję login_workflow")

# Generuj skill
await apprentice.process("Generuj skill login_to_app")
```

---

## Kryteria akceptacji (DoD):

- ✅ Nagrywanie demonstracji (mysz + klawiatura + zrzuty)
- ✅ Analiza demonstracji i generowanie ActionIntent
- ✅ Generowanie skryptów Python dla GhostAgent
- ✅ Parametryzacja workflow
- ✅ Przechowywanie i zarządzanie workflow
- ⏳ Dashboard UI "Teaching Studio"
- ⏳ Integracja z głównym orchestratorem
- ⏳ Weryfikacja odporności na pozycję okien (wymaga testów z GhostAgent)

---

**Notatki implementacyjne:**
- Używamy `mss` do szybkich zrzutów ekranu (szybsze niż PIL.ImageGrab)
- `pynput` do cross-platform'owego przechwytywania zdarzeń
- Buforowanie zrzutów w pamięci przed zapisem na dysk
- Cropowanie 512x512 wokół kursora dla lepszej precyzji analizy
- Heurystyka wykrywania haseł (brak spacji + cyfry + znaki specjalne)
- Generowany kod używa opisów elementów + fallback do współrzędnych
