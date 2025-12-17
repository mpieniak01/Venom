# Warstwa Wykonawcza Parametrów Generacji

## Przegląd

Ten dokument opisuje implementację warstwy wykonawczej (Execution Layer) dla parametrów generacji modeli AI. Stanowi kontynuację PR #172 ("Rozszerzenie Manifestu Modeli i UI strojenia"), dodając rzeczywistą funkcjonalność do wcześniej zaimplementowanej warstwy definicji i UI.

## Kontekst

W PR #172 zaimplementowano:
- Schema parametrów generacji (`GenerationParameter`, `ModelCapabilities`)
- API endpoint `/api/v1/models/{name}/config`
- Frontend UI do strojenia parametrów (`DynamicParameterForm`)
- Pole `generation_params` w `TaskRequest`

To PR dodaje:
- **Adapter parametrów generacji** - mapowanie na specyfikę vLLM/Ollama
- **Integrację z Orchestrator** - przekazywanie parametrów przez przepływ wykonania
- **Integrację z Agentami** - rzeczywiste używanie parametrów przy wywołaniach LLM
- **Testy** - unit i integration testy

## Architektura

### 1. Adapter Parametrów Generacji

Plik: `venom_core/core/generation_params_adapter.py`

**Cel:** Mapowanie generycznych parametrów na format specyficzny dla danego providera.

**Główne funkcje:**
- `adapt_params()` - adaptuje parametry do formatu providera
- `merge_with_defaults()` - łączy parametry użytkownika z domyślnymi
- `_detect_provider()` - wykrywa typ providera

**Mapowania:**

```python
# vLLM (OpenAI-compatible API)
{
    "temperature": "temperature",
    "max_tokens": "max_tokens",
    "top_p": "top_p",
    "top_k": "top_k",
    "repeat_penalty": "repetition_penalty"  # ⚠️ różna nazwa
}

# Ollama
{
    "temperature": "temperature",
    "max_tokens": "num_predict",  # ⚠️ różna nazwa
    "top_p": "top_p",
    "top_k": "top_k",
    "repeat_penalty": "repeat_penalty"
}

# OpenAI
{
    "temperature": "temperature",
    "max_tokens": "max_tokens",
    "top_p": "top_p"
    # top_k, repeat_penalty - nieobsługiwane, są pomijane
}
```

**Przykład użycia:**

```python
from venom_core.core.generation_params_adapter import GenerationParamsAdapter

# Parametry od użytkownika
params = {
    "temperature": 0.7,
    "max_tokens": 1024,
    "repeat_penalty": 1.1
}

# Adaptacja dla vLLM
adapted = GenerationParamsAdapter.adapt_params(params, "vllm")
# Rezultat: {"temperature": 0.7, "max_tokens": 1024, "repetition_penalty": 1.1}

# Adaptacja dla Ollama
adapted = GenerationParamsAdapter.adapt_params(params, "ollama")
# Rezultat: {"temperature": 0.7, "num_predict": 1024, "repeat_penalty": 1.1}
```

### 2. Integracja z Orchestrator

Plik: `venom_core/core/orchestrator.py`

**Zmiany:**
1. Zapisywanie `generation_params` w kontekście zadania
2. Przekazywanie parametrów do `TaskDispatcher.dispatch()`

```python
# W _run_task()
if request.generation_params:
    self.state_manager.update_context(
        task_id, {"generation_params": request.generation_params}
    )

# Przekazanie do dispatcher
result = await self.task_dispatcher.dispatch(
    intent, context, generation_params=request.generation_params
)
```

### 3. Integracja z TaskDispatcher

Plik: `venom_core/core/dispatcher.py`

**Zmiany:**
1. Rozszerzenie sygnatury `dispatch()` o parametr `generation_params`
2. Wywołanie `agent.process_with_params()` jeśli dostępne

```python
async def dispatch(
    self,
    intent: str,
    content: str,
    node_preference: dict = None,
    generation_params: dict = None,
) -> str:
    agent = self.agent_map.get(intent)
    
    # Sprawdź czy agent wspiera generation_params
    if generation_params and hasattr(agent, "process_with_params"):
        result = await agent.process_with_params(content, generation_params)
    else:
        result = await agent.process(content)
    
    return result
```

### 4. Integracja z BaseAgent

Plik: `venom_core/agents/base.py`

**Zmiany:**
1. Dodano metodę `process_with_params()` - może być nadpisana przez podklasy
2. Dodano helper `_create_execution_settings()` - używa adaptera do tworzenia settings

