# PR: Naprawa ciągłości sesji czatu i spójnej historii po restarcie

## TL;DR
Obecnie "ciągłość sesji" jest pozorna: UI trzyma `session_id` w localStorage, ale backend przechowuje historię per‑zadanie (`VenomTask.context_history`), więc kolejny request w tej samej sesji nie dostaje historii poprzednich wiadomości. Restart serwera nie resetuje sesji (UI nadal wysyła ten sam `session_id`), a dane historyczne są rozproszone między pamięcią wektorową, `state_dump.json` i RequestTracer (RAM).

## Objawy (z bieżącej analizy)
- Ten sam `session_id` pojawia się w kolejnych requestach, ale `session_history` zawiera tylko bieżące Q/A, więc model nie „pamięta” wcześniejszej rozmowy.
- „Podsumowanie sesji” nie powstaje dla krótkich rozmów (progi triggerów), więc nie ma co wstrzyknąć do kontekstu.
- Restart backendu nie zmienia `session_id` po stronie UI (localStorage), więc sesja „trwa” mimo restartu, ale bez pełnej historii.
- RequestTracer trzyma historię w RAM i traci ją po restarcie, a `state_dump.json` trzyma stare zadania bez agregacji po `session_id`.

## Obecny stan: dane, magazyny i narzędzia
### Dane składowane (gdzie i przez co)
- **RequestTracer (RAM)**: `/api/v1/history/requests` i `/api/v1/history/requests/{id}`. Trzyma: `request_id`, skrócony `prompt`, `status`, czasy, kroki `steps`, metadane LLM (provider/model/endpoint), forced_tool/provider. Źródło: `venom_core/core/tracer.py`. **Nietrwałe** (znika po restarcie).
- **StateManager (plik JSON)**: `data/memory/state_dump.json`. Trzyma: `VenomTask` (`content`, `result`, `logs`, `context_history`, `status`, `created_at`). Źródło: `venom_core/core/state_manager.py`. **Trwałe** (persistowane na dysku).
- **Session history (per‑zadanie)**: `context_history.session_history` i `context_history.session_history_full` w `state_dump.json`. Tworzone przez `SessionHandler.append_session_history` (`venom_core/core/orchestrator/session_handler.py`).
- **Session summary**: `context_history.session_summary` w `state_dump.json`. Tworzone przez `SessionHandler._ensure_session_summary` po przekroczeniu progów.
- **MemorySkill / VectorStore**: pamięć wektorowa (np. LanceDB). Trzyma wpisy z metadanymi (`session_id`, `user_id`, `type`, `pinned`). Używane przez `MemorySkill` oraz `SessionHandler._memory_upsert`.
- **UI localStorage**: `venom-session-id` i `venom-next-build-id` w przeglądarce. Źródło: `web-next/lib/session.tsx`.
- **Logi runtime**: `logs/backend.log`, `logs/venom.log` – statusy, trace, eventy, ale bez pełnego payloadu rozmowy.

### Dane pobierane przez chat (składanie kontekstu)
- **Prompt bazowy**: `request.content` + ewentualne przetworzenie z `_prepare_context`.
- **Blok sesji**: `SessionHandler.build_session_context_block` dodaje:
  - metadane sesji (ID, scope, język),
  - `session_summary` (jeśli istnieje),
  - `session_history` (ostatnie N wpisów),
  - `memory` z wektorowej pamięci (top‑k, filtrowane po `session_id`).
- **Odpowiedź**: zapisywana do `task.result` i do `session_history` (per‑zadanie).

## Cel PR
1) Zapewnić realną ciągłość kontekstu czatu w obrębie `session_id`.
2) Zdefiniować zachowanie po restarcie: **czy sesja ma się utrzymać, czy zostać zresetowana**. (Wymagane doprecyzowanie; patrz "Decyzje produktowe")
3) Ujednolicić źródła danych dla historii sesji (jedno spójne źródło prawdy).

## Decyzje produktowe (zatwierdzone)
- Czy restart backendu **ma** resetować sesję i generować nowe `session_id`?
  - Tak. Restart backendu ma wymuszać nową sesję.
- Czy "ciągłość" ma dotyczyć tylko UI (localStorage), czy również backendu (history store)?
  - Ma czyścić wszystko (UI + backend). Brak „ukrytej” kontynuacji po restarcie.
- Czy pamięć wektorowa ma być powiązana tylko z `session_id`, czy globalna (cross‑session)?
  - Pamięć wektorowa jest globalna (cross‑session) i czyszczona tylko ręcznie.

