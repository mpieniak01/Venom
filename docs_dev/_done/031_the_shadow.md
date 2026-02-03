# ZADANIE: 031_THE_SHADOW (Desktop Awareness, Clipboard Watcher & Proactive Assistance)

**Status:** ✅ ZREALIZOWANE
**Priorytet:** Wysoki (UX & Human-Computer Symbiosis)
**Kontekst:** Warstwa Percepcji i Interakcji
**Data zakończenia:** 2025-12-08

---

## Cel
Przekształcenie Venoma z "Pasywnego Narzędzia" w "Aktywnego Obserwatora". Venom monitoruje aktywność użytkownika na pulpicie (aktywne okno, schowek), rozumie kontekst pracy i oferuje pomoc poprzez powiadomienia systemowe.

## Zrealizowane komponenty

### 1. Desktop Sensor (`venom_core/perception/desktop_sensor.py`)
- ✅ Moduł `DesktopSensor` z funkcjami:
  - `get_active_window_title()` - zwraca tytuł aktywnego okna
  - `monitor_clipboard()` - nasłuchuje zmian w schowku
  - `capture_screen_region()` - opcjonalny zrzut ekranu
- ✅ Filtr prywatności (`PrivacyFilter`) z regex dla wrażliwych danych
- ✅ Wsparcie WSL2 z opcją satelity na Windows
- ✅ Async monitoring loop z debouncing

### 2. Shadow Agent (`venom_core/agents/shadow.py`)
- ✅ `ShadowAgent` dziedziczący po `BaseAgent`
- ✅ Pętla decyzyjna:
  - Analiza danych z Desktop Sensor
  - Integracja z `LessonsStore` dla uczenia się
  - Generowanie sugestii z progiem pewności (confidence threshold)
  - System sugestii (ErrorFix, CodeImprovement, TaskUpdate, ContextHelp)
- ✅ Tryb daemon działający w tle
- ✅ Rejestrowanie odrzuconych sugestii dla meta-uczenia

### 3. System Powiadomień (`venom_core/ui/notifier.py`)
- ✅ Moduł `Notifier` z funkcją `send_toast()`
- ✅ Wsparcie dla:
  - Windows 10/11 Toast Notifications (win10toast + PowerShell fallback)
  - Linux notify-send (libnotify)
  - WSL2 bridge do Windows
- ✅ Obsługa akcji przez webhook callback

### 4. Konfiguracja (Ghost Mode)
Dodano do `config.py`:
- ✅ `ENABLE_PROACTIVE_MODE` - przełącznik trybu proaktywnego
- ✅ `ENABLE_DESKTOP_SENSOR` - przełącznik monitorowania pulpitu
- ✅ `SHADOW_CONFIDENCE_THRESHOLD` - próg pewności dla sugestii (0.0-1.0)
- ✅ `SHADOW_PRIVACY_FILTER` - włącz/wyłącz filtr prywatności
- ✅ `SHADOW_CLIPBOARD_MAX_LENGTH` - limit długości tekstu ze schowka
- ✅ `SHADOW_CHECK_INTERVAL` - interwał sprawdzania sensora

### 5. Integracja z Main Application
- ✅ Inicjalizacja komponentów w `main.py` lifespan
- ✅ Połączenie Desktop Sensor → Shadow Agent → Notifier
- ✅ Broadcasting zdarzeń do UI przez WebSocket
- ✅ Graceful shutdown wszystkich komponentów

### 6. API Endpoints
- ✅ `GET /api/v1/shadow/status` - status Shadow Agent i komponentów
- ✅ `POST /api/v1/shadow/reject` - rejestrowanie odrzuconych sugestii

### 7. Testy
- ✅ Testy jednostkowe dla `DesktopSensor` (16 testów)
- ✅ Testy jednostkowe dla `ShadowAgent` (16 testów)
- ✅ Testy jednostkowe dla `Notifier` (10 testów)
- ✅ Wszystkie testy przechodzą

### 8. Jakość kodu
- ✅ Ruff linting i formatting
- ✅ Dokumentacja w docstringach
- ✅ Type hints

## Kryteria akceptacji

### ✅ Scenariusz "Szybka Naprawa"
- Kopiujesz do schowka fragment kodu z błędem składni
- Desktop Sensor wykrywa zmianę i przekazuje do Shadow Agent
- Shadow Agent analizuje błąd (wykrywanie przez regex traceback)
- Notifier wysyła powiadomienie toast z sugestią

### ✅ Świadomość Kontekstu
- Desktop Sensor wykrywa zmianę aktywnego okna
- Shadow Agent sprawdza czy użytkownik czyta dokumentację
- Może zasugerować kontekstową pomoc

### ✅ Nieinwazyjność
- Shadow Agent działa tylko gdy `ENABLE_PROACTIVE_MODE=True`
- Sugestie generowane tylko powyżej progu pewności (default 0.8)
- Odrzucone sugestie zapisywane do `LessonsStore` dla uczenia się
- Filtr prywatności blokuje wrażliwe dane (hasła, karty, API keys)

## Zależności
- `pyperclip` - clipboard access
- `win10toast` - Windows notifications (opcjonalne)
- `semantic-kernel` - LLM integration
- `loguru` - logging

## Uwagi techniczne

### WSL2 Support
- Desktop Sensor wykrywa WSL2 automatycznie
- Funkcje okien i powiadomień mogą wymagać satelity na Windows
- Clipboard działa przez `pyperclip` który używa native Windows API w WSL2

### Privacy Filter
Blokuje regex patterns:
- Numery kart kredytowych
- Hasła (password:, hasło:, pwd:)
- API keys i tokeny
- Adresy email (opcjonalnie)
- Klucze prywatne (PEM)

### Sugestie AI
Shadow Agent używa prostych heurystyk + LLM:
1. Regex detection dla błędów i kodu
2. Keyword matching dla dokumentacji
3. LLM analysis dla złożonych przypadków (TODO - wymaga działającego LLM)

## Możliwe rozszerzenia (TODO)
- [ ] Integracja z `Executive` dla automatycznej aktualizacji zadań
- [ ] OCR z `Eyes` dla analizy screenshots
- [ ] Głębsza integracja z `GoalStore`
- [ ] Dashboard UI dla Ghost Mode (przełącznik, lista sugestii)
- [ ] Satelita dla WSL2 (Python script na Windows)
- [ ] Więcej typów sugestii (DocumentationNeeded, TestCoverage, SecurityIssue)

## Pliki zmienione
- `venom_core/perception/desktop_sensor.py` (NOWY)
- `venom_core/agents/shadow.py` (NOWY)
- `venom_core/ui/notifier.py` (NOWY)
- `venom_core/config.py` (ZMIENIONY - dodano Shadow config)
- `venom_core/main.py` (ZMIENIONY - integracja Shadow Agent)
- `requirements.txt` (ZMIENIONY - dodano pyperclip, win10toast)
- `tests/test_desktop_sensor.py` (NOWY)
- `tests/test_shadow_agent.py` (NOWY)
- `tests/test_notifier.py` (NOWY)
