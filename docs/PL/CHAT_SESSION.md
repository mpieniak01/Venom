# Chat i sesje (aktualny stan)

Dokument opisuje, jak dziala chat, jakie dane zbiera, gdzie je przechowuje i jak sesje sa resetowane.

## Przeglad
- Chat dziala w UI `web-next` (Cockpit AI) i wysyla zadania do backendu FastAPI (QueueManager).
- Kontekst rozmowy jest budowany po stronie backendu na podstawie historii sesji i metadanych.
- Ciaglosc rozmowy jest utrzymywana w ramach `session_id`.
- Restart backendu wymusza nowa sesje (UI generuje nowe `session_id`).

## Id sesji (UI)
- `session_id` jest generowany po stronie UI i zapisywany w `localStorage`:
  - `venom-session-id` (aktywny identyfikator sesji),
  - `venom-next-build-id` (build Next.js),
  - `venom-backend-boot-id` (boot backendu).
- UI porownuje `boot_id` z backendu. Gdy jest inny, sesja jest resetowana.

## Źródła danych i magazyny
### SessionStore (źródło prawdy)
- Plik: `data/memory/session_store.json`
- Zawartosc: historia sesji (`history`), opcjonalne `summary`, metadane.
- Uzywany do budowania kontekstu dla kolejnych requestow w tej samej sesji.

### StateManager (stan zadan)
- Plik: `data/memory/state_dump.json`
- Zawartosc: `VenomTask` (content, result, logs, context_history).
- Historia sesji w `context_history` jest per-zadanie (fallback).

### RequestTracer (RAM)
- API: `/api/v1/history/requests` i `/api/v1/history/requests/{id}`
- Zawartosc: prompt (skrocony), status, kroki, metadane LLM.
- Nietrwaly (znika po restarcie).

### Event Stream (WebSocket)
- API: `/ws/events`
- Zawartosc: zdarzenia i statusy systemowe (np. stream odpowiedzi, metryki).
- Nietrwaly (po restarcie restartuje strumien).

### Pamiec wektorowa (globalna)
- Trwala wiedza cross-session (np. LanceDB).
- Zapisy: odpowiedzi, streszczenia, lekcje, fakty.
- Czyszczona tylko recznie przez "Wyczysc pamiec globalna".

## Jak powstaje kontekst chatu
1) UI wysyla `TaskRequest` z `session_id` i trescia promptu.
2) Backend buduje kontekst:
   - metadane sesji (ID, scope, jezyk),
   - historia z SessionStore (ostatnie N wpisow),
   - summary tylko gdy istnieje lub zostalo zadane explicite,
   - pamiec wektorowa tylko przy spelnieniu warunkow (np. "przypomnij", "wczesniej").
3) Model generuje odpowiedz, ktora jest zapisywana do:
   - SessionStore (historia sesji),
   - StateManager (wynik zadania),
   - opcjonalnie do pamieci wektorowej.

## Logika routingu w chat (dlaczego i co wywolywane)
- Domyslna zasada: **jesli intencja nie wymaga narzedzia i nie jest wymuszona, idzie do LLM** (GENERAL_CHAT).
- Model Router wybiera runtime LLM (LOCAL/HYBRID/CLOUD) zgodnie z `AI_MODE` i politykami.
- Narzedzia/skills uruchamiane sa tylko gdy:
  - intencja wymaga narzedzia (np. STATUS_REPORT, VERSION_CONTROL, RESEARCH), lub
  - uzytkownik wymusi to przez slash command (`/git`, `/web`, itp.).
- To zapobiega blednym przekierowaniom (np. pytanie definicyjne jako HELP_REQUEST) i utrzymuje chat jako rozmowe.

## Tryby pracy czatu (manualny przełącznik)
W UI czatu są trzy tryby. Mechanizmy retencji i semantic cache wdrożone w zadaniach 088/090 działają w pełni w trybach **DIRECT** i **NORMAL**. Tryb **COMPLEX** korzysta z tych samych danych, ale posiada własną strategię orkiestracji.

### 1) Direct (bezpośredni)
- **Routing:** bez orkiestratora, bez narzędzi, bez planowania.
- **Ścieżka krytyczna:** UI → LLM → UI (najkrótsza).
- **Logowanie:** RequestTracer z `session_id`, prompt i response (SimpleMode).
- **Zastosowanie:** referencja dla TTFT i maszynopisania.
- **Optymalizacja TTFT**: Wykorzystuje parametr `keep_alive` dla Ollama, aby uniknąć opóźnień ładowania modelu (~1s warm vs ~7s cold).

