# FRONTEND NEXT – ARCHITEKTURA I CHECKLISTA

Dokument rozszerza `docs/PL/DASHBOARD_GUIDE.md` o informacje specyficzne dla wersji `web-next`. Zawiera:
1. Architekturę i katalogi Next.js (App Router, SCC – Server/Client Components) oraz konfigurację środowiska.
2. Opis źródeł danych wykorzystywanych przez kluczowe widoki (Brain, Strategy, Cockpit) – łącznie z fallbackami.
3. Checklistę testów ręcznych i Playwright, która potwierdza gotowość funkcjonalną.
4. Kryteria wejścia do **Etapu 29** i listę elementów uznanych nadal za „legacy”.

---

## 0. Stack i struktura `web-next`

### 0.1 Katalogi
```
web-next/
├── app/                    # App Router, server components (`page.tsx`, layouty, route handlers)
│   ├── page.tsx            # Cockpit
│   ├── chat/page.tsx       # Cockpit reference (pełny układ)
│   ├── brain/page.tsx      # Widok Brain
│   ├── inspector/page.tsx  # Flow Inspector
│   ├── strategy/page.tsx   # Strategy / KPI (v2.0 - Ukryty)
│   └── config/page.tsx     # Configuration Panel (Zadanie 060)
├── components/             # Wspólne komponenty (layout, UI, overlaye)
├── hooks/                  # Hooki danych (`use-api.ts`, `use-telemetry.ts`)
├── lib/                    # Narzędzia (i18n, formatery, API client)
├── public/                 # statyczne zasoby (`meta.json`)
├── scripts/                # narzędzia buildowe (`generate-meta.mjs`, `prepare-standalone.mjs`)
└── tests/                  # Playwright (smoke suite)
```

### 0.2 S C C – zasady (Server / Client Components)
- Domyślnie komponenty w `app/*` są serwerowe – nie dodajemy `"use client"` jeżeli nie musimy.
- Komponenty interaktywne (chat, belki, overlaye) deklarują `"use client"` i korzystają z hooków Reacta.
- `components/layout/*` to mieszanka: np. `SystemStatusBar` jest klientowy (aktualizuje się w czasie rzeczywistym), natomiast sekcje Brain/Strategy pozostają serwerowe z lazy-hydrationem tylko tam, gdzie to konieczne.
- Re-używamy stylów przez tokeny (`surface-card`, `glass-panel` itd.) w `globals.css`.
- **Konwencje nazewnictwa:** wszystkie interfejsy/typy w `web-next/lib/types.ts` używają angielskich nazw (`Lesson`, `LessonsStats`, `ServiceStatus`, `Task`, `Metrics`, `ModelsUsageResponse`). Nie dopisujemy równoległych aliasów PL ani skrótów w importach – zamiast `Lekcja` używamy `Lesson`, zamiast `StatusSłużba` → `ServiceStatus`. Translacje dla UI żyją w `lib/i18n`, ale kod/typy zachowują jednolity, angielski prefiks, żeby uniknąć dryfowania konwencji przy dodawaniu nowych modułów.

### 0.3 Skrypty NPM / workflow
| Komenda                               | Cel                                                                                   |
|---------------------------------------|----------------------------------------------------------------------------------------|
| `npm --prefix web-next install`       | Instalacja zależności                                                                |
| `npm --prefix web-next run dev`       | Dev server (Next 15) z automatyczną generacją meta (`predev → generate-meta.mjs`)     |
| `npm --prefix web-next run build`     | Build prod, generuje `public/meta.json` i standalone `.next/standalone`               |
| `npm --prefix web-next run test:e2e`  | Playwright smoke w trybie prod (15 scenariuszy Cockpit + belki)                       |
| `npm --prefix web-next run lint`      | Next lint (ESLint 9)                                                                  |
| `npm --prefix web-next run lint:locales` | Walidacja spójności słowników i18n (`scripts/check-locales.ts`)                     |

### 0.4 Konfiguracja i proxy
- backend FastAPI domyślnie nasłuchuje na porcie 8000 – front łączy się poprzez *rewrites* Next (patrz `next.config.mjs`) lub poprzez zmienne:
  - `NEXT_PUBLIC_API_BASE` – baza `/api/v1/*` (gdy uruchamiamy dashboard w trybie standalone)
  - `NEXT_PUBLIC_WS_BASE` – WebSocket event stream (`ws://localhost:8000/ws/events`)
  - `API_PROXY_TARGET` – bezpośredni URL backendu; Next buduje rewritera, więc w trybie dev nie trzeba modyfikować kodu.
- `scripts/generate-meta.mjs` zapisuje `public/meta.json` z `version`, `commit`, `timestamp`. Dane konsumuje dolna belka statusu.

