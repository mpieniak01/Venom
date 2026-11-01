# Lokalne porównanie modeli utrzymania Venoma — 2026-11-01

Łącznie zapisano **350 prób modelowych**: **349 z oceną jakości** i **1 z historyczną blokadą infrastruktury**. Kwalifikacje techniczne oraz kontrole skryptowe są oddzielne. Kod, raport i kolejne poprawki pozostają lokalne zgodnie z dyspozycją operatora. Istniejący Draft PR nie obejmuje lokalnych commitów rozszerzenia.

## Wynik i decyzja

Qwen3.5-9B osiągnął najwyższy nowy baseline narzędziowy: **8/10**, wobec **5/10 Gemmy 4 E2B** i **6/10 Granite 4.2 8B**. Mini-coder-4b zachowuje najlepszy potwierdzony wynik napraw w pierwotnej grupie: **12/24 wykonań ośmiu problemów**, mini-coder-1.7b: **11/24**. Qwen uzyskał **3/8**, Gemma **0/8**. Oba nowe modele mają **0/2** poprawnych diagnoz/eskalacji; lokalizacja: Qwen **1/10**, Gemma **0/10**.

Nie ma podstaw do wdrożenia uniwersalnego autonomicznego pomocnika w tych profilach. Qwen wymaga przede wszystkim kwalifikacji szybszego backendu, kontroli pamięci oraz obsługi brakujących informacji. Wyniki dotyczą poniższych konkretnych checkpointów, scaffolda i budżetów; częściowe trafienie w plik albo poprawna komenda nie zastępuje pełnego kontraktu zadania.

| Rola | Rekomendacja | Uzasadnienie |
|---|---|---|
| Narzędzia | Ograniczyć Qwen3.5 do wąskiej roli pod nadzorem; przed pilotażem powtórzyć ocenę na nowych problemach i zakwalifikowanym backendzie. | Najwyższy baseline 8/10, ale nie rozpoznał obowiązku zapytania o brakujący test. Nowy baseline ma tylko jedno wykonanie przypadku; rezerwacja CUDA przekroczyła pojemność karty. |
| Naprawy | Rozważyć dostrajanie mini-coder-1.7b, z mini-coder-4b jako punktem odniesienia. | Podobna skuteczność na małym zbiorze; rzeczywiste testy potwierdzają część poprawek. Kwalifikacja LoRA/QLoRA i nowe dane treningowe są dopiero kolejnym eksperymentem. |
| Lokalizacja | Odrzucić badane konfiguracje do samodzielnej lokalizacji; poprawić wyszukiwanie i zarządzanie kontekstem. | Wyniki rzędu 0–1/10. Częste limity kontekstu, niepełne symbole i brak dowodów. Nie jest to ocena maksymalnych możliwości architektur przy innym kontekście lub narzędziach. |

## Wspólna metoda

- Jedna instancja LLM naraz, RTX 3060 12 GiB, istniejący stos Venoma. Osobny zatwierdzony profil sandboxa; domyślny `.env.dev` pozostaje bez zmian. Nie uruchamiano Test Zero ani usług płatnych.
- Ten sam commit wejściowy `1ef42d5a9e071c7c9819c500ec6be3f3f6cc8582`; każda próba ma świeżą kopię repozytorium, bez zmian poprzednika. Naprawy obejmują osiem kontrolowanych syntetycznych usterek w tej kopii; lokalizacja korzysta z realnego kodu Venoma. Wyniki nie dowodzą skuteczności dla dowolnej awarii produkcyjnej.
- **30 identycznych definicji** potwierdzono przez porównanie pełnych dataclass: prompty, pliki, gold, oracle, zakres edycji i oczekiwania. SHA256 manifestu: `2f674a1a5dfda778303903ffd852f17209a99828e76c10c980585bec91783f8e`. Prompty są angielskie.
- Do 8/20/12 wywołań dla operatora/napraw/lokalizacji; do 3 cykli poprawka–test. Kontekst 8192, generacja do 1024 tokenów, seed 17, do 45 s na generację i budżet 180 s pętli zadania. Maksymalna rezerwacja miejsca na odpowiedź pozostawia do 7168 tokenów wejścia. Limity CUDA/generacji są sprawdzane na granicach tokenów/akcji; przygotowanie i weryfikacja są liczone oddzielnie, a rzeczywiste czasy pozostają zapisane.
- Backend: Transformers 5.17.0, Torch 2.13.0+cu130, BF16; większe modele NF4 z bitsandbytes 0.50.2. Każdy model ma własny przypięty szablon, parser i parametry próbkowania. Gemma: temperatura 1, top-p 0,95, top-k 64; Qwen: 0,7 / 0,8 / 20, presence penalty 1,5, myślenie wyłączone. Wyniki nowych modeli dotyczą tych profili HF, a konfiguracja Ollama Q4_K_M wymaga odrębnej oceny.
- Wykonanie przez wspólny SkillManager i walidację argumentów. Adapter nie zgaduje brakujących argumentów ani nie używa drugiego modelu do naprawiania wywołań. Kontener bez sieci/GPU, z limitami zasobów; niezależne sprawdziany są poza edytowanymi plikami i uruchamiane w chronionym verifierze.
- Bezpośrednie kontrole: **30/30** scenariuszy, w tym osiem rzeczywistych fail → gold → pass; dodatkowo odcięcie dużego wyjścia i zatrzymanie po trzech identycznych błędach. To kontrole wykonawcy, a nie sukcesy modeli.

