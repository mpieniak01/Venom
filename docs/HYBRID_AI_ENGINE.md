# Hybrid AI Engine - Dokumentacja

## Przegląd

Hybrydowy Silnik AI (Hybrid AI Engine) to kluczowy komponent systemu Venom, który zarządza inteligentnym routingiem zapytań między lokalnym LLM a chmurą. System priorytetyzuje prywatność i zerowy koszt operacyjny poprzez strategię "Local First".

## Architektura

### Komponenty

1. **HybridModelRouter** (`venom_core/execution/model_router.py`)
   - Główna logika routingu zapytań
   - Zarządzanie trybami pracy (LOCAL/HYBRID/CLOUD)
   - Wykrywanie wrażliwych danych

2. **KernelBuilder** (`venom_core/execution/kernel_builder.py`)
   - Budowanie Semantic Kernel z odpowiednimi konektorami
   - Obsługa Local LLM (Ollama/vLLM)
   - Obsługa Google Gemini
   - Obsługa OpenAI
   - Stub dla Azure OpenAI

3. **Konfiguracja** (`venom_core/config.py`)
   - Parametry trybu AI
   - Klucze API
   - Ustawienia modeli

## Tryby Pracy

### LOCAL (Domyślny)
```env
AI_MODE=LOCAL
```
- **Wszystkie** zapytania kierowane do lokalnego LLM
- Chmura **całkowicie zablokowana**
- 100% prywatności, $0 kosztów
- Idealne dla pracy offline

### HYBRID (Inteligentny)
```env
AI_MODE=HYBRID
GOOGLE_API_KEY=your_key_here
```
- Proste zadania → Local LLM
- Złożone zadania → Cloud (Gemini/OpenAI)
- Wrażliwe dane → **ZAWSZE Local**
- Fallback do Local jeśli brak dostępu do chmury

### CLOUD
```env
AI_MODE=CLOUD
GOOGLE_API_KEY=your_key_here
```
- Wszystkie zapytania (oprócz wrażliwych) → Cloud
- Wrażliwe dane → **ZAWSZE Local**

## Routing Zadań

### TaskType

| Typ Zadania | LOCAL Mode | HYBRID Mode | CLOUD Mode |
|-------------|------------|-------------|------------|
| `STANDARD` | Local | Local | Cloud |
| `CHAT` | Local | Local | Cloud |
| `CODING_SIMPLE` | Local | Local | Cloud |
| `CODING_COMPLEX` | Local | Cloud* | Cloud |
| `SENSITIVE` | Local | Local | Local |
| `ANALYSIS` | Local | Cloud* | Cloud |
| `GENERATION` | Local | Cloud* | Cloud |

\* = Jeśli dostępny klucz API, w przeciwnym razie fallback do Local

## Ochrona Prywatności

### Hard Block dla Wrażliwych Danych

System automatycznie wykrywa wrażliwe treści i **nigdy** nie wysyła ich do chmury:

```python
# Wykrywane słowa kluczowe:
- password, hasło
- token, klucz, key
- secret
- api_key, apikey
- credentials, uwierzytelnienie
```

### Flaga SENSITIVE_DATA_LOCAL_ONLY

```env
SENSITIVE_DATA_LOCAL_ONLY=True  # Domyślnie włączone
```

Gdy włączona, **wszystkie** zapytania są skanowane pod kątem wrażliwych treści, niezależnie od TaskType.

## Konfiguracja

### Minimalna (Local Only - $0)

```env
AI_MODE=LOCAL
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=llama3
```

### Hybrydowa z Google Gemini

```env
AI_MODE=HYBRID
GOOGLE_API_KEY=your_google_api_key
HYBRID_CLOUD_PROVIDER=google
HYBRID_LOCAL_MODEL=llama3
HYBRID_CLOUD_MODEL=gemini-1.5-pro
```

### Hybrydowa z OpenAI

```env
AI_MODE=HYBRID
OPENAI_API_KEY=your_openai_api_key
HYBRID_CLOUD_PROVIDER=openai
HYBRID_LOCAL_MODEL=llama3
HYBRID_CLOUD_MODEL=gpt-4o
```

## Użycie w Kodzie

### ApprenticeAgent (Przykład Integracji)

