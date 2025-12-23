# Global Cost Guard - Dokumentacja

## Przegląd

**Global Cost Guard** to mechanizm bezpieczeństwa finansowego w systemie Venom, który chroni przed niekontrolowanymi kosztami API. System domyślnie działa w trybie **Eco (Local-Only)**, fizycznie blokując dostęp do płatnych API (OpenAI, Google Gemini). Użytkownik musi świadomie włączyć tryb **Pro (Paid)** aby uzyskać dostęp do modeli chmurowych.

## Funkcje

### 1. Safety Reset (Bezpieczny Start)
- System **zawsze** startuje w trybie Eco
- Stan `paid_mode_enabled` **nie jest persystowany** do pliku
- Restart aplikacji resetuje tryb do Eco
- Uniemożliwia przypadkowe pozostawienie włączonego "licznika"

### 2. Fizyczna Bramka (Cost Gate)
- Model Router sprawdza stan `paid_mode_enabled` przed każdym zapytaniem do chmury
- Jeśli tryb płatny wyłączony: automatyczny fallback do modelu lokalnego
- Logowanie każdej blokady w logach systemowych
- Zero wycieków zapytań do płatnych API

### 3. Transparentność (Model Attribution)
- Każda odpowiedź systemu oznaczona informacją o użytym modelu
- Wizualne odróżnienie: 🤖 dla lokalnych, ⚡ dla płatnych
- Badge przy każdej wiadomości: zielony (free) / fioletowy (paid)
- Użytkownik widzi w czasie rzeczywistym, za co płaci

## Tryby Pracy

### Eco Mode (Domyślny) 🌿
- **Status**: Tylko lokalne modele (Llama, Phi-3)
- **Koszt**: $0.00
- **Ikona**: Zielona plakietka
- **Zachowanie**: Wszystkie zapytania kierowane do lokalnego LLM

### Pro Mode (Opcjonalny) 💸
- **Status**: Dostęp do modeli chmurowych (GPT-4, Gemini)
- **Koszt**: Według cenika dostawcy
- **Ikona**: Fioletowa plakietka
- **Zachowanie**: Złożone zadania kierowane do chmury (w trybie HYBRID)

## Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                      Venom Dashboard                         │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Header: [🌿 Eco Mode] ◄─► [💸 Pro Mode]            │    │
│  │          Toggle Switch + Modal Confirmation          │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    API: /api/v1/system/cost-mode            │
│  GET  → Pobiera aktualny stan (enabled: bool)              │
│  POST → Ustawia tryb (enable: bool)                        │
└─────────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      StateManager                            │
│  • paid_mode_enabled: bool = False (ZAWSZE przy starcie)   │
│  • enable_paid_mode() → True                                │
│  • disable_paid_mode() → False                              │
│  • is_paid_mode_enabled() → bool                            │
└─────────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   HybridModelRouter                          │
│  ┌───────────────────────────────────────────────────┐      │
│  │ COST GUARD CHECK:                                 │      │
│  │  if target == "cloud" AND NOT paid_mode_enabled:  │      │
│  │      → FALLBACK TO LOCAL                          │      │
│  │      → LOG WARNING                                │      │
│  └───────────────────────────────────────────────────┘      │
│                                                              │
│  Routing Decision + Metadata:                               │
│  • target: "local" | "cloud"                                │
│  • model_name: "llama3" | "gpt-4o"                         │
│  • provider: "local" | "openai" | "google"                 │
│  • is_paid: bool                                            │
└─────────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Response with Badge                         │
│  [Agent Message] [🤖 Llama 3] ← Free, Local                │
│  [Agent Message] [⚡ GPT-4o]  ← Paid, Cloud                 │
└─────────────────────────────────────────────────────────────┘
```

## Użycie

### Dashboard UI

1. **Sprawdzenie aktualnego trybu**:
   - Patrz na przełącznik w nagłówku
   - 🌿 Eco Mode = Bezpłatny
   - 💸 Pro Mode = Płatny

2. **Włączenie Pro Mode**:
   - Kliknij przełącznik
   - Potwierdź w oknie dialogowym
   - Przeczytaj ostrzeżenie o kosztach
   - Kliknij "Potwierdzam i Akceptuję Koszty"

3. **Wyłączenie Pro Mode**:
   - Kliknij przełącznik
   - Automatyczne wyłączenie bez potwierdzenia

### API Programowe

```python
import requests

# Sprawdź aktualny tryb
response = requests.get("http://localhost:8000/api/v1/system/cost-mode")
print(response.json())
# {"enabled": false, "provider": "hybrid"}

