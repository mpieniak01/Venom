# Przewodnik Użycia Tooli (model-agnostic)

Ten przewodnik opisuje nasze własne toolsy (skille/adaptory) i routing `/...` w web-next.

## 1. Najważniejsze

- Model (`ollama`, `vllm`, `openai`, `google`) to warstwa generacji.
- Toolsy działają niezależnie od wybranego modelu i są uruchamiane przez routing `forced_tool`.
- Dla zapytań z prefiksem `/...` system idzie ścieżką task/orchestrator, nie prostym chat-streamem.

## 2. Jak działa routing `/...`

1. Frontend parsuje slash command i wysyła `forced_tool` / `forced_provider`.
2. Backend mapuje `forced_tool -> forced_intent`.
3. Dla `forced_tool` kontekst sesji nie jest doklejany do promptu narzędzia (tool dostaje czyste zapytanie).
4. Agent dla danej intencji używa odpowiednich skilli.

To oznacza, że `/research ...` nie powinno dziedziczyć długiego bloku historii sesji.

## 3. Dostępne komendy tooli (slash)

Aktualna mapa (`venom_core/core/slash_commands.py` + `web-next/lib/slash-commands.ts`):

- `RESEARCH`: `/research`, `/web`, `/browser`, `/github`, `/hf`, `/media`
- `VERSION_CONTROL`: `/git`, `/platform`
- `FILE_OPERATION`: `/file`
- `DOCUMENTATION`: `/docs`, `/render`
- `CODE_GENERATION`: `/compose`, `/shell`
- `E2E_TESTING`: `/test`, `/input`
- `STATUS_REPORT`: `/core`
- `TIME_REQUEST`: `/chrono`
- `COMPLEX_PLANNING`: `/parallel`, `/complexity`
- `GENERAL_CHAT`: `/assistant`, `/gcal`

Dodatkowo:
- `/gem`, `/gpt` wymuszają providera LLM.
- `/clear` resetuje sesję.

## 4. Kluczowe toolsy runtime

- `WebSearchSkill` (`venom_core/execution/skills/web_skill.py`):
  - `search`, `scrape_text`, `search_and_scrape`
  - źródło: Tavily (gdy `TAVILY_API_KEY`), fallback: DuckDuckGo.
- `BrowserSkill` (`venom_core/execution/skills/browser_skill.py`):
  - automatyzacja przeglądarki (Playwright), screenshoty, podstawowe akcje E2E.
- MCP-like adaptory (`venom_core/skills/mcp/skill_adapter.py`):
  - lokalne wystawienie `GitSkill`, `FileSkill`, `GoogleCalendarSkill` jako narzędzi.

## 5. Zależności i środowisko (`.venv`)

Wymagane dla web-research:

```bash
source .venv/bin/activate
pip install ddgs trafilatura beautifulsoup4 tavily-python
```

Opcjonalnie `.env`:

```env
TAVILY_API_KEY=...
```

## 6. Szybka weryfikacja

1. Wyślij w UI: `/research Aktualne ceny DDR5 2x16GB w Polsce i USA z linkami`.
2. Potwierdź sekcję źródeł (`URL:` lub `Źródła:`).
3. Sprawdź, że bez `/research` odpowiedź może być statyczna (modelowa).

## 7. Testy, które przeszły (lokalnie)

```bash
source .venv/bin/activate
pytest -q tests/test_slash_commands.py tests/test_web_skill.py tests/test_web_skill_tavily.py tests/test_mcp_skill_adapter_poc.py tests/test_intent_tool_requirement.py
pytest -q tests/test_tool_reliability.py tests/test_researcher_agent.py
```

Wynik: `40 passed`.