### 0.5 Optymalizacje ładowania (zad. 054)
- `lib/server-data.ts` wykonuje SSR-prefetch krytycznych endpointów (`/api/v1/metrics`, `/queue/status`, `/tasks`, `/models/usage`, `/metrics/tokens`, `/git/status`). Layout przekazuje je do `TopBar` (`StatusPills`) i `SystemStatusBar` jako `initialData`, dzięki czemu przy pierwszym renderze nie widać już pustych kresek.
- `StatusPills` i dolna belka pracują w trybie „stale-while-revalidate”: pokazują dane z SSR, a hook `usePolling` dociąga aktualizację po montowaniu (spinnery pojawiają się dopiero jeśli nie mamy żadnego snapshotu).
- `/strategy` posiada lokalny cache `sessionStorage` (`strategy-roadmap-cache`, `strategy-status-report`). Roadmapa jest prezentowana natychmiast po wejściu, a raport statusu pobiera się automatycznie w tle, jeśli poprzedni snapshot jest starszy niż 60 sekund. Cache nie blokuje ręcznego „Raport statusu” – kliknięcie wymusza nowe zapytanie.
- `next.config.ts` ma włączone `experimental.optimizePackageImports` dla `lucide-react`, `framer-motion`, `chart.js`, `mermaid`, co obcina JS „first load” i przyśpiesza dynamiczne importy ikon/animacji.
- Cockpit i Brain korzystają z serwerowych wrapperów (`app/page.tsx`, `app/brain/page.tsx`), które pobierają snapshot danych przez `fetchCockpitInitialData` / `fetchBrainInitialData`. Klientowe komponenty (`components/cockpit/cockpit-home.tsx`, `components/brain/brain-home.tsx`) łączą te snapshoty z hookami `usePolling`, więc KPI, lista modeli, lekcje i graf pokazują ostatni stan już po SSR i tylko dociągają aktualizacje po hydratacji.
- Command Console (chat) ma optimistic UI: `optimisticRequests` renderują bąbelki użytkownika + placeholder odpowiedzi jeszcze przed zwrotką API, blokują otwieranie szczegółów do czasu zsynchronizowania z `useHistory`, a `ConversationBubble` pokazuje spinner oraz raportuje ostatni czas odpowiedzi w nagłówku.
- Command Console obsługuje slash commands (`/gpt`, `/gem`, `/<tool>`) z autouzupełnianiem (max 3 propozycje) oraz badge „Forced” w odpowiedzi.
- Język UI (PL/EN/DE) jest przesyłany jako `preferred_language` w `/api/v1/tasks` i backend tłumaczy odpowiedź, jeśli wykryje inny język.
- Wyniki obliczeń (np. JSON/tablice) są formatowane w czacie do tabel/list; przy wykryciu formuł renderujemy KaTeX.

## 1. Brain / Strategy – Źródła danych i hooki

| Widok / moduł                     | Endpointy / hooki                                                                                              | Fallback / uwagi                                                                                           |
|----------------------------------|----------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| **Cockpit** – Statusy i kolejka  | `useMetrics`, `useQueueStatus`, `useHistory` → `/api/v1/metrics`, `/api/v1/queue/status`, `/api/v1/history/requests` | Brak backendu → `OverlayFallback` lub neutralne pillsy z komunikatem.                                       |
| **Cockpit** – Eventy na zywo     | `useTelemetry`, `useTaskStream` → `WS /ws/events`                                                               | Bez WS wylaczamy realtime i przechodzimy na polling.                                                       |
| **Brain** – Mind Mesh            | `useKnowledgeGraph` → `/api/v1/graph/summary`, `/api/v1/graph/scan`, `/api/v1/graph/file`, `/api/v1/graph/impact` | W przypadku błędu HTTP renderuje `OverlayFallback` i blokuje akcje (scan/upload).                          |
| **Brain** – Lessons & stats      | `useLessons`, `useLessonsStats`, `LessonActions` (tagi), `FileAnalysisForm`                                     | Brak danych wyświetla `EmptyState` z CTA „Odśwież lekcje”.                                                  |
| **Brain** – Kontrolki grafu      | `GraphFilterButtons`, `GraphActionButtons` + `useGraphSummary`                                                 | Wersje offline (np. brak `/api/v1/graph/summary`) pokazują badge `offline` w kartach BrainMetricCard.      |
### Strategy (Przesunięte do v2.0)

> [!NOTE]
> **Przesunięte do v2.0:** Ekran Strategii i powiązane funkcje (Wizja, KPI, Roadmapa) zostały przesunięte do wersji Venom v2.0. Kod pozostaje w `app/strategy`, ale jest ukryty z nawigacji w v1.0.

