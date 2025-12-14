# Plan migracji frontendu do Next.js

## 1. Cel i zakres
- Zastąpić obecną warstwę Jinja2 + statyczne JS/CSS (`web/templates`, `web/static`) nowym frontendem w Next.js (app router, TypeScript).
- Zachować pełną funkcjonalność Cockpitu (telemetria WebSocket, tworzenie zadań, metryki, kolejka, modele, git, historia), Flow Inspector, Brain (graf wiedzy) oraz War Room/Strategy.
- Backend FastAPI zostaje jako API i WebSocket (`/api/v1/**`, `/ws/events`, ewentualnie audio WS) – Next.js działa jako niezależny frontend z proxy do API.

## 2. Stan obecny (co migrujemy)
- Widoki: `index.html` (Cockpit), `flow_inspector.html` (mermaid flow), `brain.html` (graf Cytoscape), `strategy.html` (war room), `inspector.html`/`index_.html` (warianty), `_navbar.html` + `base.html`.
- Logika JS: głównie `web/static/js/app.js` (WebSocket telemetry, task send, metrics polling, queue governance, repo sync, models install/switch, history modal, tokenomics, cost mode, autonomy modal), `strategy.js`, ewentualne pliki dla Brain/Flow.
- Integracje backendu używane w UI:
  - WebSocket: `/ws/events` (logi, task/status feed; reconnection/backoff).
  - REST: `/api/v1/tasks`, `/api/v1/history/requests`, `/api/v1/metrics`, `/api/v1/git/*`, `/api/v1/lessons`, `/api/v1/graph/*`, `/api/v1/models*`, `/api/v1/scheduler/*`, `/api/v1/watcher/status`, `/api/v1/documenter/status`, `/api/v1/gardener/status`, `/api/v1/queue/*`, `/api/v1/system/*` (cost-mode, autonomy), `/api/v1/system/services`.
- Assets: `web/static/css/app.css`, `strategy.css`, czcionki z CDN, biblioteki z CDN (Chart.js, mermaid, DOMPurify, marked; Cytoscape w Brain).

## 3. Założenia techniczne migracji
- Next.js 14+ (app router) z TypeScript, ESLint, Prettier. Stylowanie: Tailwind albo CSS Modules/Styled-Components – decyzja w etapie 1 (prefer Tailwind + shadcn/ui, jeśli nie koliduje ze stylami).
- Konfiguracja `.env.local` z bazowym URL API (`NEXT_PUBLIC_API_BASE=https://...`) i WebSocket endpointem; w dev domyślnie `http://localhost:8000`.
  - **Uwaga**: `.env.local` nie powinien trafiać do repozytorium (podobnie jak obecny `.env`).
  - Należy również stworzyć odpowiednią konfigurację zgodną z istniejącym podejściem w projekcie (config.py/Settings z domyślnymi wartościami i fallbackami).
- Zachowanie SSR/ISR tam, gdzie ma sens (np. statyczne części Strategii), ale większość paneli real-time jako client components.
- Reużycie ikon/emoji z aktualnego UI; nowe fonty dopasowane do obecnej estetyki (dark dashboard).
- Funkcjonalnosci maja byc zachowane ze starego panelu ale wystandaryzowane do zunifikowanego wyglady nowego.

## 4. Plan etapowy
1) **Discovery i decyzje narzędziowe**
   - Potwierdź listę używanych endpointów (z `app.js`, `strategy.js`, backend routes) i format payloadów.
   - Wybierz stack UI (Tailwind + Radix/shadcn) i sposób importu bibliotek (Chart.js, mermaid, Cytoscape) w Next.
   - Zaplanuj proxy w Next (`next.config.js` rewrites na `/api` i `/ws` w dev).
2) **Szkielet projektu Next**
   - Utwórz katalog `web-next/` (lub zastąp `web/` po cutover), `npx create-next-app` z TS, usuń boilerplate.
   - Dodaj podstawowe layouty: `app/layout.tsx`, global theme, navbar/footer, ogólny układ 2-kolumnowy dla Cockpitu.
   - Wprowadź system design tokens (kolory, spacing) + podstawowy dark theme.
