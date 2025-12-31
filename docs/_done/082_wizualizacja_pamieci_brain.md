# 082: Wizualizacja pamięci (LessonsStore + MemorySkill/VectorStore) w /brain
Status: zakończone (backend+UI + testy API; e2e opcjonalne)

## Cel
Graficznie przedstawić dane z LanceDB (lekcje + fakty/streszczenia/preferencje) na stronie `http://localhost:3000/brain`, aby łatwiej zarządzać pamięcią wektorową.

## Stan obecny
- `/brain` pokazuje graf wiedzy (CodeGraphStore) przez istniejący widok/bibliotekę grafową.
- LessonsStore (lekcje/meta-uczenie) i MemorySkill/VectorStore (fakty, streszczenia, preferencje) nie są wizualizowane.

## Zakres / wymagania
- Endpoint API zwracający dane grafu pamięci:
  - węzły typów: `lesson`, `fact`, `summary`, `preference`, `session`;
  - meta per węzeł: `session_id`, `user_id`, `scope`, `type`, `pinned`, `timestamp`.
  - krawędzie:
    - `session -> fact/summary` (po `session_id`),
    - `user -> preference`,
    - `summary -> fact` (ta sama sesja),
    - opcjonalnie `lesson -> session` (powiązanie meta-uczenia).
  - Limity/agregacja: top-N najnowszych na typ, filtrowanie po `session_id`/`user_id`, limit całości (np. 200 węzłów).
- UI w `/brain`:
  - przełącznik „Warstwa pamięci” obok obecnego grafu;
  - węzły kolorowane per typ, legenda;
  - filtry: sesja/użytkownik, checkbox „pokaż tylko pinned”;
  - tooltip z metadanymi (pinned, scope, type, data).
  - opcjonalnie akcje kontekstowe (usuń wpis, pin/unpin) – wymaga dodatkowych endpointów.
- Performance: ograniczać wynik (limit, lazy-load przy zmianie filtra), żeby nie przeładować grafu.

## Notatki implementacyjne
- Backend: nowy endpoint `/api/v1/memory/graph` korzystający z VectorStore/LanceDB i LessonsStore; selekcja pól meta + budowa prostego grafu. ✅
- Frontend `/brain`: wykorzystać istniejącą bibliotekę grafową (jak w CodeGraphStore), dodać warstwę pamięci i przełączniki/filtry. ✅ warstwa pamięci on/off, merge grafów, kolorowanie.
- Dane wyjściowe: struktura nodes/edges (id, label, type, meta) gotowa do renderu w JS.

## Wykonane
- Backend: `/api/v1/memory/graph` (wpisy LanceDB + lekcje), `VectorStore.list_entries`, `update_metadata`/`delete_entry`, przekazanie LessonsStore do memory routes; endpointy pin/unpin i delete wpisu pamięci.
- Frontend: /brain ma toggle „Warstwa pamięci (LanceDB)”, merge grafów (knowledge + memory), kolory dla memory/session/user/lesson, licznik węzłów pamięci, obsługa błędów/ładowania; filtry session_id/only pinned + odświeżanie; akcje kontekstowe pin/odepnij i usuń wpis.
- Wydajność: domyślnie nie dołączamy lekcji do grafu pamięci (checkbox „Dołącz lekcje” do włączenia); limit 200 wpisów LanceDB; filtrowanie w UI nie wywołuje ponownego layoutu (batch hide/show).
- UX aktualne: warstwa pamięci jest domyślnie włączona i pokazuje węzły/edge LanceDB (bez nakładania demo grafu); dolny panel sterujący zawija się w dwie linie (tagi + filtry), statystyki węzłów/krawędzi biorą dane z aktualnie renderowanego grafu.
- Zakładki: dodany przełącznik „Repo / Knowledge” vs „Pamięć / Lessons” z badge źródła; dane pobierane w interwałach tylko dla aktywnej zakładki (polling 0, gdy nieaktywna).
- Legendy/UX: dodana lekka legenda kolorów (repo vs pamięć vs zaznaczenie), licznik renderowanych węzłów/krawędzi względem dostępnych; krawędzie domyślnie bez etykiet (toggle informuje o potencjalnym spowolnieniu).
- Testy: dodano test API /api/v1/memory/graph (filtry session_id + pinned oraz włączenie lekcji przez include_lessons).
- UX warstwa pamięci: potwierdzenie usunięcia wpisu + toasty dla pin/odepnij i usuwania.
- Backend: `/api/v1/knowledge/graph` przyjmuje limit węzłów (domyślnie 500); UI wysyła limit w hooku `useKnowledgeGraph`, żeby zmniejszyć payload przy dużych grafach.
- Konfiguracja: limity grafów (knowledge/memory) sparametryzowane w .env (`NEXT_PUBLIC_KNOWLEDGE_GRAPH_LIMIT`, `NEXT_PUBLIC_MEMORY_GRAPH_LIMIT`), wykorzystywane w hookach i SSR.
- Fallback: `/api/v1/memory/graph` w razie braku VectorStore zwraca pusty graf (`status: unavailable`) zamiast 500, żeby UI nie wybuchało.
- Konfiguracja backendu: nowe zmienne limitów dodane do `Settings` (pydantic), by uniknąć błędu walidacji przy odczycie `.env`.

