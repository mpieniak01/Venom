# PR 87: Optymalizacja czasów reakcji aplikacji

## Cel
Skrócić czas reakcji UI i backendu na akcje użytkownika oraz poprawić time‑to‑first‑token (LLM). Dokument zbiera obszary, diagnozę i propozycje optymalizacji.

## Zakres
- **Frontend (Next.js / web-next)**
- **Backend API**
- **LLM runtime**

## Obserwacje (wstępne)
- UI jest wrażliwy na opóźnienia w odpowiedziach /pollingu i LLM streaming.
- Największy koszt UX to **czas od kliknięcia do pierwszej widocznej reakcji**.
- LLM i backend potrafią blokować szybki feedback w Cockpit (np. opóźnienia w zapisie/odświeżaniu historii).
- Dodatkowy problem UX: **czas od wysłania wiadomości do pojawienia się jej w historii czatu** — obecnie zbyt długi, wymaga analizy i skrócenia.
- Zwiększanie częstotliwości odświeżeń **nie jest poprawnym rozwiązaniem** (często blokuje focus formularza). Preferowane są aktualizacje strumieniowe (SSE/WS) lub webhooki.
- Utrata wątku: model potrafi gubić kontekst (np. rozmowa o kwadracie, odpowiedź o sześcianie) — wymaga analizy łańcucha kontekstu i sposobu jego podawania.

## Obecny stan (obszary i źródła opóźnień)
### Frontend: Next.js / web-next
- Zbyt częsty polling (równoległe requesty co 10–15s).
- Duże komponenty klientowe z ciężkimi hookami (np. Cockpit).
- Brak lokalnych „optimistic updates” w niektórych miejscach UI.
- Zbyt szerokie re‑renderowanie (brak memoizacji na listach/wykresach).
- Koszt ładowania grafów (cytoscape) i renderów SVG.

### Backend API
- Zapytania agregujące statusy (runtime/queue/history) wykonywane równolegle bez cache.
- Brak cache na read‑only endpoints.
- Logika orchiestratora blokuje szybkie „ack” przy submit.

### LLM runtime
- Cold start modelu.
- Wysoki `max_tokens` lub duże prompty.
- Brak priorytetyzacji dla UI/komunikacji interaktywnej.

## Sprawozdanie stanu kodu: realne miejsca zysków
### Frontend (UI)
- `web-next/hooks/use-api.ts` — globalny polling registry uruchamia wiele niezależnych fetchy co 5–20s; w Cockpit aktywne jest kilka hooków równocześnie, co powoduje skoki renderów i sieci. Największy zysk: batching lub gate per‑view + odchudzenie payloadów.
- `web-next/hooks/use-api.ts` (`useSessionHistory`) — domyślny interwał 10s powoduje widoczny lag „wysłane → w historii”. Jeśli historia ma być natychmiastowa, trzeba event‑driven (SSE/WS) lub lokalne źródło prawdy.
- `web-next/components/cockpit/cockpit-home.tsx` — jedna ogromna komponenta z dużą liczbą stanów; każde odświeżenie danych (polling, clock) powoduje pełny re-render. Największy zysk: izolacja zegara i paneli w memoizowanych sub‑komponentach.
- `web-next/hooks/use-task-stream.ts` — SSE per request + throttle 250ms. Jest opóźnienie wynikające z połączenia throttlingu i backendowego pollingu; warto rozważyć natychmiastowy render pierwszego chunku i potem throttling.

### Backend API
- `venom_core/api/routes/tasks.py` — SSE działa jako polling co 0.25s na `StateManager` dla każdego taska. To ogranicza TTFT i skaluje CPU liniowo od liczby streamów. Największy zysk: event‑driven update zamiast pętli pollującej.
- `venom_core/core/streaming_handler.py` — `partial_emit_interval=0.25` + backendowy polling powodują „twarde” minimum latencji widoczności chunków. Potencjalny zysk: natychmiastowa emisja pierwszego fragmentu i rzadziej kolejne.
- `venom_core/core/orchestrator/session_handler.py` — przy dłuższych sesjach możliwe dodatkowe LLM call’e na streszczenie i memory lookup w ścieżce requestu. Zysk: asynchroniczne przygotowanie lub wyraźne progi, aby nie spowalniać odpowiedzi interaktywnej.

### LLM runtime
- `venom_core/agents/base.py` i `venom_core/utils/llm_runtime.py` — streaming działa, ale TTFT zależy od czasu uruchomienia modelu i długości promptu. Zysk: warm‑up modelu + skracanie promptów (historia, summary) dla szybkich odpowiedzi UI.

## Doprecyzowany plan: UX‑first i synchronizacja tylko przy interakcji
### Założenia UX
- Użytkownik **najpierw** wchodzi w aplikację, serwisy startują, strony się ładują; dopiero potem wchodzi w chat.
- Chat ma być **statyczny** do czasu interakcji; brak cyklicznego odświeżania boxów.
- Wpis użytkownika ma się pojawić **natychmiast** w historii (optimistic UI).
- Odpowiedź może startować od komunikatu „w toku”; efekt „maszynopisania” opcjonalny (tylko jeśli narzut jest akceptowalny).
- To pojedyncza instancja / jeden użytkownik → możemy postawić na spójność i prostotę.