# Włącz Pro Mode
response = requests.post(
    "http://localhost:8000/api/v1/system/cost-mode",
    json={"enable": True}
)
print(response.json())
# {"status": "success", "message": "Paid Mode (Pro) włączony...", "enabled": true}

# Wyłącz Pro Mode
response = requests.post(
    "http://localhost:8000/api/v1/system/cost-mode",
    json={"enable": False}
)
```

### Backend (Python)

```python
from venom_core.core.state_manager import StateManager
from venom_core.execution.model_router import HybridModelRouter, TaskType

# Inicjalizacja
state_manager = StateManager()
router = HybridModelRouter(state_manager=state_manager)

# Domyślnie: Eco Mode (paid_mode_enabled = False)
routing = router.route_task(TaskType.CODING_COMPLEX, "Refaktoryzuj kod")
print(routing["target"])  # "local" - zablokowany dostęp do chmury
print(routing["is_paid"]) # False

# Włącz Pro Mode
state_manager.enable_paid_mode()

# Teraz: dostęp do chmury
routing = router.route_task(TaskType.CODING_COMPLEX, "Refaktoryzuj kod")
print(routing["target"])  # "cloud" - dostęp do GPT-4/Gemini
print(routing["is_paid"]) # True
```

## Przepływ Typowego Użycia

### Scenariusz: Zadanie wymaga modelu chmurowego

1. **Użytkownik wysyła zadanie**: "Przeanalizuj tę architekturę i zaproponuj refaktoryzację"
2. **Router ocenia zadanie**: TaskType.CODING_COMPLEX → normalnie cloud
3. **Cost Guard sprawdza**: `paid_mode_enabled == False` → BLOKADA
4. **Fallback do LOCAL**: Zadanie wykonywane przez Llama 3
5. **UI pokazuje badge**: [🤖 Llama 3 (Local)]
6. **Użytkownik widzi**: To było wykonane lokalnie, zero kosztów

### Scenariusz: Użytkownik włącza Pro Mode

1. **Kliknięcie przełącznika** → Modal z ostrzeżeniem
2. **Potwierdzenie** → POST /api/v1/system/cost-mode (enable: true)
3. **StateManager**: `paid_mode_enabled = True`
4. **Notyfikacja**: "💸 Pro Mode włączony - Cloud API dostępne"
5. **Kolejne zapytania**: Mogą korzystać z GPT-4/Gemini (w HYBRID/CLOUD mode)
6. **UI Badge**: [⚡ GPT-4o] przy odpowiedziach z chmury

## Konfiguracja Trybu AI

Global Cost Guard współpracuje z konfiguracją `AI_MODE`:

### LOCAL Mode
```env
AI_MODE=LOCAL
```
- Wszystkie zadania → local
- Cost Guard nie ma wpływu (cloud i tak zablokowany)

### HYBRID Mode (Zalecany)
```env
AI_MODE=HYBRID
```
- Proste zadania → local (zawsze)
- Złożone zadania → cloud (tylko gdy `paid_mode_enabled == True`)
- Cost Guard aktywny dla złożonych zadań

### CLOUD Mode
```env
AI_MODE=CLOUD
```
- Wszystkie zadania → cloud
- Cost Guard blokuje WSZYSTKIE zapytania gdy `paid_mode_enabled == False`
- ⚠️ Uwaga: W tym trybie wyłączony Cost Guard = brak dostępu do AI

## Wrażliwe Dane (Sensitive Data)

**WAŻNE**: Wrażliwe dane **ZAWSZE** idą do modelu lokalnego, niezależnie od:
- Trybu AI (LOCAL/HYBRID/CLOUD)
- Stanu Cost Guard (Eco/Pro)

```python
# Przykład: hasło w zapytaniu
routing = router.route_task(
    TaskType.SENSITIVE,
    "Wygeneruj skrypt z hasłem: secret123"
)
print(routing["target"])  # "local" - ZAWSZE
print(routing["reason"])  # "Wrażliwe dane - HARD BLOCK..."
```

## Logi i Monitoring

### Logowane Zdarzenia

```
[WARNING] 🔒 COST GUARD: Zablokowano dostęp do Cloud API. Fallback do LOCAL.
[WARNING] 🔓 Paid Mode ENABLED przez API - użytkownik zaakceptował koszty
[INFO] 🔒 Paid Mode DISABLED przez API - tryb Eco aktywny
```

### Metryki Tokenów

Dashboard wyświetla koszt sesji:
```
Session Cost: $0.0000  (Eco Mode)
Session Cost: $0.0234  (Pro Mode - aktywne użycie GPT-4)
```

## Bezpieczeństwo

### Zabezpieczenia Wbudowane

1. **Safety Reset**: Zawsze startuj w Eco Mode
2. **No Persistence**: Stan nie zapisywany na dysku
3. **Explicit Confirmation**: Modal przy włączaniu Pro Mode
4. **Fallback Logic**: Błąd w Cost Guard → local (safe default)
5. **Sensitive Data Lock**: Wrażliwe dane nigdy do chmury

### Best Practices

1. **Wyłącz Pro Mode po użyciu**: Nie pozostawiaj włączonego na noc
2. **Monitoruj koszty**: Regularnie sprawdzaj "Session Cost"
3. **Używaj HYBRID**: Optymalizuje koszty vs. jakość
4. **Oznaczaj wrażliwe**: Używaj TaskType.SENSITIVE dla danych osobowych

## Rozwiązywanie Problemów

### Problem: Nie mogę uzyskać odpowiedzi z GPT-4

**Rozwiązanie**:
1. Sprawdź czy Pro Mode jest włączony (przełącznik w nagłówku)
2. Sprawdź czy masz ustawiony `GOOGLE_API_KEY` lub `OPENAI_API_KEY` w `.env`
3. Sprawdź czy `AI_MODE=HYBRID` lub `CLOUD` w `.env`

### Problem: Cost Guard blokuje mimo włączonego Pro Mode

**Rozwiązanie**:
1. Sprawdź logi: `grep "COST GUARD" logs/venom.log`
2. Restart aplikacji: Pro Mode resetuje się przy restarcie
3. Włącz ponownie przez UI

### Problem: Badge nie pokazuje się przy odpowiedziach

**Rozwiązanie**:
1. Upewnij się że używasz najnowszej wersji frontendu
2. Sprawdź konsolę przeglądarki: F12 → Console
3. Przeładuj stronę: Ctrl+Shift+R (cache clear)

## Integracja z Własnym Kodem

Jeśli tworzysz własnego agenta korzystającego z HybridModelRouter:

```python
from venom_core.core.state_manager import StateManager
from venom_core.execution.model_router import HybridModelRouter

