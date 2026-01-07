# PR: Analiza pamieci (chat + utrwalanie wiedzy)

## Cel
Ustrukturyzowac i utrzymac jeden, kompletny opis tego, jak system utrwala wiedze w czacie:
- historia sesji,
- streszczenia,
- pamiec wektorowa (LanceDB),
- lekcje i meta-uczenie,
- grafy wiedzy,
- snapshoty systemowe (Chronos),
- UI cache/snapshoty.

Dokument ma byc uzywalny jako material do PR-a: stan "as-is", luki, ryzyka, zadania i kryteria akceptacji.

## Zakres
Wchodzi:
- backend: SessionStore, StateManager, SessionHandler, MemorySkill/VectorStore, LessonsStore/LessonsManager, endpoints /api/v1/memory.
- frontend: Cockpit/Brain (cache + odczyt snapshotow).
- dokumentacja: aktualne opisy w docs.

Nie wchodzi:
- nowe feature'y, zmiany funkcjonalne; tylko analiza i plan ujednolicenia.

## Stan obecny (as-is)

### 1) Historia sesji (short-term)
- Zrodlo prawdy: `data/memory/session_store.json` (SessionStore).
- Dublowanie: `data/memory/state_dump.json` (StateManager -> context_history).
- Limit historii do promptu: `SESSION_HISTORY_LIMIT = 12` (constants).
- Reset sesji po restarcie backendu (boot_id mismatch).
- UI generuje `session_id` i trzyma w localStorage.
- **Zarzadzanie:**
  - Endpoint `DELETE /api/v1/memory/session/{session_id}` (czyści SessionStore + StateManager + wektory sesyjne).
  - UI Cockpit: Hook `clearSessionMemory` dostępny i używany (resetuje sesję).

Kod:
- `venom_core/services/session_store.py`
- `venom_core/core/orchestrator/session_handler.py`
- `venom_core/core/state_manager.py`
- `docs/CHAT_SESSION.md`

### 2) Streszczenia (mid-term)
- Auto-summary po przekroczeniu progow (20 wiadomosci lub 5000 znakow).
- Summary na zadanie ("podsumuj", "streszczenie").
- Strategia: `SUMMARY_STRATEGY` (LLM z fallbackiem lub heurystyczne).
- Summary zapisany do SessionStore + do pamieci wektorowej (type=summary, pinned=true).
- **Zarzadzanie:**
  - Usuwane razem z sesją (`DELETE /session/{id}`).
  - Brak osobnego zarządzania tylko streszczeniami w UI.

Kod:
- `venom_core/core/orchestrator/session_handler.py`
- `venom_core/core/orchestrator/constants.py`

### 3) Pamiec wektorowa (long-term)
- LanceDB w `data/memory/lancedb`.
- Zapis: MemorySkill/VectorStore, metadata (session_id, user_id, type, scope, pinned).
- Retrieval: top-3, filtr po session_id (jesli podany), heurystyczne gating w czacie.
- **Zarzadzanie:**
  - `DELETE /api/v1/memory/global` (czyści user_default).
  - `DELETE /api/v1/memory/entry/{entry_id}` (usuwa pojedynczy wpis).
  - `POST /api/v1/memory/entry/{entry_id}/pin` (przypinanie - pinuje).
  - UI Brain: Pozwala usuwać pojedyncze wpisy z grafu i czyścić pamięć globalną.

Kod:
- `venom_core/memory/vector_store.py`
- `venom_core/memory/memory_skill.py`
- `venom_core/api/routes/memory.py`
- `docs/MEMORY_LAYER_GUIDE.md`

### 4) Lekcje i meta-uczenie
- LessonsStore zapisuje lekcje do `data/memory/lessons.json`.
- LessonsManager: pre-flight dokleja lekcje do kontekstu (max 3).
- Zapis lekcji po sukcesie lub bledzie (gated przez store_knowledge i ENABLE_META_LEARNING).
- Dodatkowy log procesu nauki do `data/learning/requests.jsonl`.
- **Zarzadzanie:**
  - Backend API:
    - `DELETE /lessons/prune/latest` (usuwa N ostatnich).
    - `DELETE /lessons/prune/range` (usuwa wg zakresu dat).
    - `DELETE /lessons/prune/tag` (usuwa wg tagu).
    - `DELETE /lessons/prune/ttl` (usuwa wg TTL).
    - `DELETE /lessons/purge` (nuke all).
  - UI Brain:
    - Prezentacja: `LessonList` i statystyki.
    - **BRAK**: Interfejsu do grupowego usuwania lekcji (pruning) z poziomu UI.

Kod:
- `venom_core/memory/lessons_store.py`
- `venom_core/core/lessons_manager.py`
- `venom_core/core/orchestrator/orchestrator_core.py`

