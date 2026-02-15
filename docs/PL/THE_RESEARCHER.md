# THE RESEARCHER - Knowledge Synthesis & Web Search

## Rola

Researcher Agent to ekspert badawczy w systemie Venom, specjalizujący się w znajdowaniu i syntezie wiedzy z Internetu. Dostarcza aktualną dokumentację, przykłady kodu, najlepsze praktyki oraz informacje o bibliotekach i narzędziach.

## Odpowiedzialności

- **Wyszukiwanie informacji** - Znajdowanie aktualnych danych w Internecie (DuckDuckGo, Google Grounding)
- **Ekstrakcja treści** - Pobieranie i czyszczenie tekstu ze stron WWW (trafilatura)
- **Synteza wiedzy** - Agregacja informacji z wielu źródeł w spójną odpowiedź
- **Wyszukiwanie repozytoriów** - Znajdowanie bibliotek i narzędzi na GitHub
- **Integracja z HuggingFace** - Wyszukiwanie modeli i datasetów
- **Zarządzanie pamięcią** - Zapisywanie ważnej wiedzy do LanceDB

## Kluczowe Komponenty

### 1. Dostępne Narzędzia

**WebSearchSkill** (`venom_core/execution/skills/web_skill.py`):
- `search(query, max_results)` - Wyszukiwanie w Internecie (DuckDuckGo)
- `scrape_text(url)` - Ekstrakcja tekstu ze strony (trafilatura)
- `search_and_scrape(query, max_pages)` - Wyszukaj i pobierz treść z top wyników

**GitHubSkill** (`venom_core/execution/skills/github_skill.py`):
- `search_repos(query, language, max_results)` - Wyszukiwanie repozytoriów
- `get_repo_details(repo_name)` - Szczegóły repozytorium
- `get_readme(repo_name)` - README.md repozytorium

**HuggingFaceSkill** (`venom_core/execution/skills/huggingface_skill.py`):
- `search_models(query, task, max_results)` - Wyszukiwanie modeli ML
- `search_datasets(query, max_results)` - Wyszukiwanie zbiorów danych
- `get_model_details(model_id)` - Szczegóły modelu

**MemorySkill** (`venom_core/memory/memory_skill.py`):
- `save_fact(content, tags)` - Zapisuje wiedzę do LanceDB
- `search_memory(query)` - Przeszukuje pamięć wektorową

### 2. Integracja z Google Grounding (Gemini)

Researcher może korzystać z **Google Search Grounding** gdy dostępny jest Gemini API:

```python
# Automatyczne dodawanie źródeł do odpowiedzi
response_metadata = {
  "grounding_metadata": {
    "grounding_chunks": [
      {"title": "FastAPI Documentation", "uri": "https://fastapi.tiangolo.com/"},
      {"title": "Pydantic V2", "uri": "https://docs.pydantic.dev/"}
    ]
  }
}

# Format wyjściowy:
"""
Odpowiedź agenta...

---
📚 Źródła (Google Grounding):
[1] FastAPI Documentation - https://fastapi.tiangolo.com/
[2] Pydantic V2 - https://docs.pydantic.dev/
"""
```

**Zalety Google Grounding:**
- Zawsze aktualne wyniki (Google Index)
- Automatyczne cytowanie źródeł
- Wyższa jakość odpowiedzi niż DuckDuckGo
- Zero kosztów ekstrakcji (scraping) - tekst już jest w kontekście

**Konfiguracja:**
```bash
# W .env
GOOGLE_API_KEY=your_key_here
AI_MODE=HYBRID  # lub CLOUD
HYBRID_CLOUD_PROVIDER=google
```

### 3. Przykłady Użycia

**Przykład 1: Dokumentacja biblioteki**
```
Użytkownik: "Jak używać FastAPI z PostgreSQL?"
Akcja:
1. search("FastAPI PostgreSQL tutorial")
2. scrape_text(top_results[0])
3. save_fact(synteza_wiedzy, tags=["fastapi", "postgresql"])
4. Zwróć odpowiedź z przykładami
```

**Przykład 2: Wyszukiwanie repozytorium**
```
Użytkownik: "Znajdź bibliotekę do parsowania JSON w Pythonie"
Akcja:
1. search_repos("JSON parser", language="python")
2. get_readme(top_repo)
3. Zwróć opis + link
```

**Przykład 3: Model ML**
```
Użytkownik: "Znajdź model do sentiment analysis"
Akcja:
1. search_models("sentiment analysis", task="text-classification")
2. get_model_details(top_model)
3. Zwróć opis + instrukcję użycia
```