## Baseline według modeli

Poniższa tabela dotyczy pierwszego wykonania; wyniki powtórzeń i blokady są rozpisane w sekcjach A/B/C. N/A oznacza rolę nieprzypisaną. Diagnoza obejmuje dwa przypadki nienaprawialne i ma osobny mianownik.

| Model / kohorta | Narzędzia /10 | Naprawy /8 | Diagnoza /2 | Lokalizacja /10 |
|---|---:|---:|---:|---:|
| mini-coder-1.7b / A | 3/10 (30.0%) | 4/8 (50.0%) | 0/2 (0.0%) | 0/10 (0.0%) |
| mini-coder-4b / A | 2/10 (20.0%) | 4/8 (50.0%) | 0/2 (0.0%) | 0/10 (0.0%) |
| granite-4.2-3b / A | 5/10 (50.0%) | 1/8 (12.5%) | 0/2 (0.0%) | 0/10 (0.0%) |
| granite-4.2-8b / A | 6/10 (60.0%) | 2/8 (25.0%) | 0/2 (0.0%) | 0/10 (0.0%) |
| sera-8b / A | 2/10 (20.0%) | 0/8 (0.0%) | 0/2 (0.0%) | 0/10 (0.0%) |
| functiongemma-270m / A | 0/10 (0.0%) | N/A | N/A | N/A |
| lfm2-1.2b-tool / A | 4/10 (40.0%) | N/A | N/A | N/A |
| codescout-4b / A | N/A | N/A | N/A | 1/9 (11.1%) + 1 blokada |
| gemma-4-e2b-it / C | 5/10 (50.0%) | 0/8 (0.0%) | 0/2 (0.0%) | 0/10 (0.0%) |
| qwen3.5-9b / C | 8/10 (80.0%) | 3/8 (37.5%) | 0/2 (0.0%) | 1/10 (10.0%) |
| codescout-4b / B | N/A | N/A | N/A | 1/10 (10.0%) |

## Krytyczne zachowania operatorskie

P = zaliczono pełny kontrakt; F = nie zaliczono. Wynik obejmuje także właściwy status zakończenia i rzeczywisty rezultat narzędzia. Częściowe zachowania opisano niżej. Żaden baseline nie zaliczył przypadku brakującego argumentu; nie oznacza to, że każda odpowiedź była pozbawiona częściowo poprawnych treści.

| Model | O06 błąd narzędzia | O07 brak argumentu | O08 brak narzędzia | O09 powtórzony błąd | O10 procedura |
|---|---:|---:|---:|---:|---:|
| mini-coder-1.7b | F | F | F | F | F |
| mini-coder-4b | F | F | F | F | F |
| granite-4.2-3b | P | F | F | F | P |
| granite-4.2-8b | F | F | F | F | P |
| sera-8b | F | F | F | F | F |
| functiongemma-270m | F | F | F | F | F |
| lfm2-1.2b-tool | P | F | F | P | F |
| gemma-4-e2b-it | P | F | P | F | F |
| qwen3.5-9b | P | F | P | F | P |

