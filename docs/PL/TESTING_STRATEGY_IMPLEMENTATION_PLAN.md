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

## Najpierw rodzaj testu i miejsce w procesie wdrożenia

Podział fast/long/heavy opisuje koszt. Nie zastępuje rozróżnienia unit,
kontraktów, integracji i E2E. Nie określa też gałęzi ani momentu wykonania.
Przed zmianą workerów potrzebna jest zatwierdzona macierz zastosowania zestawów.

### Do czego służą obecne zestawy

| Rodzaj | Miejsce i komenda | Co sprawdza | Wymaga fizycznego Venoma |
|---|---|---|---|
| Unit backendu | tests/, typ unit w katalogu, 285 plików | Zachowanie funkcji i klas | Docelowo nie; aktualny typ nie gwarantuje izolacji |
| Kontrakty backendu | 88 route_contract i 86 service_contract, m.in. FastAPI TestClient | Schematy, odpowiedzi, błędy i współpracę komponentów z atrapami | Nie, jeżeli zależności są kontrolowane |
| Integracja backendu | 25 integration i część 16 gate | Granice komponentów, infrastruktura lub reguły projektu | Zależy od scenariusza; sam typ nie wystarcza |
| Unit i komponenty web | test:unit, test:unit:components; razem test:unit:ci-lite | Logika TS, render i interakcje komponentów | Nie |
| E2E przeglądarkowe z atrapami | Część *.spec.ts, np. chat-mode-routing i smoke z page.route/route.fulfill | UI, nawigacja i kontrakt przeglądarki z atrapą API | Nie potrzebują modelu; potrzebują renderera UI. Lokalnie użyć istniejącego UI, bez startu drugiej instancji |
| E2E z rzeczywistym backendem | Część tests/perf, profile latency/perf-backend, wybrane *.spec.ts | Rzeczywisty przepływ zadania, runtime, SSE i utrwalenie | Tak, z wymaganiami danego scenariusza |
| Performance | 14 perf w katalogu, część web perf | Czas CPU albo latencja rzeczywistych usług | Zależy od testu; perf nie jest synonimem testu fizycznego |
| Kontrole statyczne i build | Lint, typowanie, architektura, katalog, OpenAPI, Next build | Spójność kodu i artefaktów | Nie wymagają modelu ani działającego backendu |

Nie traktować każdego TestClient jako testu jednostkowego ani każdego Playwright
jako testu całego fizycznego systemu. Ostateczna klasyfikacja dotyczy wszystkich
zależności scenariusza, także importów, helperów, nieprzechwyconych żądań i SSR.
Same page.route nie dowodzą braku ruchu do prawdziwego backendu.

### Stan wyjściowy przed realizacją i wyzwalacze gałęzi

Poniższa tabela opisuje stan odczytany 27 października 2026 przed realizacją
zmian. Bieżące ustawienia PR i `main` opisuje `docs/PL/TESTING_POLICY.md`.