## Status testów
- API: `/api/v1/memory/graph` (filtry/pinned/include_lessons) i `/api/v1/knowledge/graph` (limit + mock fallback) pokryte unitami.
- Frontend: lint/build przechodzi; e2e/smoke dla /brain opcjonalne (do uruchomienia, gdy środowisko będzie dostępne).

## Ustalenia dalej (warstwy)
- Zostajemy przy dwóch odrębnych warstwach: Knowledge (repo) i Memory (LanceDB/Lessons). Aktualnie brak korelacji między warstwami; chcemy je prezentować osobno.
- Proponowane zakładki/tryby (bez kodu na razie): „Repo / Knowledge” i „Pamięć / Lessons”, każdy ładuje swoje API dopiero po wejściu (lazy-load), z osobnymi limitami/layoutami/kolorami i licznikami.
  - Repo/Knowledge: hierarchiczny layout (cose/dagre), limit np. 500; filtry typów węzłów (file/function/agent). Jeśli brak realnych danych, można pokazać komunikat i CTA „Skanuj graf”.
  - Pamięć: layout concentric/cola, domyślny limit 100, lekcje off domyślnie, filtry session_id/pinned/tags; licznik węzłów/krawędzi i lekcji z aktywnej warstwy.
- Statystyki/nagłówek: liczniki węzłów/krawędzi liczone dla aktywnej zakładki; liczba lekcji tylko w trybie pamięci; badge źródła (Repo vs Pamięć).
- Legenda: oddzielne kolory per warstwa; wyświetlać aktywne filtry i limity (np. „101/453 lekcji”).
- Wydajność: render tylko jednej warstwy naraz; truncacja labeli i etykiety krawędzi off domyślnie; opcjonalny limit wyświetlanych węzłów z komunikatem, by zawęzić filtr.

## Plan (rozszerzony – do wdrożenia)
1) Obecny stan / problem
- W jednym widoku łączymy dwie warstwy danych: Knowledge (repo/file/function) i Memory (LanceDB + LessonsStore).
- Przy dużej liczbie węzłów (100+), graf staje się mało czytelny, render wszystkich naraz jest ciężki (overlap labeli, obciążenie DOM/layout).
- Statystyki i panel sterujący są ogólne; źródła danych nie są jasno rozdzielone.
- Ładowanie obu warstw domyślnie powoduje opóźnienia i utrudnia interpretację.

2) Wniosek
- Dwa tryby/zakładki to lepszy UX i wydajność: osobno „Graf repo/knowledge” i osobno „Graf pamięci (LanceDB/Lessons)”. Każdy tryb odpala własne zapytanie dopiero po wejściu (lazy-load).
- Różne limity, layouty, kolory i statystyki dla rozdzielnych kontekstów; wszystko liczone z aktywnej zakładki.

3) Proponowana struktura UI (bez kodu)
- Zakładki: Repo / Knowledge | Pamięć / Lessons.
- Po przełączeniu:
  - Fetch tylko odpowiedniego API: Knowledge (`/api/v1/knowledge/graph` + summary), Pamięć (`/api/v1/memory/graph?limit=...&include_lessons=...`).
  - Oddzielne limity i layouty: Knowledge – hierarchiczny/dagre/cose, limit np. 500; Pamięć – concentric/cola, domyślnie limit 100, lekcje off.
  - Oddzielne statystyki w nagłówku: Węzły/Krawędzie z aktywnej zakładki; liczba lekcji obok (tylko dla Pamięci).
  - Oddzielne filtry: Knowledge – typ węzła (file/function/agent), ewentualnie ścieżka pliku; Pamięć – session_id, pinned, include_lessons, tagi lekcji.
  - Domyślny start: Repo, jeśli skan istnieje; jeśli brak danych repo, fallback do Pamięci.
  - CTA do przeładowania: osobne przyciski „Odśwież repo graf” i „Odśwież pamięć”.

4) Wydajność
- Lazy-load per zakładka (fetch po wejściu); cache ostatnio pobranego grafu per zakładka, ale render tylko jednego naraz.
- Trunkacja labeli i opcja wyłączenia etykiet krawędzi; limit liczby wyświetlanych węzłów (np. 200) z komunikatem „włącz filtr, aby zobaczyć więcej”.

5) Jasność danych
- Badge aktywnego źródła: „Źródło: Knowledge | Pamięć”.
- Legenda typów per zakładka (inne kolory).
- W panelu statystyk: pokazywać limit vs. całość (np. „101/453 lekcji” dla pamięci).

6) Taski implementacyjne
- Dodać zakładki (Repo vs Pamięć) i lazy-load odpowiednich endpointów.
- Ustawić osobne limity/layouty/kolory/statystyki per zakładka.
- Uspójnić panel filtrów: repo – typy węzłów; pamięć – session/pinned/lessons/tags.
- Dodać legendę źródła + licznik (rendered/total).
- Opcjonalnie: truncation labeli i wyłączenie etykiet krawędzi domyślnie.
