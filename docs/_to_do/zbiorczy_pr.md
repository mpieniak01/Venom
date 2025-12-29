# Zbiorczy PR 75,76,79,80

## Cel
Zakniencie funkcjonalnosci podstawowych dla Venom 1.0 zgodnie z zakresem:

## Zakres zmian (high-level)
- Slash commands w Cockpicie (routing /gpt, /gem, /<tool> + autouzuplenianie).
- Automatyczne przelaczanie runtime dla /gpt i /gem (globalny switch z potwierdzeniem).
- Preferowany jezyk odpowiedzi (PL/EN/DE) przesylany z UI i tlumaczenie odpowiedzi.
- Researcher: automatyczny flow search -> scrape -> streszczenie.
- Browser skill: normalizacja URL (schemat http/https).
- Formatowanie wynikow obliczen w czacie + UI badge "Forced".
- Testy jednostkowe i integracyjne dla nowych funkcji.
- Aktualizacje dokumentacji (README + przewodniki front/back).

## Pliki do recenzji
Backend:
- venom_core/core/orchestrator.py
- venom_core/core/models.py
- venom_core/core/tracer.py
- venom_core/core/slash_commands.py (nowy)
- venom_core/api/routes/system.py
- venom_core/api/routes/tasks.py
- venom_core/execution/skills/browser_skill.py
- venom_core/execution/skills/web_skill.py
- venom_core/agents/researcher.py

Frontend (web-next):
- web-next/components/cockpit/cockpit-home.tsx
- web-next/components/cockpit/conversation-bubble.tsx
- web-next/components/ui/markdown.tsx
- web-next/hooks/use-api.ts
- web-next/lib/types.ts
- web-next/lib/slash-commands.ts (nowy)
- web-next/lib/markdown-format.ts (nowy)
- web-next/tests/smoke.spec.ts
- web-next/tests/markdown-format.test.ts (nowy)
- web-next/app/globals.css
- web-next/README.md

Testy (pytest):
- tests/test_slash_commands.py (nowy)
- tests/test_llm_runtime_activation_api.py (nowy/zmiany)
- tests/test_computation_formatting.py (nowy)
- tests/test_memory_api.py (zmiany)
- tests/test_*_roi.py (nowe, pakiet ROI)

Docs:
- README.md
- docs/DASHBOARD_GUIDE.md
- docs/FRONTEND_NEXT_GUIDE.md
- docs/MODEL_MANAGEMENT.md
- docs/_done/075_prezentacja_wynikow_obliczen.md (nowy)
- docs/_done/076_pr_coverage_tests.md (nowy)
- docs/_done/076_pr_coverage_tests_report.md (nowy)
- docs/_done/079_kontener_chat_kompakt_fullscreen.md (nowy)
- docs/_done/080_slash_commands_tools_routing.md (nowy)

Konfiguracja:
- requirements.txt (ddgs zamiast duckduckgo-search)
- .coveragerc (nowy)

## Kryteria akceptacji
- Slash commands dzialaja w UI i backendzie z poprawnym wymuszeniem routingu.
- /gpt i /gem przelaczaja runtime z potwierdzeniem i poprawnym wykonaniem.
- Preferowany jezyk odpowiedzi jest respektowany (tlumaczenie gdy potrzeba).
- Researcher wykonuje search -> scrape -> streszczenie bez regresji.
- Wszystkie testy przechodza (pytest, Playwright smoke).
- Dokumentacja odzwierciedla nowe funkcje i endpointy.

## Testy
- pytest
- npm --prefix web-next run test:e2e

## Uwagi
- Do potwierdzenia: lista nowych testow ROI i ich zakres.
- Do potwierdzenia: czy przejsc na ddgs w calym srodowisku (wymaga instalacji).