```python
class BaseAgent(ABC):
    async def process_with_params(
        self, input_text: str, generation_params: Dict[str, Any]
    ) -> str:
        """Domyślnie deleguje do process(), podklasy mogą nadpisać."""
        return await self.process(input_text)
    
    def _create_execution_settings(
        self,
        generation_params: Optional[Dict[str, Any]] = None,
        default_settings: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> OpenAIChatPromptExecutionSettings:
        """Tworzy ustawienia z adaptacją parametrów."""
        runtime_info = get_active_llm_runtime()
        provider = runtime_info.provider
        
        merged_params = GenerationParamsAdapter.merge_with_defaults(
            generation_params, default_settings
        )
        adapted_params = GenerationParamsAdapter.adapt_params(
            merged_params, provider
        )
        
        return OpenAIChatPromptExecutionSettings(**adapted_params, **kwargs)
```

### 5. Implementacja w ChatAgent i CoderAgent

**ChatAgent** (`venom_core/agents/chat.py`):
```python
async def process_with_params(
    self, input_text: str, generation_params: dict
) -> str:
    return await self._process_internal(input_text, generation_params)

async def _process_internal(
    self, input_text: str, generation_params: dict = None
) -> str:
    # ... przygotowanie chat_history ...
    
    settings = self._build_execution_settings(
        enable_functions, generation_params
    )
    
    response = await chat_service.get_chat_message_content(
        chat_history=chat_history, settings=settings
    )
    return str(response)

def _build_execution_settings(
    self, enable_functions: bool, generation_params: dict = None
):
    kwargs = {}
    if enable_functions:
        kwargs["function_choice_behavior"] = FunctionChoiceBehavior.Auto()
    
    return self._create_execution_settings(
        generation_params=generation_params, **kwargs
    )
```

**CoderAgent** - analogiczna implementacja.

## Przepływ Danych

```
1. Frontend → API: POST /api/v1/tasks
   {
     "content": "Napisz funkcję...",
     "generation_params": {"temperature": 0.3, "max_tokens": 512}
   }

2. API → Orchestrator.submit_task(TaskRequest)
   TaskRequest.generation_params = {"temperature": 0.3, "max_tokens": 512}

3. Orchestrator._run_task()
   - Zapisuje params w task.context_history["generation_params"]
   - Wywołuje: dispatcher.dispatch(..., generation_params=...)

4. TaskDispatcher.dispatch()
   - Wykrywa że agent ma process_with_params()
   - Wywołuje: agent.process_with_params(content, generation_params)

5. Agent (np. ChatAgent)
   - Wywołuje: _create_execution_settings(generation_params)
   - BaseAgent._create_execution_settings():
     * Wykrywa provider (vllm/ollama/openai)
     * Wywołuje: GenerationParamsAdapter.adapt_params(params, provider)
     * Tworzy: OpenAIChatPromptExecutionSettings(**adapted_params)

6. Semantic Kernel
   - chat_service.get_chat_message_content(settings=settings)
   - Przekazuje zmapowane parametry do LLM API

7. LLM (vLLM/Ollama)
   - Otrzymuje parametry w odpowiednim formacie
   - Generuje odpowiedź z użyciem tych parametrów
```

## Testy

### Testy Jednostkowe Adaptera

Plik: `tests/test_generation_params_adapter.py`

**13 testów:**
- Adaptacja dla vLLM, Ollama, OpenAI
- Wykrywanie providera
- Łączenie z domyślnymi parametrami
- Obsługa pustych/częściowych parametrów

```bash
pytest tests/test_generation_params_adapter.py -v
# 13 passed
```

### Testy Integracyjne

Plik: `tests/test_generation_params_integration.py`

**Testy:**
- TaskRequest z generation_params
- Mapowanie dla aktywnego providera
- Deterministyczność przy temperature=0.0 (wymaga live LLM)
- Ograniczanie długości przez max_tokens (wymaga live LLM)

```bash
# Testy podstawowe (nie wymagają LLM)
pytest tests/test_generation_params_integration.py::test_generation_params_in_task_request -v

# Testy z live LLM (skip jeśli brak środowiska)
pytest tests/test_generation_params_integration.py -v
```

## Użycie

### Dla Użytkownika (Frontend)

1. Otwórz Cockpit
2. Kliknij przycisk "Tuning"
3. Dostosuj parametry (np. temperature: 0.3 dla deterministycznego kodu)
4. Wyślij zadanie - parametry będą automatycznie użyte

### Dla Developera (API)

```python
import httpx

response = httpx.post(
    "http://localhost:8002/api/v1/tasks",
    json={
        "content": "Napisz funkcję sortującą tablicę",
        "generation_params": {
            "temperature": 0.3,  # Niższa dla kodu
            "max_tokens": 512,
            "top_p": 0.95
        }
    }
)
```

### Dla Developera (Bezpośrednio w Kodzie)

```python
from venom_core.agents.chat import ChatAgent
from venom_core.execution.kernel_builder import KernelBuilder

kernel = KernelBuilder().build_kernel()
agent = ChatAgent(kernel)

# Z parametrami
result = await agent.process_with_params(
    "Wytłumacz co to jest rekurencja",
    generation_params={
        "temperature": 0.5,
        "max_tokens": 200
    }
)

# Bez parametrów (domyślne)
result = await agent.process("Wytłumacz co to jest rekurencja")
```

