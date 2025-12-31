# 081: Trzymanie kontekstu konwersacji dla LLM
Status: zrealizowano (backend + UI + testy); otwarte: testy integracyjne z działającym LLM/Docker i ewentualna retencja LanceDB.

## Cel
Zapewnic ciaglosc rozmowy w czacie: model ma rozumiec, ze kolejne wiadomości to kontynuacja dialogu, mimo ograniczen okna kontekstu.

## Założenia
- Backend zarzadza stanem rozmowy; model nie ma wbudowanej pamieci miedzy wywolaniami.
- Wykorzystujemy trzy poziomy: okno ostatnich wiadomosci, streszczenia starszych fragmentow oraz pamiec dlugoterminowa (RAG/embeddings).
- Wsparcie dla wielu sesji czatu; kazda sesja ma wlasny identyfikator i bufor historii.
- Rozróżniamy kontekst:
  - **Sesja** – historia i streszczenia tylko dla bieżącej rozmowy (resetowalne).
  - **Globalne preferencje użytkownika** – zapisywane jako fakty w pamięci długoterminowej z tagiem użytkownika (np. język, styl odpowiedzi).
- Wykorzystujemy istniejacą warstwę pamięci wektorowej (LanceDB/MemoryLayer) – nie budujemy nowego magazynu.

## Zakres
1. Okno kontekstu (short-term)
   - Ile ostatnich wiadomosci wysylamy do LLM (np. limit tokenow/wiadomosci).
   - Filtry: pomijanie logow systemowych/duzych plikow, odciete tresci powyzej limitu.
2. Streszczenia (mid-term)
   - Automatyczne skracanie starszych czesci rozmowy do krotkiego podsumowania.
   - Wstrzykiwanie streszczenia do promptu jako osobna sekcja.
3. Pamiec dlugoterminowa (long-term)
   - Zapisywanie kluczowych faktow/preferencji w wektorach (embeddings) + ewentualnie notatki strukturalne.
   - Retrieval przed zapytaniem i wstrzykniecie wynikow do promptu (RAG).
4. Persistencja
   - Gdzie zapisujemy historie/streszczenia/pamiec (np. pliki, DB, Redis, LanceDB).
   - Retencja i kasowanie starych danych.
5. API/UI
   - Identyfikator sesji w UI i backendzie.
   - Akcje: reset kontekstu, eksport, wlacz/ wylacz auto-streszczenia.
6. Bezpieczenstwo i limity
   - Maksymalna liczba tokenow wysylanych do LLM.
   - Maskowanie sekretow w historii.

## Proponowana realizacja (MVP)
- **Short-term**: trzymaj ostatnie N wiadomosci (np. 10-12) lub do limitu tokenow (np. 2k). Filtruj duze bloki kodu/JSON powyzej progu, zamieniajac je na placeholdery.
- **Mid-term**: po przekroczeniu 20-30 wiadomosci uruchamiaj streszczenie starszej czesci. Przechowuj jedno zbiorcze streszczenie + ewentualnie timestamp/wersje. Wstrzykuj do promptu jako blok "Summary".
- **Long-term**: kluczowe fakty i preferencje zapisuj jako embeddingi + notatki tekstowe. Przed kazdym zapytaniem wykonaj retrieval top-K (np. 3-5) i wstrzyknij sekcje "Relevant memory".
- **Long-term (reuse istniejących komponentów)**: używaj `MemorySkill` / `memory_layer` (LanceDB) do zapisu i retrieval. Reużyj istniejących endpointów/adapterów, dodaj tagi per session/user i typ wpisu (fact/preference/summary).
  - Fakty sesyjne: tag `session_id`, krótka retencja/auto-cleanup.
  - Preferencje globalne użytkownika: tag `user_id` + kategoria `preference` (język, ton, skracanie odpowiedzi) – zawsze dołączane na początku promptu.
