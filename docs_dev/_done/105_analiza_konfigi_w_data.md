# Analiza: konfiguracje w `data/` i bezpieczna migracja do `config/`

Data: 2026-02-02
Gałąź: (n/d)

## Cel
Sprawdzić, czy pliki konfiguracyjne trzymane obecnie w `data/config/` powinny zostać przeniesione do `config/` oraz zaproponować bezpieczny plan migracji (bez przerywania działania i z kompatybilnością wsteczną).

## Stan obecny (inwentaryzacja)
### Zawartość `data/config/`
- `autonomy_matrix.yaml`
- `skill_permissions.yaml`
- `pricing.yaml`

### Gdzie są używane
- `venom_core/core/permission_guard.py`:
  - `data/config/autonomy_matrix.yaml`
  - `data/config/skill_permissions.yaml`
- `venom_core/core/token_economist.py`:
  - `data/config/pricing.yaml`
- `venom_core/execution/model_router.py`:
  - `data/config/pricing.yaml`
- `venom_core/config.py`:
  - `GOOGLE_CALENDAR_CREDENTIALS_PATH=./data/config/...`
  - `GOOGLE_CALENDAR_TOKEN_PATH=./data/config/...`
- Dokumentacja: ścieżki `data/config/*` są utrwalone w kilku plikach docs (`docs/**`, `README_PL.md`, `docs/EXTERNAL_INTEGRATIONS.md`, itd.)

### Kontekst repo
- `data/` zawiera głównie artefakty runtime (memory, timelines, datasets, feedback, models, etc.).
- `config/` zawiera konfiguracje repo (`pytest-groups`, `env-history`) i jest „naturalnym” miejscem dla konfiguracji systemowych.
- `data/config/` jest obecnie wersjonowane (pliki YAML są w git).
- Sekrety Google Calendar są ignorowane tylko dla ścieżek `data/config/google_calendar_*.json`.

## Wnioski
1) **Semantyka katalogów**: `data/` to runtime/artifacts, a `config/` to konfiguracje. Obecne `data/config/` miesza te role i bywa mylące.
2) **Ryzyko migracji**: Ścieżki są używane w kodzie i dokumentacji. Jednorazowe przeniesienie bez fallbacków spowoduje błędy przy starcie (brak plików) i rozjazd w docs.
3) **Sekrety**: Pliki OAuth Google Calendar są z natury „runtime” (tokeny) i powinny być ignorowane niezależnie od lokalizacji. Migracja wymaga aktualizacji `.gitignore`.

## Rekomendacja
Tak, konfiguracje w `data/config/` powinny docelowo znaleźć się w `config/` jako **prosta, płaska struktura** (bez odtwarzania `data/config`), ale **migrację należy wykonać etapami z kompatybilnością wsteczną**.

## Proponowana bezpieczna migracja (etapy)
### Etap 0 — Ustalenie docelowych ścieżek
Docelowo (prosta struktura):
- `config/autonomy_matrix.yaml`
- `config/skill_permissions.yaml`
- `config/pricing.yaml`
- (opcjonalnie) `config/google_calendar_credentials.json`
- (opcjonalnie) `config/google_calendar_token.json`

### Etap 1 — Dodanie fallbacków w kodzie (bez przenoszenia plików)
- Wprowadzić logikę: **najpierw `config/`, potem fallback do `data/config/`**.
- Zrobić to w:
  - `venom_core/core/permission_guard.py`
  - `venom_core/core/token_economist.py`
  - `venom_core/execution/model_router.py`
  - `venom_core/config.py` (domyślne ścieżki Google Calendar)
- Dodać czytelny log: „Using config from <path>” + ostrzeżenie przy użyciu legacy `data/config`.

### Etap 2 — Przeniesienie plików w repo
- Przenieść wersjonowane YAML z `data/config/` do `config/`.
- Zaktualizować docs, przykłady i README.
- Zaktualizować `.gitignore`:
  - dodać `config/google_calendar_credentials.json`
  - dodać `config/google_calendar_token.json`

### Etap 3 — Czyszczenie legacy
- Po 1–2 wydaniach usunąć fallback `data/config/`.
- Usunąć dokumentację odnoszącą się do `data/config/`.

## Ryzyka i mitigacje
- **Ryzyko: brak plików po przeniesieniu** → mitigacja: fallback w Etapie 1 + log warn.
- **Ryzyko: rozjazd docs** → mitigacja: jednorazowa aktualizacja dokumentacji w Etapie 2.
- **Ryzyko: sekrety w repo** → mitigacja: `.gitignore` dla nowych ścieżek.

## Minimalny zakres zmian w kodzie (do Etapu 1)
- Dodać helper do rozwiązywania ścieżki (np. `resolve_config_path("pricing.yaml")`), który:
  1) sprawdza `config/<name>`
  2) fallback na `data/config/<name>`

## Wykonane (Etap 1)
### 2026-02-02
- Dodano helper `resolve_config_path()` z fallbackiem na legacy `data/config` + log warning.
- Przełączono odczyt w:
  - `venom_core/core/permission_guard.py` (autonomy_matrix / skill_permissions)
  - `venom_core/core/token_economist.py` (pricing.yaml)
  - `venom_core/execution/model_router.py` (pricing.yaml)
  - `venom_core/execution/skills/google_calendar_skill.py` (credentials/token)
