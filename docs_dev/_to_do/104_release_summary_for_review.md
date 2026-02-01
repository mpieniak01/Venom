# Release Summary (103+104 combined)

Date: 2026-02-01
Branch: 103_translations_continuation

## Scope
Single release that combines the original 103 i18n scope and the stabilization work tracked in 104.

## Key Changes
1) i18n + UI consistency
- Extended/updated locales (PL/EN/DE).
- Day.js locale initialization for correct date formatting.
- UI text normalization in Cockpit/Brain/Config components.

2) API + test stabilization
- Dependency overrides for tests; cleanup fixtures for memory/lessons.
- Added compatibility in memory graph lessons parsing (mock-safe, dict-friendly).
- Fixed mypy errors in memory graph lessons mapping.

3) E2E stabilization
- SSE parsing now accepts object payloads as well as JSON strings.
- Added deterministic language in E2E (venom-language=pl).
- Added hydration wait in Playwright tests to avoid SSR handler flakiness.

4) Test suite reliability
- Light test ordering adjusted to run longest tests first.
- Flaky core nervous system tests changed to sync client + polling for completion.

## Notable Files
- web-next/hooks/use-task-stream.ts
- web-next/lib/i18n/index.tsx
- web-next/tests/*.spec.ts (smoke, chat-mode-routing, chat-context-icons, streaming)
- venom_core/api/routes/memory.py
- tests/test_core_nervous_system.py
- config/pytest-groups/light.txt

## Verification
- Targeted pytest subsets passed (memory + api dependencies + core nervous system).
- Playwright functional suite stabilized; smoke and chat mode tests pass after hydration/lang fixes.

## Notes for Reviewers
- This release intentionally ships 103 + 104 together to reduce churn.
- MCP is required (proxy already in use); dependencies remain in requirements.txt.
