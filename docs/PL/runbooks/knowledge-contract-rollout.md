# Runbook: Rollout kontraktu Knowledge (200B)

## Cel

Bezpieczne wdrożenie kanonicznego kontraktu `KnowledgeEntry`:
- najpierw backend (`GET /api/v1/knowledge/entries`),
- potem konsumenci UI,
- z jawną walidacją i ścieżką rollback.

## Zakres

- Kanoniczny endpoint odczytu: `GET /api/v1/knowledge/entries`
- Kontrakt payloadu mutacji lessons: `mutation.{target,action,source,affected_count,scope,filter}`
- Audyt udanych mutacji lessons:
  - `source=knowledge.lessons`
  - `action=mutation.applied`

## Faza 1: rollout backend-only

1. Wdróż backend z endpointem federowanym i kontraktem mutacji/audytu.
2. Utrzymaj istniejące endpointy knowledge/memory/lessons jako ścieżkę kompatybilności.
3. Zweryfikuj:
   - `GET /api/v1/knowledge/entries` zwraca wpisy ze źródeł session/lessons/vector/graph.
   - `DELETE /api/v1/lessons/prune/latest?count=1` zwraca blok `mutation`.
   - strumień audytu zawiera `knowledge.lessons / mutation.applied`.

## Faza 2: adopcja UI (zrealizowana w 200B)

1. Użyj `knowledge/entries` jako domyślnej ścieżki odczytu w widokach lessons/knowledge.
2. Zachowaj niezmienione ścieżki mutacji (`/api/v1/lessons/*`) w tej fazie.
3. Zweryfikuj parytet testami kontraktowymi i smoke na stagingu (count/źródła/filtry session).

## Faza 3: utwardzenie kontraktu

1. Traktuj `knowledge/entries` jako kanoniczne źródło odczytu widoków knowledge.
2. Utrzymaj endpointy legacy do czasu zamknięcia okna deprecjacji.
3. Dodaj release note przed wyłączeniem zależności od legacy DTO.

## Checklista walidacji

1. `make pr-fast` na zielono.
2. Testy kontraktowe `knowledge/entries` na zielono.
3. Testy guardów mutacji (`403` kanoniczny payload) na zielono.
4. Testy audytu udanych mutacji na zielono.
5. Brak krytycznych zgłoszeń Sonara w zmienionych plikach.

## Rollback

1. Cofnij ścieżkę odczytu UI do mapowania endpointów legacy (backend pozostaje wdrożony).
2. Zachowaj kontrakt mutacji/audytu backendu, jeśli jest kompatybilny.
3. W razie potrzeby wykonaj rollback backendu do ostatniego stabilnego taga.

## Znane ryzyka

1. Częściowa dostępność źródeł w odczycie federowanym przy degradacji jednego store.
2. Wyższy koszt zapytań dla dużych `limit` bez cache.
3. Założenia UI o polach legacy spoza kanonicznego DTO.
