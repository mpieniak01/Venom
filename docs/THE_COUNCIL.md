# The Council - AutoGen Swarm Intelligence

## Przegląd

The Council to system inteligencji rojowej (Swarm Intelligence) oparty na bibliotece AutoGen, który pozwala agentom Venom współpracować autonomicznie poprzez rozmowę zamiast ręcznej orkiestracji.

## Architektura

### Główne komponenty:

1. **VenomAgent (swarm.py)** - Wrapper łączący agenty Semantic Kernel z AutoGen ConversableAgent
2. **CouncilConfig (council.py)** - Konfiguracja Group Chat i uczestników
3. **CouncilSession (council.py)** - Sesja rozmowy między agentami
4. **Orchestrator** - Logika decyzyjna: Council vs standardowy flow

### Uczestnicy Council:

- **User** (UserProxy) - Reprezentuje użytkownika, zleca zadanie
- **Architect** - Planuje strukturę i kolejność działań
- **Coder** - Pisze kod, tworzy pliki
- **Critic** - Sprawdza jakość i bezpieczeństwo kodu
- **Guardian** - Weryfikuje testy, zatwierdza finalną wersję

### Graf przepływu rozmowy:

```
User → Architect → Coder ↔ Critic
                    ↓
                Guardian → User (TERMINATE)
```

## Jak to działa?

### 1. Automatyczna decyzja

Orchestrator decyduje automatycznie czy użyć Council na podstawie:

- **Intencja COMPLEX_PLANNING** - zawsze używa Council
- **Długość zadania** > 100 znaków + obecność słów kluczowych:
  - "projekt", "aplikacja", "system"
  - "stwórz grę", "zbuduj"
  - "zaprojektuj", "zaimplementuj"
  - "kompletny", "cała aplikacja"

### 2. Proces rozmowy

```python
# Przykład zadania wymagającego Council:
task = "Napisz grę w węża w Pythonie z GUI używając pygame"

# Przebieg rozmowy:
# 1. User zleca zadanie
# 2. Architect planuje strukturę (main loop, grafika, logika)
# 3. Coder pisze kod
# 4. Critic sprawdza kod, wskazuje błędy
# 5. Coder poprawia (pętla 3-4 powtarza się)
# 6. Guardian uruchamia testy
# 7. Jeśli testy OK: Guardian mówi "TERMINATE"
```

### 3. Streaming do WebSocket

Wszystkie wiadomości z rozmowy są streamowane do klientów przez WebSocket:

```javascript
// Nowe typy zdarzeń:
// - COUNCIL_STARTED
// - COUNCIL_MEMBERS
// - COUNCIL_COMPLETED
// - COUNCIL_ERROR
// - COUNCIL_AGENT_SPEAKING (TODO: dodać w przyszłości)
```

## Konfiguracja

### Local-First LLM

The Council domyślnie używa lokalnego modelu (Ollama):

```python
from venom_core.core.council import create_local_llm_config

# Domyślna konfiguracja
llm_config = create_local_llm_config()
# {
#   "config_list": [{
#     "model": "llama3",
#     "base_url": "http://localhost:11434/v1",
#     "api_key": "EMPTY"
#   }],
#   "temperature": 0.7
# }

# Niestandardowa konfiguracja
llm_config = create_local_llm_config(
    base_url="http://localhost:8080/v1",
    model="mixtral",
    temperature=0.5
)
```

### Włączanie/wyłączanie Council

W `orchestrator.py`:

```python
ENABLE_COUNCIL_MODE = True  # Ustaw False aby wyłączyć
COUNCIL_TASK_THRESHOLD = 100  # Minimalna długość zadania

# Edytuj słowa kluczowe
COUNCIL_COLLABORATION_KEYWORDS = [
    "projekt", "aplikacja", ...
]
```

## Przykłady użycia

### Przykład 1: Proste zadanie (używa standardowego flow)

```python
request = TaskRequest(content="Napisz funkcję hello world")
# → Orchestrator użyje CoderAgent bezpośrednio
```

