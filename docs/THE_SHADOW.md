# THE SHADOW - Desktop Awareness & Proactive Assistance

## Przegląd

Shadow Agent to system proaktywnej pomocy, który monitoruje aktywność użytkownika (schowek, aktywne okno) i oferuje kontekstową pomoc bez przerywania przepływu pracy. To inteligentny "cień", który obserwuje Twoją pracę i pomaga w kluczowych momentach.

## Architektura

```
┌─────────────────┐
│ Desktop Sensor  │  ← Monitoruje schowek i okna
└────────┬────────┘
         │ Sensor Data
         ↓
┌─────────────────┐
│  Shadow Agent   │  ← Analizuje kontekst, generuje sugestie
└────────┬────────┘
         │ Suggestions
         ↓
┌─────────────────┐
│    Notifier     │  ← Wysyła powiadomienia systemowe
└─────────────────┘
```

## Komponenty

### 1. Desktop Sensor (`venom_core/perception/desktop_sensor.py`)

Monitoruje aktywność pulpitu:
- **Schowek**: Wykrywa zmiany w schowku (pyperclip)
- **Aktywne okno**: Śledzi tytuł aktywnego okna (Windows/Linux)
- **Zrzuty ekranu**: Opcjonalnie robi screenshots (PIL)
- **Privacy Filter**: Blokuje wrażliwe dane (hasła, karty, API keys)

**Features:**
- Async monitoring loop z debouncing (1s)
- Automatyczne wykrywanie WSL2
- Konfigurowalna długość max tekstu (default: 1000 chars)
- Thread-safe callbacks

**Przykład użycia:**
```python
from venom_core.perception.desktop_sensor import DesktopSensor

async def handle_clipboard(data):
    print(f"Clipboard changed: {data['content'][:50]}...")

sensor = DesktopSensor(
    clipboard_callback=handle_clipboard,
    privacy_filter=True
)
await sensor.start()
```

### 2. Shadow Agent (`venom_core/agents/shadow.py`)

Inteligentny agent analizujący kontekst pracy:
- **Wykrywanie błędów**: Regex dla tracebacks, exceptions
- **Analiza kodu**: Heurystyki dla snippetów
- **Kontekst dokumentacji**: Wykrywa czytanie docs
- **Uczenie się**: Zapisuje odrzucone sugestie do LessonsStore

**Typy sugestii:**
- `ERROR_FIX` - Naprawa błędów w kodzie
- `CODE_IMPROVEMENT` - Poprawa jakości kodu
- `TASK_UPDATE` - Aktualizacja statusu zadań
- `CONTEXT_HELP` - Kontekstowa pomoc

**Przykład użycia:**
```python
from venom_core.agents.shadow import ShadowAgent

shadow = ShadowAgent(
    kernel=build_kernel(),
    confidence_threshold=0.8,
    lessons_store=lessons_store
)
await shadow.start()

suggestion = await shadow.analyze_sensor_data({
    "type": "clipboard",
    "content": "Traceback (most recent call last):\n  Error: ...",
    "timestamp": "2024-01-01T00:00:00"
})

if suggestion:
    print(f"Sugestia: {suggestion.title}")
    print(f"Pewność: {suggestion.confidence:.2%}")
```

### 3. Notifier (`venom_core/ui/notifier.py`)

System powiadomień natywnych:
- **Windows**: Toast Notifications (win10toast + PowerShell fallback)
- **Linux**: notify-send (libnotify)
- **WSL2**: Bridge do Windows przez powershell.exe

**Features:**
- Async subprocess execution
- Bezpieczne przekazywanie argumentów (brak command injection)
- Wsparcie dla akcji w powiadomieniach
- Konfigurowalna pilność (low/normal/critical)

**Przykład użycia:**
```python
from venom_core.ui.notifier import Notifier

async def handle_action(payload):
    print(f"User clicked: {payload}")

notifier = Notifier(webhook_handler=handle_action)

await notifier.send_toast(
    title="Błąd wykryty",
    message="Znalazłem błąd w Twoim kodzie",
    action_payload={"type": "error_fix", "code": "..."}
)
```

## Konfiguracja

W pliku `.env`:

```env
# Włącz Shadow Agent
ENABLE_PROACTIVE_MODE=True
ENABLE_DESKTOP_SENSOR=True

# Próg pewności dla sugestii (0.0-1.0)
SHADOW_CONFIDENCE_THRESHOLD=0.8

# Filtr prywatności
SHADOW_PRIVACY_FILTER=True

# Maks. długość tekstu ze schowka
SHADOW_CLIPBOARD_MAX_LENGTH=1000

# Interwał sprawdzania (sekundy)
SHADOW_CHECK_INTERVAL=1
```

## API Endpoints

### GET /api/v1/shadow/status
Zwraca status Shadow Agent i komponentów.

**Response:**
```json
{
  "status": "success",
  "shadow": {
    "shadow_agent": {
      "is_running": true,
      "confidence_threshold": 0.8,
      "queued_suggestions": 0,
      "rejected_count": 2
    },
    "desktop_sensor": {
      "is_running": true,
      "system": "Linux",
      "is_wsl": false,
      "privacy_filter": true
    },
    "notifier": {
      "system": "Linux",
      "is_wsl": false,
      "webhook_handler_set": true
    },
    "config": {
      "confidence_threshold": 0.8,
      "privacy_filter": true,
      "desktop_sensor_enabled": true
    }
  }
}
```

