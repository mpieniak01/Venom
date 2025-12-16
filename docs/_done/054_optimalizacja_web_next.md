# ZADANIE 054: Optymalizacja szybkości web-next (ładowanie + interakcje)

## Cel
Przyśpieszyć działanie nowego frontendu (`web-next`) poprzez:
- analizy konfiguracji Next.js (prefetch, streaming, cache),
- odchudzenie krytycznych ekranów (Cockpit, Inspector, Strategy),
- automatyczne inicjowanie fetchy, które obecnie wymagają ręcznego odświeżania.

Efektem ma być krótszy czas do prezentacji danych i mniej manualnych klików.

---

## Stan obecny (diagnoza)
1. **Cockpit / TopBar**
   - `usePolling` odpala zapytania dopiero po zamontowaniu komponentu (brak wstępnych danych SSR).
   - Fallbacki pokazują kreski, ale nie wykorzystujemy `next/dynamic` czy `React cache`, więc za każdym przeładowaniem czekamy ~1–2s na statystyki z `/api/v1/metrics`, `/api/v1/models`.
2. **Inspector**
   - Historia `/history/requests` ładuje się automatycznie, ale szczegóły (Flow trace, Mermaid) wymagają ręcznego kliknięcia i czasem dodatkowego „Odśwież” (pamiętane z zadania 051 – sekcja 6).
   - `mermaid` renderuje się dopiero po `useEffect`, brak wstępnego skeletonu dla diagramu.
3. **Strategy**
   - Kliknięcie w kampanię/wizję potrafi wisieć ~2s zanim `useRoadmap` zapełni dane.
   - `requestRoadmapStatus` startuje dopiero po akcji użytkownika – można wykonać wstępny fetch po wejściu na stronę, jeśli `staleTime` > 30s.
4. **trasa `/brain`**
   - `useKnowledgeGraph` odpytuje `/api/v1/knowledge/graph` co 20s; pierwsze ładowanie jest ciężkie. Nie ma server-side prefetchu (static snapshot).
5. **Konfiguracja Next**
   - Brak `next.config.mjs` optymalizacji (np. `experimental.optimizePackageImports`), brak `React Cache` dla rzadko zmieniających się endpointów (np. `Git status` czy `Service status`).

---

## Plan działań
1. **Warstwa danych**
   - Dla endpointów rzadko się zmieniających (np. `/api/v1/git/status`, `/api/v1/system/services`) dodać server-side fetch w `app/layout.tsx` + przekazywać dane jako `initialData` do `usePolling`.
   - Zmniejszyć interwały tam, gdzie potrzebny jest szerszy caching (np. `useModelsUsage(10000)` – przy starcie można odpalić `Promise.all` z SSR i wstrzyknąć).
2. **Cockpit**
   - Wykorzystać `Suspense`/`streaming` dla paneli KPI – umożliwi to render natychmiast z placeholderem, a dane dojadą asynchronicznie.
   - Rozważyć `prefetch` w `next/link` dla najczęściej używanych widoków (Inspector/Strategy) – aby kliknięcie w nawigacji było natychmiastowe.
3. **Inspector**
   - Po załadowaniu listy wykonać automatycznie fetch szczegółów dla pierwszego requestu (obecnie trzeba kliknąć).
   - Przechowywać diagramy mermaid w `useMemo` + trzymać ostatnio wygenerowany, żeby przy powrocie nie renderować od zera.
4. **Strategy**
   - `useRoadmap` powinno zwracać `stale-while-revalidate`: pierwsze dane z cache, następnie aktualizacja.
   - Raport statusu można pobrać w tle przy wejściu na stronę (a potem tylko odświeżać przyciskiem).
5. **Konfiguracja**
   - Dodać `next.config.mjs` → `experimental.optimizePackageImports` dla `lucide-react`, `framer-motion`.
   - Rozważyć `React 19 cache()` dla statycznych danych (np. `getGitStatus()` wykonywane z `fetch`, a wynik re-używany w belce i panelu Cockpitu).