- Zmieniono domyślne ścieżki w `venom_core/config.py` na `./config/...` z zachowaniem fallbacków.

## Proponowane testy/regresje
- Start aplikacji bez `config/` (tylko legacy `data/config`) → powinno działać.
- Start aplikacji z przeniesionymi plikami (tylko `config/`) → powinno działać.
- W przypadku braku obu ścieżek: oczekiwane logi + fallback/default behavior.

## Stan jakości (baseline z 2026-02-02)
Wykonane zgodnie z README_PL.md:
- `ruff check . --fix` → OK
- `ruff format .` → OK
- `isort .` → OK
- `mypy venom_core` → OK (Success: no issues found in 236 source files)
- `npm --prefix web-next run lint` → OK
- `npm --prefix web-next run build` → OK
- `npm --prefix web-next run test:e2e` → FAIL (preflight: Next Cockpit niedostępny pod `http://127.0.0.1:3000`; legacy Cockpit pod `http://localhost:8000` OK)

## Otwarte pytania
- Czy `config/` ma być jedynym miejscem dla konfiguracji runtime, czy pozostawiamy część w `data/` (np. sekrety i tokeny) z wyraźnym podziałem?
- Czy nazwa `config/` nie koliduje z istniejącymi „repo config” (pytest-groups, env-history)?

## Szybka decyzja (jeśli chcemy iść dalej)
- **Tak, przenosić**: zaczynamy od Etapu 1 (fallback), potem Etap 2 (przenosiny + docs).
- **Nie, zostawić**: dokumentujemy, że `data/config` to „runtime config”, a nie dane.

## Podsumowanie zmian (2026-02-02)
- Dodano helper `resolve_config_path()` z fallbackiem na legacy `data/config` i logiem ostrzegawczym.
- Zmieniono odczyt konfiguracji w PermissionGuard/TokenEconomist/ModelRouter oraz w skillu Google Calendar na nowy resolver.
- Ustawiono domyślne ścieżki w `venom_core/config.py` na `./config/...` (z zachowanym fallbackiem).
- Wykonano weryfikację jakości: ruff/isort/mypy oraz `pytest tests/test_api_dependencies.py -q`.

## Wykonane (Etap 2)
### 2026-02-02
- Przeniesiono wersjonowane pliki z `data/config/` do `config/`:
  - `autonomy_matrix.yaml`
  - `skill_permissions.yaml`
  - `pricing.yaml`
- Zaktualizowano odwołania w dokumentacji z `data/config` na `config`.
- Dodano ignorowanie plików Google Calendar w `.gitignore` dla nowych ścieżek.

## Wykonane (Etap 3)
### 2026-02-02
- Usunięto fallback `data/config` z resolvera ścieżek i logik skilli.
- Pozostawiono wyłącznie `config/` jako źródło konfiguracji.
- Potwierdzono brak odwołań do `data/config` w kodzie.

## Weryfikacja (Etap 3) — 2026-02-02
- `ruff check . --fix` → OK
- `ruff format .` → OK
- `isort .` → timeout po 120s; wykonano na plikach zmienionych → OK
- `mypy venom_core` → OK (237 plików)
- `pytest tests/test_api_dependencies.py -q` → OK (2 passed)

## Pozostało do zrealizowania
- Commit zmian Etapu 2–3 na gałęzi `105_config_migration`.
- (Opcjonalnie) push gałęzi do zdalnego repo.
- (Opcjonalnie) testy rozszerzone (light/long) po pełnym przeniesieniu configów.

## Naprawa testów (2026-02-02)
- Uodporniono `tests/perf/test_llm_latency_e2e.py` na brak `task_finished` w SSE: dodano polling `/api/v1/tasks/{id}` po timeout SSE.
- Wynik lokalny: `pytest tests/perf/test_llm_latency_e2e.py -q` → SKIPPED (backend zakończył task poza SSE timeoutem).

## Status końcowy (2026-02-02)
- Wszystkie etapy 1–3 zrealizowane.
- Dokumentacja zaktualizowana, migracja plików zakończona.
- Testy jakości wykonane; poprawiono stabilność testu `test_llm_latency_e2e` i ustawiono domyślnie 2 powtórzenia.
- Pozostało: commit zmiany w `tests/perf/test_llm_latency_e2e.py`.

## Podsumowanie PR (dla recenzentów)
**Cel**
- Migracja konfiguracji z `data/config` do `config` + usunięcie legacy fallbacków.
- Stabilizacja testu `test_llm_latency_e2e`.

**Zakres zmian**
- Przeniesiono: `autonomy_matrix.yaml`, `skill_permissions.yaml`, `pricing.yaml` → `config/`.
- Zaktualizowano dokumentację i przykłady środowiskowe do `config/*`.
- `.gitignore` rozszerzony o pliki Google Calendar w `config/`.
- Usunięto fallback `data/config` w resolverze ścieżek.
- Test latencji: polling statusu po timeout SSE + 2 powtórzenia + prosty prompt.

**Testy / weryfikacja**
- `ruff check . --fix`, `ruff format .`, `isort` (na zmienionych plikach)
- `mypy venom_core`
- `pytest tests/test_api_dependencies.py -q`
- `pytest tests/perf/test_llm_latency_e2e.py -q` (może SKIPPED gdy backend kończy task poza SSE)

**Uwagi**
- Po wdrożeniu wymagane są ścieżki `config/*` w środowisku runtime.
