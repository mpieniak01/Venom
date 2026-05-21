# THE CHAT - Repository Analysis Assistant

## Role

Chat Agent is the repository-facing assistant in Venom. Its job is to reason about the current workspace and help the operator make fact-based decisions.

## Quick start

If you want to start using the Copilot chat in Venom, begin here:

1. Start the local-first runtime:
   ```bash
   make local-first-start MODEL=qwen2.5-coder:7b
   ```
2. Check that the runtime is ready:
   ```bash
   make local-first-status
   ```
3. Open the local Copilot-backed chat lane:
   ```bash
   make local-first-codex MODEL=qwen2.5-coder:7b PROMPT='Powiedz tylko OK.'
   ```
4. If you need real repo truth before the answer, use the repo-truth lane:
   ```bash
   make local-first-repo-truth-agent MODEL=qwen2.5-coder:7b PROMPT='Przeanalizuj stan repo i podaj kolejny krok.'
   ```
5. For technical runtime, session, and tool details, continue in `CHAT_OPERATOR.md` and `CHAT_SESSION.md`.

## What it is for

- repository state and branch status,
- API contract scope and drift between docs and code,
- documentation and script remodeling,
- memory-backed operator decisions,
- optional calendar or small-talk handling when explicitly requested.

## Main integrations

- `MemorySkill` - recall and persist long-lived operator facts.
- `GoogleCalendarSkill` - optional calendar actions, not the default focus.

Calendar is available, but it is not the primary chat topic.

Detailed chat runtime, session routing, tools, and make targets are delegated to `CHAT_OPERATOR.md` and `CHAT_SESSION.md`.

## Operating rules

- Repo and facts first.
- Memory second.
- Respond operationally and keep answers concise.
- Save important operator facts when they matter.

## Handled intents

**GENERAL_CHAT**
- repository status,
- branch status,
- API contract scope,
- documentation and script remodeling,
- memory capture,
- explicit calendar questions.

**Not handled here**
- code generation,
- complex planning,
- research,
- knowledge search.

## See also

- [CHAT_OPERATOR.md](CHAT_OPERATOR.md) - operator-facing workflow, runtime, and quick-start commands
- [CHAT_SESSION.md](CHAT_SESSION.md) - session storage, routing, and runtime details
- [THE_RESEARCHER.md](THE_RESEARCHER.md) - current information search
- [MEMORY_LAYER_GUIDE.md](MEMORY_LAYER_GUIDE.md) - memory model
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - intent classification