- **Sesje**: UI przesyla `session_id`, backend przechowuje historie w StateManager/DB. Reset/nowa sesja czysci okno i streszczenie, zostawia pamiec dlugoterminowa.
- **Limity**: buduj prompt w kolejnosci: system → summary → retrieved memory → historia (ostatnie wiadomosci) → biezace pytanie. Jesli prompt przekracza budzet tokenow, obcinaj najstarsze wiadomosci z okna.
- **Logi**: zapisuj streszczenia i decyzje trimowania w logach zadania (dla debugowania).

## Scenariusze testowe
1) Kontynuacja rozmowy z 15+ wiadomosciami: starsze czesci streszczone, nowe tresci nadal spiete.
2) Reset sesji: po resecie model nie widzi historii, ale preferencje z pamieci dlugoterminowej sa wstrzykiwane.
3) Limit tokenow: gdy prompt przekracza budzet, najstarsze wiadomosci sa obcinane, wynik nadal spójny.
4) Retrieval: pytanie o fakt zapisany w pamieci dlugoterminowej bez kontekstu bieżącego – model powinien odpowiedziec poprawnie.

## Otwarte pytania
- Jak przechowywac streszczenia i historie: w plikach/Redis/DB? (preferencja: lekka persystencja w StateManager/Redis, pamięć wektorowa w LanceDB zgodnie z obecną warstwą)
- Kto wykonuje streszczenie: dedykowany prompt w backendzie czy agent? (koszt vs. latwosc)
- Jak dluga retencja pamieci dlugoterminowej? (per sesja, per uzytkownik)
- Czy dopuscic reczne pine-owanie faktow do pamieci, czy tylko automatycznie?
- Jak przekazać z UI flagę „globalne preferencje” vs „tylko na tę sesję” i jak ją odwzorować w tagach pamięci?

## Proponowane pola UI → backend (payload)
- `session_id` (string, opcjonalne): identyfikator bieżącej sesji czatu; brak = nowa sesja.
- `preferred_language` (enum: pl/en/de): język odpowiedzi; jeżeli `preference_scope=global`, zapisujemy w pamięci globalnej użytkownika (tag `user_id`, kategoria `preference`).
- `preference_scope` (enum: `session`/`global`): zasięg preferencji (język, ton, styl).
- `tone` (opcjonalne, enum: `concise`/`detailed`/`neutral`): preferencja stylu odpowiedzi; mapowana na pamięć globalną lub sesyjną wg `preference_scope`.
- `style_notes` (opcjonalne, string): dodatkowe wskazówki stylu, traktowane jak preferencje (tagowane `preference` + `session_id` lub `user_id`).
- `store_knowledge` (bool): czy zapisywać fakty do pamięci długoterminowej (LanceDB).
- `extra_context` (TaskExtraContext): pliki/linki/ścieżki/notatki – trafiają do kontekstu zadania (short-term) i opcjonalnie do pamięci, jeśli `store_knowledge=true`.

### Mapowanie na tagi pamięci
- Sesja: `{"session_id": <id>, "scope": "session"}` dla faktów/streszczeń specyficznych dla rozmowy.
- Globalne preferencje: `{"user_id": <id>, "scope": "global", "type": "preference"}` dla języka/tonu/stylu.
- Fakty ogólne: `{"user_id": <id>, "type": "fact"}` (jeśli dotyczą użytkownika) lub bez `user_id` jeśli to wiedza ogólna.

## Plan wykorzystania obecnej pamięci
- Short-term + mid-term: bufor w StateManager (per `session_id`), streszczenia przechowywane jako notatki z metadanymi czasu.
- Long-term: bez nowego magazynu, używamy LanceDB + `MemorySkill` do `memorize/recall` (dodajemy tagi sesji/użytkownika).
- Retrieval: przed wywołaniem LLM wykonujemy `recall` (top-K) z istniejącej warstwy; starsze fakty są dostępne dzięki temu bez duplikacji. **(zaimplementowane – top-3, filtr po session_id jeśli podano)**