### 5) Grafy wiedzy
- CodeGraphStore: graf zaleznosci kodu (AST -> JSON w `data/memory/code_graph.json`).
- Oracle/GraphRAG: osobna sciezka ingestu dokumentow i grafu wiedzy (nie jest domyslnie w czacie).
- **Zarzadzanie:**
  - Prezentacja: Endpoint `/api/v1/memory/graph` i wizualizacja w UI Brain.

Kod:
- `venom_core/memory/graph_store.py`
- `docs/ORACLE_GRAPHRAG_GUIDE.md`

### 6) Snapshoty systemowe (Chronos)
- Snapshoty stanu systemu (kod + pamiec + konfiguracja) w `data/timelines/...`.
- To nie jest snapshot rozmowy; sluzy do rollbacku stanu systemu.

Kod:
- `venom_core/core/chronos.py`
- `docs/THE_CHRONOMANCER.md`

### 7) UI cache/snapshoty
- Cockpit: cache ostatnich ~200 wpisow historii w sessionStorage (szybki render).
- Brain/Strategy: SSR snapshot + polling; stale-while-revalidate dla raportow.

Kod:
- `web-next/components/cockpit/cockpit-home.tsx`
- `web-next/lib/server-data.ts`
- `docs/FRONTEND_NEXT_GUIDE.md`

## Mapowanie Funkcji na Ekrany (UI Scope)

### 1. Cockpit Screen (`/`)
Centralne miejsce interakcji z historią bieżącą i kontekstem sesji.
- **Funkcje dostępne:**
  - `Reset Sesji`: Przycisk w nagłówku/menu (czyści kontekst, SessionStore, wektory sesyjne).
  - `Manual Summary`: Komenda `/podsumuj` (wymusza snapshot).
  - `Debug/Mode Badge`: Wskaźnik trybu (Direct/Normal/Complex) i użycia pamięci (plany na przyszłość).
- **Braki UI:**
  - Brak wizualnego wskaźnika "Memory Used" (czy retrieved context został użyty w tej odpowiedzi).

### 2. Brain Screen (`/brain`)
Centrum zarządzania wiedzą długoterminową i strukturą grafową.
- **Funkcje dostępne:**
  - `Memory Graph`: Wizualizacja węzłów wiedzy i relacji.
  - `Global Wipe`: Przycisk "Wyczyść pamięć globalną" (destrukcyjny).
  - `Node Action`: Kliknięcie w węzeł -> Pin/Unpin, Delete (pojedyncze wpisy).
- **Proponowane rozszerzenie (Nowy Tab "Hygiene"):**
  - Widok dedykowany do masowego zarządzania lekcjami (Lesson Pruning).
  - Sekcje:
    - *By Date*: "Usuń lekcje starsze niż X dni".
    - *By Quantity*: "Zachowaj tylko N ostatnich lekcji".
    - *By Tag*: "Usuń wszystkie lekcje z tagiem [X]".
  - Tabela z listą lekcji i checkboxami do grupowego usuwania.

### 3. Settings / Admin (Planowane lub Modal w Cockpicie)
Miejsce na konfigurację systemową (gating, constants).
- **Funkcje (Planowane):**
  - Konfiguracja `SESSION_HISTORY_LIMIT`.
  - Toggle `ENABLE_META_LEARNING`.
  - Suwaki heurystyk (Thresholds).

## Analiza Luk w Zarządzaniu Pamięcią (Gap Analysis)

| Aspekt Pamięci | Backend (API) | Frontend (UI) | Status |
| :--- | :---: | :---: | :--- |
| **Session History** | ✅ Pełne API (Clear/Get) | ✅ Przycisk "Reset sesji" (Clear) | ZARZĄDZANE |
| **Global Long-term** | ✅ endpoint `/global` | ✅ Przycisk "Wyczyść pamięć globalną" | ZARZĄDZANE |
| **Memory Entries** | ✅ Delete/Pin endpointy | ✅ Akcje na węzłach grafu (Pin/Delete) | ZARZĄDZANE |
| **Lessons (Pruning)**| ✅ Bogate API (Range, TTL, Tag) | ❌ **BRAK UI** do pruningu | CZĘŚCIOWO (Tylko API) |
| **Wizualizacja** | ✅ Endpoint `/graph` | ✅ Graf w Brain | ZARZĄDZANE |

**Wnioski:**
1. System posiada bardzo rozbudowane API do higieny pamięci (`venom_core/api/routes/memory.py`), szczególnie dla lekcji.
2. UI (Cockpit/Brain) eksponuje podstawowe czyszczenie (sesja/global) i zarządzanie pojedynczymi wpisami (graf).
3. **Główna luka**: Brak interfejsu "Admin / Memory Hygiene" w UI, który pozwalałby na uruchomienie zaawansowanych strategii czyszczenia lekcji (np. "usuń lekcje starsze niż 30 dni" lub "usuń wszystkie lekcje z tagiem X").