### Plan synchronizacji (proponowany)
1. **Wyłącz polling w chat** jako domyślny mechanizm (pozostaw ręczne odświeżenie).
2. **Optimistic UI**: po kliknięciu „Wyślij” natychmiast dodaj wpis do historii lokalnej.
3. **Event‑driven** zamiast pollingu:
   - Po utworzeniu taska natychmiast otwórz SSE na `tasks/{id}/stream`.
   - Pierwsza odpowiedź „w toku” wyświetlana od razu po event `task_update`.
4. **Stream opcjonalny**:
   - Tryb „maszynopisania” tylko jeśli SSE działa stabilnie.
   - Jeśli streaming jest obciążający, fallback do: „w toku → gotowe”.
5. **Historia sesji**:
   - Po zakończeniu taska: jednorazowy refresh historii (lub lokalny merge).
   - Brak cyklicznego odświeżania `useSessionHistory`.

### Konkretne zmiany (kolejność wdrożenia)
1. **Wyłączenie auto‑pollingu** w chat view:
   - Ustawić `useSessionHistory` na `intervalMs=0` w Cockpit.
   - Zastąpić polling triggerem po submit i po zakończeniu taska.
2. **Local source of truth**:
   - Trzymać „historię renderu” w stanie UI (optimistic + merge).
   - Po zakończeniu taska spiąć z backendowym history (jednorazowo).
3. **SSE jako główny kanał**:
   - Utrzymać SSE tylko dla aktywnych requestów (lista „tracked”).
   - Odciąć SSE, gdy status terminalny.
4. **Fallback bez streamingu**:
   - Jeśli SSE błąd → pokazuj „w toku” i odśwież tylko przy końcu taska.

### Kryteria sukcesu UX
- Wpis użytkownika pojawia się w historii ≤100ms po kliknięciu.
- „W toku” pojawia się ≤250ms od utworzenia taska.
- Brak widocznych „skoków” UI od cyklicznego pollingu.

## Diagnostyka (do wykonania)
1. Zmierzyć **TTFR** (time‑to‑first‑response) w Cockpit po wysłaniu.
2. Zmierzyć latencję UI → API → LLM → UI.
3. Zidentyfikować **top 3 najcięższe komponenty** w web‑next.
4. Sprawdzić logi / telemetry dla opóźnionych requestów.
5. Zmierzyć **czas od submit do pojawienia się wpisu w historii** (UI/SessionStore/History).

## Plan optymalizacji
### Frontend (UI)
- Spójny **optimistic UI** na wejściu użytkownika.
- Ograniczenie pollingu do aktywnych paneli.
- Memoizacja list/wykresów + podział komponentów.
- Lazy‑load ciężkich widoków (Brain, Inspector, Charts).
- Opóźnione mountowanie danych (defer fetch po pierwszym paint).
- Profiling React: wskazać sekcje Cockpit do odciążenia.

### Backend API
- **Szybki ACK** po przyjęciu tasku (minimalny payload).
- Cache dla `/metrics`, `/queue/status`, `/runtime/status` (krótki TTL).
- Batchowanie pollingu (jeden endpoint zbiorczy).
- Profiling endpointów pod opóźnienia.

### LLM runtime
- Warm‑up modelu po starcie backendu.
- Dynamiczne limity odpowiedzi (short dla UI).
- Stream first token ASAP (low‑latency).
- Profiling modeli (TTFT + throughput).

## Zakres do zrealizowania (z progresem)
1. Test E2E „LLM latency” (model + powtórzenia + TTFT/TTFA) — **zrobione**.
2. Mechanizm streaming/webhook zamiast agresywnego pollingu — **do zrobienia**.
3. Cache statusów backendu i szybki ACK — **do zrobienia**.
4. Warm‑up LLM + niskolatencyjna konfiguracja — **do zrobienia**.

## Testy wydajności (stan obecny)
- `pytest tests/perf/test_chat_pipeline.py -m performance` — pomiar SSE.
- `pytest tests/perf/test_llm_latency_e2e.py -m performance` — test E2E LLM latency.

## Wyniki testów wydajności (referencyjne)
| Data (UTC) | Kategoria | Test | Czas | Status |
| --- | --- | --- | --- | --- |
| 2026-01-02 | Jednostkowe/perf (pipeline) | `pytest tests/perf/test_chat_pipeline.py -m performance` | 0.52s | PASS |
| 2026-01-02 | E2E (LLM latency) | `pytest tests/perf/test_llm_latency_e2e.py -m performance` | 6.39s | PASS |
| 2026-01-02 | Zbiorczy (perf) | `pytest tests/perf -m performance` | 6.53s | PASS |

## Kryteria sukcesu
- UI reaguje natychmiast na akcje (≤100ms visual feedback).
- TTFR LLM skrócony o 30–50%.
- Stabilne opóźnienia API przy 1–3 równoległych taskach.
