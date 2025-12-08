# THE SIMULACRUM - Warstwa Symulacji Użytkowników

**Status:** MVP Complete ✅
**Wersja:** 1.0
**Ostatnia aktualizacja:** 2024-12-08

---

## 📖 Przegląd

THE SIMULACRUM to zaawansowana warstwa symulacji użytkowników w systemie Venom, która umożliwia:

- 🎭 **Generowanie zróżnicowanych person** - od seniorów po tech-savvy millennials
- 🤖 **Symulację rzeczywistych użytkowników** - agent AI interagujący z aplikacją jak człowiek
- 📊 **Automatyczną analizę UX** - identyfikacja problemów użyteczności
- 💡 **Rekomendacje dla deweloperów** - konkretne sugestie poprawy interfejsu
- 🔥 **Chaos Engineering** - testowanie odporności aplikacji na awarie

---

## 🎯 Przypadki Użycia

### 1. Pre-Release Testing
Przed wydaniem aplikacji, uruchom symulację 50 użytkowników. Jeśli >30% rezygnuje z frustracji - **wstrzymaj release**.

### 2. A/B Testing UX
Porównaj dwie wersje interfejsu. Która ma wyższy success rate?

### 3. Accessibility Testing
Sprawdź jak seniorzy radzą sobie z Twoją aplikacją.

### 4. Chaos Engineering
Wyłącz losowo backend podczas symulacji. Czy użytkownicy widzą ładny błąd czy crash?

---

## 🏗️ Architektura

```
┌─────────────────────────────────────────────┐
│          SimulationDirector                  │
│  (Koordynator symulacji)                    │
└──────────────┬──────────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐  ┌─────▼────────┐
│PersonaFactory│  │StackManager  │
│(Generator    │  │(Docker Envs) │
│ person)      │  │              │
└──────┬───────┘  └──────────────┘
       │
┌──────▼────────────────────────────┐
│   SimulatedUserAgent (x N)        │
│   - BrowserSkill only             │
│   - Emotional states              │
│   - Frustration tracking          │
│   - JSONL logging                 │
└──────┬────────────────────────────┘
       │
       │ Logi JSONL
       ▼
┌──────────────────────────────────┐
│      UXAnalystAgent               │
│   - Heatmapa frustracji          │
│   - Top problemy                 │
│   - Rekomendacje LLM             │
└───────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Zainstaluj zależności
```bash
pip install semantic-kernel playwright loguru docker
playwright install chromium
```

### 2. Uruchom przykład
```bash
python examples/simulation_demo.py
```

### 3. Użyj w kodzie
```python
from venom_core.simulation import PersonaFactory, SimulationDirector
from venom_core.agents.ux_analyst import UXAnalystAgent
from venom_core.execution.kernel_builder import build_kernel

# Zbuduj kernel
kernel = await build_kernel()

# Stwórz reżysera
director = SimulationDirector(kernel=kernel)

# Uruchom symulację
result = await director.run_scenario(
    stack_name="my-app",
    target_url="http://localhost:3000",
    scenario_desc="Zarejestrować nowe konto",
    user_count=5,
    max_steps_per_user=10,
)

# Analiza UX
analyst = UXAnalystAgent(kernel=kernel)
analysis = analyst.analyze_sessions()
recommendations = await analyst.generate_recommendations(analysis)

