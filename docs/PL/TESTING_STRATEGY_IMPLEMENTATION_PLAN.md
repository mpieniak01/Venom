# Plan zmian strategii testów na jednym komputerze

Stan analizy: 27 października 2026, kod bazowy `b595ed24ac0d496067ae347c3e73112fb9609457`.
Status: plan realizacji; poniższe PR-y nie zostały jeszcze utworzone ani wdrożone.

Celem jest powtarzalna weryfikacja kodu bez uruchamiania drugiej instancji Venoma,
bez przełączania modelu operatora i bez kolizji między testami a działającą aplikacją.
Testy fizyczne używają istniejącej instancji; gdy Venom nie działa, są pomijane.
Workery pytest wykonujące testy z atrapami nie są instancjami serwera Venom.

## Wnioski z analizy kodu i wcześniejszych przebiegów

| Obszar | Potwierdzony stan | Konsekwencja |
|---|---|---|
| Katalog | 514 plików: 285 unit, 88 route_contract, 86 service_contract, 25 integration, 16 gate, 14 perf | Typ testu nie opisuje dostępu do fizycznych zasobów |
| Grupy wydaniowe | 459 fast, 41 long, 14 heavy | Podział dotyczy plików, nie liczby przypadków pytest |
| Klasyfikacja | `_release_bucket` używa typu i nazwy pliku | Integracja może używać atrap; test jednostkowy może importować kod dotykający usług |
| Workery | heavy=1, long=2, fast=6; grupy wykonywane kolejno | Brak kwalifikacji optymalnej liczby workerów na tym PC |
| Scheduler | `pytest.ini` ustawia `--dist loadfile` | Plik pozostaje w jednym workerze; największy plik może wydłużyć koniec grupy |
| Warunek gotowości | `requires_stack` jest obsługiwany w conftest, ale spis nie znalazł jego użycia w plikach katalogu | Obecny wspólny mechanizm nie chroni testów fizycznych |
| Testy direct LLM | Test wydajności odpytuje Ollamę i wykonuje `ollama run` | Może użyć modelu przy wyłączonym Venomie i ominąć kontrolę dostępu hosta |
| Preflight E2E | `ensureActiveChatModel` może wykonać POST aktywujący model | Samo sprawdzenie gotowości zmienia runtime operatora |
| Playwright | `webServer.command` może wystartować Next.js; reuse oznacza ponowne użycie, jeżeli znaleziono serwer | Brak istniejącego UI może uruchomić nowy proces aplikacji |
| Adresy | W wielu helperach domyślnie API 8000 i UI 3000; profil lokalny używa 8800 i 3300 | Możliwe pominięcie działającej instancji lub trafienie do innej usługi |
| Stan symulowanych testów | Fixture izoluje m.in. workspace i Academy, ale nie MEMORY_ROOT ani globalnego obiektu admission | Zaobserwowano kolizje z blokadą serwera i pozostawiony runtime_busy |
| Dobór coverage | Budżet i poprzedni JUnit zmieniają wybrany zestaw; fallback uwzględnia changed-lines, a floor jest sprawdzany później | Pierwszy gate przeszedł, kolejny naruszył floor skill_adapter.py; większy budżet pomógł, nie usunął przyczyny |
| Ograniczenia runnera | Stały cwd, kasowanie PYTEST_ADDOPTS, brak własnego limitu testu | Inny checkout może skierować wykonanie do aktywnego repo; limit z zewnątrz może zniknąć |

Spis AST i prostych odwołań do sieci/procesów objął wszystkie 514 plików.
178 plików jest kandydatami do ręcznej weryfikacji; to nie jest liczba testów
fizycznych, ponieważ część używa atrap. Markery znalezione w kodzie obejmują
14 plików performance, 3 manual_llm, 6 integration, 3 requires_docker i
3 requires_docker_compose. Te zbiory mogą się przecinać.

