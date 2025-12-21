# 068: Kontrola warstwy lekcji (learning governance)

## Cel
Wprowadzić pełną kontrolę nad warstwą „lekcyjną”:
włączanie/wyłączanie zapisu, pauza, czyszczenie, audyt i retencja.
To warstwa pośrednia do wykrywania wzorców, która finalnie powinna prowadzić
do tooli lub ukrytych promptów, a nie żyć wiecznie sama dla siebie.

## Zakres
1. **Przełączniki zapisu**
   - Globalny „learning on/off”.
   - Per-request: możliwość wyłączenia zapisu (Lab Mode).

2. **Operacje na lekcjach**
   - Usuń ostatnie N.
   - Usuń po zakresie czasu.
   - Usuń po tagu.
   - Purge całości (z potwierdzeniem).

3. **Retencja i higiena**
   - TTL dla lekcji.
   - Deduplikacja i scalanie wzorców.
   - Oznaczanie jakości (np. tylko z kciuka w górę).

4. **Audyt i podgląd**
   - Lista ostatnich zapisów.
   - Informacja: kto/który request spowodował zapis.
   - „Dlaczego” dana lekcja została zapisana.

## Kryteria akceptacji
- Można włączyć/wyłączyć zapis lekcji globalnie i per-request.
- Dostępne operacje czyszczenia (N, czas, tag, purge).
- Retencja i deduplikacja ograniczają wzrost danych.
- Audyt pokazuje źródło i powód zapisu.

## Status
Zakończone.

## Wykonane
- Dodano globalny toggle uczenia (`/api/v1/memory/lessons/learning/*`) i flagę w configu.
- Dodano TTL (`/api/v1/memory/lessons/prune/ttl`) oraz deduplikację (`/api/v1/memory/lessons/dedupe`).
- Rozszerzono metadane lekcji o źródło, intencję, powod i agenta.
- Zaktualizowano dokumentację `docs/KNOWLEDGE_HYGIENE.md`.
- Dodano testy governance lekcji.

## Proponowane pliki do zmiany
- `venom_core/core/models.py` (flagi zapisu, metadane)
- `venom_core/memory/*` (retencja, deduplikacja, audyt)
- `venom_core/api/routes/*` (endpointy zarządzania lekcjami)
- `docs/KNOWLEDGE_HYGIENE.md` (rozszerzenie dokumentacji)