| Kontekst | Faktyczny trigger i zakres | Ograniczenie |
|---|---|---|
| Lokalna gałąź robocza, np. feature/* lub codex/* | pre-commit przy commicie; pre-push uruchamia pr-fast; ręcznie można uruchomić te same cele | Nazwa gałęzi nie wybiera zestawu. pr-fast wykrywa diff względem origin/main lub wskazanej bazy |
| Push gałęzi roboczej bez PR | Główny CI i Quick Validate nie mają takiego triggera | Push nie oznacza automatycznego sprawdzenia na GitHub; wyjątki to osobne workflow i ich filtry |
| PR z dowolnej gałęzi do main | ci.yml: backend baseline+new-code+auto-include, bez limitu czasowego selekcji; lint+unit+components web, kontrakty i Sonar. Quick Validate | branches:[main] dotyczy celu PR, nie nazwy gałęzi źródłowej; backend job limit 25 min, krok coverage 18 min |
| PR do main zmieniający web-next | Dodatkowy Playwright E2E: domyślnie profil smoke, worker=1 | Nie jest to pełny profil functional/full; zestaw miesza testy z atrapami i warunki gotowości |
| PR do main zmieniający Docker/locki/compose | Docker Sanity: build obrazów, start stosu kontenerowego, health i cleanup | To odrębna kwalifikacja na runnerze GitHub; nie jest lokalną lekką bramką PR |
| Push do main | CI backend uruchamia sonar-reports-backend: wszystkie odkryte pytest z filtrem not performance and not smoke, 4 workery; web unit/components i pozostałe kontrole | Szersza regresja backendu, nie pełna kwalifikacja systemu ani testów fizycznych |
| Push do main zmieniający web-next | E2E smoke i Turbopack Smoke | Nadal nie pełne E2E wszystkich scenariuszy |
| Full CI | Tylko workflow_dispatch; można wskazać ref, workflow nie ma automatycznego triggera branchowego | Backend: pre-commit i pytest -q bez filtra markerów; web: lint+build. Nazwa kroku Pytest(smoke) nie odpowiada komendzie |
| Ręczne E2E | workflow_dispatch: smoke/functional/full; perf-backend osobno z adresami | Profil full to lista wybranych komend, nie wszystkie *.spec.ts i nie dowód wykonania na fizycznym Venomie |
| Zadania nocne | Security Delta Nightly i Web Next Turbopack Smoke na domyślnej gałęzi | Brak harmonogramu pełnej regresji funkcjonalnej |
| Wydanie tagu v* lub ręczne publikowanie obrazów | Publish sprawdza m.in. wersję, main i pochodzenie SHA | W tych workflow brak powiązania needs z Full CI oraz kwalifikacją E2E dla dokładnie wydawanego SHA |

Główne CI pomija zmiany wyłącznie markdown/docs i modules. Quick Validate pomija
modules, ale nie ma takiego samego wyjątku dla markdown. Opcjonalne moduły mają
własne repozytoria: wynik core nie potwierdza testów zmienionego modułu.
Żaden z odczytanych głównych workflow nie definiuje automatycznej ścieżki dla
PR do develop lub release/*. Nie należy takiej ścieżki zakładać na podstawie nazwy.

Historia odczytana 27 października 2026: ostatni dostępny [Full CI](https://github.com/mpieniak01/Venom/actions/runs/21806257259)
uruchomiono ręcznie na main 8 lutego 2026. Tymczasem [CI po obecnej poprawce](https://github.com/mpieniak01/Venom/actions/runs/40512432868)
wykonał 7981 testów backendu i pominął 126. Brak świeżego Full CI nie oznacza braku
świeżej regresji backendu; te dwa workflow mają różny zakres.

### Osobne zestawy GitHub Actions i raporty dla Sonara

GitHub nie jest powtórzeniem lokalnego pr-fast. Quick Validate, testy CI oraz
SonarCloud mają różne zadania i różne warunki powodzenia.

| Zestaw | Dobór i wykonanie dzisiaj | Raport lub warunek powodzenia |
|---|---|---|
| Lokalny pr-fast, backend | ci-lite + sonar-new-code + zakres diff; domyślny budżet selekcji 90 s, exclude-slow-fastlane=1, 4 workery | pytest, changed-lines >=80% i file floors; rzeczywisty czas jest dłuższy od samego budżetu selekcji |
| Quick Validate na GitHub | compileall, statyczny audyt zależności CI-lite i poprawności skryptów package.json | To kontrola statyczna, nie wykonanie unit ani E2E |
| GitHub PR do main, backend-lite | check-new-code-coverage: baseline+new-code+auto-include, 4 workery; TIME_BUDGET=0, EXCLUDE_SLOW_FASTLANE=0, MAX_TESTS=0 | Testy i lokalny checker coverage/floor; następnie upload sonar-backend-reports |
| GitHub push main, backend-lite | sonar-reports-backend: discovery pytest z filtrem not performance and not smoke, 4 workery | pytest generuje XML coverage i JUnit; ta komenda nie wywołuje samodzielnie changed-lines ani floor checkera |
| Ręczne uruchomienie głównego CI | Obecny warunek rozróżnia tylko event push; workflow_dispatch trafia do ścieżki new-code | Ref i bazę trzeba zapisać; ręczne CI nie jest automatycznie pełnym zestawem main |
| GitHub frontend-lite | Lint i test:unit:ci-lite = logika TS + komponenty | Sukces testów; ten job nie generuje ani nie wysyła LCOV |
| GitHub browser E2E | Osobny workflow, smoke dla PR/push ze zmianą web; functional/full ręcznie | Wynik Playwright i własne quality thresholds; artefakty nie są w tym CI wejściem do Sonara |
| GitHub OpenAPI | Eksport schematu i codegen typów TS | Osobny kontrakt; to nie raport pokrycia pytest |
| SonarCloud Scan | Osobny job po architecture, backend-lite, frontend-lite i openapi-contract | Import artefaktu backendu, analiza statyczna i oczekiwanie na wynik quality gate |

Aktualne listy: ci-lite zawiera 73 pliki, sonar-new-code 377. Wspólne jest
46 plików, a unia liczy 404. Nie wolno dodawać liczebności grup jako liczby
unikalnych testów. To zakres kandydatów przed filtrowaniem, doborem dla diff i
przejściem do konkretnych przypadków pytest, a nie stała liczba wykonywanych testów.
Katalog decyduje, które testy są uprawnione do zestawu; nazwa pliku sonar_* sama
w sobie nie określa osobnego obowiązkowego przebiegu.

Przepływ jest następujący:

1. Wybrany job backendu wykonuje pytest i zbiera coverage dla venom_core.
2. Zapisuje test-results/sonar/python-coverage.xml i python-junit.xml oraz logi.
3. Upload przekazuje je pod nazwą sonar-backend-reports w ramach workflow run.
4. Job Sonar pobiera raporty, analizuje źródła i używa qualitygate.wait=true.

Sonar nie uruchamia w tym jobie osobnego pytest. Uruchomione wcześniej testy
dostarczają mu pokrycie. Udany pytest, udany upload i udana bramka Sonara są
trzema odrębnymi wynikami. needs wymusza również oczekiwanie na frontend i OpenAPI,
więc czas całego CI z Sonarem nie jest sumą samych czasów pytest ani budżetem
lokalnego PR. Sonar ma job timeout 20 min, backend-lite 25 min z krokiem coverage
18 min, a frontend-lite 12 min; te limity nie dowodzą rzeczywistego czasu całości.

Zakres Sonara z sonar-project.properties:

- Źródła do analizy obejmują venom_core i wybrane katalogi runtime web-next.
- Testy są jawnie sklasyfikowane jako tests i web-next/tests.
- Importowane jest pokrycie Python XML i raport wykonania JUnit.
- web-next/** jest wyłączony w sonar.coverage.exclusions; brak skonfigurowanego importu LCOV.
- Część backendu również jest wyłączona z pokrycia. Wynik Sonara nie oznacza pokrycia całej aplikacji ani całego przebiegu E2E.
- Local changed-lines checker korzysta z wykluczeń Sonara, a osobny floor checker ma własny plik progów. Ich zgodność wymaga audytu, nie założenia.
- PR z forka nie wykonuje tego joba Sonara; bez SONAR_TOKEN krok analizy zostaje pominięty. Pominięcie nie jest potwierdzeniem zielonej bramki jakości.

Do decyzji w T8: czy frontend ma zostać objęty pomiarem pokrycia Sonara.
Jeżeli tak, potrzebny jest generowany w tym samym run LCOV, upload/download,
konfiguracja importu, kontrolowana aktualizacja wykluczeń i testy adekwatne do
zakresu. Nie usuwać wykluczeń jednorazowo ani nie przenosić frontend coverage do
lokalnego 10-minutowego PR bez zmierzenia jego kosztu.

Raport kwalifikacji musi przechowywać osobno lokalny wynik PR, GitHub PR,
GitHub main i bramkę Sonara. Każdy wiąże się z SHA, bazą diff, konfiguracją,
wybranymi testami, filtrem, workerami, raportami i ich zakresem. Coverage z
ograniczonego PR nie jest globalnym coverage main. Artefakt z innej rewizji nie
uzupełnia brakującego raportu aktualnego kandydata.

### Docelowy moment wykonania regresji

To propozycja zmian do zatwierdzenia w T0, nie aktywny harmonogram ani nowe branch rules.

| Moment | Wymagany zestaw docelowy | Charakter |
|---|---|---|
| Praca na dowolnej gałęzi | Testy zmienionego komponentu i szybkie statyczne sprawdzenie | Krótka pętla pracy |
| Lokalna gotowość PR i pre-push | Jeden pr-fast: baseline unit/kontrakty, testy zmienionego zakresu, wymagane coverage/floor; web lint+unit+components gdy dotknięto web | Cel całkowity około 10 min; bez pełnej regresji i rzeczywistej generacji |
| PR do main | Lokalnie zgodne kontrakty + kontrole GitHub; mały browser smoke z kontrolowanym API dla zmienionego UI | Zakres ryzyka PR. E2E na prawdziwym modelu stanowi oddzielny wynik i nie blokuje z powodu wyłączonego lokalnego hosta |
| Po scaleniu do main | Pełna regresja symulowana backendu, web unit/components, build i szersze browser E2E z atrapami | Raport per SHA, bez budżetu 10 min. Nie uruchamiać jej ponownie przy każdym lokalnym pushu |
| Nocna regresja | Pełny zestaw symulowany na aktualnym main, jeśli zmienił się SHA lub środowisko kwalifikacji | Wykrywa zależności kolejności i regresje poza diff; osobno od nocnych skanów security |
| Przed wydaniem | Udana pełna regresja symulowana dokładnego kandydata i deklarowany zakres E2E na istniejącej instancji | Sprawdzić SHA i skład modułów. Pominięte testy fizyczne pozostają niezweryfikowane; brak hosta nie uruchamia nowej instancji |
| Testy fizyczne i wydajności modelu | Istniejący, gotowy Venom i spełnione wymagania scenariusza; brak konkurencyjnej generacji | Oddzielne okno wykonania; nie część lokalnego pr-fast |

Dla kwalifikacji lokalnego kandydata z gałęzi roboczej nie wolno twierdzić, że testy
wykonane przez API działającego main sprawdziły backend tej gałęzi. Trzeba zapisać
rewizję procesu aplikacji i wskazać, które zmiany faktycznie objęła próba.
Ewentualna aktualizacja jedynej instancji jest świadomym wdrożeniem kandydata,
a nie efektem ubocznym pytest lub preflight.

### Kontrakt lokalnego PR w około 10 minut

`config/testing/lane_contracts.yaml` już deklaruje pr-fast max_runtime_minutes=10.
Nie ma jeszcze potwierdzenia, że ten limit obejmuje cały lokalny przepływ mieszany
oraz wszystkie wymagane kontrole z dokumentacji. Sam wpis ani timeout nie jest pomiarem.

- Budżet 600 s dotyczy całej lokalnej bramki dla danego SHA i diff-base, nie osobno backendu, web i każdego workera.
- Pomiar zaczyna się przy wejściu do pr-fast i obejmuje dobór, import/collection, kontrole statyczne, testy, coverage oraz raport końcowy.
- Gotowe, zgodne zależności są precondition. Instalację venv/npm, pobieranie przeglądarek i modeli mierzyć oddzielnie; nie uruchamiać ich niejawnie w tej bramce.
- Najpierw ustalić obowiązkowe kontrakty i pokrycie, potem dopasować liczbę workerów. Nie ucinać wymaganych testów po osiągnięciu budżetu.
- Wymagane mypy/pre-commit/metadane trzeba uwzględnić w całościowym pomiarze. Nie chować dodatkowych minut pod obowiązkowymi komendami poprzedzającymi pr-fast.
- Nie wykonywać osobno pełnego test-ci-lite, a potem ponownie tego samego baseline wewnątrz pr-fast jako stałej ścieżki PR. Samodzielne cele pozostają do diagnostyki.
- Testy po commitach i pre-push należy raportować osobno. Ewentualne ponowne użycie wyniku wymaga zgodności SHA/tree, bazy diff, zależności i konfiguracji; nie wolno pomijać hooka na podstawie starej zielonej wiadomości.
- Przekroczenie budżetu jest problemem wydajności lub zakresu bramki, nie wynikiem PASS dla nieukończonych testów.
- Kwalifikacja mierzy zakres backend-only, frontend-only i mixed. Minimum kilka prób na każdy zakres; po zebraniu historii raportować także P95 i rozrzut zamiast jednego najlepszego przebiegu.

Projekt roboczego podziału budżetu do sprawdzenia pomiarami: 60 s na plan i kontrole
wstępne, 240 s na backend z coverage, 180 s na web, 60 s na pozostałe wymagane statyczne
sprawdzenia i 60 s rezerwy. Te wartości nie są wynikami pomiaru ani obietnicą czasu.
Jeżeli rzeczywisty zakres nie mieści się w 600 s, najpierw usunąć duplikację i
niepotrzebne koszty, potem jawnie rozdzielić pr-fast i pełną regresję.

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
| T0 | P0 | Macierz typów testów, gałęzi i budżetu PR | Brak |
| T1 | P0 | Audyt i jawne metadane wykonania testów | T0 |
| T2 | P0 | Wspólny warunek dostępu do istniejącego Venoma | T1 |
| T3 | P0 | E2E bez autostartu i aktywacji modelu | T1, kontrakt T2 |
| T4 | P0 | Izolacja stanu symulowanych testów i workerów | T1, T2 |
| T5 | P1 | Powtarzalna bramka pokrycia | T1, T4 |
| T6 | P1 | Spójny runner grup i limity workerów | T1, T2, T3, T4 |
| T8 | P1 | Zestawy GitHub i kontrakt raportów Sonara | T0, T1, T4, T5 |
| T7 | P1 | Pomiar workerów i kwalifikacja całości | T2–T6, T8 |

Wdrażać małe PR-y z własnymi testami i aktualizacją polityki.
T0 poprzedza zmiany mechanizmu; T1 realizuje ustaloną klasyfikację. T3 może powstawać równolegle po ustaleniu kontraktu T2, bez nakładających się zmian.
T5 i T6 muszą uzgodnić jednego właściciela zmian w make/tests.mk.
Numery T0–T8 są identyfikatorami planu, nie numerami istniejących PR-ów GitHub.

### T0 Macierz typów testów, gałęzi i budżetu PR

Warunek startu pozostałych PR-ów: najpierw ustalić, do czego używamy zestawów,
na jakiej rewizji/gałęzi działają i kiedy wymagamy pełnej regresji.

- [ ] Zweryfikować zakres backend unit/kontrakty/integration oraz web unit/components/browser i odróżnić kontrolowane atrapy od fizycznego środowiska.
- [ ] Zapisać mapowanie wejście -> komenda -> zbiór testów -> trigger -> gałąź docelowa -> wymagany wynik; uwzględnić filtry ścieżek, osobne moduły, GitHub PR/main i raporty dla Sonara.
- [ ] Zatwierdzić zakres lokalnego pr-fast i pomiar całej bramki w około 600 s, również dla zmian backend+frontend.
- [ ] Ustalić pełną regresję symulowaną po merge na main, nocną po zmianie SHA/środowiska i kwalifikację dokładnego kandydata przed wydaniem. Wdrożenie harmonogramów należy do T6, nie do samego dokumentu.
- [ ] Sprawdzić politykę wydania oraz powiązać ją z wynikami właściwego SHA; sam tag na historii main nie jest potwierdzeniem pełnej kwalifikacji.
- [ ] W raporcie pokazać luki: brak testu, świadomy SKIP, test kodu innej gałęzi, brak pomiaru budżetu. Osobno nazwać zakres pełny symulowany i fizyczny.

Odbiór: jedna macierz odróżnia stan obecny od docelowego, obejmuje feature/fix/codex,
PR do main, push main, ręczne wykonanie i release/tag oraz potwierdza, że pełna
regresja nie jest bezwarunkowym składnikiem lokalnego pr-fast.

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
- [ ] Ujednolicić kontrakt pytest/make/pr-fast/CI przy zachowaniu różnych zakresów: szybki, pełny symulowany, fizyczny. Wdrożyć macierz triggerów i pełnych regresji zatwierdzoną w T0. CI bez istniejącego Venoma nie wykonuje fizycznych testów.

Odbiór: dry-run pokazuje grupy, workery, adresy, filtry i zasoby bez startu usług.
Nieprawidłowy worker/port daje błąd konfiguracji. Wyłączony Venom pomija wszystkie
fizyczne operacje. Przerwanie kończy tylko własne procesy, a wynik grup nie ginie.

### T8 Zestawy GitHub i kontrakt raportów Sonara

Problem: lokalny PR, hosted PR, main i Sonar są różnymi kwalifikacjami;
aktualny frontend CI nie dostarcza Sonarowi pokrycia, a testy E2E mają osobne raporty.
Zakres: ci.yml i powiązane workflow, cele sonar-reports, konfiguracja Sonara,
raporty testów oraz dokumentacja zakresów.

- [ ] Zapisać jawne zestawy dla GitHub PR, push main i workflow_dispatch. Nie opierać zakresu ręcznego uruchomienia wyłącznie na event != push.
- [ ] Utrzymać różnicę między szybką lokalną kwalifikacją do 600 s, szerszą kwalifikacją PR na GitHub i pełną regresją main; zapisać ich wspólne obowiązkowe kontrakty.
- [ ] Walidować obecność, kompletność i zgodność SHA raportów coverage/JUnit oraz artefaktu pobranego przez job Sonara. Brak lub niewłaściwy artefakt daje jawny błąd.
- [ ] Przy fallback zachować raport wykonania wszystkich faz, nie nadpisywać całego JUnit wynikiem wyłącznie ostatniej fazy; scalać coverage zgodnie z identycznym kodem.
- [ ] Rozdzielić wyniki pytest, changed-lines, file-floor, uploadu i Sonar quality gate. Jawnie oznaczać przypadek forka/braku sekretu bez prezentowania go jako wykonanej analizy.
- [ ] Zinwentaryzować wykluczenia coverage backendu/frontendu i ich uzasadnienia. Przed ewentualnym dodaniem LCOV zdefiniować zakres pomiaru i koszt; zmiana wykluczeń wymaga osobnego review.
- [ ] Zachować oddzielne raporty browser E2E i testów fizycznych. Sama obecność tych testów w sonar.tests nie dostarcza ich pokrycia produkcyjnego JS/TS.
- [ ] Sprawdzić zależności jobs i rzeczywisty czas do końca bramki Sonara; eliminować duplikaty testów w jednym run bez pomijania odrębnej kwalifikacji innego SHA/środowiska.

Odbiór: dla PR, main i ręcznego run można odtworzyć wybrane testy, zakres pokrycia
i wynik każdej bramki. Symulacje obejmują brak/wadliwy artefakt, błędny SHA,
fallback, brak tokenu i błąd quality gate. Wynik main obejmuje jego szerszy zestaw,
a raport PR nie jest prezentowany jako pełna regresja. Ten sam kontrakt działa
bez lokalnego Venoma i nie uruchamia rzeczywistego modelu na runnerze CI.

### T7 Pomiar workerów i kwalifikacja całości

Problem: 6 workerów dla fast nie zostało dotąd potwierdzone porównywalnym pomiarem.
Zakres: lokalny profil hosta, raport pomiarów, dokumentacja EN/PL i macierz CI.

- [ ] Ustalić jedną rewizję kodu, środowisko, identyczny zestaw testów i wersje zależności. Kwalifikować całą bramkę PR osobno dla backend-only, frontend-only i mixed, zgodnie z T0.
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