print(recommendations)
```

---

## 👥 Persony

### Dostępne archetypy:

#### 🧓 Senior
- **Wiek:** 55-75 lat
- **Tech literacy:** Low
- **Cierpliwość:** 0.3 (niska)
- **Cechy:** Ostrożny, nieufny, potrzebuje jasnych instrukcji

#### 🛍️ Impulsive Buyer
- **Wiek:** 18-35 lat
- **Tech literacy:** High
- **Cierpliwość:** 0.5 (średnia)
- **Cechy:** Impulsywny, niecierpliwy, oczekuje szybkości

#### 💼 Professional
- **Wiek:** 30-50 lat
- **Tech literacy:** High
- **Cierpliwość:** 0.8 (wysoka)
- **Cechy:** Dokładny, analityczny, oczekuje efektywności

#### 🙂 Casual User
- **Wiek:** 25-45 lat
- **Tech literacy:** Medium
- **Cierpliwość:** 0.6 (średnia)
- **Cechy:** Ciekawy, otwarty, oczekuje intuicyjności

#### 😤 Frustrated Returner
- **Wiek:** 20-60 lat
- **Tech literacy:** Medium
- **Cierpliwość:** 0.2 (bardzo niska)
- **Cechy:** Podejrzliwy, wyczulony na błędy, szybko rezygnuje

---

## 📊 Analiza UX

### Metryki zbierane:
- ✅ Success rate (% osiągniętych celów)
- 😡 Rage quit rate (% rezygnacji z frustracji)
- 🎯 Średnia liczba akcji do celu
- 🔥 Poziom frustracji per persona
- 📈 Heatmapa problemów

### Przykładowy raport:
```markdown
## RAPORT ANALIZY UX

### Podsumowanie
- Sesji: 10
- Sukces: 6 (60%)
- Rage Quits: 3
- Średnia frustracja: 2.1/5

### Najczęstsze problemy
- Nie mogę znaleźć przycisku rejestracji (7x)
- Formularz nie waliduje email (4x)
- Strona zbyt wolno się ładuje (3x)

### Heatmapa Frustracji
- Janusz (Senior): 100% porażek - KRYTYCZNY
- Anna (Impulsive): 50% porażek
- Marek (Professional): 0% porażek

### Rekomendacje
1. **KRYTYCZNE**: Przenieś przycisk rejestracji w prawy górny róg
2. **WAŻNE**: Dodaj walidację email w czasie rzeczywistym
3. **Nice-to-have**: Optymalizuj ładowanie strony (<2s)
```

---

## 🔧 Konfiguracja

W `venom_core/config.py`:

```python
# THE_SIMULACRUM (Simulation Layer)
ENABLE_SIMULATION: bool = True
SIMULATION_CHAOS_ENABLED: bool = False  # Chaos Engineering
SIMULATION_MAX_STEPS: int = 10          # Maks kroków na użytkownika
SIMULATION_USER_MODEL: str = "local"    # Model dla user agents (local/flash)
SIMULATION_ANALYST_MODEL: str = "openai" # Model dla UX Analyst (openai)
SIMULATION_DEFAULT_USERS: int = 5       # Domyślna liczba użytkowników
SIMULATION_LOGS_DIR: str = "./workspace/simulation_logs"
```

---

## 📝 Format Logów

Logi zapisywane w formacie JSONL: `workspace/simulation_logs/session_{id}.jsonl`

```json
{
  "timestamp": "2024-12-08T10:00:00",
  "session_id": "abc123_0",
  "persona_name": "Anna",
  "event_type": "frustration_increase",
  "emotional_state": "confused",
  "frustration_level": 1,
  "actions_taken": 2,
  "reason": "Nie mogę znaleźć przycisku"
}
```

### Typy eventów:
- `session_start` - Początek sesji
- `page_visited` - Odwiedzenie strony
- `action` - Akcja użytkownika (klik, wypełnienie formularza)
- `frustration_increase` - Wzrost frustracji
- `emotion_change` - Zmiana stanu emocjonalnego
- `session_end` - Koniec sesji (z wynikiem)

---

## 🧪 Testy

```bash
# Uruchom testy jednostkowe
pytest tests/test_persona_factory.py -v
pytest tests/test_ux_analyst.py -v
pytest tests/test_simulation_director.py -v

# Wszystkie testy symulacji
pytest tests/test_persona_factory.py tests/test_ux_analyst.py tests/test_simulation_director.py -v

