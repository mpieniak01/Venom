# Coding Agent + MCP Policy

Ten dokument definiuje zasady użycia MCP z GitHub Coding Agent w repo Venom.

## Cel

Używać MCP tylko tam, gdzie realnie poprawia jakość planowania/implementacji, bez rozszerzania powierzchni ryzyka.

## Zasady bazowe

1. Minimal privilege: podłączaj tylko te MCP, które są potrzebne.
2. Minimal scope: ogranicz serwery MCP do konkretnych use-case'ów.
3. No blind trust: dane z MCP traktuj jak wejście wymagające walidacji.
4. No secret sprawl: tokeny/sekrety tylko przez bezpieczne mechanizmy GitHub/organizacji.

## Rekomendacja dla Venom

1. Domyślnie polegaj na lokalnym kontekście repo + CI gates.
2. MCP włączaj selektywnie:
   - issue/PR context enrichment,
   - read-only knowledge retrieval,
   - integration-specific diagnostics.
3. Nie uzależniaj Hard Gate od dostępności MCP.

## Niedozwolone praktyki

1. MCP jako źródło decyzji merge bez walidacji CI.
2. Nadawanie serwerom MCP uprawnień wykraczających poza zadanie.
3. Trwałe osadzanie sekretów MCP w repo.

## Operacyjna checklista przed włączeniem nowego MCP

- [ ] Uzasadniony przypadek użycia.
- [ ] Zdefiniowany owner i odpowiedzialność operacyjna.
- [ ] Ocenione uprawnienia i ryzyka.
- [ ] Zapewniony fallback bez MCP.
- [ ] Udokumentowany wpływ na workflow agenta.
