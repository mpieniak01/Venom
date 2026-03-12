# Venom Cockpit – Next.js frontend (MVP)

Szkielet nowego frontendu Venom (Cockpit, Flow Inspector, Brain, War Room).

## Wymagania
- Node 18.19+ (rekomendacja: 20.x)
- Działający backend FastAPI Venoma (domyślnie `http://localhost:8000`)

## Instalacja
```bash
cd web-next
npm install
```

## Konfiguracja
Ustaw adres backendu i WebSocket (nie commitujemy):
```bash
# .env.local
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000
```

W dev można użyć proxy z `next.config.ts` (`API_PROXY_TARGET` lub `NEXT_PUBLIC_API_BASE`).

## Uruchomienie
```bash
npm run dev    # http://localhost:3000
npm run build
npm run start
```

## Struktura
- `app/` – strony: Cockpit `/` (widok produkcyjny), Cockpit reference `/chat` (pełna kopia), Inspector `/inspector`, Brain `/brain`, Strategy `/strategy` (v2.0 - Ukryty/Hidden)
- `components/ui` – panele, karty, badge
- `lib/env.ts` – źródło adresów API/WS (env + fallback)
- `lib/api-client.ts` – fetch z obsługą błędów
- `lib/ws-client.ts` – klient WebSocket z autoreconnect
- `next.config.ts` – proxy do FastAPI (dev), output `standalone`

## Stack UI
- Tailwind CSS 4 + autorski `tailwind.config.ts` (system themingu oparty o tokeny CSS)
- shadcn/ui (Sheet, Accordion) na bazie Radix UI
- `framer-motion` (animacje chatu), `@tremor/react` (karty KPI)
- `react-zoom-pan-pinch` w Inspectorze (nawigacja po Mermaid)
- `lucide-react` (ikony), `tailwindcss-animate`

## Theming (globalny styl aplikacji)
- Dostępne motywy: `venom-dark`, `venom-light`.
- Rejestr motywów: `lib/theme-registry.ts` (`ThemeId`, `THEME_REGISTRY`, `DEFAULT_THEME`).
- Provider i runtime state: `lib/theme.tsx` (`ThemeProvider`, `useTheme`).
- Bootstrap bez migania: `app/layout.tsx` (ustawienie `data-theme` przed hydratacją).
- Priorytet źródeł motywu: `localStorage["venom-theme"]` (user override) > backend `UI_THEME_DEFAULT` (`/api/v1/config/runtime`) > `DEFAULT_THEME`.
- Persist preferencji: `localStorage` pod kluczem `venom-theme` + best-effort sync do backendu (`UI_THEME_DEFAULT`).
- Selektor UI: `components/layout/theme-switcher.tsx` (TopBar).

Dodawanie nowego motywu:
1. Dopisz ID i metadane do `lib/theme-registry.ts`.
2. Dodaj mapę tokenów w `app/globals.css` pod `html[data-theme="<id>"]`.
3. Dodaj etykiety i opisy i18n (`pl/en/de`) w `lib/i18n/locales/*`.
4. Rozszerz testy: `tests/theme-registry.test.ts`, `tests/theme-i18n-keys.test.ts`.

## System design / tokeny
- **Tokeny globalne** (`app/globals.css`):
  - `--radius-panel`, `--radius-card` – ustandaryzowane promienie dla paneli i kart
  - `--shadow-card` – cień stosowany w `glass-panel` i klasie pomocniczej `shadow-card`
  - `--surface-muted` + `surface-card` – półprzezroczyste tło z ramką, używane w overlayach i kartach list
  - `card-shell` + `card-base` – bazowy wzorzec kart (ramka/cień + neutralne tło)
  - `box-base` / `box-muted` / `box-subtle` – mniejsze boxy wewnątrz paneli (spójne tło + obrys)
- **Komponenty UI** (`components/ui`):
  - `Button` – warianty `primary/secondary/outline/ghost/subtle/warning/danger`, rozmiary `xs/sm/md`, domyślne `type="button"`
  - `IconButton` – opakowanie na ikonowe CTA (TopBar/Sidebar) z tymi samymi wariantami co `Button`
  - `ListCard` – sekcje list/akcji z opcjonalnym `badge`, `meta` oraz ikoną (QuickActions, Command Center, Alert/Notification Drawer)
  - `EmptyState` – spójne komunikaty w panelach z ikoną i opisem
  - `Panel` / `StatCard` – korzystają z tokenów promieni/cieni (glassmorphism) i stanowią podstawę kart Cockpitu
