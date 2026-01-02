# Chat i sesje (aktualny stan)

Dokument opisuje, jak dziala chat, jakie dane zbiera, gdzie je przechowuje i jak sesje sa resetowane.

## Przeglad
- Chat dziala w UI `web-next` (Cockpit AI) i wysyla zadania do backendu FastAPI.
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

## Reset sesji
- Reset sesji w UI tworzy nowe `session_id`.
- Reset sesji czyści:
  - SessionStore dla danej sesji,
  - wpisy sesyjne w `state_dump.json`,
  - pamiec sesyjna w wektorowej pamieci (jesli byla tagowana `session_id`).
- Pamiec wektorowa globalna nie jest czyszczona automatycznie.

## Konsekwencje dla tokenow
- Summary i pamiec wektorowa zwiekszaja dlugosc promptu tylko wtedy, gdy sa wlaczane.
- Domyslnie summary nie jest generowane automatycznie; powstaje na zadanie lub przy jasnym triggerze.

## Obecne podejscie
- Reset sesji po restarcie backendu jest celowy (boot_id). To zachowanie moze zostac zmienione, jesli pojawi sie potrzeba podtrzymania sesji po restarcie.
- Pamięć wektorowa jest globalna i trwała; nie jest kasowana per‑sesja. W przyszlosci moze zostac wprowadzony dodatkowy tryb „session‑only” lub reguly TTL.
- Summary jest generowane tylko na zadanie/trigger. Mozliwe jest przestawienie na auto‑summary dla dlugich sesji, kosztem tokenow.
- Retrieval z pamieci jest warunkowy (heurystyki). W przyszlosci mozna to sterowac konfiguracyjnie lub per‑model.

## Gdzie szukac kodu
- UI sesji: `web-next/lib/session.tsx`
- Chat UI: `web-next/components/cockpit/cockpit-home.tsx`
- Budowa kontekstu: `venom_core/core/orchestrator/session_handler.py`
- SessionStore: `venom_core/services/session_store.py`