| **Strategy** – KPI / Vision      | `useRoadmap` (`/api/v1/roadmap`), `requestRoadmapStatus`, `createRoadmap`, `startCampaign`                      | Wszystkie akcje owinięte w `useToast`; w razie 4xx/5xx panel wyświetla `OverlayFallback`.                   |
| **Strategy** – Milestones/Tasks  | `RoadmapKpiCard`, `TaskStatusBreakdown` (wykorzystuje `/api/v1/roadmap` oraz `/api/v1/tasks` dla statusów)      | Brak zadań → komunikat „Brak zdefiniowanych milestone’ów” (EmptyState).                                     |
| **Strategy** – Kampanie          | `handleStartCampaign` pyta `window.confirm` (jak legacy), po czym wysyła `/api/campaign/start`.                 | W razie braku API informuje użytkownika toastem i nie zmienia lokalnego stanu.                              |
| **Config** – Usługi              | `/api/v1/runtime/status`, `/api/v1/runtime/{service}/{action}`, `/api/v1/runtime/profile/{profile}`             | Wyświetla live status usług (backend, UI, LLM, Hive, Nexus) z metrykami CPU/RAM. Akcje start/stop/restart.    |
| **Config** – Parametry           | `/api/v1/config/runtime` (GET/POST), `/api/v1/config/backups`, `/api/v1/config/restore`                         | Edycja whitelisty parametrów z `.env`, maskowanie sekretów, backup do `config/env-history/`, restart warnings. |
| **Config** – Audyt               | `/api/v1/audit/stream` (GET/POST)                                                                                 | Kanoniczny techniczny strumień audytu z jednoliniowymi wpisami i filtrami kanał/wynik.                      |

> **Notatka:** wszystkie hooki korzystają z `lib/api-client.ts`, który automatycznie pobiera bazowy URL z `NEXT_PUBLIC_API_BASE` lub rewritów Next. Dzięki temu UI działa zarówno na HTTP jak i HTTPS bez ręcznej konfiguracji.

---

## 1.1 Configuration Panel – Zarządzanie stosem (Zadanie 060)

### Cel
Panel konfiguracji (`/config`) pozwala zarządzać usługami Venom (backend, UI, LLM, moduły rozproszone) oraz edytować kluczowe parametry z poziomu UI, bez ręcznej edycji `.env`.

### Funkcjonalność

#### Panel "Usługi"
- **Kafelki statusów**: Każda usługa (backend, ui, llm_ollama, llm_vllm, hive, nexus, background_tasks) pokazuje:
  - Status (running/stopped/error)
  - PID i port
  - CPU i RAM
  - Uptime
  - Ostatni log
- **Akcje**: Przyciski start/stop/restart dla każdej usługi
- **Profile szybkie**:
  - **Full Stack**: Uruchamia wszystkie usługi
  - **Light**: Tylko backend i UI (bez LLM)
  - **LLM OFF**: Backend i UI, wyłącza modele językowe
- **Historia akcji**: Lista ostatnich 10 akcji z timestampem

#### Panel "Parametry"
- **Sekcje konfiguracji**:
  - Tryb AI (AI_MODE, LLM_SERVICE_TYPE, endpointy modeli, klucze API)
  - Komendy serwera LLM (VLLM_START_COMMAND, OLLAMA_START_COMMAND)
  - Hive – przetwarzanie rozproszone (ENABLE_HIVE, Redis config)
  - Nexus – distributed mesh (ENABLE_NEXUS, port, token)
  - Zadania w tle (auto-dokumentacja, gardening, konsolidacja pamięci)
  - Shadow Agent (desktop awareness)
  - Ghost Agent (GUI automation)
  - Avatar (audio interface)
- **Maskowanie sekretów**: API keys i tokeny są domyślnie maskowane, przycisk "pokaż" odkrywa wartość
- **Walidacja**: Frontend sprawdza obecność wartości, backend waliduje whitelistę
- **Backup**: Każdy zapis tworzy backup `.env` w `config/env-history/.env-YYYYMMDD-HHMMSS`
- **Restart warnings**: Po zapisie UI informuje, które komponenty wymagają restartu

#### Panel "Audyt"
- **Źródło kanoniczne**: `/api/v1/audit/stream`
- **Filtry**: po kanale API i wyniku
- **Wpisy**: kompaktowe jednoliniowe rekordy sortowane po czasie
- **Badge**: osobny badge kanału API i badge statusu

#### Info Box: Ollama vs vLLM vs ONNX
Panel zawiera sekcję informacyjną wyjaśniającą różnice między runtime'ami LLM:
- **Ollama (Light)**: Szybki start, niski footprint, single user
- **vLLM (Full)**: Dłuższy start, większy VRAM, benchmarki i testy wydajności
- **ONNX (Full/profil opcjonalny)**: Runtime in-process, lokalna ścieżka zgodna ze standardem ONNX, wymaga profilu ONNX LLM
- Link do `/benchmark` z sugestią porównania modeli

