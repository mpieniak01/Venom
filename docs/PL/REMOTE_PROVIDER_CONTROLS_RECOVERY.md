# Lokalne poprawki API zdalnych — 2026-10-30

Zakres przygotowano na gałęzi `codex/remote-provider-controls-recovery`,
na bazie `main` `8d74e9f9`. Do wydania przez PR przygotowano nową gałąź
`codex/remote-apis-scoped-recovery`; poniżej zachowano wyniki kolejnych etapów lokalnych.

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
  Bieżące środowiska obejmują plany mające własny dziennik management.
  Dawne próby CLI są widoczne w osobnej tabeli **Historia prób uruchomienia**:
  ID próby, model, ID instancji, zapisany wynik i błąd. Tabela nie ma przycisków
  operujących na dawnym hoście, a historyczny stan nie potwierdza obecnej
  dostępności. Uszkodzony zapis próby pozostaje widoczny z informacją o błędzie.
  Historyczne pliki pozostają zachowane. Nie wykonano zamówień, zatrzymań ani DELETE u dostawcy.
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

## Przywrócenie historii prób VAST

Po doprecyzowaniu widoku dodano tabelę **Historia prób uruchomienia** w zakładce
Modele → VAST, pod bieżącymi środowiskami. Potwierdzono w API i rzeczywistym DOM
siedem historycznych prób (także uszkodzony wpis) oraz zero bieżących środowisk.
Historia jest tylko do odczytu; jej wyświetlenie nie uruchamia zamówień ani połączeń.

Walidacja tej korekty:
- `pytest -q tests/test_vast_management.py tests/test_api_routes_import_guard.py`:
  39 PASS.
- Testy komponentu `vast-environments.component.test.tsx`: 10 PASS, w tym
  brak przycisków operujących na historii i brak żądań POST przy odczycie.
- `make test-web-unit`, `make test-ci-lite` (895 PASS), katalog/grupy testów
  i diagnostyka pokrycia: PASS.
- `tsc --noEmit --incremental false`, `mypy venom_core/services/vast_management.py`
  oraz hooki Ruff: PASS.
- Końcowe `make pr-fast`: PASS (186,15 s), 1567 testów Python i 252 testy
  komponentów; pokrycie zmian **90,43%**. Brak pominiętych testów komponentów.
- Chrome: tabela historii widoczna, siedem wpisów, zero błędów konsoli przy odbiorze;
  ostrzeżenia preload pozostają poza zakresem. Nie wykonano Test Zero ani
  operacji na zasobach dostawcy. Kod nadal wyłącznie lokalny.

## Spójny styl zakładek OpenRouter i VAST

Panele używają tła, obramowań, cieni i nagłówków odpowiadających zakładkom
Modele / Modele zdalne. Wspólne klasy dotyczą kart, pól formularzy, etykiet
i tabel. Formularze przechodzą do jednej kolumny na wąskich ekranach;
historia VAST ma własne przewijanie poziome bez łamania nazw modeli.
Zmiana obejmuje prezentację, zachowuje istniejące wywołania API i potwierdzenia.

Walidacja:
- Istniejące testy komponentów OpenRouter i VAST: **21 PASS**, zero SKIP.
- `make test-web-unit`: PASS (4,83 s).
- `tsc --noEmit --incremental false`: PASS (22,66 s).
- `make pr-fast`: PASS (185,89 s); 1567 testów Python i 252 komponentów PASS.
  Pokrycie zmian całej lokalnej gałęzi: **91,30%** (próg 80%).
- Po wizualnej korekcie tabeli ponownie wykonano ESLint pięciu zmienionych
  plików (PASS) i powyższe 21 testów komponentów (PASS).
- Chrome: odbiór obu zakładek przy szerokości 1681 px i 390 px. Przy 390 px
  panel miał 350 px szerokości i 350 px zawartości: brak poziomego przepełnienia
  panelu; tabela historii przewija się osobno. Zero błędów konsoli podczas
  odbioru. Pozostają ostrzeżenia preload wspólnego interfejsu.
Nie wykonywano generacji modeli, zamówień VAST ani Test Zero.
Kod pozostaje lokalny na tej samej gałęzi.

## Przegląd przed wydaniem przez PR

Zakres obejmuje wszystkie dotychczasowe poprawki, historię i styl paneli oraz
dwie dodatkowe naprawy mechanizmu odzyskiwania LLM:

1. Ścieżka LLM nie zakłada już bariery modeli działających wewnątrz procesu.
   Wizja i lokalne operacje głosu mogą kontynuować pracę. Runtime switch gate
   i admission nadal blokują generację LLM oraz nakładające się cleanupy.
   Pełne zwalnianie modeli nadal zakłada globalną barierę.
2. Nieudany cleanup LLM ma odrębny typ operacji `llm_cleanup`. Ponowienie
   po przejściowym błędzie może usunąć tę niepewność dopiero po pozytywnej
   weryfikacji silników. Nie kasuje niepewności pełnego cleanupu, operacji
   innych modułów ani aktywnej dzierżawy.

Nowe regresje najpierw wykazały oba błędy. Testy obejmują równoległą pracę
synchroniczną i asynchroniczną, sukces/błąd/anulowanie, wzajemne wykluczanie
obu zakresów cleanupu, zakaz generacji podczas odzyskiwania, bezpieczne
ponowienie i zachowanie niepewności pełnego cleanupu.
Przegląd wewnętrzny nie pozostawił innych zidentyfikowanych blokerów;
recenzja zewnętrzna i bramki GitHub/Sonara pozostają osobnym etapem.

