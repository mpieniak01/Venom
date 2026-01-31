# Google Search Grounding Integration - Dokumentacja

## Przegląd

Integracja Google Search Grounding pozwala Agentowi Venom na dostęp do informacji z ostatniej chwili (newsy, giełda, dokumentacja), eliminując halucynacje przez wykorzystanie natywnego mechanizmu "Grounding with Google Search" w modelach Gemini 1.5.

**Kluczowe cechy:**
- ✅ Natywna integracja z Google Gemini 1.5 Pro
- ✅ Ściśle powiązana z Global Cost Guard (paid_mode)
- ✅ Automatyczne cytowanie źródeł
- ✅ Wizualne oznaczenia jakości w UI
- ✅ Fallback do DuckDuckGo gdy paid mode wyłączony

## Architektura

### 1. Backend: StateManager - Global Cost Guard

```python
from venom_core.core.state_manager import StateManager

# Inicjalizacja
state_manager = StateManager()

# Włącz tryb płatny (Google Grounding dostępny)
state_manager.set_paid_mode(True)

# Sprawdź status
if state_manager.is_paid_mode_enabled():
    print("Płatne funkcje włączone - Google Grounding dostępny")
```

### 2. Backend: TaskType.RESEARCH

```python
from venom_core.execution.model_router import TaskType

# Nowy typ zadania dla research
task_type = TaskType.RESEARCH
```

### 3. Backend: Model Router

Router automatycznie decyduje o wykorzystaniu Google Grounding vs DuckDuckGo:

```python
from venom_core.execution.model_router import HybridModelRouter, TaskType

router = HybridModelRouter()

# Zadanie research - router wybiera odpowiedni backend
routing = router.route_task(TaskType.RESEARCH, "Aktualna cena Bitcoin")

# W zależności od konfiguracji:
# - paid_mode ON + Google API key -> Google Grounding
# - paid_mode OFF lub brak API key -> DuckDuckGo (WebSearchSkill)
```

Logowanie decyzji:
```
[Router] Research mode: GROUNDING (Paid)  # gdy paid_mode=True
[Router] Research mode: DUCKDUCKGO (Free) # gdy paid_mode=False
```

### 4. Backend: Kernel Builder

```python
from venom_core.execution.kernel_builder import KernelBuilder

builder = KernelBuilder()

# Parametr enable_grounding kontroluje Google Search
kernel = builder._register_service(
    kernel,
    service_type="google",
    model_name="gemini-1.5-pro",
    enable_grounding=True  # Włącz Google Search Grounding
)
```

Konfiguracja z Google Search (gdy biblioteka dostępna):
```python
import google.generativeai as genai

genai.configure(api_key=GOOGLE_API_KEY)

# Włącz grounding
tools = [{"google_search": {}}]
model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    tools=tools
)
```

### 5. Backend: ResearcherAgent

Agent automatycznie formatuje źródła z Google Grounding:

```python
from venom_core.agents.researcher import ResearcherAgent, format_grounding_sources

agent = ResearcherAgent(kernel)

# Process research query
result = await agent.process("Jaka jest aktualna cena Bitcoina?")

# Odpowiedź zawiera sekcję źródeł:
"""
Bitcoin obecnie kosztuje około $43,500 według najnowszych danych [1].

---
📚 Źródła (Google Grounding):
[1] CoinMarketCap - Bitcoin Price - https://coinmarketcap.com/currencies/bitcoin/
[2] Bloomberg - Crypto Markets - https://bloomberg.com/crypto
"""

# Sprawdź źródło wyszukiwania
source = agent.get_last_search_source()
# 'google_grounding' lub 'duckduckgo'
```

### 6. Frontend: UI Badges

Wizualne oznaczenie źródła danych w interfejsie:

```javascript
// Badge 🌍 Google Grounded (niebieski)
// - Wyświetlany gdy użyto Google Search Grounding
// - Kolor: #1e40af (niebieski)

// Badge 🦆 Web Search (szary)
// - Wyświetlany gdy użyto DuckDuckGo
// - Kolor: #6b7280 (szary)
```

## Scenariusze użycia

### Scenariusz 1: Paid Mode OFF (Domyślny)

```python
# Stan początkowy
state_manager.set_paid_mode(False)

# Użytkownik pyta: "Aktualna cena Bitcoina?"
# ↓
# Router: TaskType.RESEARCH → LOCAL + DuckDuckGo
# ↓
# ResearcherAgent używa WebSearchSkill (DuckDuckGo)
# ↓
# Odpowiedź z badge 🦆 Web Search
```

**Logi:**
```
[Router] Research mode: DUCKDUCKGO (Free)
[WebSearchSkill] Szukanie 'aktualna cena bitcoin'...
[ResearcherAgent] Użyto DuckDuckGo
```

### Scenariusz 2: Paid Mode ON

```python
# Włącz paid mode
state_manager.set_paid_mode(True)

# Użytkownik pyta: "Aktualna cena Bitcoina?"
# ↓
# Router: TaskType.RESEARCH → CLOUD + Google Grounding
# ↓
# KernelBuilder: enable_grounding=True
# ↓
# Google Gemini z Google Search Grounding
# ↓
# Odpowiedź z badge 🌍 Google Grounded + cytowania
```