### 2) Normal (standard)
- **Routing:** orkiestrator + klasyfikacja intencji + standardowe logi.
- **Ścieżka krytyczna:** UI → (intent/gating) → LLM → UI.
- **Logowanie:** pełne (history, steps, runtime).
- **Zastosowanie:** domyślna praca systemu.

### 3) Complex (planowanie)
- **Routing:** wymuszona intencja `COMPLEX_PLANNING` → Architect → plan/kroki.
- **Ścieżka krytyczna:** UI → planowanie → LLM → UI.
- **Logowanie:** pełne + kroki planu + decyzje.
- **Zastosowanie:** zadania wieloetapowe i złożone.

## Szczegóły requestu i timingi
Panel „Szczegóły requestu” pokazuje kluczowe metryki ścieżki krytycznej:
- **UI timings:** `submit → historia`, `TTFT (UI)`.
- **Backend timings:** `LLM.start` (krok tracera), `first_token.elapsed_ms`, `streaming.first_chunk_ms`, `streaming.chunk_count`, `streaming.last_emit_ms`.
To pozwala ocenić, czy streaming działa przyrostowo oraz gdzie powstaje opóźnienie.

## Wzorzec ścieżki krytycznej (UI → LLM → UI)
Cel: wszystko poza wysłaniem promptu i pierwszym chunkem ma działać w tle.
- **Na ścieżce:** submit → TTFT → streaming/odpowiedź.
- **W tle:** trace, memory, refreshy paneli, dodatkowe logi.

## Reset sesji
- Reset sesji w UI tworzy nowe `session_id`.
- Reset sesji czyści:
  - SessionStore dla danej sesji,
  - wpisy sesyjne w `state_dump.json`,
  - pamiec sesyjna w wektorowej pamieci (jesli byla tagowana `session_id`).
- Pamiec wektorowa globalna nie jest czyszczona automatycznie.

## Zarządzanie Retencją (Memory Hygiene)
System udostępnia dedykowane endpointy API do zarządzania cyklem życia wiedzy (Lekcji):
- **Pruning wg TTL:** Usuwanie lekcji starszych niż N dni.
- **Pruning wg Ilości:** Zachowanie tylko N ostatnich lekcji.
- **Pruning wg Tagu:** Usuwanie grup tematycznych (np. po refactoringu biblioteki).
- **Global Wipe:** Pełne czyszczenie pamięci długoterminowej.

Te operacje są kluczowe dla utrzymania jakości kontekstu w czasie. Interfejs do tych operacji znajduje się w panelu **Brain -> Hygiene**.

## Konsekwencje dla tokenow
- Summary i pamiec wektorowa zwiekszaja dlugosc promptu tylko wtedy, gdy sa wlaczane.
- Domyslnie summary nie jest generowane automatycznie; powstaje na zadanie lub przy jasnym triggerze.

## Obecne podejscie
- Reset sesji po restarcie backendu jest celowy (boot_id). To zachowanie moze zostac zmienione, jesli pojawi sie potrzeba podtrzymania sesji po restarcie.
- Pamięć wektorowa jest globalna i trwała; nie jest kasowana per‑sesja. W przyszlosci moze zostac wprowadzony dodatkowy tryb „session‑only” lub reguly TTL.
- Summary jest generowane tylko na zadanie/trigger. Mozliwe jest przestawienie na auto‑summary dla dlugich sesji, kosztem tokenow.
- Retrieval z pamieci jest warunkowy (heurystyki). W przyszlosci mozna to sterowac konfiguracyjnie lub per‑model.

## Plany na v2.0 (multi‑chat + zalaczniki)
- **Multi‑chat:** tworzenie wielu nazwanych sesji, lista/przelaczanie oraz zachowanie historii bez utraty poprzednich sesji.
- **Powrot do sesji:** mozliwosc wznawiania dawnych sesji i kontynuowania z zachowanym kontekstem (bez wymuszonego resetu po restarcie backendu).
- **Zalaczniki w chacie:** upload/przechowywanie/listowanie/usuwanie zalacznikow, metadata (typ, rozmiar, zrodlo) i mozliwosc ponownego dolaczania do nowych wiadomosci.
- **Zasady retencji:** limity per‑sesja oraz polityki przechowywania (manualne usuwanie, TTL lub zakres projektu).

## Gdzie szukac kodu
- UI sesji: `web-next/lib/session.tsx`
- Chat UI: `web-next/components/cockpit/cockpit-home.tsx`
- Budowa kontekstu: `venom_core/core/orchestrator/session_handler.py`
- SessionStore: `venom_core/services/session_store.py`