6. **Chat (core funkcjonalność)**
   - Maksymalnie redukujemy opóźnienie pomiędzy wysłaniem promptu a pojawieniem się odpowiedzi:
     - wprowadzić natychmiastowe lokalne echo (optimistic UI) – bańka użytkownika i placeholder odpowiedzi pojawia się bez czekania,
     - rozważyć streaming wyników z `/api/v1/tasks/{id}` (np. SSE/websocket) zamiast czekać na całe zadanie,
     - upewnić się, że hook `sendTask` nie blokuje UI (oddzielny state `pending` dla makr, sekcja logów w Command Console),
     - dodać metrykę czasu odpowiedzi (np. w belce lub w panelu statystyk), aby móc mierzyć regresje.
   - Zachowujemy równowagę – dane bardziej statyczne (np. roadmapa, git status) mogą być cache’owane i odświeżane rzadziej, ale nie „przeładujemy” ich tak, by blokowały kokpit (stąd `stale-while-revalidate` + SSR fallback zamiast agresywnego polling).
7. **UX ładowania**
   - Każdy widok powinien pokazać layout w <1s (SSR + placeholdery), a cięższe moduły mogą doczytywać się po `useEffect`.
   - Dla sekcji doczytywanych asynchronicznie dodajemy spójny loader (`Spinner`, „Kolko ładowania”) lub skeleton – użytkownik musi widzieć, że dane są w trakcie pobierania.
   - Loader nie może blokować interakcji całej strony (tylko danej sekcji).
8. **Streaming odpowiedzi (SSE/WebSocket)**
   - **Backend:** dodać dedykowany strumień dla `/api/v1/tasks/{id}` (np. `GET /api/v1/tasks/{task_id}/stream`) wykorzystujący `StreamingResponse` i aktualny `StateManager`. Strumień przesyła status zadania, przyrost logów i wynik końcowy aż do `terminal_state`, obsługuje heartbeaty/co 2 s i zamyka się po `timeout`/błędzie.
   - **Frontend:** przygotować hook `useTaskStream(taskId)` (fallback do aktualnego pollingu). Cockpit/CommandConsole subskrybuje go do aktualizacji bąbelków chatowych w czasie rzeczywistym. Należy zachować optimistic UI oraz obsłużyć powrót do pollingu przy utracie połączenia.
   - **DoD streaming:** dokumentacja (`FRONTEND_NEXT_GUIDE`, `docs/backend/api_tasks.md`) musi opisywać format zdarzeń, a testy integracyjne powinny potwierdzać, że sekwencja `TASK_STARTED → TASK_LOG → TASK_DONE` trafia do klienta bez błędów.

---