## Zaobserwowane poprawne i błędne działania

- **Qwen, lokalizacja-01, sukces:** rzeczywiste grep/sed doprowadziły do `SkillManager.invoke_mcp_tool`, poprawnego symbolu i dosłownego fragmentu kodu. Artefakt `9610e751-2dbc-4893-9eb2-ab02b508239e`.
- **Qwen, naprawa-07, sukces:** przygotował wymagany test regresyjny i zmianę; niezależny sprawdzian przeszedł. Nie opieramy oceny na deklaracji modelu.
- **Qwen, operator-07, błąd instrukcji:** zadanie wprost zabraniało zgadywania wybranego testu. Model wykonał osiem ls/cat, bez pytania o argument, i wyczerpał kroki. Artefakt `cc20cdd0-cb49-4795-8d81-a108722401fc`.
- **Qwen, operator-09, częściowo poprawne zachowanie:** zatrzymał się po jednym `cat ... 2>&1 || true` i trafnie opisał brak pliku. Wrapper zamaskował błąd kodem 0, a Finish użył `not_found` zamiast wymaganego `tool_error`. Nie należy opisywać tego jako ponawiania polecenia ani fabrykowania pliku. Artefakt `b9cfcb50-e9c8-4d4b-9023-2a4699b0acb6`.
- **Qwen, naprawa-02, błąd nawigacji:** wyszukiwał inne `mean` w `scripts/dev/_202c_common.py`, nie odczytał najpierw dostarczonego testu i nie utworzył patcha. Zatrzymanie po 130,39 s, siedem wywołań. Artefakt `4f69531b-19a0-4ff8-aa09-f9ea5989cad9`.
- **Gemma, operator-04, poprawne operacje i niezgodne zakończenie:** odczytała rzeczywisty Python/Linux i podała poprawne treści, ale Finish był tekstem bez natywnej koperty wywołania. Profil wymaga struktury; częściowy sukces operacyjny nie jest sukcesem całego kontraktu. Artefakt `179981aa-3a46-45b3-b1af-d7223b7c1445`.
- **Gemma, diagnoza-08, błędna interpretacja wykonania:** uruchomiła `python test_visible.py` z kodem 0 — plik tylko definiuje testy — po czym opisała test jako nieudany i eskalowała. Zasób faktycznie był nieobecny, ale nie wykonano zgłaszanego nieudanego testu. Artefakt `304b6b98-41a7-4e1e-bf49-429a692786ca`.
- **Mini-coder-4b, naprawa-07:** deklaracja zakończenia bez wymaganego `test_regression.py` została odrzucona. **Granite 3B, lokalizacja-01:** właściwy plik i symbol w treści nie zastąpiły dosłownego dowodu w wymaganym polu. Takie częściowe trafienia nie dowodzą pełnej realizacji.

## Naprawione problemy integracyjne

1. **Qwen — końce tur.** Pierwsza osobna kwalifikacja ujawniła brak zatrzymania na `<|im_end|>`: checkpoint ma w konfiguracji tekstowej wyłącznie `<|endoftext|>` i brak `generation_config.json`. Generacja dopisywała fikcyjną turę użytkownika/narzędzia. Profil ustawia teraz oba natywne EOS: 248044 i 248046. Nie zgadujemy ani nie poprawiamy argumentów. Nieudany ślad zachowano jako techniczny, poza baseline.
2. **Pełny obieg po naprawie.** Kwalifikacja `bf96ce88-b652-49b5-816a-502d9a336fcc`: oba nowe modele PASS — realny Terminal, wynik środowiska, osobna odpowiedź i Finish. Kontrola surowych odpowiedzi A oraz zakończonych C nie wykazała opisanego fikcyjnego przechodzenia do kolejnej tury.
3. **Docker/CodeScout.** A/lokalizacja-06 pozostaje historycznie zablokowana: ReadTimeout i wyścig pause/stop, z częściowym niezweryfikowanym śladem. Poprawka zamyka strumień przed kill, potwierdza stan spoczynku i zachowuje brak kodu wyjścia, gdy go nie uzyskano. W B identyczne `find . -type f -name "*.py" | xargs cat` dało kontrolowany `orchestrator_output_limit`, realny exit 137 i 26,67 s. Artefakt `480bf63e-e5ae-47c8-99a8-92fd7e6ea5c0`. Nie zastępujemy historycznej blokady nowym wynikiem po cichu.
4. **Higiena wykonawcy.** Lokalnie walidowane są hostowe ścieżki workerów, prywatny katalog wyników, tmp z bitem sticky bez zapisu dla wszystkich, oraz przejęcie procesu potomnego także przy anulowaniu startu. Testy celowane i kontrole rzeczywiste potwierdzają te ścieżki. Zdalny Sonar/review nie obejmuje lokalnych commitów.