**Logi:**
```
[Router] Research mode: GROUNDING (Paid)
[KernelBuilder] Konfiguracja Google Gemini: model=gemini-1.5-pro, grounding=True
[ResearcherAgent] Dodano źródła z Google Grounding do odpowiedzi
```

### Scenariusz 3: Fallback (Brak API key)

```python
# Paid mode włączony, ale brak Google API key
state_manager.set_paid_mode(True)
# GOOGLE_API_KEY = ""

# ↓
# Router: TaskType.RESEARCH → LOCAL (fallback)
# ↓
# Używa DuckDuckGo mimo włączonego paid_mode
# ↓
# Badge 🦆 Web Search
```

**Logi:**
```
[Router] Research mode: RESEARCH -> LOCAL (DuckDuckGo fallback)
```

## Kryteria Akceptacji (DoD)

✅ **1. Paid Mode OFF → DuckDuckGo**
```python
state_manager.set_paid_mode(False)
# Agent używa DuckDuckGo
# Logs: "[Router] Research mode: DUCKDUCKGO (Free)"
# UI: Badge 🦆 Web Search
```

✅ **2. Paid Mode ON → Google Grounding**
```python
state_manager.set_paid_mode(True)
# Agent używa Google Grounding
# Logs: "[Router] Research mode: GROUNDING (Paid)"
# UI: Badge 🌍 Google Grounded
# Odpowiedź zawiera sekcję "📚 Źródła (Google Grounding)"
```

✅ **3. Formatowanie grounding_metadata**
```python
response_metadata = {
    "grounding_metadata": {
        "grounding_chunks": [
            {"title": "Bitcoin Price", "uri": "https://example.com"}
        ]
    }
}

sources = format_grounding_sources(response_metadata)
# Zwraca sformatowaną sekcję ze źródłami
```

✅ **4. Bezpiecznik kosztowy**
```python
# Próba wymuszenia Google Search gdy paid_mode=False
# → System automatycznie używa DuckDuckGo
# → Brak możliwości obejścia bezpiecznika
```

## Konfiguracja

### Zmienne środowiskowe

```bash
# .env
GOOGLE_API_KEY=your-google-api-key-here
AI_MODE=HYBRID
HYBRID_CLOUD_PROVIDER=google
HYBRID_CLOUD_MODEL=gemini-1.5-pro
```

### Włączanie/wyłączanie paid mode

#### Przez API:
```python
POST /api/v1/settings/paid-mode
{
  "enabled": true
}
```

#### Programowo:
```python
from venom_core.core.state_manager import StateManager

state_manager = StateManager()
state_manager.set_paid_mode(True)
```

## Bezpieczeństwo

### Global Cost Guard

- ✅ Paid mode domyślnie wyłączony (`paid_mode_enabled=False`)
- ✅ Persystencja stanu w `state_dump.json`
- ✅ Brak możliwości obejścia - router wymusza fallback
- ✅ Logowanie wszystkich decyzji routingu

### Limity

- Google Search Grounding działa tylko z `gemini-1.5-pro`
- Wymaga aktywnego klucza Google API
- Koszty Google Search są dodatkowo naliczane przez Google

## Troubleshooting

### Problem: Google Grounding nie działa mimo paid_mode=True

**Sprawdź:**
1. Czy `GOOGLE_API_KEY` jest ustawiony?
2. Czy model to `gemini-1.5-pro`?
3. Czy biblioteka `google-generativeai` jest zainstalowana?

```bash
pip install google-generativeai
```

### Problem: Brak cytowań w odpowiedzi

**Przyczyny:**
- Model nie użył Google Search (zapytanie nie wymagało świeżych danych)
- Brak `grounding_metadata` w odpowiedzi
- ResearcherAgent używa DuckDuckGo (paid_mode=False)

**Sprawdź logi:**
```
[ResearcherAgent] Dodano źródła z Google Grounding do odpowiedzi  # OK
[ResearcherAgent] Użyto DuckDuckGo  # Fallback
```

### Problem: Badge nie wyświetla się w UI

**Sprawdź:**
- Czy metadata zawiera `search_source`?
- Czy WebSocket przekazuje eventData?
- Czy CSS dla `.research-source-badge` jest załadowany?

## Roadmap

### Faza 1: Infrastruktura ✅ (Current)
- [x] StateManager: paid_mode_enabled
- [x] TaskType.RESEARCH
- [x] Router: logika decyzyjna
- [x] KernelBuilder: enable_grounding
- [x] ResearcherAgent: formatowanie źródeł
- [x] Frontend: UI badges

### Faza 2: Full Integration (TODO)
- [ ] Implementacja dedykowanego Google Gemini connectora dla Semantic Kernel
- [ ] WebSocket events z metadata (search_source)
- [ ] API endpoint dla toggle paid_mode
- [ ] Monitoring kosztów Google Search

### Faza 3: Optimization (TODO)
- [ ] Cache wyników Google Search
- [ ] Rate limiting dla Google API
- [ ] Statystyki użycia (Google vs DuckDuckGo)
- [ ] A/B testing jakości odpowiedzi

## Zobacz też

- [Google AI - Grounding with Google Search](https://ai.google.dev/docs/grounding)
- [Semantic Kernel Documentation](https://learn.microsoft.com/en-us/semantic-kernel/)
- [DuckDuckGo Search API](https://duckduckgo.com/api)
