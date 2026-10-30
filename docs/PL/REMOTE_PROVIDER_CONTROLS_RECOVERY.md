# Lokalne poprawki API zdalnych — 2026-10-30

Zakres przygotowano na gałęzi `codex/remote-provider-controls-recovery`,
na bazie aktualnego `main` `8d74e9f9`. Zmiany pozostają lokalne.

## Diagnoza i zachowanie

- **OpenAI / Google:** zakładka Modele → Modele zdalne ma przyciski Włącz API /
  Wyłącz API. Flaga jest trwała, niezależna od wybranego modelu i dostępności
  poświadczeń. Wyłączone API znika z listy dostawców czatu; katalog, aktywacja
  oraz nowe wywołania istniejących klientów respektują tę flagę. Wyłączenie
  nie anuluje odpowiedzi już wysłanej do dostawcy.
- **409 przy wyborze modelu:** rejestr admission zawierał niepewną operację
  `maf_generation` po nieistniejącym procesie. Blokada nadal chroni przed
  równoległą pracą; UI rozróżnia zajętość i konieczność odzyskania. Akcja
  **Przywróć LLM / odblokuj czat** używa osobnego lokalnego endpointu
  `POST /api/v1/system/models/recover-llm`. Weryfikuje lokalne silniki LLM;
  nie wywołuje zwalniania zarejestrowanych modeli wizji/głosu. Nie usuwa
  niepewności innych operacji modułów ani aktywnej dzierżawy.
- **VAST:** siedem widocznych wcześniej pozycji stanowiło historię prób CLI,
  a nie bieżące zamówienia panelu. Odczyt konta dostawcy zwrócił zero instancji.
  Widok zarządzania pokazuje tylko plany mające własny dziennik management;
  błędny dziennik takiego zamówienia nadal jest widoczny jako błąd. Historyczne
  pliki pozostają zachowane. Nie wykonano zamówień, zatrzymań ani DELETE u dostawcy.
- **Czerwony main:** CI i Simulated regression zatrzymał ten sam test
  `test_api_routes_layer_imports_are_explicitly_whitelisted`: trasa VAST
  importowała klienta infrastruktury z pominięciem serwisu. Import usunięto
  bez zmiany allowlisty. Skan Sonara dla tego uruchomienia był pominięty;
  wcześniejszy zielony wynik Sonara nie jest wynikiem analizy tej rewizji.

Źródła stanu main:
[CI](https://github.com/mpieniak01/Venom/actions/runs/41013857400),
[Simulated regression](https://github.com/mpieniak01/Venom/actions/runs/41013857450).

## Walidacja

Automatyczne testy wykonano w istniejącym venv, z odizolowaną siecią,
ukrytymi danymi/modelami produkcyjnymi, GPU i socketami usług. Transporty
zewnętrznych API były atrapami. Dodatkowo testy otrzymały własne pliki
wyboru dostawcy, modelu i przełączników, zamiast stanu operatora.

| Polecenie / grupa | Wynik | Czas |
| --- | --- | --- |
| pytest: 10 zmienionych grup backendu + guard importów | 375 PASS | 36,06 s |
| pytest: release, provider control, VAST runtime (ostatnie kontrakty) | 117 PASS | 3,81 s |
| pytest: provider control po uzupełnieniu walidacji metadanych | 38 PASS | 1,77 s |
| ukierunkowane testy UI | 40 PASS, 1 SKIP | 5,46 s |
| make test-web-unit | PASS | 4,37 s |
| make test-ci-lite | 895 PASS | 78,18 s |
| make test-catalog-check / test-groups-check / check-new-code-coverage-diagnostics | PASS | 0,26 s |
| Ruff + mypy dla 11 zmienionych modułów | PASS | 68,21 s |
| tsc --noEmit --incremental false | PASS | 25,75 s |
| make pr-fast — końcowy przebieg | PASS | 188,74 s |

Końcowe `pr-fast`: 1566 testów Python PASS, frontend lint i jednostki PASS,
251 testów komponentów PASS. Pokrycie zmienionych linii **90,57%** przy progu
80%. Pierwszy przebieg miał 78,43%; uzupełniono testy obsługi metadanych,
błędów autoryzacji, transportu i nieprawidłowych odpowiedzi, bez obniżania progów.
Jedyny SKIP w ukierunkowanym UI dotyczy istniejącego opcjonalnego pomiaru wydajności.

## Odbiór lokalny i ograniczenia

Przeładowano wyłącznie API. API 8800 i UI 3300 działają z kanonicznego checkoutu.
Po starcie admission zwraca `available`, zero operacji. Rejestr nadal zawiera
właścicieli vision, STT, TTS oraz voice_sessions.

W rzeczywistym Chrome kliknięto Wyłącz API dla OpenAI i Google. Obie pozycje
zniknęły z rozwiniętego selektora serwera czatu oraz z runtime/options.
Przywrócono poprzednie wartości obu przełączników. API VAST zwraca pustą
listę bieżących środowisk.

Nie wykonano płatnej generacji, rzeczywistego Test Zero ani testu ruchu robota.
Aktywacja modeli i ścieżki błędów są zweryfikowane testami z atrapami transportu;
nie jest to dowód odpowiedzi rzeczywistego modelu zewnętrznego.
Konsola czatu zgłasza też niedostępny opcjonalny daemon multi_runtime na 8014;
nie uruchamiano drugiego silnika tylko na potrzeby tego odbioru.
Nie publikowano commitów ani nie zmieniano zdalnych bramek.
