# Zadanie 101: Wyszukiwanie i instalacja modeli (Ollama + HF)

## Cel
Umożliwienie użytkownikowi wyszukiwania modeli w zasobach Ollama i HuggingFace bezpośrednio z poziomu UI (strona `/models`), a następnie ich instalacji.

## Zakres zmian

### 1. Backend (`venom_core`)

#### Nowy endpoint wyszukiwania
- **`GET /api/v1/models/search`**
    - Parametry: `q` (query), `provider` (ollama/huggingface), `limit` (default 10).
    - Zwraca listę modeli z metadanymi: `name`, `description`, `downloads`, `likes`, `size_gb` (jeśli dostępne).

#### Rozbudowa `ModelRegistry` i Klientów
- **`HuggingFaceClient`**:
    - Metoda `search_models(query: str, limit: int)` wykorzystująca API `https://huggingface.co/api/models?search={query}`.
    - Mapowanie wyników API HF na ujednolicony format.
- **`OllamaClient`**:
    - Metoda `search_models(query: str, limit: int)`.
    - **Wyzwanie**: Ollama nie posiada publicznego JSON API do przeszukiwania biblioteki (`ollama.com/library`).
    - **Rozwiązanie**: Implementacja prostego scrapera HTML dla `https://ollama.com/search?q={query}` (parsersing `BeautifulSoup` lub `regex` na `httpx` response).
    - Alternatywa: Wyszukiwanie tylko "popularnych" tagów jeśli scraping okaże się niestabilny, ale wymaganie mówi o "wyszukiwaniu po nazwie".

### 2. Frontend (`web-next`)

#### Rozbudowa `ModelsViewer`
- Dodanie paska wyszukiwania (Search Input) nad sekcjami (lub w dedykowanej zakładce "Odkrywaj").
- Obsługa stanu wyszukiwania (loading, wyniki, brak wyników).
- Wyświetlanie wyników w formie kart (podobnych do `CatalogCard`), ale z przyciskiem "Zainstaluj".
    - Dla Ollama: `ollama pull {name}`.
    - Dla HF: `download_snapshot`.

#### Obsługa instalacji
- Wykorzystanie istniejącej funkcji `handleInstall`.
- Upewnienie się, że `installRegistryModel` przyjmuje nazwy modeli pochodzące z wyszukiwania (dla HF nazwa to `repo_id`, dla Ollama to `model_name`).

## Analiza techniczna

### HuggingFace API
- Endpoint: `https://huggingface.co/api/models`
- Query params: `search`, `limit`, `sort=downloads`.
- Zwraca JSON z pełnymi metadanymi.

### Ollama Library
- Brak oficjalnego API.
- Scraping `https://ollama.com/search?q=llama3`:
    - Parsowanie listy wyników (selektor np. `li` w liście wyników).
    - Wyciągnięcie nazwy (np. `library/llama3`) i opisu.
    - **Ryzyko**: Zmiany w strukturze HTML ollama.com mogą zepsuć funkcję. Należy obsłużyć błędy parsowania (fallback do pustej listy z komunikatem).

## Plan wdrożenia
- [x] Implementacja `search_models` w `HuggingFaceClient`.
- [x] Implementacja `search_models` w `OllamaClient` (scraping).
- [x] Dodanie metody `search_external_models` w `ModelRegistry`.
- [x] Wystawienie endpointu `/api/v1/models/search`.
- [x] Implementacja UI wyszukiwarki w `ModelsViewer`.
- [x] Weryfikacja instalacji znalezionych modeli (manual & script).

## Status realizacji

- **Backend**: Gotowy (Endpoint `/api/v1/models/search` działa, scraping Ollama działa).
- **Frontend**: Gotowy (Wyszukiwarka dodana do `ModelsViewer`, zintegrowana z instalacją).
- **Weryfikacja**: Przetestowano backend skryptem `verify_search.py`. UI gotowe do testów manualnych.