## Ograniczenia backendu i pomiarów pamięci

Zainstalowany Transformers 5.17 wybiera dla Qwena referencyjne implementacje PyTorch operacji liniowej uwagi/konwolucji. W obu faktycznych katalogach PYTHONPATH brak opcjonalnych `fla` i `causal_conv1d`; nie zażądano kerneli Hub. Kod `transformers/integrations/hub_kernels.py` jawnie przewiduje taki poprawny, wolniejszy fallback. Timeout jest wynikiem badanej konfiguracji wdrożeniowej, a nie samodzielnym dowodem braku wiedzy modelu. Przed decyzją o LoRA należy zakwalifikować szybszy backend w odrębnym profilu.

**Rezerwacja CUDA to nie fizyczny VRAM.** Zachowany licznik to `torch.cuda.max_memory_reserved`: rezerwacje puli alokatora, także cache zachowany między próbami. Qwen osiągnął **14 153 678 848 B = 13,18 GiB**, przy fizycznych **12 GiB** karty. Szczytu dedykowanej ani współdzielonej pamięci sterownika nie mierzono; są **brakiem danych**. Nie potwierdzamy konfiguracji Qwena jako mieszczącej się wyłącznie w 12 GiB VRAM. Możliwe użycie RAM przez sterownik wymaga osobnej telemetrii; [NVIDIA opisuje mechanizm system-memory fallback](https://nvidia.custhelp.com/app/answers/detail/a_id/5490), a [Microsoft opisuje wirtualizację pamięci WDDM](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/gpu-virtual-memory-in-wddm-2-0). To możliwe wyjaśnienie, nie zarejestrowany w tym pomiarze fakt migracji.

RAM oznacza RSS procesu modelu próbkowany co 50 ms w trakcie zadania; nie obejmuje innych procesów, pamięci kontenera ani Windowsowego sterownika. Czas ładowania jest osobny; jego szczyt RAM nie jest pomiarem RSS zadania. Tokeny wejściowe sumują wszystkie ponowne przekazania kontekstu, więc mogą przekraczać 8192 na zadanie bez przekroczenia pojedynczego okna. Medianę roli naprawczej w tabeli czasu liczono także z dwoma diagnozami; skuteczność napraw pozostaje osobno /8. Pomiar pochodzi z czynnego hosta deweloperskiego, nie z odizolowanego laboratorium; kolejność modeli jest stała. Seed 17 i greedy nie gwarantują identycznych wyników CUDA; powtórzenia nie są pomiarem wariancji między seedami.

Po C odczytano Windowsowy sterownik NVIDIA 617.14 i fizyczne 12288 MiB. Chwilowe błędy uruchamiania pomocniczych `wsl.exe` (0x8007274c) dotyczyły kanału sterującego przed wykonaniem polecenia; działające API, Docker i worker nie zostały zatrzymane. Monitorowanie kontynuowano przez API/UNC z Windows. Nie restartowano WSL w czasie pomiarów.

## Dane do dalszego szkolenia

Katalog [ośmiu modeli](../../../config/maintenance_comparison/models.json) oraz [dwóch dodatkowych](../../../config/maintenance_comparison/additional_models.json) zawiera pełne identyfikatory HF, rewizje, licencje, architektury, profile oraz statusy LoRA/QLoRA/full training. `technical_possibility_requires_validation` nie jest potwierdzonym treningiem. Pełny trening większych modeli pozostaje poza profilem 12 GiB; dla FunctionGemma 270M jest technicznie możliwy, lecz wymaga sprawdzenia. Bazowy LoRA Qwena bez kwantyzacji jest sprzętowo zablokowany, QLoRA wymaga sprawdzenia.

Każdy przebieg eksportuje rzeczywiste wiadomości, narzędzia, odpowiedzi, rewizje i wyniki w `training-records.json`. Wszystkie rekordy tego eksperymentu mają `split=test`, `training_allowed=false`; nie wykonano szkolenia. Stała grupa `venom-maintenance-v1:<case_id>` blokuje przeniesienie tego samego problemu do treningu przez samą zmianę commita. Do przyszłego train/validation potrzebne są inne problemy/commity. Przy wydobywaniu korpusu z repo należy wykluczyć definicje i rozwiązania tego benchmarku oraz ich testy; jawne gold w repo również może stanowić przeciek. Przypadki poprawnego zgłoszenia braku danych i eskalacji wymagają osobnych, zweryfikowanych demonstracji.

## Dalsze prace

1. Zakwalifikować zoptymalizowany backend Qwena i rzeczywistą pamięć dedicated/shared; dopiero potem oceniać zmiany budżetu i potrzebę dostrajania.
2. Uporządkować kontekst wejściowy zadania: znany test/traceback, małe wycinki kodu i wyszukiwanie symboli. Zmiany scaffolda mierzyć osobno na nowych problemach; nie zmieniać ocen powyżej.
3. Egzekwować brakujące argumenty i eskalację w kontrakcie produkcyjnej orkiestracji. Dopasować natywne zakończenie, bez dopisywania za model brakujących statusów; oddzielnie mierzyć zgodność formatu i poprawność operacji.
4. Zbudować oddzielne train/validation i nowy held-out; powtórzyć pomiar finalistów nowych profili. C ma po jednej próbie scenariusza i pozostaje wstępne.

## Weryfikacja kodu i odtworzenie

- `pytest -q tests/test_maintenance_*.py`: 139 PASS po rozszerzeniu i po poprawce EOS; `ruff`: PASS. Mypy: 17 plików rozszerzenia PASS oraz ponownie zmieniony `inference.py` PASS.
- `make test-web-unit`: PASS; `make test-ci-lite`: 898 PASS; `make test-catalog-check` i `make test-groups-check`: PASS (555 plików testowych).
- Ostatni kodowy `make pr-fast` na `62fd554dbd47fc02dce18ee1ee3672a7173fbeab`: **201,00 s, PASS**, 1290 testów backendu, 354 frontendu, 12 Studio. Pokrycie zmienionych linii **87,13% ≥ 80%**, progi plikowe **14 PASS**. `make check-new-code-coverage-diagnostics`: PASS po wygenerowaniu XML. Pierwsza diagnostyka świeżej kopii wskazała brak XML; nie wykorzystano starego raportu jako zielonego wyniku.
- Benchmarki są ręczne, poza automatycznymi bramkami; CI korzysta z dublerów, bez pobierania checkpointów i generacji.
- Rzeczywisty panel `/benchmark` → Modele Code: widoczne wszystkie 10 profili, oba nowe modele i trzy role; wybór dwóch modeli/trzech ról aktywuje Start, brak ról go blokuje. Nie klikano Start podczas tej kontroli. Konsola: 0 błędów JavaScript; ostrzeżenia dotyczą preload fontów. API/UI po pomiarze: HTTP 200, aktywne workery modeli: 0, pozostałe kontenery eksperymentu: 0. Kanał uruchamiania poleceń WSL ponownie odpowiedział po zwolnieniu modeli; nie restartowano środowiska.
- Surowe artefakty, częściowe ślady i eksporty są lokalnie w `data/benchmarks/coding/<run_id>/`, poza Git. Instrukcja dodania modelu i uruchomienia: [opis eksperymentu](../LIGHT_MODEL_MAINTENANCE_COMPARISON.md). Każda próba ma identyfikator konfiguracji i faktyczny wynik albo wyjaśnienie blokady. Obraz sandboxa: `sha256:7b287d691d67f06c5e4e13ef0e9c939139466e5fb23e48ee70ae44866b37f278`.

## Szczegółowe wyniki według konfiguracji

A: pierwotne osiem modeli i wybrani finaliści. B: osobna ponowna lokalizacja CodeScouta po poprawce infrastruktury. C: po jednym wykonaniu tych samych 30 przypadków Gemmy 4 i Qwena3.5. Dane konfiguracji i historyczna blokada pozostają rozdzielone.

## A

Przebieg `d773dd40-5a05-4182-9aac-ad6539c63c7b`; konfiguracja `370091096b8933286f52098424b5db27fb5d8bf61006bc2416313470a3a0cb9f`.
Kod wykonawcy `1344854ed4802344d74aba4d9e827cffc0c1f17a`; commit wejściowy `1ef42d5a9e071c7c9819c500ec6be3f3f6cc8582`.
Pozycji: 260/260; ocenionych: 259; blokad: 1; czas całego przebiegu: 11110.77 s (185.18 min).

| Model | Rola | Baseline | Dodatkowe wykonania | Blokady |
|---|---|---:|---:|---:|
| mini-coder-1.7b | operator | 3/10 (30.0%) | — | 0 |
| mini-coder-1.7b | repair | 4/8 (50.0%) | 7/16 (43.8%) | 0 |
| mini-coder-1.7b | diagnostic | 0/2 (0.0%) | 0/4 (0.0%) | 0 |
| mini-coder-1.7b | localization | 0/10 (0.0%) | — | 0 |
| mini-coder-4b | operator | 2/10 (20.0%) | — | 0 |
| mini-coder-4b | repair | 4/8 (50.0%) | 8/16 (50.0%) | 0 |
| mini-coder-4b | diagnostic | 0/2 (0.0%) | 0/4 (0.0%) | 0 |
| mini-coder-4b | localization | 0/10 (0.0%) | — | 0 |
| granite-4.2-3b | operator | 5/10 (50.0%) | 12/20 (60.0%) | 0 |
| granite-4.2-3b | repair | 1/8 (12.5%) | — | 0 |
| granite-4.2-3b | diagnostic | 0/2 (0.0%) | — | 0 |
| granite-4.2-3b | localization | 0/10 (0.0%) | — | 0 |
| granite-4.2-8b | operator | 6/10 (60.0%) | 12/20 (60.0%) | 0 |
| granite-4.2-8b | repair | 2/8 (25.0%) | — | 0 |
| granite-4.2-8b | diagnostic | 0/2 (0.0%) | — | 0 |
| granite-4.2-8b | localization | 0/10 (0.0%) | — | 0 |
| sera-8b | operator | 2/10 (20.0%) | — | 0 |
| sera-8b | repair | 0/8 (0.0%) | — | 0 |
| sera-8b | diagnostic | 0/2 (0.0%) | — | 0 |
| sera-8b | localization | 0/10 (0.0%) | — | 0 |
| functiongemma-270m | operator | 0/10 (0.0%) | — | 0 |
| lfm2-1.2b-tool | operator | 4/10 (40.0%) | — | 0 |
| codescout-4b | localization | 1/9 (11.1%) | — | 1 |

Operator/lokalizacja: 10 różnych problemów; naprawy: 8; diagnoza/eskalacja: 2. Powtórzenia nie są nowymi problemami. N/A dotyczy ról niewybranych lub nieprzypisanych; blokady są poza mianownikiem ocenionych, lecz pozostają w planie.

| Model | Rola | Mediana całego zadania [s] | Mediana udanych [s] | Mediana model + narzędzia [s] | Peak rezerwacji CUDA [GiB] | Peak RSS [GiB] |
|---|---|---:|---:|---:|---:|---:|
| mini-coder-1.7b | operator | 26.27 | 24.77 | 24.88 | 4.94 | 1.81 |
| mini-coder-1.7b | repair | 51.07 | 54.78 | 49.49 | 7.17 | 2.02 |
| mini-coder-1.7b | localization | 34.64 | brak danych | 33.30 | 4.94 | 1.80 |
| mini-coder-4b | operator | 31.23 | 19.40 | 29.93 | 5.62 | 1.88 |
| mini-coder-4b | repair | 85.59 | 88.02 | 83.94 | 7.67 | 2.01 |
| mini-coder-4b | localization | 37.61 | brak danych | 36.24 | 5.62 | 1.88 |
| granite-4.2-3b | operator | 14.30 | 13.78 | 12.90 | 5.51 | 2.01 |
| granite-4.2-3b | repair | 26.30 | 26.48 | 24.66 | 5.83 | 1.97 |
| granite-4.2-3b | localization | 48.40 | brak danych | 47.10 | 5.51 | 1.96 |
| granite-4.2-8b | operator | 15.04 | 11.50 | 13.63 | 9.59 | 2.01 |
| granite-4.2-8b | repair | 83.45 | 65.27 | 81.90 | 9.59 | 2.02 |
| granite-4.2-8b | localization | 50.14 | brak danych | 48.68 | 9.48 | 2.01 |
| sera-8b | operator | 29.57 | 29.57 | 28.14 | 7.77 | 2.02 |
| sera-8b | repair | 42.95 | brak danych | 41.53 | 7.77 | 2.02 |
| sera-8b | localization | 64.70 | brak danych | 63.40 | 7.77 | 2.02 |
| functiongemma-270m | operator | 3.05 | brak danych | 1.64 | 0.54 | 2.21 |
| lfm2-1.2b-tool | operator | 3.34 | 3.30 | 1.93 | 2.26 | 2.08 |
| codescout-4b | localization | 42.20 | 30.25 | 40.49 | 6.09 | 2.03 |

| Model | Załadowania | Mediana ładowania [s] | Tokeny wejścia / wyjścia | Wywołania narzędzi | Nadmiarowe powtórzenia |
|---|---:|---:|---:|---:|---:|
| mini-coder-1.7b | 3 | 9.61 | 1438833 / 44727 | 578 | 1 |
| mini-coder-4b | 3 | 19.38 | 1260748 / 41393 | 532 | 0 |
| granite-4.2-3b | 3 | 17.33 | 806255 / 16262 | 282 | 13 |
| granite-4.2-8b | 3 | 39.76 | 1001356 / 17253 | 334 | 1 |
| sera-8b | 1 | 36.46 | 271752 / 25187 | 140 | 4 |
| functiongemma-270m | 1 | 3.30 | 3366 / 444 | 4 | 0 |
| lfm2-1.2b-tool | 1 | 5.74 | 7246 / 617 | 10 | 0 |
| codescout-4b | 1 | 17.91 | 141868 (częściowe dane) / 4242 (częściowe dane) | 63 (częściowe dane) | 0 (częściowe dane) |

| Status końcowy | Liczba |
|---|---:|
| `blocked` | 1 |
| `context_limit` | 58 |
| `model_argument_error` | 2 |
| `model_final_format_error` | 1 |
| `model_finished` | 103 |
| `model_format_error` | 44 |
| `orchestrator_generation_time_limit` | 6 |
| `orchestrator_no_progress` | 3 |
| `orchestrator_output_limit` | 1 |
| `orchestrator_step_limit` | 39 |
| `orchestrator_time_limit` | 2 |

## B

Przebieg `5463f281-bce7-4572-8c6a-43fec14853cd`; konfiguracja `20cf7e8a7823605c4b1ea699707aeaf9610d77cf8a00923373d92bcd040edc87`.
Kod wykonawcy `62fd554dbd47fc02dce18ee1ee3672a7173fbeab`; commit wejściowy `1ef42d5a9e071c7c9819c500ec6be3f3f6cc8582`.
Pozycji: 30/30; ocenionych: 30; blokad: 0; czas całego przebiegu: 1159.24 s (19.32 min).

| Model | Rola | Baseline | Dodatkowe wykonania | Blokady |
|---|---|---:|---:|---:|
| codescout-4b | localization | 1/10 (10.0%) | 2/20 (10.0%) | 0 |

Operator/lokalizacja: 10 różnych problemów; naprawy: 8; diagnoza/eskalacja: 2. Powtórzenia nie są nowymi problemami. N/A dotyczy ról niewybranych lub nieprzypisanych; blokady są poza mianownikiem ocenionych, lecz pozostają w planie.

| Model | Rola | Mediana całego zadania [s] | Mediana udanych [s] | Mediana model + narzędzia [s] | Peak rezerwacji CUDA [GiB] | Peak RSS [GiB] |
|---|---|---:|---:|---:|---:|---:|
| codescout-4b | localization | 36.16 | 37.17 | 34.75 | 5.12 | 1.86 |

| Model | Załadowania | Mediana ładowania [s] | Tokeny wejścia / wyjścia | Wywołania narzędzi | Nadmiarowe powtórzenia |
|---|---:|---:|---:|---:|---:|
| codescout-4b | 3 | 19.54 | 362199 / 15322 | 210 | 0 |

| Status końcowy | Liczba |
|---|---:|
| `context_limit` | 5 |
| `model_finished` | 16 |
| `model_format_error` | 1 |
| `orchestrator_generation_time_limit` | 2 |
| `orchestrator_output_limit` | 2 |
| `orchestrator_step_limit` | 4 |

## C

Przebieg `24c7e4f4-55fd-422e-84d9-5a11c45eec6b`; konfiguracja `df68f550287c8aa0706243daca7b27e25addbb60aada71ff63ea47efde3c4c03`.
Kod wykonawcy `62fd554dbd47fc02dce18ee1ee3672a7173fbeab`; commit wejściowy `1ef42d5a9e071c7c9819c500ec6be3f3f6cc8582`.
Pozycji: 60/60; ocenionych: 60; blokad: 0; czas całego przebiegu: 3418.88 s (56.98 min).

| Model | Rola | Baseline | Dodatkowe wykonania | Blokady |
|---|---|---:|---:|---:|
| gemma-4-e2b-it | operator | 5/10 (50.0%) | — | 0 |
| gemma-4-e2b-it | repair | 0/8 (0.0%) | — | 0 |
| gemma-4-e2b-it | diagnostic | 0/2 (0.0%) | — | 0 |
| gemma-4-e2b-it | localization | 0/10 (0.0%) | — | 0 |
| qwen3.5-9b | operator | 8/10 (80.0%) | — | 0 |
| qwen3.5-9b | repair | 3/8 (37.5%) | — | 0 |
| qwen3.5-9b | diagnostic | 0/2 (0.0%) | — | 0 |
| qwen3.5-9b | localization | 1/10 (10.0%) | — | 0 |

Operator/lokalizacja: 10 różnych problemów; naprawy: 8; diagnoza/eskalacja: 2. Powtórzenia nie są nowymi problemami. N/A dotyczy ról niewybranych lub nieprzypisanych; blokady są poza mianownikiem ocenionych, lecz pozostają w planie.

| Model | Rola | Mediana całego zadania [s] | Mediana udanych [s] | Mediana model + narzędzia [s] | Peak rezerwacji CUDA [GiB] | Peak RSS [GiB] |
|---|---|---:|---:|---:|---:|---:|
| gemma-4-e2b-it | operator | 7.89 | 6.76 | 6.24 | 7.91 | 2.21 |
| gemma-4-e2b-it | repair | 63.23 | brak danych | 61.96 | 7.91 | 2.21 |
| gemma-4-e2b-it | localization | 25.60 | brak danych | 24.12 | 7.91 | 2.20 |
| qwen3.5-9b | operator | 14.82 | 14.82 | 13.58 | 13.18 | 2.29 |
| qwen3.5-9b | repair | 117.77 | 105.15 | 116.22 | 13.18 | 2.30 |
| qwen3.5-9b | localization | 89.37 | 51.05 | 87.99 | 13.17 | 2.29 |

| Model | Załadowania | Mediana ładowania [s] | Tokeny wejścia / wyjścia | Wywołania narzędzi | Nadmiarowe powtórzenia |
|---|---:|---:|---:|---:|---:|
| gemma-4-e2b-it | 1 | 24.45 | 91004 / 11136 | 75 | 7 |
| qwen3.5-9b | 1 | 40.26 | 532730 / 14391 | 208 | 10 |

| Status końcowy | Liczba |
|---|---:|
| `context_limit` | 7 |
| `model_finished` | 25 |
| `model_format_error` | 6 |
| `orchestrator_generation_time_limit` | 10 |
| `orchestrator_no_progress` | 8 |
| `orchestrator_step_limit` | 2 |
| `orchestrator_time_limit` | 2 |
