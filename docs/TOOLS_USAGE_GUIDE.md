# Tools Usage Guide (model-agnostic)

This guide explains our built-in tools (skills/adapters) and `/...` routing in web-next.

## 1. Core principles

- Model selection (`ollama`, `vllm`, `openai`, `google`) controls generation runtime.
- Tools run independently from model choice, through `forced_tool` routing.
- Requests with `/...` use the task/orchestrator path, not the simple direct chat stream.

## 2. How `/...` routing works

1. Frontend parses a slash command and sends `forced_tool` / `forced_provider`.
2. Backend maps `forced_tool -> forced_intent`.
3. For `forced_tool`, session block is not prepended to tool prompt (tool gets a clean query).
4. Intent-specific agent runs and uses matching skills.

This means `/research ...` should not inherit a long session-context preamble.

## 3. Available slash tool commands

Current mapping (`venom_core/core/slash_commands.py` + `web-next/lib/slash-commands.ts`):

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

Also:
- `/gem`, `/gpt` force LLM provider.
- `/clear` resets session.

## 4. Key runtime tools

- `WebSearchSkill` (`venom_core/execution/skills/web_skill.py`):
  - `search`, `scrape_text`, `search_and_scrape`
  - source: Tavily (when `TAVILY_API_KEY` is set), fallback: DuckDuckGo.
- `BrowserSkill` (`venom_core/execution/skills/browser_skill.py`):
  - browser automation (Playwright), screenshots, core E2E actions.
- MCP-like adapters (`venom_core/skills/mcp/skill_adapter.py`):
  - expose local `GitSkill`, `FileSkill`, `GoogleCalendarSkill` as tools.

## 5. Dependencies and environment (`.venv`)

Required for web research:

```bash
source .venv/bin/activate
pip install ddgs trafilatura beautifulsoup4 tavily-python
```

Optional `.env`:

```env
TAVILY_API_KEY=...
```

## 6. Quick verification

1. Send in UI: `/research Current DDR5 2x16GB prices in Poland and the US with links`.
2. Confirm source section in output (`URL:` or `Sources:`/`Źródła:`).
3. Check that without `/research`, answer can be static/model-only.