- **TopBar & overlaye**: wszystkie ikonowe akcje (Alert/Notifications/Command Palette/Quick Actions) używają `IconButton` i tokenów `surface-card`; QuickActions/Command/Alert/Notification Drawer bazują na `ListCard` + `EmptyState`.

## Funkcje dostępne w Cockpit (Next)
- Telemetria WS (`/ws/events`) z auto-reconnect
- Zadania: wysyłanie / listowanie (`/api/v1/tasks`), Lab Mode toggle
- Slash commands: `/gpt`, `/gem`, `/<tool>` z autouzupełnianiem i badge „Forced”
- Preferowany język odpowiedzi (PL/EN/DE) przekazywany do backendu jako `preferred_language`
- Kolejka: status + akcje pause/resume/purge/emergency stop (`/api/v1/queue/*`)
- Modele: lista / switch / instalacja (`/api/v1/models*`)
- Git: status + sync/undo (`/api/v1/git/*`)
- Cost Mode & Autonomy (`/api/v1/system/cost-mode`, `/api/v1/system/autonomy`)
- Tokenomics (`/api/v1/metrics/tokens`), usługi systemowe (`/api/v1/system/services`)
- Historia: ostatnie requesty + detail (`/api/v1/history/requests`)
- Flow: timeline mermaid dla wybranego requestu (kroki z `/history/requests/{id}`)
- Brain: graf wiedzy z Cytoscape (`/api/v1/knowledge/graph`), filtrowanie węzłów, podgląd detali
- Chart.js: trend tokenów (ostatnie próbki z `/metrics/tokens`)
- Lessons & Graph scan: `/api/v1/lessons`, `/api/v1/graph/scan`
- Flow: filtrowanie/kopiowanie kroków timeline, eksport JSON
- Brain: filtry lekcji po tagach, relacje węzłów, analiza plików (`/graph/file`, `/graph/impact`)
- War Room: dane roadmapy z `/api/roadmap` + raport statusu/kampania, renderowanie Markdown wizji/raportów
- Formatowanie wyników obliczeń w czacie (tabele/listy, KaTeX dla formuł)

## Kolejne kroki
- Dynamic import bibliotek (Chart.js, mermaid, Cytoscape) w trybie CSR.
- Testy E2E (Playwright) dla kluczowych ścieżek Cockpitu.

## Testy E2E (Playwright)
1. Uruchom backend FastAPI (port 8000). Frontend nie musi być ręcznie startowany — Playwright sam odpali `npm run dev -- --hostname 127.0.0.1 --port 3001` (domyślny port możesz zmienić zmienną `PLAYWRIGHT_PORT`).
2. W terminalu:
   ```bash
   cd web-next
   npm run test:e2e -- --reporter=list
   ```
   (opcjonalnie `BASE_URL=http://127.0.0.1:3001` gdy chcesz wymusić inny adres).
3. Profile uruchamiania:
   ```bash
   npm run test:e2e:smoke
   npm run test:e2e:smoke:academy
   npm run test:e2e:functional
   npm run test:e2e:profile:full
   ```
   `smoke` to szybki profil bez zależności od backend runtime; `smoke:academy` jest profilem backend-zależnym.
4. CI:
   - workflow `Web Next Playwright E2E` uruchamia domyślnie profil `smoke` na `push/pull_request`,
   - workflow cache’uje binaria Playwright (`~/.cache/ms-playwright`), co skraca pipeline o czas ponownego pobierania przeglądarek.
   - workflow generuje raport trendu niestabilności (`test-results/e2e/flakiness-summary.json` + `flakiness-history.jsonl`).
   - dla profili `smoke/functional` workflow egzekwuje quality gate (`min tests` + `max flaky rate`).
   - osobny workflow `Web Next Playwright Perf (Backend)` uruchamia profil wydajnościowy dla środowiska z backendem (manual `workflow_dispatch`).
5. Profil perf (backend):
   - używa `PERF_NEXT_BASE_URL`, `PERF_API_BASE` i dedykowanego progu `PERF_NEXT_LATENCY_BUDGET`,
   - tworzy `test-results/e2e/perf-summary.json` i failuje run, gdy przekroczony zostanie próg latency.
6. Raporty i materiały z nieudanych testów znajdują się w `web-next/test-results/`.

## Testy unit + coverage pod Sonar
Uruchamianie lokalne:

```bash
cd web-next
npm run test:unit:coverage
```

Raport coverage dla Sonara zapisuje się do:
- `web-next/coverage/lcov.info`

Uwaga:
- pliki raportów (`web-next/coverage/**`, `test-results/**`) są artefaktami lokalnymi/CI i nie powinny być commitowane do repo.