### Backend API

#### Runtime Controller
```
GET  /api/v1/runtime/status            # Lista usług z statusem, PID, CPU/RAM
POST /api/v1/runtime/{service}/{action} # start/stop/restart (service: backend, ui, llm_ollama, etc.)
GET  /api/v1/runtime/history           # Historia akcji (limit 50)
POST /api/v1/runtime/profile/{name}    # Aplikuj profil (full, light, llm_off)
```

#### Config Manager
```
GET  /api/v1/config/runtime            # Pobierz whitelistę parametrów (mask_secrets=true)
POST /api/v1/config/runtime            # Zapisz zmiany (updates: {key: value})
GET  /api/v1/config/backups            # Lista backupów .env
POST /api/v1/config/restore            # Przywróć backup (backup_filename)
```

#### Audit Stream
```
GET  /api/v1/audit/stream?limit=200    # Odczyt kanonicznego technicznego strumienia audytu
POST /api/v1/audit/stream              # Ingest technicznego zdarzenia audytu
```

### Bezpieczeństwo
- **Whitelist parametrów**: Tylko wybrane parametry (55 kluczy) są edytowalne przez UI
- **Maskowanie sekretów**: Pola zawierające "KEY", "TOKEN", "PASSWORD" są maskowane
- **Backup automatyczny**: Każda zmiana `.env` tworzy kopię zapasową
- **Restart notification**: UI informuje które usługi wymagają restartu po zmianie konfiguracji

### Testy
- Backend: `tests/test_runtime_controller_api.py`, `tests/test_config_manager_api.py`
- Frontend: TODO – Playwright scenarios dla nawigacji, start/stop, edycji parametrów

---

## 2. Testy – Brain / Strategy (manualne + Playwright)

### 2.1 Manual smoke (po każdym release)
1. **Brain**
   - `Scan graph` zwraca spinner i nowy log w „Ostatnie operacje grafu”.
   - Kliknięcie w węzeł otwiera panel z relacjami, tagami i akcjami (file impact, lessons).
2. **Strategy**
   - Odśwież roadmapę (`refreshRoadmap`) i sprawdź, że KPI/Milestones pokazują dane z API.
   - `Start campaign` → confirm prompt → komunikat sukcesu/błędu + log w toastach.

### 2.2 Playwright (do dodania / rozszerzenia)
| Nazwa scenariusza                    | Wejście / oczekiwania                                                                 |
|-------------------------------------|----------------------------------------------------------------------------------------|
| `brain-can-open-node-details`       | `page.goto("/brain")`, kliknięcie w pierwszy węzeł (seed data) → widoczny panel detali |
| `strategy-campaign-confirmation`    | Otwórz `/strategy`, kliknij „Uruchom kampanię”, sprawdź confirm + komunikat offline    |
| `strategy-kpi-offline-fallback`     | Przy wyłączonym backendzie widoczny `OverlayFallback` + tekst „Brak danych”.           |

> TODO: scenariusze powyżej dodajemy do `web-next/tests/smoke.spec.ts` po ustabilizowaniu CI. Dokument zostanie zaktualizowany wraz z PR-em dodającym testy.

---

## 3. Mapa bloków → etap 29

### 3.1 Checklist „legacy vs. next”
- [x] Sidebar / TopBar – korzystają z tokenów glass i wspólnych komponentów.
- [x] Cockpit – hero, command console, makra, modele, repo → wszystkie w stylu `_szablon.html`.
- [x] Brain / Strategy – opisane powyżej.
- [ ] Inspector – brak ręcznego „Odśwież” + panelu JSON (zadanie 051, sekcja 6).
- [ ] Strategy KPI timeline – wymaga realnych danych z `/api/v1/tasks` (zadanie 051, sekcja 6.3).

### 3.2 Kryteria wejścia do **Etapu 29**
1. **Parzystość funkcjonalna** – każde legacy view ma odpowiednik w `web-next`; brak duplikatów paneli.
2. **Komponenty współdzielone** – wszystkie listy/historie używają `HistoryList`/`TaskStatusBreakdown`.
3. **Testy** – Playwright obejmuje Cockpit, Brain, Inspector, Strategy + krytyczne overlaye.
4. **Dokumentacja** – niniejszy plik + README posiadają sekcję źródeł danych i testów.
5. **QA** – lista uwag z zadania 051 (sekcje 4–7) oznaczona jako ✅.

Po spełnieniu powyższych punktów można oficjalnie zamknąć etap 28 i przejść do 29 (np. optymalizacje wydajności, A/B testy UI).