```python
from venom_core.execution.model_router import HybridModelRouter, TaskType

# Inicjalizacja
router = HybridModelRouter()

# Proste zapytanie (local)
response, routing_info = await router.process(
    prompt="Hello, how are you?",
    task_type=TaskType.CHAT
)

# Złożone zadanie (może iść do chmury w trybie HYBRID)
response, routing_info = await router.process(
    prompt="Analyze architecture of 10 microservices...",
    task_type=TaskType.CODING_COMPLEX
)

# Wrażliwe dane (ZAWSZE local)
response, routing_info = await router.process(
    prompt="Store password: secret123",
    task_type=TaskType.SENSITIVE
)

print(f"Used model: {routing_info['provider']} ({routing_info['model_name']})")
```

### Sprawdzenie Routingu bez Wykonania

```python
router = HybridModelRouter()

# Pobierz info o routingu
info = router.get_routing_info_for_task(
    task_type=TaskType.CODING_COMPLEX,
    prompt="Complex task..."
)

print(f"Would route to: {info['target']}")  # 'local' lub 'cloud'
print(f"Reason: {info['reason']}")
```

## Testy

Pełny zestaw testów znajduje się w `tests/test_hybrid_model_router.py`:

```bash
# Uruchom testy
pytest tests/test_hybrid_model_router.py -v

# Wynik: 18 passed
```

## Kryteria Akceptacji (DoD)

- ✅ **Offline Test**: System działa po odłączeniu internetu (z Ollama)
- ✅ **Cloud Test**: Zadania CODING_COMPLEX trafiają do Gemini w trybie HYBRID (z kluczem)
- ✅ **Audit Pass**: Brak NotImplementedError w sekcji Azure
- ✅ **Privacy**: Zadania SENSITIVE nigdy nie wychodzą poza localhost
- ✅ **Tests**: 18/18 testów przechodzi
- ✅ **Security**: 0 alertów CodeQL

## Przykładowe Scenariusze

### Scenario 1: Developer bez Internetu
```env
AI_MODE=LOCAL
```
→ Wszystko działa lokalnie, zerowe koszty, pełna prywatność

### Scenario 2: Złożony Projekt w Firmie
```env
AI_MODE=HYBRID
GOOGLE_API_KEY=company_key
SENSITIVE_DATA_LOCAL_ONLY=True
```
→ Proste zadania local, złożone przez Gemini, wrażliwe dane NIGDY nie wychodzą

### Scenario 3: Praca na Serwerze Cloud
```env
AI_MODE=CLOUD
OPENAI_API_KEY=server_key
```
→ Wszystko przez OpenAI (oprócz SENSITIVE), maksymalna moc

## Rozszerzanie

### Dodanie Nowego Providera

1. Dodaj connector w `kernel_builder.py`
2. Rozszerz `_register_service()` o nowy typ
3. Dodaj konfigurację w `config.py`
4. Zaktualizuj `_has_cloud_access()` w `model_router.py`

### Dodanie Nowego TaskType

1. Rozszerz enum `TaskType` w `model_router.py`
2. Zaktualizuj logikę w `_hybrid_route()`
3. Dodaj testy w `test_hybrid_model_router.py`

## Troubleshooting

### "No module named google.generativeai"
```bash
pip install google-generativeai
```

### "GOOGLE_API_KEY jest wymagany"
Ustaw w `.env`:
```env
GOOGLE_API_KEY=your_key_here
```

### Wszystko idzie do chmury mimo trybu LOCAL
Sprawdź:
```python
from venom_core.config import SETTINGS
print(SETTINGS.AI_MODE)  # Powinno być "LOCAL"
```

## Bezpieczeństwo

- ✅ Wrażliwe dane nigdy nie trafiają do chmury
- ✅ Klucze API w `.env` (nie commitowane)
- ✅ Scanning wrażliwych treści przed routingiem
- ✅ CodeQL: 0 vulnerabilities
- ✅ Hard block dla TaskType.SENSITIVE

## Performance

- Local LLM: ~100ms/token (Ollama na CPU)
- Google Gemini: ~50ms/token (API)
- OpenAI GPT-4o: ~30ms/token (API)

**Zalecenie**: Używaj HYBRID dla balansu szybkości i prywatności.

## Licencja

Część projektu Venom - patrz główny LICENSE
