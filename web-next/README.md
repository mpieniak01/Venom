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
- `app/` – strony: Cockpit `/` (widok produkcyjny), Cockpit reference `/chat` (pełna kopia), Inspector `/inspector`, Brain `/brain`, Strategy `/strategy`
- `components/ui` – panele, karty, badge
- `lib/env.ts` – źródło adresów API/WS (env + fallback)
- `lib/api-client.ts` – fetch z obsługą błędów
- `lib/ws-client.ts` – klient WebSocket z autoreconnect
- `next.config.ts` – proxy do FastAPI (dev), output `standalone`

## Stack UI
- Tailwind CSS 4 + autorski `tailwind.config.ts` (ciemny motyw, glassmorphism)
- shadcn/ui (Sheet, Accordion) na bazie Radix UI
- `framer-motion` (animacje chatu), `@tremor/react` (karty KPI)
- `react-zoom-pan-pinch` w Inspectorze (nawigacja po Mermaid)
- `lucide-react` (ikony), `tailwindcss-animate`

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
3. Raporty i materiały z nieudanych testów znajdują się w `web-next/test-results/`.