## Implementacja – stan
- UI: `session_id`, `preference_scope` przekazywane z kokpitu; wyświetlamy aktywny `session_id`, przycisk „Resetuj sesję”; slash `/clear`/`/cler` resetuje kontekst (nowe `session_id`).
- Backend API: `TaskRequest` z polami sesji/preferencji; `context_history` per sesja; reset `/clear` czyści historię i streszczenie.
- Orchestrator: budowa promptu system → summary → retrieved memory → historia → pytanie; okno historii limitowane (`SESSION_HISTORY_LIMIT`), placeholdery dla długich bloków, budżet znaków (`MAX_CONTEXT_CHARS`); RAG top-3 (MemorySkill) filtrowany po `session_id`; summary LLM (aktywny model) z fallbackiem heurystycznym; strategia `SUMMARY_STRATEGY` (`llm_with_fallback` domyślnie, `heuristic_only` opcja); w trybie testowym omija RAG/summary.
- Pamięć wektorowa: wpisy tagowane `session_id`/`user_id` (scope, type), summary zapisywane do pamięci jeśli sesja podana; preferencje globalne wstrzykiwane zawsze.
- Testy: dodane jednostkowe/integracyjne dla historii sesji, streszczeń LLM/heurystyki, slash `/clear`, trim kontekstu; pełna suita przechodzi (1696 pass, 108 skipów środowiskowych LLM/Docker).

## Akceptacja / kryteria techniczne
- Pola sesji/preferencji (`session_id`, `preference_scope`, `tone`, `style_notes`, `preferred_language`) przekazywane w UI → `/api/v1/tasks` i zapisane w `context_history.session`.
- Historia sesji w `context_history.session_history` ograniczona do limitu (domyślnie 12 wpisów).
- Budowa promptu (do zaimplementowania): system → summary → retrieved memory → historia (ostatnie N) → bieżące pytanie, z obcinaniem po budżecie tokenów.
- Preferencje globalne (scope=global) zapisywane w pamięci wektorowej z tagiem `user_id`, scope=global, type=preference; preferencje sesyjne tagowane `session_id`.
- Reset sesji czyści short/mid-term (history + summary), zostawia preferencje globalne.
- Testy: unit (sesja, historia, tagi) + integracyjne (utrzymanie kontekstu, reset, zastosowanie preferencji języka/tonu).
- Slash `/clear` tworzy nowy kontekst sesji (reset w obrębie zadania).

## Zrealizowane
- UI + backend przyjmują `session_id`/`preference_scope`; widoczny `session_id` i akcja resetu sesji + slash `/clear`.
- Historia sesji limitowana (`SESSION_HISTORY_LIMIT=12`), placeholdery dla długich bloków; kontekst trymowany do `MAX_CONTEXT_CHARS`.
- Streszczenia: LLM na aktywnym modelu (maks 400 toksenów, wejście 5k znaków) z fallbackiem heurystycznym; strategia konfigurowalna `SUMMARY_STRATEGY`; zapis streszczeń do pamięci z tagami sesji.
- RAG: top-3 z MemorySkill, filtrowane po `session_id`, tagi `user_id` dla preferencji globalnych.
- Reset sesji czyści short/mid-term; preferencje globalne stale wstrzykiwane.
- Testy: nowe testy historii/streszczeń/slash, pełna suita przechodzi (skipy tylko środowiskowe LLM/Docker/integration).

## Pozostałe (opcjonalne, zależne od środowiska)
- Uruchomienie testów integracyjnych wymagających lokalnego LLM/Docker (`--run-integration`, `LLM_LOCAL_ENDPOINT`, działający docker/compose).
- Ewentualne retencje/cleanup wpisów sesyjnych w LanceDB (planowane, niewymagane dla MVP).

## Decyzje po ustaleniach (wdrożone)
- Pamięć: zostajemy przy LanceDB (brak Redis, brak mnożenia usług).
- Czyszczenie: dwa przyciski w UI przy oknie czatu:
  - „Wyczyść pamięć sesji” – usuwa historię, streszczenie i wektory z tagiem `session_id` (bez naruszania preferencji globalnych).
  - „Wyczyść pamięć globalną” – usuwa preferencje/fakty globalne (tag `user_id`), restartuje stan do defaultu.
- Pinowanie: automatyczne pinowanie ważnych faktów/streszczeń (`pinned=true` w meta); pinned nie podlega auto-clean.
- Cleanup wpisów sesyjnych LanceDB pozostaje opcjonalny (możliwa retencja/lazy pruning).