## Dodawanie Wsparcia w Nowych Agentach

Aby dodać wsparcie dla generation_params w nowym agencie:

```python
from venom_core.agents.base import BaseAgent

class MyCustomAgent(BaseAgent):
    async def process_with_params(
        self, input_text: str, generation_params: dict
    ) -> str:
        # Przygotuj chat_history...
        chat_history = self._prepare_history(input_text)
        
        # Użyj helpera z BaseAgent
        settings = self._create_execution_settings(
            generation_params=generation_params,
            # Dodaj własne parametry jeśli potrzeba
            temperature=0.7,  # domyślna temperatura dla tego agenta
        )
        
        # Wywołaj LLM
        chat_service = self.kernel.get_service()
        response = await chat_service.get_chat_message_content(
            chat_history=chat_history,
            settings=settings
        )
        
        return str(response)
```

## Różnice Między Providerami

### vLLM

```python
# Wejście
{"temperature": 0.7, "max_tokens": 1024, "repeat_penalty": 1.1}

# Wyjście (po adaptacji)
{"temperature": 0.7, "max_tokens": 1024, "repetition_penalty": 1.1}
```

**Uwagi:**
- vLLM używa `repetition_penalty` zamiast `repeat_penalty`
- Kompatybilny z OpenAI API

### Ollama

```python
# Wejście
{"temperature": 0.7, "max_tokens": 1024, "top_k": 40}

# Wyjście (po adaptacji)
{"temperature": 0.7, "num_predict": 1024, "top_k": 40}
```

**Uwagi:**
- Ollama używa `num_predict` zamiast `max_tokens`
- Wspiera większość parametrów

### OpenAI

```python
# Wejście
{"temperature": 0.7, "max_tokens": 1024, "top_k": 40, "repeat_penalty": 1.1}

# Wyjście (po adaptacji)
{"temperature": 0.7, "max_tokens": 1024}
# top_k i repeat_penalty pominięte - nieobsługiwane
```

**Uwagi:**
- OpenAI nie wspiera `top_k` i `repeat_penalty`
- Niewspierane parametry są pomijane bez błędu

## Troubleshooting

### Problem: Parametry nie wpływają na odpowiedź

**Przyczyny:**
1. Model nie obsługuje danego parametru
2. Backend (vLLM/Ollama) ignoruje parametr
3. Wartość parametru jest poza zakresem

**Rozwiązanie:**
```python
# Włącz debug logging
import logging
logging.getLogger("venom_core.core.generation_params_adapter").setLevel(logging.DEBUG)
logging.getLogger("venom_core.agents.base").setLevel(logging.DEBUG)

# Sprawdź logi:
# "Zaadaptowano X parametrów dla providera 'Y'"
# "Utworzono ustawienia wykonania z parametrami: {...}"
```

### Problem: Błąd przy wywołaniu LLM

**Komunikat:** `"Parameter X is not supported"`

**Rozwiązanie:**
- Sprawdź czy używasz poprawnego providera w konfiguracji
- Sprawdź dokumentację providera dla obsługiwanych parametrów
- Adapter automatycznie pomija niewspierane parametry dla OpenAI

### Problem: Agent nie używa parametrów

**Przyczyna:** Agent nie implementuje `process_with_params()`

**Rozwiązanie:**
1. Dodaj metodę `process_with_params()` do agenta (patrz sekcja "Dodawanie Wsparcia")
2. Lub użyj `ChatAgent`/`CoderAgent` które już ją mają

## Metryki i Monitoring

Parametry generacji są logowane w kilku miejscach:

```python
# Orchestrator
logger.info(f"Zapisano parametry generacji dla zadania {task_id}: {params}")

# TaskDispatcher
logger.debug(f"Przekazuję parametry generacji do agenta: {params}")

# Agent
logger.debug(f"Parametry generacji: {params}")

# Adapter
logger.info(f"Zaadaptowano {len(adapted)} parametrów dla providera '{provider}'")
logger.debug(f"Zmapowano parametr: {generic} -> {provider_specific} = {value}")
```

## Przyszłe Rozszerzenia

1. **Wsparcie dla więcej agentów** - Architect, Researcher, Critic
2. **Adaptacja per-model** - różne limity dla różnych modeli
3. **Validacja parametrów** - sprawdzanie zakresów przed wysłaniem
4. **Cache parametrów** - zapamiętywanie ulubionych ustawień użytkownika
5. **Profile parametrów** - predefiniowane zestawy (creative, precise, balanced)

## Zobacz Także

- [MODEL_TUNING_GUIDE.md](MODEL_TUNING_GUIDE.md) - Frontend i schemat parametrów
- PR #172 - Rozszerzenie Manifestu Modeli i UI strojenia
- `venom_core/core/generation_params_adapter.py` - implementacja adaptera
- `tests/test_generation_params_adapter.py` - testy jednostkowe
- `tests/test_generation_params_integration.py` - testy integracyjne