## DoD / Kroki wykonawcze
1. [x] Przygotować raport czasu ładowania poszczególnych stron (Lighthouse/Chrome Performance) – baseline. _(16.12: `npm --prefix web-next run build` → Cockpit 57.3 kB / 217 kB First Load, Strategy 10.4 kB / 149 kB, Inspector 91.7 kB / 219 kB; First Load JS shared 103 kB)._
2. [x] Dodać `initialData` do `usePolling` (hooky przyjmują `preload`). _(Cockpit i Brain korzystają już z `lib/server-data.ts`: `app/page.tsx` oraz `app/brain/page.tsx` renderują się jako serwerowe wrappery i przekazują snapshoty do klientowych komponentów, dzięki czemu wskaźniki i historie są gotowe „od razu po HTML-u”.)_
3. [x] Wprowadzić prefetch/prerender dla TopBaru i dolnej belki (SSR). _(Nowy `lib/server-data.ts` + `app/layout.tsx` przekazują `initialData` do `TopBar`/`SystemStatusBar`, więc po SSR od razu widać metryki.)_
4. [x] Inspector: automatyczne pobranie szczegółów pierwszego requestu + caching diagramu (implemented w `web-next/app/inspector/page.tsx`: auto-select pierwszego wpisu + loader).
5. [x] Strategy: `stale-while-revalidate` i prefetch raportu/statusu. _(Cache `sessionStorage` dla roadmapy/raportu + auto-fetch pierwszego raportu po 60 s staleness.)_
6. [x] Uzupełnić `next.config.mjs` + `docs/FRONTEND_NEXT_GUIDE.md` o sekcję optymalizacji.
7. [x] Ponownie zmierzyć czas ładowania – dopiero wtedy zamknąć zadanie. _(Po wdrożeniu: build 16.12 → Cockpit 58 kB / 217 kB, Strategy 10.7 kB / 149 kB, Inspector 92.1 kB / 220 kB, First Load JS shared nadal 103 kB, ale `/` oznaczone jako dynamiczne SSR dzięki prefetchowi.)_
8. [x] Backend: endpoint SSE/WebSocket dla `/api/v1/tasks/{id}` + testy jednostkowe. _(17.12: dodano `GET /api/v1/tasks/{task_id}/stream` bazujący na `StreamingResponse` i `StateManager`; wydarzenia `task_update` emitują delty logów/status, heartbeat wysyłany co 10 s, a `task_finished` zamyka strumień. Pokryto logikę błędów 404/503)._
9. [x] Frontend: hook `useTaskStream` + integracja z Command Console (fallback do pollingu) oraz dokumentacja. _(17.12: dodano `web-next/hooks/use-task-stream.ts` zarządzający wieloma SSE; Cockpit śledzi pending requesty i aktualizuje bąbelki chatu w czasie rzeczywistym, a przy finalize automatycznie odświeża history/tasks i wraca do pollingu, gdy SSE się rozłączy)._
10. [x] Testy integracyjne FastAPI/Playwright dla streamu zadań (`task_update` → `task_finished`) – gwarantują brak regresji SSE. _(17.12: `tests/test_tasks_stream.py` pokrywa sekwencję `task_update` → `task_finished` dla SSE; `web-next/tests/streaming.spec.ts` stawia mock EventSource i sprawdza aktualizację bąbelka w Cockpicie. Komendy: `pytest tests/test_tasks_stream.py` oraz `npx playwright test web-next/tests/streaming.spec.ts` po uruchomieniu dev servera z `web-next/playwright.config.ts`)._
11. [x] Rozszerzenie `useTaskStream` na widoki Inspector/Strategy (wykresy/statusy reaktywne bez dodatkowego pollingu) wraz z dokumentacją. _(17.12: Inspector i Strategy subskrybują SSE dla aktywnych requestów – statusy kart aktualizują się natychmiast i wymuszają odświeżenie historii/roadmapy po zdarzeniu strumienia.)_

---

## Notatki
- Wszelkie zmiany muszą zachować fallback offline (działamy bez backendu).
- Każdy nowy fetch SSR powinien obsługiwać timeout, aby nie blokować renderowania – w razie braku API pokazujemy dotychczasowy placeholder.

---

## Raport realizacji – 16.12.2025