### Przykład 2: Złożone zadanie (używa Council)

```python
request = TaskRequest(content="""
Stwórz kompletną aplikację TODO list w Pythonie z:
- FastAPI backend z REST API
- Bazą danych SQLite
- Prostym HTML/CSS frontendem
- Testami jednostkowymi
""")
# → Orchestrator aktywuje The Council
# → Architect planuje strukturę projektu
# → Coder pisze kolejne komponenty
# → Critic sprawdza każdy komponent
# → Guardian weryfikuje testy
```

### Przykład 3: Ręczne użycie Council (programistyczne)

```python
from venom_core.core.council import CouncilConfig, CouncilSession, create_local_llm_config

# Setup
llm_config = create_local_llm_config()
council_config = CouncilConfig(
    coder_agent=coder,
    critic_agent=critic,
    architect_agent=architect,
    guardian_agent=guardian,
    llm_config=llm_config
)

# Stwórz sesję
user_proxy, group_chat, manager = council_config.create_council()
session = CouncilSession(user_proxy, group_chat, manager)

# Uruchom rozmowę
result = await session.run("Napisz grę Snake")

# Analiza rozmowy
print(f"Liczba wiadomości: {session.get_message_count()}")
print(f"Uczestnicy: {session.get_speakers()}")
```

## Wymagania

### Software:

1. **Python 3.10+**
2. **pyautogen>=0.2.0** (zainstalowany automatycznie)
3. **semantic-kernel>=1.9.0** (wymagany przez Venom)
4. **Lokalny LLM Server** (opcjonalny, ale zalecany):
   - Ollama z modelem llama3/mixtral
   - LiteLLM
   - vLLM
   - Llama.cpp server

### Instalacja Ollama (zalecane):

```bash
# Linux/WSL2
curl -fsSL https://ollama.com/install.sh | sh

# Uruchom model
ollama pull llama3
ollama serve

# Test
curl http://localhost:11434/v1/models
```

## Troubleshooting

### Problem: "Connection refused to localhost:11434"

**Rozwiązanie**: Upewnij się, że Ollama jest uruchomione:

```bash
ollama serve
```

### Problem: Council nie aktywuje się dla mojego zadania

**Rozwiązanie**: Sprawdź długość zadania i słowa kluczowe, lub wymuszaj przez COMPLEX_PLANNING:

```python
# W intent_manager.py - dodaj regułę dla swojego typu zadania
```

### Problem: Rozmowa Council trwa za długo

**Rozwiązanie**: Zmniejsz `max_round` w GroupChat:

```python
# W council.py
group_chat = GroupChat(
    agents=agents,
    max_round=10,  # Zamiast 20
    ...
)
```

## Metryki i monitoring

### Dostępne eventy WebSocket:

```python
COUNCIL_STARTED      # Council rozpoczął pracę
COUNCIL_MEMBERS      # Lista uczestników
COUNCIL_COMPLETED    # Dyskusja zakończona
COUNCIL_ERROR        # Błąd podczas dyskusji
```

### Logi:

```python
# Włącz debug logging
import logging
logging.getLogger("venom_core.core.council").setLevel(logging.DEBUG)
logging.getLogger("venom_core.core.swarm").setLevel(logging.DEBUG)
```

## Dalszy rozwój

### Planowane funkcje:

- [ ] Streaming pojedynczych wiadomości agentów (COUNCIL_AGENT_SPEAKING)
- [ ] Możliwość przerwania rozmowy przez użytkownika
- [ ] Zapisywanie historii rozmów Council do bazy
- [ ] Dashboard z wizualizacją grafu rozmowy
- [ ] Niestandardowe grafy przepływu (configurable transitions)
- [ ] Więcej agentów specjalistycznych (Tester, DevOps, Security)

## Zobacz też

- [AutoGen Documentation](https://microsoft.github.io/autogen/)
- [Semantic Kernel Documentation](https://learn.microsoft.com/en-us/semantic-kernel/)
- [Venom Architecture Overview](../README.md)