Dowód działania poprawki bazowej: [CI na main](https://github.com/mpieniak01/Venom/actions/runs/40512432868)
zakończył się sukcesem; backend raportował 7981 passed i 126 skipped.
Nie jest to kwalifikacja pełnego runnera heavy/long/fast ani optimum workerów.

### Miejsca kodu do sprawdzenia w implementacji

- [Klasyfikacja i generowanie grup](../../scripts/sync_pytest_groups_from_catalog.py).
- [Runner grup backendu](../../scripts/run-pytest-optimal.sh), [cele make](../../make/tests.mk).
- [Fixture i warunki gotowości](../../tests/conftest.py).
- [Direct Ollama](../../tests/perf/test_llm_runtime_direct.py).
- [API testów fizycznych](../../tests/perf/chat_pipeline.py).
- [Preflight E2E](../../web-next/scripts/check-e2e-env.mjs).
- [Konfiguracja Playwright](../../web-next/playwright.config.ts).
- [Dobór coverage](../../scripts/run_new_code_coverage_gate.py), [resolver](../../scripts/resolve_sonar_new_code_tests.py).
- [Kontrakty zasobów runtime](../RUNTIME_ADMISSION.md).

## Docelowe reguły wykonania

Dwie niezależne osie opisu: koszt wykonania oraz środowisko i skutki uboczne.
`fast`, `long` i `heavy` pozostają zgodnymi nazwami istniejących grup.
Do czasu pomiarów nie zmieniamy globalnie domyślnego fast=6 na niezweryfikowaną wartość.

| Tryb | Venom wyłączony | Venom włączony i wolny | Venom zajęty |
|---|---|---|---|
| Symulowany | Wykonanie z własnym stanem | Wykonanie z własnym stanem i limitem CPU/RAM | Wykonanie z limitem zasobów; bez dostępu do żywego runtime |
| Fizyczny odczyt API/UI | SKIP stack_not_started | Tylko niezbędne odczyty | Odczyty dopuszczone przez host; brak aktywacji modeli |
| Fizyczne zadania/generacja | SKIP stack_not_started | Jedna seria, admission hosta, oznaczone dane testu | SKIP runtime_busy przed rozpoczęciem |
| Fizyczny runtime wymagany, brak modelu | SKIP stack_not_started | SKIP runtime_model_unavailable dla testów wymagających modelu | Bez naprawiania runtime przez test |
| Operacje zmieniające usługi/kontenery/model | Bez automatycznego startu | Wyłącznie jako wydzielony scenariusz o zadeklarowanych skutkach | Bez wykonywania podczas pracy operatora |

Gotowość jest warunkiem konkretnego scenariusza. Odczyt UI lub zdrowia API
nie powinien wymagać załadowanego modelu. Preflight jest odczytowy.
Brak warunków na wejściu daje SKIP z powodem; błąd funkcjonalny po prawidłowym
rozpoczęciu jest FAIL. Utrata środowiska w trakcie wymaga osobnego wyniku
przerwania; nie wolno automatycznie zamieniać FAILED zadania na SKIP.
Raport nie może utożsamiać pominięcia wszystkich testów fizycznych z ich zaliczeniem.

## Kolejność i zależności PR

| ID | Priorytet | Temat | Zależności |
|---|---|---|---|
| T1 | P0 | Audyt i jawne metadane wykonania testów | Brak |
| T2 | P0 | Wspólny warunek dostępu do istniejącego Venoma | T1 |
| T3 | P0 | E2E bez autostartu i aktywacji modelu | T1, kontrakt T2 |
| T4 | P0 | Izolacja stanu symulowanych testów i workerów | T1, T2 |
| T5 | P1 | Powtarzalna bramka pokrycia | T1, T4 |
| T6 | P1 | Spójny runner grup i limity workerów | T1, T2, T3, T4 |
| T7 | P1 | Pomiar workerów i kwalifikacja całości | T2–T6 |

Wdrażać małe PR-y z własnymi testami i aktualizacją polityki.
T3 może powstawać równolegle po ustaleniu kontraktu T2, bez nakładających się zmian.
T5 i T6 muszą uzgodnić jednego właściciela zmian w make/tests.mk.
Numery T1–T7 są identyfikatorami planu, nie numerami istniejących PR-ów GitHub.

### T1 Audyt i jawne metadane wykonania testów

Problem: nazwa, czas i typ pliku nie określają rzeczywistych zależności i skutków.
Zakres: katalog testów, generator, walidator, synchronizacja grup i dokumentacja.

- [ ] Zweryfikować 514 plików; zacząć od 178 kandydatów oraz helperów uruchamiających procesy i wykonujących I/O przy imporcie.
- [ ] Dodać jawne pola: koszt (`fast/long/heavy`), środowisko (`simulated/live`), wymagane zasoby i skutki (`read/write/generation/lifecycle`). Dopuszczalne wartości zamknąć w walidatorze.
- [ ] Opisać wymagania gotowości per scenariusz: API, UI, aktywny model, Docker lub inny zasób. Docker i direct runtime na tym PC traktować jako fizyczne zasoby podlegające warunkowi działającego Venoma.
- [ ] Rozdzielić pliki mieszające testy fizyczne i symulowane albo obsłużyć jawne nadpisanie na poziomie nodeid. Nie przypisywać bezpieczeństwa na podstawie samego mocka w nazwie.
- [ ] Zachować ręcznie potwierdzone metadane przy regeneracji; nowe i nieznane testy wymagają klasyfikacji przed wejściem do automatycznej grupy.
- [ ] Dodać walidację zgodności markerów z katalogiem, rozłączności grup kosztu, kompletności i uzasadnienia wyjątków.

Odbiór: każdy plik/node ma jednoznaczny tryb, koszt i wymagania; `--plan`/raport
pokazuje zakres bez kontaktu z runtime. Regeneracja jest idempotentna.
Markery i metadane są spójne; szybka bramka nie wybiera testów fizycznych.
Testy audytu obejmują plik mieszany, nowe nieznane testy i import z efektem ubocznym.

### T2 Wspólny warunek dostępu do istniejącego Venoma

Problem: sprawdzanie samej Ollamy lub samego /healthz nie spełnia reguły hosta.
Zakres: conftest, helpery fizycznych testów, kontrakt runnera i endpointów.

- [ ] Rozwiązywać adresy z jawnego profilu lub argumentów, dla lokalnego Full 8800/3300. Weryfikować tożsamość docelowego API; nie szukać losowego otwartego portu.
- [ ] W jednym odczytowym preflight określać stack_not_started, stack_degraded, runtime_model_unavailable, runtime_busy i ready według potrzeb testu.
- [ ] Odciąć fizyczne operacje przed wejściem w test, również przy bezpośrednim `pytest`, pominięciu wrappera i imporcie modułów testowych.
- [ ] Usunąć bezpośrednie generowanie i `ollama run` z automatycznego zestawu. Jeżeli osobny scenariusz direct ma pozostać, musi używać obsługiwanego mechanizmu rezerwacji hosta; brak takiego mechanizmu blokuje scenariusz.
- [ ] Korzystać z admission działającego hosta. Nie tworzyć lokalnego obiektu na jego bazie blokad ani nie obchodzić admission przez pomocniczy proces.
- [ ] Porządkować wyłącznie dane/sesje utworzone przez test, z identyfikatorem przebiegu. Żadnego czyszczenia całej pamięci, restartu, pobierania lub przełączania modeli.

Odbiór: symulowane testy polityki potwierdzają brak mutującego wywołania i startu
procesu przy wyłączonym Venomie, także gdy Ollama nadal odpowiada. Test bez modelu
nie blokuje odczytu API. Zajęty runtime nie przyjmuje generacji testu.
Zmiana dostępności po preflight jest ponownie sprawdzana przez admission hosta.

### T3 E2E bez autostartu i aktywacji modelu

Problem: istniejący preflight może aktywować model, a Playwright ma komendę startu UI.
Zakres: check-e2e-env.mjs, run-e2e.mjs, konfiguracje Playwright, package.json,
run-e2e-optimal.sh i powiązane workflow.

- [ ] Usunąć automatyczną aktywację modelu z preflight; brak modelu oznacza wynik warunku, nie próbę naprawy.
- [ ] Fizyczne E2E kierować wyłącznie do istniejącego UI/API; usunąć możliwość automatycznego uruchomienia Next.js w tym trybie.
- [ ] Obsłużyć spójnie SKIP z preflight we wszystkich wejściach, także skrócie shell. Zachować osobny licznik pominięć w raporcie.
- [ ] Sprawdzić odpowiedzi błędne i obcą usługę na wskazanym porcie; samo HTTP <500 nie potwierdza tożsamości ani gotowości.
- [ ] UI z atrapami w CI nazwać i skonfigurować jako odrębny test symulowany; nie podszywać go pod kwalifikację fizycznego Venoma. W lokalnym trybie istniejącego hosta nie uruchamiać dodatkowego serwera.
- [ ] Rozróżnić testy przeglądarkowe czytające UI od wysyłających rzeczywiste zadania; te drugie wykonuje jeden worker.

Odbiór: dla braku UI/API/modelu nie wystartuje proces aplikacji ani nie zostanie
wysłane żądanie aktywacji. Scenariusz odczytu działa bez modelu. Testy wrappera
sprawdzają stan pominięty i błąd właściwego scenariusza oddzielnie.

### T4 Izolacja stanu symulowanych testów i workerów

Problem: niepełna izolacja MEMORY_ROOT i globalnego admission powoduje kolizje.
Zakres: wczesny bootstrap testów, fixture, testy admission i zależne serwisy.

- [ ] Przed inicjalizacją zależności przydzielić każdemu przebiegowi/workerowi własne katalogi pamięci, SQLite, logów, cache i artefaktów.
- [ ] Tam, gdzie stan nie jest częścią scenariusza, tworzyć go per test lub zapewnić kontrolowany reset i zamknięcie własnych uchwytów po teście.
- [ ] Obsłużyć globalne singletony i wykonawców tła; nie zerować stanu blokad działającej aplikacji ani nie zwalniać cudzych właścicieli.
- [ ] Zapewnić, że symulowany test nie łączy się z rzeczywistymi usługami; testy transportu korzystają z jawnie kontrolowanej atrapy lub zadeklarowanej lokalnej fixture.
- [ ] Zachować testy prawdziwej synchronizacji admission na osobnych testowych bazach. Nie wyłączać admission globalną flagą dla uzyskania zielonego wyniku.

Odbiór: te same testy przechodzą przy Venomie włączonym i wyłączonym, przy 1/2/4/6
workerach oraz ponownym przebiegu. Nie powstaje plik w żywym MEMORY_ROOT;
brak runtime_busy po zakończeniu symulowanego testu. Zweryfikować anulowanie,
przerwanie i sprzątanie procesów należących do sesji testowej.

### T5 Powtarzalna bramka pokrycia

Problem: zmienna selekcja zależna od JUnit może spełnić changed-lines, ale nie floor.
Zakres: resolver, runner coverage, floor checker, pr-fast i pre-push.

- [ ] Chroniony zestaw obowiązkowy obejmuje baseline, testy zmienionego zakresu oraz pokrycie plików z coverage-file-floor.txt; budżet nie może go obciąć.
- [ ] Czasy testów mogą optymalizować kolejność i dobór dodatkowego zakresu. Dla tego samego kodu nie mogą usuwać testów wymaganych do blokujących kryteriów.
- [ ] Fallback uwzględnia changed-lines i floor oraz scala coverage bez ukrywania błędów któregokolwiek przebiegu.
- [ ] Wykluczyć fizyczne testy z obowiązkowej bramki lokalnej i CI kodu. Brak pokrycia symulowanego rozwiązywać testami kontraktów, nie startem modelu lub obniżeniem progu.
- [ ] Oddzielić raport czasu od końcowego raportu kwalifikacji; zapisać wybrane nodeid, SHA, przyczynę wyboru i konfigurację.

Odbiór: świeży checkout, stary/niepełny JUnit i kolejne uruchomienie dają zgodne
blokujące kryteria. Regresja floor jest wykrywana i uruchamia właściwe uzupełnienie.
Utrzymać istniejące progi, w tym 80% changed-lines i wartości z pliku floor.

### T6 Spójny runner grup i limity workerów

Problem: wiele ścieżek wykonania ma odmienne filtry, porty, workery i limity.
Zakres: run-pytest-optimal.sh, make/tests.mk, pr-fast, CI i generator planu.

- [ ] Wyznaczać repo z położenia skryptu; walidować dodatnie wartości workerów i profil zasobów.
- [ ] Udostępnić parametry workerów grup i profilu hosta. Liczbę fast dobrać dopiero na podstawie T7; long i heavy również nie są dowodem bezpieczeństwa równoległości.
- [ ] Uruchamiać lekkie i średnie testy symulowane przed ciężkimi, a fizyczne dopiero po ich preflight. Nie mieszać generacji modelu z benchmarkiem CPU/RAM.
- [ ] Zachować loadfile jako punkt odniesienia, dopóki pomiar nie uzasadni zmiany; oznaczyć zasoby wyłączne i wymagającą izolacji resztę testów.
- [ ] Zastąpić bezwarunkowe kasowanie PYTEST_ADDOPTS kontrolą filtrów; egzekwować limit testu i limit grupy. Nie usuwać zewnętrznego timeoutu.
- [ ] Rozróżnić oczekiwane pominięcie fizycznych testów od błędu pustej grupy wymaganych testów; raportować również niewykonane grupy po fail-fast.
- [ ] Ujednolicić kontrakt pytest/make/pr-fast/CI przy zachowaniu różnych zakresów: szybki, pełny symulowany, fizyczny. CI bez istniejącego Venoma nie wykonuje fizycznych testów.

Odbiór: dry-run pokazuje grupy, workery, adresy, filtry i zasoby bez startu usług.
Nieprawidłowy worker/port daje błąd konfiguracji. Wyłączony Venom pomija wszystkie
fizyczne operacje. Przerwanie kończy tylko własne procesy, a wynik grup nie ginie.

### T7 Pomiar workerów i kwalifikacja całości

Problem: 6 workerów dla fast nie zostało dotąd potwierdzone porównywalnym pomiarem.
Zakres: lokalny profil hosta, raport pomiarów, dokumentacja EN/PL i macierz CI.

- [ ] Ustalić jedną rewizję kodu, środowisko, identyczny zestaw testów i wersje zależności.
- [ ] Wykonać bazowy przebieg fast z 1 workerem oraz minimum 3 porównywalne przebiegi dla 2, 4 i 6 workerów.
- [ ] Zapisać medianę czasu, rozrzut, RAM procesów, presję pamięci/swap, czas zbierania testów i najdłuższe pliki. Samo zajęte swap nie dowodzi bieżącej presji.
- [ ] Dobrać profil z Venomem wyłączonym oraz z uruchomionym, stabilnym Venomem. Drugi profil nie wysyła generacji testowej równolegle z pomiarem lekkich testów.
- [ ] Sprawdzić macierz: Venom off; on bez modelu; on gotowy; on zajęty; restart w trakcie. Stany mutujące host najpierw symulować, fizycznie kwalifikować tylko obsługiwane scenariusze w istniejącej instancji.
- [ ] Potwierdzić, że model, procesy i konfiguracja operatora nie zmieniają się wskutek preflight, a testy nie zostawiają zadań generacji ani własnych procesów.
- [ ] Wykonać pełny zestaw symulowany, pr-fast i pre-push; porównać ich zakresy i wyniki. Wybrane fizyczne E2E wykonać tylko przy spełnionych warunkach hosta.

Odbiór: rekomendacja liczby workerów ma pomiary i jawne ograniczenia, a nie tylko
ocenę liczby rdzeni. Raport rozdziela passed, failed, skipped i niewykonane grupy.
Wyniki fizyczne nie są przenoszone na inne modele lub niewykonane scenariusze.

## Wspólny kontrakt odbioru zmian

Każdy implementacyjny PR ma testy własnego kontraktu, zgodny katalog/grupy i zielony
`make pr-fast`; zmiany frontendowe dodatkowo przechodzą wymagane testy web.
Nowe testy rejestruje się zgodnie z AGENTS.md, bez duplikowania tych samych przypadków.
Wynik wykonania zapisuje SHA, profil i rzeczywisty zakres testów.

Dla zmian testów/backendu obowiązują polecenia z docs/AGENTS.md, w tym:
`make test-ci-lite`, `make test-catalog-check`, `make test-groups-check`,
`make check-new-code-coverage-diagnostics` po wygenerowaniu raportu i `make pr-fast`.
Brak starego coverage XML w świeżej kopii wymaga wygenerowania raportu,
nie kopiowania wyniku z innej rewizji. Testy fizyczne nie naprawiają czerwonej
bramki symulowanej i nie zastępują wymaganych testów kontraktowych.

Zmiana wyłącznie tego planu jest markdown-only: ciężkie bramki są pomijane zgodnie
z polityką repozytorium. Analiza nie uruchamiała testów fizycznych, modeli ani
serwerów. Obserwacje runnerów i scenariuszy są analizą statyczną; pełna kwalifikacja
obciążenia i wszystkich kombinacji workerów stanowi zadanie T7.