### POST /api/v1/shadow/reject
Rejestruje odrzuconą sugestię dla uczenia się.

**Body:**
```json
{
  "suggestion_type": "error_fix"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Odrzucona sugestia typu 'error_fix' zarejestrowana"
}
```

## Privacy & Security

### Privacy Filter
Blokuje następujące typy danych:
- 💳 Numery kart kredytowych (`\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}`)
- 📧 Adresy email (opcjonalnie)
- 🔑 Hasła (`password:`, `hasło:`, `pwd:`)
- 🔐 API keys i tokeny
- 🌐 Adresy IP (opcjonalnie)
- 🔒 Klucze prywatne (PEM format)

### Security Features
- ✅ Brak command injection (subprocess z argument list)
- ✅ Regex validation dla wrażliwych danych
- ✅ Konfigurowalna max długość tekstu
- ✅ CodeQL security check passed (0 alerts)

## Workflow - Przykładowy scenariusz

1. **Użytkownik kopiuje błąd do schowka:**
   ```python
   Traceback (most recent call last):
     File "main.py", line 10
       result = 10 / 0
   ZeroDivisionError: division by zero
   ```

2. **Desktop Sensor wykrywa zmianę:**
   - Privacy Filter sprawdza czy nie ma wrażliwych danych
   - Przekazuje do Shadow Agent

3. **Shadow Agent analizuje:**
   - Regex wykrywa `ZeroDivisionError`
   - Generuje sugestię typu `ERROR_FIX`
   - Pewność: 85% (> threshold 80%)

4. **Notifier wysyła powiadomienie:**
   ```
   ┌────────────────────────────────────┐
   │ 🔍 Venom                           │
   │                                    │
   │ Wykryto błąd w schowku             │
   │ Znalazłem błąd w skopiowanym       │
   │ kodzie. Czy chcesz, abym go        │
   │ przeanalizował?                    │
   │                                    │
   │ [Analizuj] [Odrzuć]                │
   └────────────────────────────────────┘
   ```

5. **Użytkownik klika [Odrzuć]:**
   - Shadow Agent zapisuje odrzucenie do LessonsStore
   - W przyszłości podobne sugestie będą rzadsze

## WSL2 Support

Shadow Agent działa w WSL2, ale z ograniczeniami:
- ✅ **Clipboard**: Działa przez pyperclip (native Windows API)
- ⚠️ **Window tracking**: Wymaga satelity na Windows
- ⚠️ **Notifications**: Wymaga bridge przez powershell.exe

### Opcjonalny satelita dla WSL2
Dla pełnej funkcjonalności w WSL2, uruchom `venom_satellite.py` na Windows:
```python
# venom_satellite.py (uruchom na Windows)
# Monitoruje okna i wysyła dane do Venom w WSL przez HTTP

import requests
import win32gui

while True:
    window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
    requests.post("http://localhost:8000/api/v1/shadow/window", 
                  json={"title": window_title})
    time.sleep(1)
```

## Demo

Uruchom demo aby zobaczyć Shadow Agent w akcji:
```bash
cd /home/runner/work/Venom/Venom
PYTHONPATH=/home/runner/work/Venom/Venom python examples/shadow_demo.py
```

Demo pokazuje:
- Privacy Filter w akcji
- Wykrywanie błędów w kodzie
- Generowanie sugestii z różnymi typami
- Status wszystkich komponentów

## Testy

Uruchom testy:
```bash
pytest tests/test_desktop_sensor.py tests/test_shadow_agent.py tests/test_notifier.py -v
```

**Test Coverage:**
- 16 testów Desktop Sensor
- 16 testów Shadow Agent
- 10 testów Notifier
- **42 testy total - wszystkie ✅**

## Roadmap

### Planned Features
- [ ] Integracja z Eyes dla OCR z screenshots
- [ ] Głębsza integracja z GoalStore (auto task updates)
- [ ] Więcej typów sugestii (DocumentationNeeded, TestCoverage)
- [ ] Dashboard UI dla Ghost Mode
- [ ] Satelita WSL2 (Python service na Windows)
- [ ] Machine Learning dla lepszego confidence scoring
- [ ] Context window ze historią aktywności

### Known Limitations
- Shadow Agent używa prostych heurystyk + LLM (może dawać false positives)
- Windows Toast wymaga win10toast lub PowerShell
- WSL2 wymaga bridge/satelity dla pełnej funkcjonalności
- Credit card detection może dawać false positives (brak Luhn validation)

## Contributing

Zgłaszaj issues i PRy na GitHub:
- Bug reports: Issues z tagiem `shadow-agent`
- Feature requests: Issues z tagiem `enhancement`
- Security issues: Prywatne security advisories

## License

Część projektu Venom - patrz główny README.md

---

**Status:** ✅ Production Ready  
**Last Updated:** 2025-12-08  
**Version:** 1.0.0