## Luki / ryzyka (zaktualizowane)
- Brak jednej, spojnej dokumentacji "end-to-end" (stan + reguly wstrzykiwania).
- Kryteria gatingu pamieci (heurystyka) nie sa konfigurowalne z UI.
- Summary moze sie pojawic automatycznie, ale nie zawsze jest widoczny dla UI jako osobny artefakt.
- Roznica "session history" w SessionStore vs StateManager moze rozjechac sie po awarii.
- Czyszczenie pamieci globalnej usuwa wszystko po user_id (domyslnie user_default) bez osobnej whitelisty.
- Oracle/GraphRAG to osobna sciezka; brak jasnej adnotacji w UI, ze to nie zasila czatu.
- **Brak UI do zarządzania retencją lekcji (Lessons Pruning).**

## Zadania (PR Scope - Analysis & Specs)
1. **Dokumentacja i Procesy:**_DONE_
   - [x] Stworzyc `docs/MEMORY_IN_CHAT.md` (diagram przepływu, tabele retencji).
   - [x] Ujednolicic nazewnictwo (session vs history vs summary vs memory).
2. **Specyfikacja UI (Brain Hygiene):**_DONE_
   - [x] Zaprojektować (mockup/opis) nowy tab "Memory Hygiene" w Brain.
   - [x] Zdefiniować interfejsy TypeScript dla akcji pruningowych (pod istniejące API).
3. **Specyfikacja Cockpit Feedback:**_DONE_
   - [x] Opisać sposób prezentacji "Memory Context" w dymkach czatu (np. ikona mózgu gdy użyto RAG).
4. **Weryfikacja:**_DONE_
   - [x] Stworzyć test plan dla scenariuszy: "User usuwa lekcje -> Czat traci wiedzę".

## Zadania (Phase 2: Implementation - Coding)

### 1. Backend: Expose Context Usage_DONE_
*Aby wyświetlić ikony w Cockpicie, frontend musi wiedzieć o użytym kontekście.*
- [x] Zmodyfikować `venom_core/core/models/task.py`: dodać pole `context_used` (lessons, memory_entries).
- [x] Zmodyfikować `venom_core/core/orchestrator/orchestrator_core.py`: wypełniać `context_used` danymi z retrievala.
- [x] Zaktualizować `venom_core/api/routes/tasks.py` / StreamingHandler, aby zwracały to pole w odpowiedzi/streamie.

### 2. Frontend: Brain Hygiene (Nowy Tab)_DONE_
*Zarządzanie retencją lekcji zgodnie ze specyfikacją.*
- [x] Stworzyć hook `useLessonPruning` w `web-next/hooks/use-api.ts`.
- [x] Dodać komponent `LessonPruningPanel` w `web-next/components/brain/`.
- [x] Zintegrować nowy tab "Hygiene" w `BrainHome`.

### 3. Frontend: Cockpit Feedback (Icons)_DONE_
*Wizualizacja użycia pamięci.*
- [x] Zaktualizować typy `ChatMessage` / `Task` w frontendzie o `context_used`.
- [x] Dodać logikę w `cockpit-home.tsx` (parsowanie streamu/odpowiedzi).
- [x] Zaktualizować `ConversationBubble` o wyświetlanie ikon 🎓/🧠 z tooltipem.

## Kryteria akceptacji
- Jest jeden dokument, ktory opisuje caly przeplyw pamieci w czacie.
- Dokument zawiera: diagram, tablice "dane -> zapis -> odczyt -> retention".
- Jasno rozroznione: session history, summary, memory vectors, lessons, graph, chronos.
- Jest lista testow manualnych + kroki odtworzenia.

## Propozycja docelowego pliku
- `docs/MEMORY_IN_CHAT.md` (nowy)

## Kontekst Testowy (manual)
- Sesja: nowy `session_id` -> historia pojawia sie w SessionStore.
- Summary: po przekroczeniu progu powstaje summary w SessionStore i LanceDB (type=summary).
- Retrieval: zapytanie "przypomnij" dokleja memory block do promptu.
- Reset sesji: czysci SessionStore + StateManager + session vectors w LanceDB.
- Czyszczenie globalne: usuwa globalne wpisy w LanceDB.

## Artefakty do sprawdzenia
- `data/memory/session_store.json`
- `data/memory/state_dump.json`
- `data/memory/lessons.json`
- `data/memory/lancedb`
- `data/learning/requests.jsonl`
- `data/memory/code_graph.json`
- `data/timelines/`
