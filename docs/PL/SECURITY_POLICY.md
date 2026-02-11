# Polityka Bezpieczeństwa

Ten dokument definiuje oficjalną politykę bezpieczeństwa dla działania Venom: ochronę API/runtime, kontrolę autonomii agentów oraz zasady izolacji i testów regresji.

## Zakres

Polityka obejmuje:

- zabezpieczenia API/runtime dla lokalnej administracji,
- egzekwowanie autonomii dla operacji mutujących,
- założenia izolacji przestrzeni roboczej i wykonania,
- minimalne bramki jakości i testy wymagane do blokowania regresji.

Dla higieny zależności/CVE zobacz `docs/PL/SECURITY_FIXES.md`.

## Model bezpieczeństwa

Venom działa w modelu podwójnym:

1. bezpieczeństwo względem agenta AI (ochrona przed niepożądanym działaniem automatyki),
2. suwerenność lokalnego administratora (pełna kontrola nad konfiguracją lokalną).

Założenia operacyjne:

- administracja single-user na hoście lokalnym,
- domyślnie sieć zaufana/prywatna,
- brak bezpośredniej publicznej ekspozycji endpointów administracyjnych backendu.

## Zasady nadrzędne

1. Suwerenność lokalnego admina
- Lokalny administrator może modyfikować konfigurację `.env`.
- Polityka nie narzuca blacklisty zmiennych dla operacji wykonywanych z localhost.

2. Lokalny dostęp do powierzchni administracyjnej
- Endpointy administracyjne konfiguracji muszą działać wyłącznie z localhost (`127.0.0.1` / `::1`).
- Żądania zdalne do tych endpointów muszą zwracać `403`.

3. Minimalne uprawnienia agenta
- Operacje mutujące wymagają jawnej kontroli poziomu autonomii.
- Nieznane/nieskategoryzowane ścieżki mutujące są domyślnie blokowane.

4. Obrona warstwowa
- Ograniczenia hosta + kontrola autonomii + izolacja deploymentu.

## Wymagania dla API i konfiguracji

Następujące endpointy są traktowane jako administracyjne i muszą egzekwować localhost-only:

- `POST /api/v1/config/runtime`
- `GET /api/v1/config/backups`
- `POST /api/v1/config/restore`

Dodatkowy wymóg:

- `GET /api/v1/config/runtime` musi zwracać sekrety w postaci maskowanej (`mask_secrets=True`).

## Wymagania egzekwowania autonomii

Wszystkie mutujące ścieżki skills muszą być objęte kontrolą uprawnień. Standardowe helpery:

- `require_file_write_permission()`
- `require_shell_permission()`
- `require_core_patch_permission()`

Minimalny zakres ochrony:

- skille zapisu/edycji plików,
- skille wykonujące shell,
- operacje patch/rollback w rdzeniu,
- ścieżki importu MCP, które uruchamiają komendy shell.

## Granice izolacji

1. Rdzeń (`venom_core/`)
- Traktowany jako obszar systemowy wymagający ochrony.
- Modyfikacje inicjowane przez agenta muszą być jawnie ograniczane i audytowalne.

2. Workspace (`workspace/`)
- Podstawowa piaskownica mutowalna dla artefaktów tworzonych przez agenta.

3. Rozszerzenia MCP/runtime
- Działają jako kontrolowane procesy zewnętrzne i nadal podlegają polityce hosta oraz autonomii.

## Testy i bramki jakości

Zmiana bezpieczeństwa jest uznana za poprawną dopiero po przejściu testów regresji.

Wymagane przed merge:

- `pre-commit run --all-files`
- `mypy venom_core`
- `make check-new-code-coverage`
- `make pr-fast`

Rekomendowane pod release:

- `make pytest`
- `make sonar-reports`

Zakres testów bezpieczeństwa powinien obejmować:

- zachowanie localhost-only (`403` dla hosta zdalnego),
- maskowanie sekretów przy odczycie runtime config,
- `AutonomyViolation` dla zabronionych operacji mutujących.

Zobacz też: `docs/PL/TESTING_POLICY.md` i `docs/PL/AUTONOMY_GATE.md`.

## Ograniczenia deploymentu

Ta polityka zakłada brak publicznej ekspozycji powierzchni sterowania backendu.

Jeśli wymagany jest dostęp zdalny/publiczny:

- użyj reverse proxy,
- dodaj uwierzytelnianie/autoryzację,
- ogranicz dostęp do zaufanych operatorów.

Zobacz: `docs/PL/DEPLOYMENT_NEXT.md`.