**Przykład 4: Aktualna cena/informacja**
```
Użytkownik: "Jaka jest aktualna cena Bitcoina?"
Akcja (z Google Grounding):
1. LLM Gemini z tools=[google_search_retrieval]
2. Automatyczne wyszukanie + synteza
3. Zwróć odpowiedź ze źródłami
```

## Integracja z Systemem

### Przepływ Wykonania

```
ArchitectAgent tworzy plan:
  Krok 1: RESEARCHER - "Znajdź dokumentację PyGame"
        ↓
TaskDispatcher wywołuje ResearcherAgent.execute()
        ↓
ResearcherAgent:
  1. search("PyGame documentation collision detection")
  2. scrape_text(top 3 wyniki)
  3. Synteza wiedzy (LLM)
  4. save_fact(synteza, tags=["pygame", "game-dev"])
  5. Zwraca wynik z linkami
        ↓
CoderAgent używa wiedzy do implementacji
```

### Współpraca z Innymi Agentami

- **ArchitectAgent** - Dostarcza wiedzę techniczną na początku projektu
- **CoderAgent** - Przekazuje dokumentację i przykłady do implementacji
- **MemorySkill** - Zapisuje ważną wiedzę do długoterminowej pamięci
- **ChatAgent** - Odpowiada na pytania użytkownika o fakty

## Konfiguracja

```bash
# W .env
# Tryb wyszukiwania
AI_MODE=LOCAL               # Tylko DuckDuckGo
AI_MODE=HYBRID              # DuckDuckGo + opcjonalnie Google Grounding
AI_MODE=CLOUD               # Preferencja Google Grounding

# Google Grounding (Gemini)
GOOGLE_API_KEY=your_key
HYBRID_CLOUD_PROVIDER=google

# Tavily AI (opcjonalne, lepsze wyniki niż DuckDuckGo)
TAVILY_API_KEY=your_key

# HuggingFace
ENABLE_HF_INTEGRATION=true
HF_TOKEN=your_token

# GitHub
GITHUB_TOKEN=ghp_your_token
```

## Strategie Wyszukiwania

### 1. DuckDuckGo (Domyślne)
- **Zalety**: Darmowe, prywatne, bez limitów API
- **Wady**: Mniej wyników niż Google, czasem przestarzałe
- **Użycie**: Tryb LOCAL, backup dla HYBRID

### 2. Google Grounding (Gemini API)
- **Zalety**: Najlepsze wyniki, automatyczne źródła, zawsze aktualne
- **Wady**: Wymaga API key, koszty per request
- **Użycie**: Tryb HYBRID/CLOUD, pytania faktograficzne

### 3. Tavily AI (Opcjonalne)
- **Zalety**: AI-optimized search, wyższa jakość niż DDG
- **Wady**: Płatne, limity API
- **Użycie**: Profesjonalne deployments

## Metryki i Monitoring

**Kluczowe wskaźniki:**
- Liczba zapytań wyszukiwania (per sesja)
- Średnia liczba źródeł na odpowiedź
- Współczynnik użycia cache (memory hit rate)
- Czas wyszukiwania + scraping (średnio)
- Stosunek Google Grounding vs DuckDuckGo (w trybie HYBRID)

## Best Practices

1. **Cache w pamięci** - Zawsze zapisuj ważną wiedzę do `save_fact()`
2. **Weryfikuj źródła** - Sprawdź datę publikacji (preferuj <1 rok)
3. **Agreguj wiedzę** - Nie kopiuj surowego tekstu, syntetyzuj kluczowe punkty
4. **Taguj odpowiednio** - Używaj spójnych tagów dla łatwiejszego wyszukiwania
5. **Google dla faktów** - Pytania o cenę/wiadomości → Google Grounding

## Znane Ograniczenia

- DuckDuckGo ma limity rate-limit (zazwyczaj nie problem)
- Scraping może zawieść dla stron z JavaScript (trafilatura nie renderuje JS)
- Google Grounding wymaga Gemini API (koszty)
- Brak wsparcia dla płatnych źródeł (paywalls, subskrypcje)

## Zobacz też

- [THE_ARCHITECT.md](THE_ARCHITECT.md) - Planowanie z wykorzystaniem wiedzy
- [THE_CODER.md](THE_CODER.md) - Implementacja bazująca na dokumentacji
- [MEMORY_LAYER_GUIDE.md](MEMORY_LAYER_GUIDE.md) - Pamięć długoterminowa
- [GOOGLE_SEARCH_GROUNDING_INTEGRATION.md](../GOOGLE_SEARCH_GROUNDING_INTEGRATION.md) - Google Grounding
- [HYBRID_AI_ENGINE.md](HYBRID_AI_ENGINE.md) - Routing LOCAL/HYBRID/CLOUD