## Otwarte działania
- Środowisko: uruchomić testy integracyjne z lokalnym LLM/Docker (`--run-integration`).
- (Opcjonalnie) dodać retencję/cleanup wpisów sesyjnych w LanceDB.
- Zadanie 084 zawiera nową wizualizację pamięci w `/brain` – realizować tam (nie w ramach 081).

## Zadania do implementacji (PR 82 – etap czyszczenia pamięci)
1) Backend – API czyszczenia
   - Dodać w `venom_core/api/routes/memory.py` endpointy:
     - `DELETE /api/v1/memory/session/{session_id}`: usuwa wpisy w VectorStore z tagiem `session_id` + czyści historię/streszczenie w StateManagerze dla sesji.
     - `DELETE /api/v1/memory/global`: usuwa wpisy z tagami globalnymi (`user_id`, `scope=global`, `type=preference/fact`) w VectorStore.
   - W VectorStore/MemorySkill dodać metodę usuwania po filtrze meta (`delete_by_metadata`), jeśli brak.
   - Oznaczać auto-piny: przy zapisie streszczeń/kluczowych faktów dodawać meta `pinned=true` (już istniejące wpisy zostawić; nowe mają flagę).
2) UI – kokpit czatu
   - Dwa przyciski przy oknie czatu: „Wyczyść pamięć sesji” (bieżące `session_id`) i „Wyczyść pamięć globalną”.
   - Wywołują odpowiednie endpointy; po sukcesie pokazują toast i odświeżają `session_id` (dla sesji).
3) Testy
   - Unit: mock VectorStore `delete_by_metadata`, sprawdzić wywołanie endpointów i czyszczenie historii/streszczenia.
   - E2E/UI (opcjonalne): smoke, że przycisk wywołuje API (można zostawić TODO, jeśli brak frameworka).

## Miejsca w kodzie do zmian
- DTO/payload: `venom_core/core/models.py` (`TaskRequest`) + `web-next/hooks/use-api.ts` / `cockpit-home.tsx` (UI).
- Sesja/historia: `venom_core/core/orchestrator.py` (zapisy w `context_history`), `StateManager`.
- Budowa promptu + trim tokenów: `orchestrator._prepare_context` / nowy helper (do dodania).
- Pamięć wektorowa: `MemorySkill` / `memory_layer` (tagi session/user) + ewentualne API dla preferencji.

## Nowe zadanie: wizualizacja pamięci (LessonsStore + MemorySkill/VectorStore) w /brain
- Cel: graficzna prezentacja danych z LanceDB na stronie `http://localhost:3000/brain` (biblioteka grafowa już w projekcie).
- Stan obecny: `/brain` pokazuje graf wiedzy (CodeGraphStore); brak wizualizacji lekcji i wpisów wektorowych.
- Potrzebne:
  - Endpoint API zwracający węzły/krawędzie dla pamięci wektorowej:
    - typy węzłów: `lesson`, `fact`, `summary`, `preference`, `session`;
    - meta: `session_id`, `user_id`, `scope`, `type`, `pinned`, `timestamp`.
  - Agregacja/limity: top-N najnowszych na typ, filtrowanie po `session_id`/`user_id`, limit całości (np. 200 węzłów).
  - UI w `/brain`: przełącznik „Warstwa pamięci” obok obecnego grafu; węzły z relacjami:
    - `session -> fact/summary` (po session_id),
    - `user -> preference`,
    - `summary -> fact` (ta sama sesja),
    - opcjonalnie `lesson -> session` (meta-uczenie powiązane z zadaniem).
  - Interakcje: filtr po sesji/użytkowniku, checkbox „pokaż tylko pinned”, tooltip z meta (pinned, scope, type, data).
  - Styl: kolory węzłów per typ; proste legendy.
  - Opcjonalnie akcje kontekstowe (usuń, pin/unpin) – wymaga dodatkowych endpointów.
  - Performance: paginacja/limit oraz lazy-load przy zmianie filtrów, żeby nie zalewać grafu.
