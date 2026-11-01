# Przegląd lokalny i wydanie aktualizacji PR #575 — 2026-11-01

Gałąź: `feat/light-model-maintenance-comparison`. Bazowy `origin/main` to
`1ef42d5a9e071c7c9819c500ec6be3f3f6cc8582`; gałąź nie wymaga scalania main.
Operator zlecił publikację aktualizacji do recenzji. Wcześniejsze wzmianki
w raportach o wstrzymaniu publikacji opisują stan historyczny.

## Zakres przeglądu

Sprawdzono izolację sandboxa, hostową dzierżawę wykonawcy, walidację jego
ścieżek, limity i kończenie operacji oraz rozróżnianie rzeczywistych instalacji,
wyboru i obserwowanego stanu modeli. Katalog obejmuje osiem pierwotnych modeli
oraz Gemmę 4 E2B i Qwena3.5. Raport 350 prób i późniejsze porównanie 30 prób
przyspieszonego Qwena są oddzielnymi wynikami. Techniczne kwalifikacje adapterów
nie są doliczane do baseline.

Znaleziono i naprawiono dwie dodatkowe usterki:

- niepoprawny typ `weight_map` w indeksie checkpointu mógł przerwać listowanie;
- niepoprawny adres IPv6 silnika mógł przerwać agregację obserwacji runtime.

Pięć wariantów regresji potwierdziło fail → pass. Błędne dane są teraz odrzucane
lub pozostają niezweryfikowane, bez zgadywania stanu modelu.

## Walidacja

- Celowane `pytest` ośmiu plików maintenance oraz discovery: **180 PASS**, 5,71 s.
- Ruff check i format zmienionego kodu: PASS; hooki lokalnego commita: PASS.
- Kontrola diffu dla typowych formatów jawnych sekretów: zero dopasowań;
  nie zastępuje skanerów bezpieczeństwa.
- `npm --prefix web-next ci`: PASS, 46.95 s.
- `mypy venom_core/services/maintenance_comparison venom_core/core/model_inventory.py venom_core/core/model_manager_discovery.py venom_core/services/model_runtime_inventory.py venom_core/api/routes/models_install.py`: PASS, 59.16 s.
- `make test-web-unit`: PASS, 8.38 s.
- `make test-ci-lite`: PASS, 84.54 s.
- `make test-catalog-check`: PASS, 0.06 s.
- `make test-groups-check`: PASS, 0.05 s.
- `make check-new-code-coverage-diagnostics`: PASS, 0.13 s.
- `make pr-fast`: PASS, 226.99 s.
- `make check-new-code-coverage-diagnostics`: PASS, 0.13 s.

Łączny czas sekwencji od `npm ci` do końcowej diagnostyki: **426.39 s
(7.11 min)**. `make pr-fast`: **226,99 s**, 1376 testów backendu,
358 testów komponentowych i 12 testów Studio oraz testy jednostkowe/lint frontendu.
Pokrycie zmienionych linii: **87,56%**, wymagane 80%; końcowa diagnostyka PASS.
Kod wykonawczy sprawdzono na `f0d3be12`; po bramce uzupełniono wyłącznie raport.

## Ograniczenia i kontrole GitHub

- Nie powtarzano zadań modeli, generacji, Test Zero ani operacji VAST.
  Kontrole lokalne korzystały z atrap; nie uruchamiano drugiego stosu.
- Sonar na starej rewizji `1344854e` zgłaszał 57 otwartych problemów i zero
  hotspotów. Część dotyczy już poprawionych lokalnie ścieżek, uprawnień tmpfs
  i operacji async. Weryfikację ich zamknięcia pozostawiono świeżemu skanowi.
  Nie zmieniano ręcznie statusów zgłoszeń.
- CodeRabbit wcześniej pominął Draft; to nie jest zaliczony przegląd.
  Aktualizacja ma zostać skierowana do rzeczywistej recenzji.
- `npm ci` zgłosił 16 podatności moderate w istniejącym lockfile. Nie wykonywano
  automatycznego `audit fix --force`; wymagane skany zależności pozostają osobną
  kontrolą GitHub.
- Historia prób, checkpointy, prywatne logi i konfiguracja hosta pozostają lokalne.
  Czyszczenie dysku i zmiany dwóch niezależnych projektów Compose nie są częścią PR.