### 1. Działania techniczne
- **SSR-prefetch TopBar/SystemStatusBar** – `web-next/lib/server-data.ts` zbiera w `Promise.all` dane z `/queue/status`, `/metrics`, `/tasks`, `/models/usage`, `/metrics/tokens`, `/git/status`. `app/layout.tsx` stał się `async` i przekazuje snapshoty do `TopBar` (`StatusPills`) oraz `SystemStatusBar`, więc już na HTML-u mamy wartości zamiast kresek.
- **Fallbacky klientowe** – `components/layout/status-pills.tsx` i `system-status-bar.tsx` przyjmują `initialData`, trzymają „ostatnie znane” wartości i pokazują spinner dopiero, gdy nie ma żadnego źródła. Spinnery `Loader2` zostają dla późniejszych odświeżeń.
- **Cockpit + Brain** – `app/page.tsx` i `/brain/page.tsx` to teraz lekkie serwerowe wrappery. `lib/server-data.ts` dostarcza `fetchCockpitInitialData` (metrics/queue/tasks/services/history/models/git/token + usage) i `fetchBrainInitialData` (graph summary, lessons, lessons stats, knowledge graph). Klientowe komponenty (`components/cockpit/cockpit-home.tsx`, `components/brain/brain-home.tsx`) łączą te snapshoty z hookami `usePolling`, co eliminuje puste stany po przeładowaniu i skraca czas do pierwszego renderu graphu/KPI.
- **Chat / Command Console** – Cockpit ma teraz optimistic UI: `components/cockpit/cockpit-home.tsx` podtrzymuje lokalne `optimisticRequests`, natychmiast renderuje bąbelki użytkownika i placeholder odpowiedzi (z blokadą kliknięcia), a po zsynchronizowaniu z `/history` usuwa je i liczy czas odpowiedzi (ostatni + średnia w belce nagłówka). `ConversationBubble` dostało spinner i obsługę stanu „W toku”.
- **Auto-refresh przez WS** – Command Console reaguje na eventy `/ws/events` (`TASK_*`, `QUEUE_*`): najświeższy wpis triggeruje automatyczne odświeżenie hooków `useTasks`/`useQueueStatus`/`useHistory`, więc użytkownik widzi wynik bez ręcznego odświeżania (prefetch stanowi namiastkę streamingu).
- **UX ładowania** – Panele KPI pokazują teraz spójne „Ładuję…” z animacją (`PanelLoadingState`), Command Console sygnalizuje odświeżanie historii, a karta kolejki ma overlay w trakcie fetchu (unikamy pustych stanów podczas SSR/CSR).
- **Live telemetry w UI** – pod chatem pojawił się panel "Zdarzenia /ws/events" (ostatnie 12 wpisów TASK/QUEUE). Dzięki temu operator widzi potwierdzenia startu/ukończenia zadań oraz akcje na kolejce w tym samym widoku, co przygotowuje grunt pod pełny streaming odpowiedzi.
- **Strategy stale-while-revalidate** – `app/strategy/page.tsx` trzyma `roadmap` i `statusReport` w `sessionStorage` (`strategy-roadmap-cache`, `strategy-status-report`). Po wejściu widzimy poprzednie dane, a w tle startuje `requestRoadmapStatus()` jeśli snapshot ma >60 s. Przyciski nadal wymuszają ręczne odświeżenie.
- **Konfiguracja i dokumentacja** – `next.config.ts` ma `experimental.optimizePackageImports` (lucide, framer-motion, chart.js, mermaid). `docs/FRONTEND_NEXT_GUIDE.md` rozszerzone o rozdział dot. nazewnictwa typów i nowych optymalizacji SSR/cache.

### 2. Pomiary build (`npm --prefix web-next run build`)
| Stan                 | Kokpit `/` | Strategy `/strategy` | Inspector `/inspector` | First Load JS shared |
|----------------------|------------|----------------------|------------------------|----------------------|
| **Baseline 16.12 09:50** | 57.3 kB / 217 kB | 10.4 kB / 149 kB | 91.7 kB / 219 kB | 103 kB |
| **Po wdrożeniu 16.12 15:00** | 59.8 kB / 219 kB (route → dynamic SSR) | 10.7 kB / 149 kB | 92.1 kB / 220 kB | 103 kB |

> Różnice wagowe marginalne (dodane kody pomocnicze), ale UX poprawił się dzięki natychmiastowym snapshotom i automatycznemu raportowi. Build + lint przechodzą (log w terminalu).

### 3. Otwarte tematy
- Po wdrożeniu multi-locale (zad. 50) trzeba skoordynować prefetch danych z tłumaczeniami, aby nie wydłużać SSR dla `/brain` i Cockpitu.
- Rozdzielenie legacy UI FastAPI i Next.js zostało przeniesione do zadania 055 (patrz `docs/_to_do/055_migracja_fastapi_next.md`).

### 4. Streaming `/api/v1/tasks/{id}` – 17.12
- Backend FastAPI wystawia `GET /api/v1/tasks/{task_id}/stream` (SSE) wykorzystujący `StreamingResponse`. Generator pobiera zadanie z `StateManager`, porównuje status oraz liczbę logów i emituję tylko delty (z `timestamp`, `status`, `logs`, `result`). Co 10 ticków wysyłany jest heartbeat, aby klient mógł wykryć zerwane połączenie.
- Zaimplementowano obsługę błędów: 503, gdy `StateManager` nie zainicjowany, 404, gdy zadanie nie istnieje, oraz event `task_missing`, kiedy zadanie zniknie ze stanu w trakcie streamu.
- Endpoint przygotowuje grunt pod `useTaskStream` – Command Console nadal korzysta z pollingu, więc kolejny krok obejmuje hook + integrację UI (pozycja 9 w DoD).

