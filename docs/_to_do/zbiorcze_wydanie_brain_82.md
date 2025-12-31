# Zbiorcze wydanie – wizualizacja /brain (PR 82)

## Zakres zmian
- Podział widoku /brain na zakładki (Repo/Knowledge, Pamięć/Lessons) z osobnym limitem/layoutem; domyślna zakładka: Pamięć.
- Warstwa pamięci (LanceDB/Lessons): kolory po topic, wygaszanie starszych wpisów (timestamp), topic filter, flow mode (sekwencyjne krawędzie), preset layout gdy dostępne `x,y` z projekcji.
- Projekcja embeddingów: endpoint `/api/v1/memory/embedding-project` (PCA 2D zapisujące `x,y`), przycisk „Odśwież projekcję” w UI.
- Czyszczenie pamięci: przyciski „Wyczyść tok sesji” (DELETE /memory/session/{id}) i „Wyczyść całą pamięć” (DELETE /memory/global + wipe kolekcji); toasty z wynikami, odświeżanie grafu.
- Statystyki Lessons: „Top tagi” wyświetlane jako czytelna lista, liczba lekcji/tagów.
- Flow toggle i zawsze widoczne filtry grafu (naprawiony smoke test Playwright).

## Backend
- Memory graph: nody z topic + opcjonalnym `position`; tryb `mode=flow` (krawędzie sekwencyjne); global/session wipe usuwa realne rekordy (delete_session, wipe_collection).
- Projekcja: nowy router `memory_projection` (PCA -> x,y).
- LibrarianAgent prompt zaostrzone, by nie uruchamiać narzędzi dla pytań ogólnych.

## Frontend
- /brain: auto preset layout, topic colors/opacity, topic filter, flow toggle, stałe filtry grafu, przyciski czyszczenia i projekcji, brak auto-pollingu dla pamięci (brak resetu po drag).
- e2e smoke „Brain view loads filters and graph container” naprawiony.

## Testy
- Unit API: `/api/v1/memory/graph` (flow) i `/api/v1/knowledge/graph` (limit/mock).
- Lint/build OK; Playwright smoke dla /brain przechodzi.

## Uwagi
- E2E/UX usprawnienia (krawędzie podobieństwa, cluster/sampling >500) pozostają opcjonalne na kolejny etap.