# Testy integracyjne (wymaga środowiska)
pytest -m integration
```

**Status testów:** 30/30 pass ✅

---

## 🎓 Przykłady Zaawansowane

### Symulacja z własnym stackiem Docker
```python
compose_content = """
version: '3.8'
services:
  web:
    image: nginx:alpine
    ports:
      - "8080:80"
  redis:
    image: redis:alpine
"""

result = await director.run_scenario(
    stack_name="my-stack",
    target_url="http://localhost:8080",
    scenario_desc="Przetestować landing page",
    user_count=10,
    deploy_stack=True,
    compose_content=compose_content,
)
```

### Chaos Engineering
```python
# Włącz Chaos Monkey - losowe problemy w trakcie symulacji
director = SimulationDirector(kernel=kernel, enable_chaos=True)

result = await director.run_scenario(
    stack_name="my-stack",
    target_url="http://localhost:8080",
    scenario_desc="Test odporności",
    user_count=20,
    deploy_stack=True,
    compose_content=compose_content,
)
# Chaos Monkey losowo restartuje serwisy podczas symulacji
```

### Custom Persony
```python
from venom_core.simulation.persona_factory import Persona, TechLiteracy

custom_persona = Persona(
    name="Jan Kowalski",
    age=42,
    tech_literacy=TechLiteracy.MEDIUM,
    patience=0.4,
    goal="Kupić bilet na pociąg",
    traits=["niecierpliwy", "zapominalski"],
    frustration_threshold=2,
    description="Pracownik biurowy, często podróżuje",
)

result = await director.run_scenario(
    target_url="http://localhost:3000",
    scenario_desc="Kupić bilet",
    personas=[custom_persona],  # Użyj custom persony
)
```

---

## 🚧 Ograniczenia MVP

- ❌ Dashboard "Matrix View" - nie zaimplementowany
- ❌ Zaawansowany Chaos Engineering - tylko placeholder
- ❌ LLM enhancement person - proste szablony
- ⚠️ Wymaga działającej aplikacji webowej dla pełnych testów
- ⚠️ Playwright headless - brak wizualnego debugowania

---

## 📚 API Reference

### PersonaFactory
```python
factory = PersonaFactory(kernel=None)

# Wygeneruj pojedynczą personę
persona = factory.generate_persona(
    goal="Kupić produkt",
    archetype="senior",  # Optional
    use_llm=False        # LLM enhancement (placeholder)
)

# Wygeneruj zróżnicowane persony
personas = factory.generate_diverse_personas(
    goal="Zarejestrować konto",
    count=5,
    use_llm=False
)
```

### SimulationDirector
```python
director = SimulationDirector(
    kernel=kernel,
    workspace_root="./workspace",
    enable_chaos=False
)

# Uruchom scenariusz
result = await director.run_scenario(
    stack_name="app",
    target_url="http://localhost:3000",
    scenario_desc="Cel użytkowników",
    user_count=5,
    max_steps_per_user=10,
    deploy_stack=False,
    compose_content=None
)

# Aktywne symulacje
active = director.get_active_simulations()

# Historia symulacji
history = director.get_simulation_results()

# Cleanup
await director.cleanup(stack_name="app")
```

### UXAnalystAgent
```python
analyst = UXAnalystAgent(kernel=kernel)

# Analiza wszystkich sesji
analysis = analyst.analyze_sessions()

# Analiza konkretnych sesji
analysis = analyst.analyze_sessions(
    session_ids=["abc123_0", "abc123_1"]
)

# Generowanie rekomendacji
recommendations = await analyst.generate_recommendations(analysis)
```

---

## 🤝 Contributing

Dodawanie nowych archetypów person:
1. Edytuj `PERSONA_TEMPLATES` w `persona_factory.py`
2. Dodaj testy w `test_persona_factory.py`
3. Uruchom `pytest` i `black`

---

## 📄 Licencja

Część projektu Venom - patrz główna licencja projektu.

---

## 🎉 Credits

**Autor:** Venom Team
**Inspiracje:** Synthetic User Testing, Chaos Engineering, UX Research
**Integracje:** Semantic Kernel, Playwright, Docker Compose