Walidacja przed publikacją:
- `pytest -q tests/test_model_resources_release.py tests/test_runtime_admission.py tests/test_llm_runtime_activation_api.py tests/test_remote_provider_control.py`: **200 PASS**.
- `make test-ci-lite`: **895 PASS** (79,60 s).
- `make test-web-unit`: PASS (4,87 s).
- `make test-catalog-check test-groups-check check-new-code-coverage-diagnostics`: PASS.
- `mypy venom_core/services/runtime_release_service.py venom_core/services/runtime_admission.py`: PASS; hooki Ruff/isort: PASS.
- `python scripts/export_openapi.py --output <prywatny-raport>`: PASS.
- `make pr-fast`: 1575 testów Python PASS, pokrycie zmienionych linii **92,80%** (próg 80%). Pełny wynik zapisano w opisie PR.

Testy używają atrap i izolacji sieci/GPU/usług. Nie wykonano płatnej generacji,
Test Zero ani działań na robocie. Nie obniżono progów i nie pomijano regresji
na potrzeby wydania. Starsze lokalne zapisy niepewnego pełnego cleanupu
pozostają blokujące: naprawa LLM nie udaje ich zweryfikowania.

### Uzupełnienie izolacji po kontroli pre-push

Pierwszy hook pre-push wykrył zależność testu braku klucza od prywatnego pliku
poświadczeń operatora. Autouse fixture przydziela teraz każdemu testowi także
odrębną ścieżkę pliku klucza OpenRouter. Produkcyjny plik i konfiguracja
operatora pozostają bez zmian.

Regresja z jawnym plikiem-atrapą klucza:
`pytest -q tests/test_openrouter_runtime.py tests/test_remote_provider_control.py tests/test_test_environment_isolation.py`
— **111 PASS**. Pełny obowiązkowy hook pre-push jest ponawiany bez obejść.

## Poprawki po recenzji PR #567

Cztery uwagi recenzji i dodatkową uwagę o stanach VAST potwierdzono w kodzie:
- Kontrola wyłączenia OpenAI/Google jest wykonywana przy każdym wyjściu
  HTTP, również po narzędziu i w retry SDK. Lokalna odmowa zachowuje wcześniejsze
  dowody transportu: zakończona odpowiedź lub zweryfikowane odrzucenie nie
  tworzą fałszywej kwarantanny, ale timeout/niepewne 500 nie mogą zostać ukryte.
  Ponowne włączenie API podczas retry unieważnia wcześniejszą lokalną odmowę.
- 401/403 są klasyfikowane jako problem uwierzytelniania; 429 i błędy serwera
  jako niedostępność dostawcy.
- Plan CLI pozostaje w historii, lecz zachowuje obserwowane połączenie.
  Odświeżanie katalogu czatu uwzględnia połączenia w obu listach.
- Historia pokazuje możliwe opłaty i wskazówkę sprawdzenia/zwolnienia instancji
  w konsoli VAST. Nie dodano automatycznych działań na dawnych hostach.
- Stany `submitting`, `created` i `outcome_unknown` mają tłumaczenia PL/EN/DE;
  inne nierozpoznane stany pozostają widoczne w oryginalnej postaci.

Regresje używają prawdziwego SDK z MockTransport, bez sieci i generacji modeli.
Sprawdzają brak wysyłki wyniku narzędzia po wyłączeniu API, wyścig między
walidacją i wysłaniem, retry, zachowanie kwarantanny oraz jej niewymaganie
po zakończonej operacji. Testy VAST obejmują zmianę połączenia CLI, ostrzeżenia
o opłatach i czytelne wyniki, bez żądań POST przy samym odczycie historii.

Walidacja: 162 testy backendu PASS; 12 testów komponentu VAST PASS;
`make test-ci-lite` (895 testów) PASS; `make test-web-unit`, katalog/grupy
i diagnostyka pokrycia PASS; mypy czterech modułów, TypeScript i Ruff PASS.
Hook `pre-push` uruchamia pełne `make pr-fast` dla zmian objętych zakresem;
kontrola `block-docs-dev-tracked` jest wykonywana osobno.
Poprzednie zdalne CI, oba E2E i bramka Sonara dla `1f6d9225` są zielone;
po aktualizacji wymagają ponownego potwierdzenia dla nowego SHA.

### Zgłoszenia Sonara po aktualizacji recenzji

Bramka Sonara dla `b2ae025e` była zielona, lecz raport zawierał 16 zgłoszeń
utrzymaniowych: 3 HIGH i 13 MEDIUM. Wprowadzono naprawy wszystkich wskazań:
- wydzielono walidację bariery mutacji oraz odczyt jednego wpisu VAST,
  zmniejszając złożoność funkcji bez zmiany warunków blokad i obsługi błędów;
- dodano jedną stałą sufiksu planu;
- testy wyjątków wykonują w bloku `pytest.raises` tylko badane wywołanie;
  przygotowanie danych jest poza tym blokiem;
- regresja timeoutu wymaga konkretnego `ChatClientException`;
- sprawdzenie spoczynku transportu ma jawne warunki zachowujące kolejność
  i logikę oceny wcześniejszych prób.

Regresje: 256 testów PASS; Ruff PASS. Nie wyłączano reguł ani nie zmieniano
statusów zgłoszeń. Zamknięcie wskazań wymaga wyniku kolejnego skanu.
Poprawiono też doprecyzowanie recenzenta dotyczące kierunku wywołania hooka:
to `pre-push` uruchamia `make pr-fast`, a nie odwrotnie.