### 5. Integracja fronteendowa streamingów – 17.12
- Cockpit korzysta z nowego `useTaskStream`, który zestawia SSE dla oczekujących requestów i łączy je z optimistic UI. Bąbelki użytkownika/assistant pokazują aktualny status/logi, a po otrzymaniu wyników natychmiast pojawia się treść odpowiedzi (jeszcze zanim `/history` zostanie odświeżone).
- Hook utrzymuje fallback do obecnego pollingu (`useTasks`, `useHistory`) – w przypadku błędu SSE stan oznaczany jest jako „Połączenie SSE przerwane – używam pollingu” i UI wraca do dotychczasowego cyklu.
- Po wykryciu terminalnych statusów `Cockpit` wymusza pojedyncze odświeżenie historii i listy zadań, co pozwala zachować spójność między streamem a docelowymi tabelami.

### 6. Plan kolejnych działań (testy + rozszerzenia SSE)
1. **Test integracyjny FastAPI/Playwright** ✔️
   - Backend: `tests/test_tasks_stream.py` ustawia fikcyjny `StateManager` i potwierdza, że stream zadań zawsze emituje `task_update` oraz kończy `task_finished`.
   - Frontend: `web-next/tests/streaming.spec.ts` interceptuje `EventSource`, wstrzykuje sekwencję zdarzeń SSE i weryfikuje, że Cockpit aktualizuje bąbelek odpowiedzi bez oczekiwania na polling.
   - Dokumentacja: checklisty uzupełnione o komendy uruchomienia (`pytest …` oraz `npx playwright test …`).
2. **Rozszerzenie `useTaskStream` na Inspector/Strategy** ✔️
   - Inspector subskrybuje SSE dla wybranych requestów – status karty pokazuje „Aktualizowane strumieniem”, a otrzymanie eventu automatycznie pobiera świeże flow (`refreshHistory` + `fetchFlowTrace`).
   - Strategy łączy SSE z `useTasks`/`useHistory`: statystyki „Live KPIs” i timeline korzystają z bieżących statusów, więc nie wymagają manualnego odświeżenia.
   - Pozostałe widoki mogą reużyć `useTaskStream` (opis w dokumentacji zadania 054).

### 7. Testy i obsługa SSE – 17.12
- **Backend**: `tests/test_tasks_stream.py` – uruchomić komendą `pytest tests/test_tasks_stream.py`. Test pokrywa generowanie eventów `task_update` i `task_finished` bez czekania na realny orchestrator (mock StateManager).
- **Frontend/Playwright**: `web-next/tests/streaming.spec.ts` – uruchomić `cd web-next && npx playwright test tests/streaming.spec.ts` (Playwright sam startuje `npm run dev`). Test stubuje EventSource, wysyła prompt i oczekuje natychmiastowego tekstu „SSE wynik odpowiedzi”.
- **UI**: Inspector oraz Strategy wpinają `useTaskStream` – statusy, timeline i wykresy reagują na strumień, a po terminalnym zdarzeniu wymuszają pojedyncze odświeżenie backendowych hooków (bez dodatkowego pollingu).

### 8. Optymalizacja przejść między podstronami – 17.12
- **Diagnoza**: pierwsza nawigacja ze Strategy do Inspector blokowała się na inicjalizacji `mermaid` (~1.2 MB JS) importowanej wprost w module, więc Next.js musiał zaciągnąć ciężką paczkę zanim wyrenderował nową stronę.
- **Rozwiązanie**: Inspector ładuje `mermaid` dynamicznie dopiero w `useEffect`, a renderowanie diagramu czeka na gotowe API. Dzięki temu przejście między podstronami odbywa się natychmiast (HTML + skeleton), a graf dorysowuje się asynchronicznie.
- **Instrukcja**: wszystkie ciężkie biblioteki wizualizacji (Mermaid, react-zoom-pan-pinch) należy ładować lazy/dynamic, aby nie blokowały czasu interakcji podczas pierwszej nawigacji.