3) **Warstwa komunikacji (API + WS)**
   - Stwórz `lib/apiClient.ts` (fetch z base URL, obsługa błędów, typy Pydantic) i `lib/wsClient.ts` (autoreconnect, heartbeats).
   - Zaimplementuj hooki do kluczowych obszarów: `useTelemetryFeed` (WS `/ws/events`), `useMetrics`, `useQueueStatus`, `useTasks`, `useHistory`, `useModels`, `useGitStatus`, `useSystemSettings` (cost/autonomy), `useGraph`, `useLessons`.
   - Rozważ React Query/SWR dla cachingu/pollingu; ustal harmonogram odpytań zgodny z obecnym UI (metrics 5s, queue 5s, repo 15s itp.).
4) **Migracja widoków funkcjonalnych**
   - **Cockpit**: chat + task submit (Lab Mode), live feed/logs, metrics, integrations matrix, active operations, live terminal, queue governance (pause/resume/purge/emergency stop), widget grid, history modal, tokenomics & cost mode toggle, autonomy modal, repo status.
   - **Flow Inspector**: lista tasków + timeline z mermaid, szczegóły kroków, odświeżanie.
   - **Brain (graf)**: render grafu (Cytoscape/vis.js) na bazie `/api/v1/graph/summary`/`scan`, filtry/widoki.
   - **War Room/Strategy**: wizja, KPIs, milestones, roadmapa (API z `strategy.js`), akcje przycisków.
   - **Pozostałe**: ewentualny Inspector/index_ – zdecydować, czy łączymy z Cockpitem czy robimy osobną stronę.
   - Dodaj fallbacki/empty states i obsługę błędów (toast/notification system).
5) **Styling i UX**
   - Przeniesienie istniejących motywów (ciemny) w nowy system stylów; dopracowanie responsywności (mobile/desktop).
   - Zamiana CDN na npm (Chart.js, mermaid, DOMPurify, marked, Cytoscape) + dynamic import tam, gdzie potrzebne CSR.
6) **Integracja i konfiguracja**
   - Next dev podłączony do działającego backendu FastAPI (CORS lub proxy).
   - Skrypty w `package.json` (`dev`, `build`, `start`, `lint`), aktualizacja README z instrukcją uruchomienia frontendu.
   - Dodanie CI dla lint/build (ESLint, Prettier, ewentualne testy jednostkowe) zgodnie z istniejącymi praktykami w projekcie (pre-commit + Black + Ruff).
7) **Testy i cutover**
   - Test ręczny krytycznych ścieżek (task submit, telemetry feed, queue actions, model install/switch, git sync/undo, history, graph, strategy flow).
   - E2E smoke (Playwright/Cypress) dla najważniejszych ekranów, jeśli czas pozwoli.
   - Po potwierdzeniu parity: odpięcie Jinja templates z FastAPI lub pozostawienie jako fallback; aktualizacja serwowania statyków, by wskazywać na build Next (`.next/out` lub `next start` za reverse proxy).

## 5. Artefakty do dostarczenia
- Repo/katalog `web-next` z gotowym Next.js, skonfigurowanym proxy do FastAPI.
- Warstwa API/WS z typami + hookami.
- Strony Cockpit, Flow Inspector, Brain, Strategy z funkcjonalnością 1:1 z obecną wersją.
- Dokumentacja uruchomienia i konfiguracji (`docs/DASHBOARD_GUIDE` update lub nowy `docs/FRONTEND_NEXT_GUIDE.md`).
- Testy:
  - Testy jednostkowe i integracyjne dla komponentów frontendu (Jest/Vitest/React Testing Library).
  - Testy E2E (Playwright/Cypress, jeśli wdrożone).
  - Dokumentacja testowania (opis uruchamiania, zakres pokrycia).

