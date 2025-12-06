# Hybrydowe Rozpoznawanie Intencji (Local-First Brain)

System klasyfikacji intencji użytkownika z wykorzystaniem lokalnych lub chmurowych LLM.

## Konfiguracja

### Tryb Lokalny (domyślny)

Utwórz plik `.env` w głównym katalogu projektu:

```env
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://localhost:11434/v1
LLM_MODEL_NAME=phi3:latest
LLM_LOCAL_API_KEY=venom-local
```

### Tryb Chmurowy (OpenAI)

```env
LLM_SERVICE_TYPE=openai
LLM_MODEL_NAME=gpt-4o
OPENAI_API_KEY=sk-your-api-key-here
```

## Typy Intencji

System klasyfikuje wejście użytkownika do jednej z trzech kategorii:

1. **CODE_GENERATION** - prośby o kod, skrypty, refactoring
   - Przykład: "Napisz funkcję w Pythonie do sortowania"

2. **KNOWLEDGE_SEARCH** - pytania o wiedzę, fakty, wyjaśnienia
   - Przykład: "Co to jest GraphRAG?"

3. **GENERAL_CHAT** - rozmowa ogólna, powitania
   - Przykład: "Witaj Venom, jak się masz?"

## Użycie w Kodzie

### Podstawowe użycie z Orchestrator

```python
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.core.models import TaskRequest

# Inicjalizacja
state_manager = StateManager(state_file_path="./data/state.json")
orchestrator = Orchestrator(state_manager)

# Wyślij zadanie - intencja zostanie automatycznie sklasyfikowana
response = await orchestrator.submit_task(
    TaskRequest(content="Napisz funkcję sortującą")
)

# Sprawdź wynik
task = state_manager.get_task(response.task_id)
print(f"Wynik: {task.result}")  # Zawiera sklasyfikowaną intencję
```

### Bezpośrednie użycie IntentManager

```python
from venom_core.core.intent_manager import IntentManager

# Użyj domyślnej konfiguracji
manager = IntentManager()

# Klasyfikuj intencję
intent = await manager.classify_intent("Napisz kod w Python")
print(f"Intencja: {intent}")  # Output: CODE_GENERATION
```

### Własna konfiguracja

```python
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.core.intent_manager import IntentManager
from pydantic_settings import BaseSettings

# Custom settings
class CustomSettings(BaseSettings):
    LLM_SERVICE_TYPE: str = "local"
    LLM_LOCAL_ENDPOINT: str = "http://localhost:8000/v1"
    LLM_MODEL_NAME: str = "mistral:latest"
    LLM_LOCAL_API_KEY: str = "custom-key"

# Zbuduj kernel z custom settings
builder = KernelBuilder(settings=CustomSettings())
kernel = builder.build_kernel()

# Utwórz IntentManager z custom kernel
manager = IntentManager(kernel=kernel)
```

## Wymagania

### Tryb Lokalny

Wymagany lokalny serwer LLM zgodny z API OpenAI, np.:

- [Ollama](https://ollama.ai/) - najprostsze rozwiązanie
  ```bash
  ollama serve
  ollama pull phi3
  ```

- [vLLM](https://vllm.ai/) - wydajniejsze dla produkcji
- [LocalAI](https://localai.io/) - alternatywa

### Tryb Chmurowy

Wymagany klucz API OpenAI.

## Testy

```bash
# Wszystkie testy
pytest tests/test_kernel_builder.py tests/test_intent_manager.py tests/test_orchestrator_intent.py -v

# Tylko testy KernelBuilder
pytest tests/test_kernel_builder.py -v

# Tylko testy IntentManager
pytest tests/test_intent_manager.py -v
```

## Rozwiązywanie Problemów

### Błąd połączenia z lokalnym serwerem

Upewnij się, że lokalny serwer LLM działa:

```bash
# Dla Ollama
curl http://localhost:11434/v1/models

# Sprawdź czy model jest pobrany
ollama list
```

### Wolne odpowiedzi

Lokalne modele mogą odpowiadać wolniej niż chmura. Rozważ:
- Użycie mniejszego modelu (np. `phi3:mini`)
- Przyspieszenie przez GPU (`ollama run phi3 --gpu`)
- Zwiększenie timeoutów w konfiguracji

## Licencja i Prywatność

Tryb lokalny zachowuje pełną prywatność - żadne dane nie opuszczają Twojego komputera.