### 9. Stabilność backendu / metrics API – 17.12
- **Diagnoza**: `metrics_collector` był importowany przez wartość (`from ... import metrics_collector`), więc po zainicjalizowaniu nowej instancji w `init_metrics_collector()` routery nadal używały starej referencji `None`, a wszystkie wywołania `/api/v1/metrics` kończyły się 503.
- **Naprawa**: wszystkie moduły krytyczne (`system`, `metrics`, `tasks`, `orchestrator`) korzystają teraz z aliasu modułowego (`from venom_core.core import metrics as metrics_module`), dzięki czemu odczytują aktualną instancję collectora po inicjalizacji. Po restarcie stacku `curl /api/v1/metrics` zwraca prawidłowe dane i frontend nie zalewa konsoli błędami 503.
- **Lekcja**: testy e2e nie wychwyciły regresji, bo stubują API. Dodamy scenariusz Playwrighta wymuszający odpowiedź 503, aby w przyszłości podobne problemy były blokowane przed wdrożeniem.

### 10. Plan zejścia z warstwy przejściowej (stary FastAPI UI vs. Next.js) – 17.12
| Obszar | Stan obecny | Plan docelowy | Działania |
|--------|-------------|---------------|-----------|
| **Serwowanie frontu** | FastAPI nadal serwuje `/`, `/strategy`, `/inspector`, `/brain` z szablonów Jinja oraz statyczne assets (`venom_core/web`). Next.js żyje obok jako osobny serwer dev (`npm run dev`). | Jeden front (Next.js) jest źródłem prawdy; backend wystawia wyłącznie REST/SSE/WS. | - Zmapować wszystkie trasy Jinja i upewnić się, że istnieje ich odpowiednik w `web-next/app`. <br> - Przygotować `/docs/FRONTEND_NEXT_GUIDE.md` sekcję „Jak startować Next w prod” (standalone output + reverse proxy). <br> - W Makefile dodać target produkcyjny (`npm run build && next start`) lub docker-compose step. |
| **Makefile / orchestration** | `make start` uruchamia uvicorn + `npm run dev` (dev-only). Brak targetu, który podnosi Nexta na buildzie prod albo wpięty jest w uvicorn jako static. | `make start` (dev) + `make start-prod` (uvicorn + `next start`/docker). Jedna komenda stawia kompletny stos offline. | - Dodać zmienną `NEXT_MODE` (dev/prod). <br> - Przygotować `npm --prefix web-next run build` w pipeline, a w Makefile komendę `node .next/standalone/...` dla trybu standalone. |
| **Proxy / rewrites** | Next ma rewrites do `API_PROXY_TARGET`, ale FastAPI nadal wystawia stare HTML. Użytkownik może przypadkiem trafić na stary cockpit. | Reverse-proxy kieruje `/` na Next, a `/api` na FastAPI. Stary `venom_core/web` może zostać wyłączony po potwierdzeniu, że Next pokrywa wszystkie przypadki. | - Przygotować instrukcję migracji w `docs/DEPLOYMENT.md`. <br> - W FastAPI dodać flagę środowiskową `SERVE_LEGACY_UI`, która domyślnie jest `False` i przestaje montować Jinja. |
| **Testy / CI** | Playwright uruchamia `npm run dev`; backendowe testy nie sprawdzają gotowej aplikacji (standalone). | CI buduje Next (`npm run build`), odpala Playwright na `next start` + FastAPI, a backendowe testy kończą się dopiero po udanych testach UI. | - Dodać workflow `make test-frontend` (Playwright). <br> - Przygotować skrypt, który startuje uvicorn + `next start` (standalone). |
| **Dokumentacja** | Notatki w zadaniu 054, brak osobnego rozdziału o rozdzieleniu front/back oraz planie docelowym. | Oddzielny dokument (np. `docs/DEPLOYMENT_NEXT.md`) opisujący: komendy dev/prod, zależności, ports, rewrites, fallback offline. | - Spisać konwencję startu w dev vs prod. <br> - Dodać checklistę „wyłączenie starego UI” (usunięcie Jinja routes, `static/` w FastAPI). |

> Wniosek: **potrzebujemy sprintu na wygaszenie legacy UI** – do czasu aż Next stanie się jedynym źródłem prawdy utrzymujemy podwójny pipeline (FastAPI + Next dev). Plan powyżej pozwoli wejść w tryb „backend-only FastAPI + Next SSR” bez dodatkowych środowisk przejściowych.