## Proponowane zmiany (backend)
- [x] Wprowadzić *globalny store sesji* na backendzie, np. `SessionStore`, mapujący `session_id -> historia, summary, meta`.
- [x] Persistencja store'u do pliku (np. `data/memory/session_store.json`), z TTL lub rozmiarem limitowanym.
- [x] Podczas budowania kontekstu (`SessionHandler.build_session_context_block`) pobierać historię z `SessionStore`, a nie tylko z bieżącego `VenomTask`.
- [x] Zapisywać każdą wiadomość do `SessionStore` (user + assistant) niezależnie od zadań.
- [x] Uporządkować summary: tworzyć „mini‑summary” nawet dla krótkich sesji (np. po 2‑3 wymianach) albo generować on‑demand przy kolejnym pytaniu.
- [x] Ujednolicić czyszczenie: endpoint `/api/v1/memory/session/{id}` powinien czyścić **zarówno** wektorową pamięć, jak i `SessionStore` + `state_dump` wpisy.

## Proponowane zmiany (frontend)
- [x] Dodać mechanizm „reset na restart” jeśli produktowo wymagane:
  - backend udostępnia `runtime_id` lub `boot_id` (np. w `/api/v1/system/status`),
  - UI porównuje z wartością w localStorage i resetuje `session_id` jeśli różne.
- [x] UI powinno wysyłać `session_id` zawsze, ale mieć też szybki przycisk „Nowa sesja” (już jest `resetSession()`).

## Kierunek realizacji (jedno źródło prawdy)
### Założenia
- Jedno źródło prawdy dla historii sesji: **SessionStore** po stronie backendu.
- Restart backendu = nowa sesja (UI resetuje `session_id` na podstawie `boot_id`).
- „Ciągłość” jest wyłącznie w ramach aktywnej sesji; po restarcie wszystko jest czyszczone.
- Minimalizujemy koszty tokenów: nie wstrzykujemy automatycznie streszczeń ani RAG bez potrzeby.

### Proponowana realizacja
1) **SessionStore (backend, persistent)**
   - Nowy magazyn `session_id -> history[] + summary + metadata`.
   - Zapis/odczyt do `data/memory/session_store.json`.
   - API do czyszczenia sesji usuwa dane z SessionStore + wektory + kontekst w `state_dump.json`.

2) **Budowanie kontekstu (chat)**
   - `SessionHandler.build_session_context_block` bierze historię z SessionStore (ostatnie N wpisów).
   - Summary tylko *opcjonalne* (np. po przekroczeniu limitu lub na żądanie).
   - RAG/Memory: **trwała wiedza globalna** (nie kasujemy per‑sesja). Włączane tylko gdy **użytkownik odwołuje się do wcześniejszej wiedzy** lub przekracza próg długości.

3) **Reset po restarcie**
   - Backend publikuje `boot_id` (np. w `/api/v1/system/status`).
   - UI porównuje z localStorage; jeśli inny → `resetSession()` + czyszczenie sesji.

### Konsekwencje dla tokenów
- Summary nie jest automatycznie dołączane → niższy koszt tokenów.
- Wektory nie są automatycznie dołączane → koszt tylko przy świadomym użyciu (np. trigger).

### Ustalenie: pamięć wektorowa
- Pamięć wektorowa służy do trwałego wzbogacania wiedzy chatu (cross‑session).
- Nie jest kasowana per‑sesja; jest czyszczona wyłącznie ręcznie (przycisk „Wyczyść pamięć globalną”).
- Pamięć sesyjna (SessionStore + state_dump) jest czyszczona przy resecie sesji lub restarcie.

## Audyt danych i źródeł historii
- RequestTracer (RAM): `/api/v1/history/requests` – **nietrwałe**.
- StateManager: `data/memory/state_dump.json` – trzyma `VenomTask` z `context_history` per‑zadanie.
- MemorySkill / vector_store: trwały RAG, ale wyszukiwanie po semantyce, nie po `session_id` bez filtra.
- UI: localStorage (`venom-session-id`) – trwałe między restartami.

## Kryteria akceptacji
- Kolejny request w tej samej sesji dostaje poprzednie wiadomości w prompt (min. N ostatnich wiadomości).
- Po restarcie zachowanie sesji jest **spójne z decyzją produktową**.
- Czyszczenie sesji usuwa historię z wszystkich magazynów.
- UI panel „Szczegóły requestu” pokazuje spójne dane nawet po restarcie.

## Testy
- [x] Unit: SessionStore (append, prune, load/save).
- [x] Integracyjne: nowy request w tej samej sesji → kontekst zawiera wcześniejsze wiadomości.
- [x] E2E: reset sesji w UI → nowe `session_id`, brak starego kontekstu.

## Pliki docelowe (orientacyjnie)
- `venom_core/core/orchestrator/session_handler.py`
- `venom_core/core/state_manager.py`
- `venom_core/api/routes/memory.py`
- `web-next/lib/session.tsx`
- `web-next/components/cockpit/cockpit-home.tsx`
- Nowy: `venom_core/services/session_store.py` (lub podobny)