## 6. Ryzyka i mitigacje
- **Niezgodność API**: ustalić kontrakty (schematy odpowiedzi) na starcie; dodać typy i walidacje runtime.
- **WS stabilność**: implementować backoff i sygnalizację reconnect; fallback na polling dla krytycznych metryk.
- **Biblioteki w CSR**: mermaid/Chart.js/Cytoscape wymagają dynamic importu w Next – planować komponenty klientowe (client components).
- **Różnice stylów**: jeśli Tailwind, wyekstrahować kolory/spacing z `app.css`, uniknąć podwójnego stylowania.
- **Kompatybilność wersji Next.js i bibliotek zewnętrznych**: ryzyko niezgodności wersji Next.js (np. 14+ vs. potencjalne 15/16) z React, TypeScript, Chart.js, mermaid, Cytoscape itp.
  - **Mitigacja**:
    - Przed migracją i przy każdej aktualizacji sprawdzić peerDependencies i changelogi tych bibliotek.
    - Wykonać testy smoke po podniesieniu wersji.
    - W razie potrzeby zablokować wersje w `package.json` lub rozważyć downgrade/alternatywy.
    - W fazie discovery potwierdzić minimalne i maksymalne wspierane wersje kluczowych zależności.

## 7. Następne kroki wykonawcze (do rozpoczęcia migracji)
- Utworzyć lub zaktualizować plik opisu zadania w `docs/_to_do` zgodnie z wytycznymi projektu (numer, cel, Definition of Done, notatki). Dokument powinien zawierać jasno określone kryteria DoD dla całej migracji, aby po spełnieniu wszystkich warunków można było przenieść zadanie do `docs/_done`.
- Potwierdzić strukturę katalogu (`web-next/` vs zastąpienie `web/`) i wybór stacku stylów.
- Wygenerować projekt Next.js i skonfigurować proxy do `http://localhost:8000`.
- Zaimportować typy z Pydantic (ręcznie lub generacja `openapi-typescript`), stworzyć warstwę klienta i placeholdery stron.

## 8. Postęp implementacji (aktualizacja)
- Cockpit Next: realtime telemetry, zadania, kolejka, modele/git/cost/autonomy + tokenomics oraz wykres Chart.js trendu tokenów, podgląd historii z detale `/history/requests`.
- Flow Inspector: lista historii + dynamiczny timeline mermaid generowany z kroków `/history/requests/{id}`, panel kroków z filtrowaniem/eksportem.
- Brain: graf Cytoscape z filtrowaniem, highlight tagów lekcji, panel relacji, statystyki LessonsStore, akcja skanowania `/api/v1/graph/scan`, analiza pliku (`/graph/file`, `/graph/impact`), podgląd szczegółów węzła.
- Strategy (War Room): integracja z `/api/roadmap`, raport statusu i kampania, formularz tworzenia wizji, renderowanie Markdown wizji/raportów/stanu.
- Playwright smoke test (`npm run test:e2e`) oczekuje uruchomionego Nexta (BASE_URL) i weryfikuje podstawowe ekrany Cockpit/Flow/Brain.
- 2025-12-13: Potwierdzony przebieg smoke suite (`BASE_URL=http://127.0.0.1:3001 npm run test:e2e -- --reporter=list`) przy działającym `npm run dev` (Next przełączył się na port 3001, bo 3000 był zajęty). 3/3 testy zielone, artefakty w `web-next/test-results/` dołączone do zadania.
- 2025-12-13 (wieczór): Zwolniono port 3000 (ubita zaległa instancja Next), wystartowano świeży `npm run dev` na domyślnym porcie i uruchomiono smoke suite ponownie (`BASE_URL=http://127.0.0.1:3000 npm run test:e2e -- --reporter=list`) – ponownie komplet zielonych testów, dzięki czemu dev-flow wrócił na standardowy adres.
- 2025-12-13 (następny krok): Tokenomics Chart.js korzysta już z dynamicznego importu (`import("chart.js/auto")` wywoływane w `TokenChart`) – zgodnie z planem etap 5 „Styling i UX” ograniczamy wczytywanie ciężkich bibliotek do client components.
