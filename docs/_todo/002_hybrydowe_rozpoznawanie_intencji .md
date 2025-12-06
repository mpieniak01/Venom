# ZADANIE: 002_INTENT_RECOGNITION_HYBRID (Local-First Brain)

## 1. Kontekst
Venom to system Local-First. Wymagamy, aby "mózg" (Semantic Kernel) działał przede wszystkim na lokalnie zainstalowanych dużych modelach językowych (LLM), a nie polegał wyłącznie na chmurze. Orchestrator musi potrafić klasyfikować intencje ("Czy user chce kod?", "Czy user chce rozmawiać?") używając lokalnych zasobów.

## 2. Zakres prac

### A. Konfiguracja (`venom_core/config.py`)
Rozszerz `Settings` o konfigurację dla lokalnego LLM:
- `LLM_SERVICE_TYPE`: str (domyślnie `"local"`, opcje: `"local"`, `"openai"`, `"azure"`)
- `LLM_LOCAL_ENDPOINT`: str (np. `"http://localhost:11434/v1"` dla Ollama/vLLM)
- `LLM_MODEL_NAME`: str (np. `"phi3:latest"`, `"mistral"`, `"gpt-4o"`)
- `OPENAI_API_KEY`: Opcjonalne (wymagane tylko dla typu `"openai"`).

### B. Kernel Builder (`venom_core/execution/kernel_builder.py`)
Zaimplementuj klasę `KernelBuilder`, która dynamicznie buduje jądro Semantic Kernel w zależności od konfiguracji:
- Metoda `build_kernel() -> Kernel`.
- **Logika Local:** Jeśli `LLM_SERVICE_TYPE == "local"`, skonfiguruj `OpenAIChatCompletion` (lub dedykowany konektor), ale przekieruj `endpoint_url` na adres lokalny (`LLM_LOCAL_ENDPOINT`) i użyj `api_key="venom-local"`.
- **Logika Cloud:** Jeśli `LLM_SERVICE_TYPE == "openai"`, użyj standardowego połączenia z kluczem API.
- Rejestracja serwisu w jądrze (AddChatCompletionService).

### C. Menedżer Intencji (`venom_core/core/intent_manager.py`)
Zaimplementuj `IntentManager` wykorzystujący Semantic Kernel:
- **Prompt Systemowy:** Zdefiniuj jasny prompt klasyfikujący wejście użytkownika do jednej z kategorii:
  - `CODE_GENERATION` (prośba o kod, refactor, skrypt).
  - `KNOWLEDGE_SEARCH` (pytanie o wiedzę).
  - `GENERAL_CHAT` (rozmowa, powitanie).
- Metoda `async def classify_intent(self, user_input: str) -> str`: Wywołuje Kernel z promptem i zwraca czystą kategorię.

### D. Integracja z Orchestratorem (`venom_core/core/orchestrator.py`)
Zaktualizuj metodę `_run_task`:
1. Zainicjalizuj `IntentManager` (wstrzyknij zależność).
2. Zamiast "sleep", wywołaj `classify_intent` na treści zadania.
3. Zapisz wynik klasyfikacji w `task.result` oraz w logach.

---

## 3. Kryteria Akceptacji (DoD)
1.  **Działa bez Internetu:** Testy muszą przechodzić przy konfiguracji `LLM_SERVICE_TYPE="local"`, zakładając, że pod adresem `localhost` nasłuchuje makieta lub lokalny serwer LLM (w teście można użyć mocka odpowiedzi HTTP).
2.  **Elastyczność:** Zmiana jednej zmiennej w `.env` przełącza Venoma z trybu lokalnego na chmurowy.
3.  **Poprawna Klasyfikacja:**
    - Input: "Napisz funkcję w Pythonie do sortowania" -> Output: `CODE_GENERATION`.
    - Input: "Witaj Venom, jak się masz?" -> Output: `GENERAL_CHAT`.
4.  **Brak Hardcodowania:** Adresy IP i nazwy modeli muszą pochodzić z `config.py`.

---

## 4. Wskazówki Techniczne
- Semantic Kernel w Pythonie obsługuje lokalne serwery zgodne z API OpenAI (jak Ollama, LM Studio, LocalAI) poprzez klasę `OpenAIChatCompletion` z parametrem `endpoint` lub `base_url`. To preferowana metoda integracji dla MVP.
- Pamiętaj o obsłudze timeoutów – lokalne modele mogą odpowiadać wolniej niż chmura.