class MyCustomAgent:
    def __init__(self, state_manager: StateManager):
        # Przekaż state_manager do routera
        self.router = HybridModelRouter(state_manager=state_manager)

    async def process_task(self, prompt: str):
        # Routing z Cost Guard
        routing = self.router.route_task(TaskType.STANDARD, prompt)

        # Użyj routing["model_name"], routing["provider"]
        # ...

        # Zwróć odpowiedź z metadanymi
        return {
            "response": "...",
            "metadata": {
                "model_name": routing["model_name"],
                "provider": routing["provider"],
                "is_paid": routing["is_paid"]
            }
        }
```

## FAQ

**Q: Czy Cost Guard wpływa na wydajność?**
A: Nie. Sprawdzenie flagi `paid_mode_enabled` to operacja O(1), praktycznie zerowy overhead.

**Q: Co jeśli zapomnę wyłączyć Pro Mode?**
A: Restart aplikacji automatycznie wyłącza Pro Mode (Safety Reset).

**Q: Czy mogę programowo wymusić użycie Cloud API?**
A: Nie. Cost Guard jest physical gate - nie ma bypassa. Musisz włączyć Pro Mode.

**Q: Jak działa w trybie LOCAL?**
A: W LOCAL mode Cost Guard jest transparentny - cloud i tak jest zablokowany przez AI_MODE.

**Q: Czy Cost Guard chroni przed wszystkimi kosztami?**
A: Tak - blokuje OpenAI, Google Gemini, Azure. Nie blokuje lokalnych modeli (są darmowe).

## Changelog

### v1.4.0 (2024-12-09)
- ✨ Dodano Global Cost Guard
- ✨ Dodano Model Attribution (badges)
- ✨ Dodano Master Switch w UI
- ✨ Dodano API endpoints dla cost mode
- ✨ Dodano Safety Reset mechanism
- 📝 Dokumentacja COST_GUARD.md
- ✅ Testy jednostkowe dla Cost Guard

## Kontakt

W razie pytań lub problemów:
- GitHub Issues: [mpieniak01/Venom/issues](https://github.com/mpieniak01/Venom/issues)
- Dokumentacja: `/docs/`

---

**Venom v1.4 - Global Cost Guard** 🛡️
*Zero Surprise Costs. Maximum Control.*
