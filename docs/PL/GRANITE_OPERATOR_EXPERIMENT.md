# Granite operator — dane i artefakty wyłącznie lokalnie

## Kod i lokalne artefakty

Git zawiera implementację treningu, testy, lock zależności i ogólną recepturę
`config/granite_operator_profile.json`. Wszystkie zbiory danych, decyzje kuracji,
manifesty korpusu, dowody wykonania, checkpointy, logi, częściowe wyniki i
podsumowania przebiegów pozostają w ignorowanych katalogach.

Cały eksperyment przechowujemy w `data/training/<eksperyment>/`:

| Katalog lub plik względny | Zawartość |
|---|---|
| raw/ | Przypięte pliki źródłowe oraz README i licencje |
| hf/ | Kandydaci, decyzje przeglądu, ledger audytu i znormalizowane splity HF |
| recipes/ | Prywatne receptury zawierające konkretne przykłady treningowe |
| domain/ | Autorskie rozmowy, izolowane fixture i dowody wykonania |
| history-requirements.json | Prywatne pochodzenie wymagań z historii chatów |
| download-manifest.json | Adresy pobrań, rewizje i sumy kontrolne |
| pilot-manifest.json | Hashe splitów, liczby rekordów i kontrola jakości danych |
| analysis/ | Lokalne analizy i opisy wyników |
| runs/ | Wszystkie żądania, lokalizacje, logi, metryki i checkpointy |
| training-results.json | Lokalne zbiorcze wyniki |
| private_git_history/ | Lokalne kopie odzyskiwania historii; bez publikacji |

Ignorowany jest cały katalog, również przyszłe pliki i zagnieżdżone repozytoria
fixture. Dodatkowe lokalne przestrzenie to `data/datasets/`, `data/experiments/`,
`data/academy/`, `artifacts/training/`, `artifacts/datasets/` oraz katalogi
w korzeniu: `datasets/`, `training-data/`, `training-runs/`,
`training-results/`, `checkpoints/`, `adapters/`, `wandb/`, `mlruns/`
i `lightning_logs/`. Są ignorowane w całości.
Starszy katalog `config/granite_operator/` również jest wyłącznie lokalny.
Nowe manifesty i decyzje kuracji zapisujemy pod katalogiem danych.

Reguła ignore nie usuwa wcześniej śledzonych plików ani ich commitów.
Przed publikacją sprawdzamy zarówno `git ls-files`, jak i nazwy obiektów
osiągalnych z proponowanej gałęzi. Nie dodajemy artefaktów przez force-add.

## Źródła i przygotowanie

Downloader przypina rewizje i SHA-256 źródeł
[nvidia/When2Call](https://huggingface.co/datasets/nvidia/When2Call) i
[Team-ACE/ToolACE](https://huggingface.co/datasets/Team-ACE/ToolACE).
Licencje i atrybucję zachowujemy w lokalnym katalogu źródeł.
Obserwacje HF są etykietami dostarczonymi przez źródło, nie dowodami lokalnego
wykonania. Generator domain tworzy syntetyczne fixture inspirowane lokalnymi
wymaganiami; nie kopiuje surowych chatów Codex do korpusu.

Skrypty w `scripts/granite_operator/` używają `GRANITE_DATA_ROOT`.
Pobieranie: `download.py --data-root ABSOLUTNY_LOKALNY_KATALOG_DANYCH`.
`prepare_hf.py` tworzy kandydatów; decyzje zapisujemy lokalnie w
`hf/review-decisions.json`. Repozytorium nie dostarcza domyślnych decyzji kuracji.
Autorską recepturę domain przechowujemy lokalnie w `DATA_ROOT/recipes/prepare_domain.py`;
nie jest częścią publikowanego kodu. Uruchamiamy ją w izolowanym kontenerze bez sieci,
z nowym katalogiem danych; odmawia nadpisania istniejących fixture.
`finalize_data.py` wymaga `GRANITE_SNAPSHOT`, stosuje zapisane decyzje i używa
natywnego tokenizera. `audit_data.py` zapisuje `pilot-manifest.json`.
Loader sprawdza hashe manifestu, liczby rekordów i rozłączność rodzin problemów.

## Natywny kontrakt treningu

Obecny fallback Academy spłaszcza instruction/input/output i gubi obieg narzędzi.
Eksperyment używa osobnego opcjonalnego CLI zachowującego `tools + messages`,
wywołania asystenta, pasujące obserwacje narzędzi i natywny szablon Granite.
Maska obejmuje wyłącznie nadzorowane tury asystenta, wraz z wywołaniami i końcami tur.
Instrukcje systemu/użytkownika i obserwacje narzędzi są zamaskowane.
Ucięcie kontekstu lub token przecinający granicę roli kończy run błędem.

Przypięty checkpoint Granite, NF4/BF16 i parametry LoRA znajdują się w ogólnej
recepturze. Instalacja izolowanego komponentu:

```bash
source .venv/bin/activate
python scripts/bootstrap_dependency_profile.py --profile granite-operator-training \
  --venv /absolute/local/venvs/granite-training --storage-root /mnt/f
```

Przed rezerwacją jedynego GPU zatrzymujemy API i runtime modelu przez ich
właściwy launcher. Używamy rzeczywistego ledgeru hosta Venom.
CLI nie zatrzymuje usług automatycznie i odmawia pracy przy aktywnym porcie
API/modelu. Nowy katalog wyjściowy umieszczamy wewnątrz ignorowanego eksperymentu.

```bash
python -m venom_core.services.granite_operator.cli smoke \
  --data-root /absolute/local/data/training/experiment \
  --snapshot /absolute/local/hub/snapshots/4e9c275e232f10211ec88644d106a1f6a1b60e06 \
  --worker-python /absolute/local/venvs/granite-training/bin/python \
  --admission-db /actual/host/data/memory/runtime-admission.sqlite3 \
  --output /absolute/local/data/training/experiment/runs/smoke-unique
```

Bez `--manifest` CLI czyta `DATA_ROOT/pilot-manifest.json`.
Inny lokalny manifest można wskazać jawnie; ścieżka trafia do lokalnego
locations.json. Repozytorium nie dostarcza manifestu konkretnego korpusu.

Smoke obejmuje 32 rozmowy train i 8 validation, 16 aktualizacji optymalizatora,
checkpoint, nowy proces i wznowienie o cztery kroki. Sprawdza maskę, skończone
loss/gradienty, zmianę adaptera i zamrożoną bazę, logity po odczycie, stan
optymalizatora/RNG, adapter on/off, backward przy pełnym kontekście oraz
wygenerowany obieg Terminal → rzeczywista obserwacja → Finish. Nie ma opcji skip.

Trening używa tych samych ścieżek z komendą `train`, argumentem
`--qualification DATA_ROOT/runs/smoke-unique/qualification.json`,
`--dataset domain|hf|mixed` i jawnym budżetem aktualizacji.
Zmiana kodu, profilu, danych, środowiska lub checkpointu wymaga nowego zgodnego
smoke. Trening zapisuje i ponownie odczytuje checkpoint przed końcem pierwszej epoki.

Końcowy adapter sprawdzamy przez
`python -m scripts.granite_operator.verify_checkpoint` z `--run`,
`--admission-db` i `--worker-python`. Weryfikator używa wskazanego venv,
porównuje NLL i wykonuje rzeczywisty obieg narzędzi; zapisuje lokalne dowody i logi.
`python scripts/granite_operator/report.py LOKALNY_RUN` odczytuje zmierzone
czasy treningu, nadzorowane tokeny/s, p50/p95 kroków, NLL i pamięć.

## Interpretacja

Wyniki przebiegów i prywatne pochodzenie danych opisujemy wewnątrz ignorowanego
katalogu eksperymentu, bez osadzania ich w publikowanej dokumentacji repozytorium.
NLL i probe techniczny potwierdzają zachowanie procesu. Skuteczność operatora
i opóźnienia inferencji wymagają osobnego zamrożonego porównania bazy, kontroli
promptu i adapterów w tych samych warunkach. Szybkość treningu nie potwierdza
szybszego wykonania zadań. Adapter pozostaje eksperymentalny do czasu porównania;
nie ma automatycznego treningu zdalnego ani wdrożenia.


## Sparowane porównanie inferencji

`scripts/granite_operator/comparison.py` przyjmuje lokalny zamrożony manifest przez
`--cases`, zweryfikowany pierwszy adapter przez `--training-run`, właściwy
`--worker-python`, rzeczywisty `--admission-db` i nowy ignorowany `--output`.
Definicje przypadków, oracle i konkretne wyniki pozostają pod katalogiem danych.
Wznowienie wymaga jawnego `--resume` i zgodnej tożsamości danych, kodu i wag.

Oba ramiona korzystają z tej samej załadowanej bazy i kwantyzacji: kontrola ma
adapter PEFT wyłączony, drugie ramię włączony. Wagi są zamrożone; nie zachodzi
trening ani wdrożenie. Jest to kontrola numeryczna na wspólnej bazie, nie osobny
pomiar zimnego ładowania ani niezależnej pamięci modelu bez rezydującego adaptera.
Kolejność ramion jest równoważona i mieszana stałym ziarnem. Generowanie jest
greedy, z identycznymi limitami kontekstu, tokenów, tur i czasu.

Każde ramię ma oddzielną kopię fixture w kontenerze bez sieci, GPU i socketu
hosta, z read-only root i zapisem wyłącznie do kopii zadania. Procesy modelowych
narzędzi są zatrzymywane przed oceną. Oracle używa rzeczywistego stanu plików,
obserwacji i — gdy potrzeba — nowego kontenera tylko do odczytu.

Raport zawiera wszystkie próby, także błędne i timeouty, skuteczność zadania,
niepotwierdzone success, naruszenia zakresu, czas zadania p50/p95 oraz osobno
czas generowania, narzędzi i oracle. Przygotowanie fixture i oracle nie wchodzą
do czasu operatora. Przedział niepewności różnicy skuteczności grupuje próbki
po rodzinie szablonu; warianty i pary językowe nie są niezależnymi zadaniami.

## Porównanie adaptera trenowanego na zdalnym hoście

`scripts.granite_operator.remote_comparison` uruchamia sparowaną inferencję na
istniejącym hoście SSH, a narzędzia i oracle wykonuje lokalnie przez `DockerTool`.
Nie potrzebuje Dockera na hoście GPU. Lokalny operator musi mieć działający,
autoryzowany dostęp do swojego Dockera i przypięty obraz fixture. Nie wykonujemy
komend modelu w kontenerze treningowym ani bezpośrednio na lokalnym hoście.

```bash
python -m scripts.granite_operator.remote_comparison \
  --cases /data/eval/manifest.json --output /data/eval/run-unique \
  --ssh-config /private/operator/ssh_config --host gpu-training \
  --remote-result /workspace/data/remote-training/runs/RUN_ID/attempts/0002/result \
  --adapter-sha256 HASH_Z_POTWIERDZONEGO_ODBIORU --max-seconds 7200
```

Zdalny interpreter domyślnie to `/workspace/data/remote-training/rpc-python`.
Serwer sprawdza terminalny sukces treningu, tożsamość bazy/profilu/kodu/zależności
oraz konkretny hash wag adaptera. Model rezyduje raz na zdalnym GPU; wariant
kontrolny wyłącza adapter PEFT. Ustawienia generowania są identyczne, greedy,
z rozgrzewką niezależną od testów i przeplataną kolejnością obu wariantów.
Połączenie przenosi wyłącznie stały protokół JSONL: inferencję i pomiary pamięci.
Właściciel RuntimeAdmission i blokada GPU obowiązują przez całą sesję; EOF,
sygnały i limit czasu kończą proces modelu i zwalniają rezerwację. Host nie jest
usuwany ani zatrzymywany.

Każda próba jest zapisywana w `trials.jsonl`; `progress.json` i stdout pokazują
licznik ukończonych prób oraz sukcesy obu ramion. `summary.json` zawiera ocenę
oracle, błędy, czasy i sparowaną różnicę wyników. `--resume` zachowuje ukończone
pary, kontroluje duplikaty oraz zgodność danych, adaptera, ustawień i kodu.
Błąd infrastruktury przerywa sesję; błędna odpowiedź modelu i przekroczenie
kontekstu są wynikiem konkretnego zadania.

Dotychczasowy zestaw G01 jest diagnostyczny po wykorzystaniu jego kategorii
błędów do przygotowania G02. Powtórzenie na nim pokazuje naprawione zachowania
oraz regresje; niezależne potwierdzenie poprawy wymaga świeżego holdoutu.

## Poprawa materiału po diagnozie

Nowa wersja materiału powstaje w nowym ignorowanym katalogu eksperymentu.
Zachowujemy poprzedni korpus, adapter i zamrożony test. Z diagnozy wykorzystujemy
kategorie błędów; nie kopiujemy przypadków testowych ani fixture do treningu.
Po dostrojeniu materiału na podstawie wyników dotychczasowy test staje się
diagnostyczny. Potwierdzenie poprawy wymaga nowego, niezależnego holdoutu.

Materiał pokazuje rozwiązywanie wskazanych i względnych ścieżek, odczyt stanu,
minimalną zmianę, rzeczywistą kontrolę po zapisie oraz końcowy Finish.
Rozróżniamy poprawny odczyt pliku od pozytywnego wyniku opisanego w nim zadania,
błąd zbierania testów od zaliczonych testów oraz brak wymaganych danych od zgody
na zgadywanie celu zmiany. Polecenia pozostają krótkie; nie powielamy flag.

Błędna akcja poprzedzająca poprawną naprawę jest kontekstem, a nie pozytywną
etykietą. Opcjonalne pole `supervised_assistant_indices` wskazuje indeksy tur
asystenta podlegających loss; musi obejmować ostatnią turę. Brak pola zachowuje
dotychczasowy nadzór wszystkich tur. W korpusie naprawczym
`context_only_assistant_indices` i dowód wykonania identyfikują błędne prefiksy.
Cały prefiks wraz z prawdziwą obserwacją pozostaje w wejściu, z etykietami -100.
Poprawna komenda sprawdzająca, która wykryła błąd, nadal jest nadzorowana.
Ponowienie testu jest uzasadnione po zmianie plików, nie po identycznym błędzie.

Każdy autorski obieg ma rzeczywiste stdout/stderr/exit_code, stan przed i po,
kontrolę zakresu oraz niezależne oczekiwanie dotyczące wyniku. Pary językowe
dzielą fixture i pozostają z całą rodziną po tej samej stronie podziału.
Mieszamy kolejność rodzin i języków; kontrolujemy udział nadzorowanych tokenów,
aby długie komendy jednej rodziny nie zdominowały korpusu. Zbiór HF pozostaje
oddzielną opcją retencji, z niezmienionymi hashami i pochodzeniem.

### Przyjęcie danych bez treningu

```bash
python -m scripts.granite_operator.validate_material \
  --data-root /absolute/local/data/training/new-material \
  --snapshot /absolute/local/hub/snapshots/4e9c275e232f10211ec88644d106a1f6a1b60e06
```

To polecenie ładuje wyłącznie lokalny tokenizer i tworzy batch na CPU.
Nie tworzy modelu, optymalizatora ani sesji treningowej i nie rezerwuje GPU.
Sprawdza hashe, schematy, dowody narzędziowe, maski błędnych prefiksów,
końce tur, pełny kontekst bez ucięcia oraz round-trip natywnego protokołu.
Wynik zapisuje pod `DATA_ROOT/checks/intake.json`.
`PASS_DATA_INTAKE_ONLY` oznacza poprawność przyjęcia materiału, nie poprawę
skuteczności modelu i nie zastępuje kwalifikacji treningowej smoke.
Nowy materiał nie uruchamia automatycznie smoke, treningu ani wdrożenia.

## Kolejny PR

Zakres kompletnej pętli zdalnego treningu zapisano w
[backlogu REMOTE-TRAINING-01](BACKLOG.md#remote-training-01--kompletna-pętla-treningu-na-zdalnym-hoście).
Obejmuje transfer danych, obsługę sesji na hoście, odbiór i weryfikację adaptera
oraz metryk. Zapis planu nie uruchamia usług ani treningu.

## Testy komponentu w CI

Backend CI instaluje osobny plik requirements-granite-operator-tests.txt:
przypięty wheel Torch CPU dla Linux x86_64/Python 3.14 i Transformers.
Profil aplikacyjny ci-lite pozostaje bez zależności treningowych.
Testy sprawdzają obliczenia na małych tensorach CPU i atrapy granic procesów;
nie pobierają wag i nie uruchamiają rzeczywistego modelu ani treningu GPU.

## Integralność przygotowania i porównania

Finalizacja i audyt czytają ten sam profil co trening (domyślnie
config/granite_operator_profile.json; dla skryptów przygotowania można wskazać
GRANITE_PROFILE). Intake przyjmuje opcjonalny --profile. Nowy manifest zawiera
kontekst i deskryptor execution_receipts. Audyt używa tego samego kontraktu
obserwacji i masek co intake oraz odmawia nadpisania istniejącego manifestu.
Dla zamrożonego korpusu używamy intake; nie przebudowujemy historycznych danych.

Tożsamość kwalifikacji obejmuje również pliki tokenizera, szablonu i konfiguracji
generowania. Porównanie weryfikuje ich zgodność z treningiem i zapisuje ją na
potrzeby resume. Starszy dowód bez tych pól nie jest automatycznie uzupełniany
hashami aktualnego snapshotu. Inwentarz fixture obejmuje wszystkie pliki,
także metadane Git; dodanie pliku lub symlinku unieważnia zamrożony zestaw.

Zapisy modelu trafiają do tmpfs kontenera: 16 MiB i 1024 inody; pojedynczy plik
ma limit 1 MiB ustawiany wewnątrz kontenera. Seed jest bind-mountem tylko do
odczytu, a zweryfikowany eksport regularnych plików odtwarza stan zadania na
hoście. Snapshot sprawdza liczbę i logiczny rozmiar plików przed ich hashowaniem.
Verifier nadal używa bind-mountu tylko do odczytu. Zmiana sandboxu wymaga nowego
porównania; nie łączymy jego prób ze starszymi wynikami.

Profile JSON można czytać z katalogu config repozytorium lub spod
GRANITE_DATA_ROOT ustawionego przez operatora. Ścieżki poza tymi korzeniami
i symlinki profili są odrzucane. Dotyczy to również własnego --profile.


### Konfigurowalne porównanie na jednym hoście

Moduł `scripts.granite_operator.comparison` obsługuje odebrany wynik treningu.
**Model, narzędzia Docker i niezależne sprawdzanie wyników działają na tej samej
maszynie.** Polecenie uruchom lokalnie albo w sesji SSH na hoście treningowym.
`--execution-host` zapisuje wybrane miejsce wykonania; nie wynajmuje hosta ani nie
nawiązuje SSH. Starszy `remote_comparison` pozostaje mostem: zdalny model i lokalne
narzędzia. Nowe parametry dotyczą wykonania całego etapu na jednym hoście.

```bash
source .venv/bin/activate
python -m scripts.granite_operator.comparison \
  --host-root /bezwzgledny/katalog-konfiguracji-hosta \
  --adapter-root /bezwzgledny/zweryfikowany-wynik-treningu \
  --expected-adapter-sha256 <sha256> \
  --cases /bezwzgledny/benchmark/manifest.json \
  --output /bezwzgledny/nowy-katalog-wynikow \
  --execution-host local --concurrency 2 --batch-size 2
```

Na zdalnej maszynie użyj jej skonfigurowanego interpretera i ścieżek oraz
`--execution-host remote --concurrency 4 --batch-size 4`. Najpierw przenieś pełny,
zamrożony benchmark z plikami zadań i przypięty obraz kontenera. Host musi
obsługiwać dotychczasową izolację Docker: sam kontener z dostępem SSH nie wystarcza.
Dostępność obrazu jest sprawdzana przed załadowaniem modelu; uruchomienie kontenera
musi też spełnić wszystkie dotychczasowe ograniczenia. Kod nie przenosi narzędzi
z powrotem lokalnie i nie uruchamia ich bez izolacji. API i usługi modeli muszą
być zatrzymane, a rezerwacja GPU wolna.

| Parametr | Domyślnie | Znaczenie |
|---|---:|---|
| `--concurrency` | lokalnie: 1; zdalnie: 4 | Aktywne zadania: 1, 2, 4 lub 8; jedna instancja modelu. |
| `--batch-size` | concurrency | Maksymalna paczka GPU dla tego samego wariantu modelu: od 1 do concurrency. |
| `--batch-wait-ms` | 20 | Oczekiwanie na zebranie paczki: 0–100 ms. |
| `--task-seconds` | 60 | Budżet aktywnej pracy zadania: 1–600 s, bez kolejki GPU. |
| `--max-seconds` | 7200 | Limit całego uruchomienia, z rozruchem i kolejką: 1–14400 s. |
| `--execution-host` | local | Oznaczenie miejsca wykonania: local albo remote. |

Lokalnie domyślne jest 1 zadanie; można wybrać 2. Profil zdalny startuje od
4 zadań z adaptacją. Jego poprawność nadal wymaga kwalifikacji. Jedna kolejka steruje GPU
i przełączaniem adaptera, każde zadanie ma osobny katalog i kontener. Parametry
zmieniaj między uruchomieniami, zapisując wyniki w nowym katalogu. Wznowienie
`--resume` wymaga zgodnego kodu, benchmarku, adaptera, wersji środowiska,
tożsamości hosta i parametrów wykonania.

Wyniki rozdzielają `task_seconds` (czas oczekiwania użytkownika), `queue_seconds`
i `active_task_seconds`. Czas wspólnej paczki GPU jest liczony raz w podsumowaniu
przepustowości. Plik `execution-<run-id>.json` zapisuje czas paczek GPU, czas całego
przebiegu i wspólny szczyt pamięci. Szczyty GPU pojedynczych prób mają wartość null,
ponieważ pamięć należy do wspólnej sesji. Metryki wznowienia opisują tylko nową pracę.

Przebiegi równoległe pozostają diagnostyczne, a `proposed_promotion_gate_passed`
pozostaje false. Przed utrwaleniem wariantu porównaj poprawność z wykonaniem
pojedynczym na tym samym hoście i profilu. Grupowanie może zmieniać wyniki
numeryczne oraz odpowiedzi. Czas zadania obciążonego kolejką nie zastępuje pomiaru
latencji modelu bez konkurencji. Testy automatyczne nie uruchamiają płatnych hostów;
każda rzeczywista próba dostawcy wymaga osobnego zlecenia operatora.


Profil `--execution-host remote` startuje od razu z czterema zadaniami i adaptacją.
Nie wykonuje najpierw pełnego benchmarku pojedynczego; krótka rozgrzewka modelu
pozostaje. `--no-adaptive` utrzymuje wybraną liczbę zadań.

- `--max-concurrency 8` ogranicza wzrost; lokalny domyślny sufit adaptacji to 2.
- `--window-trials 16` ustawia okno obserwacji, od 8 do 128 prób.
- `--low-gpu-percent 50`: co najmniej trzy odczyty obciążenia GPU muszą być poniżej
  progu, zanim kod podwoi liczbę aktywnych zadań.
- `--high-memory-percent 80`: wszystkie odczyty zajętości VRAM w tym oknie także
  muszą być poniżej progu. Brak wiarygodnej telemetrii blokuje wzrost.
- Odzyskiwalny CUDA OOM obniża limit 4→2→1. Zapisane wyniki pozostają zachowane;
  powtarzane są tylko niedokończone próby, po zakończeniu wątków i zwolnieniu cache.
  Timeout zadania/narzędzia obniża limit następnego okna; wynik timeoutu pozostaje
  w raporcie. Pozostałe błędy infrastruktury lub danych zatrzymują etap do naprawy.
- Po błędzie kod nie wraca w tym przebiegu do problematycznego poziomu. Nadal
  obowiązują rezerwacja GPU, zachowanie hosta i diagnostyczny charakter wyników.

Decyzje są zapisywane od razu w `concurrency-decisions.jsonl`. Każda próba zapisuje
rzeczywiste `execution_concurrency` i `execution_batch_size`. Metryki wykonania
zawierają odczyty GPU/VRAM i historię decyzji. Wielkość paczki skaluje się wraz
z limitem, zachowując początkową proporcję. Zmiana następuje między oknami, przy
jednym właścicielu GPU i bez przełączania adaptera przez wątki zadań.


### Niezależne etapy treningu i adaptery 80 / 125 / 160

Pełna specyfikacja i polecenia: [REMOTE_TRAINING_MILESTONES.md](../REMOTE_TRAINING_MILESTONES.md).
Plan opisuje osobne akcje; nie uruchamia automatycznie całej sekwencji ani hosta.

1. Utwórz lokalny plan: `python -m venom_core.services.remote_training.cli plan
   --run-id granite-g03-milestones --milestones 80 125 160 --max-seconds 7200
   --output data/training/g03-campaign/plan.json`.
2. Przygotuj jeden pakiet wejściowy z `pack --updates 160 --max-seconds 7200`,
   wgraj go i osobno wykonaj smoke. Dane, profil i tożsamość wejścia pozostają stałe.
3. `start --stage train --until-update 80` kończy pierwszy etap i zwalnia GPU.
4. `attempts --run-id ...` pokazuje rzeczywiste numery prób, osiągnięty krok i
   `result_checkpoint`. Numery zależą także od awarii; nie zakładaj stałych 0002/0003.
5. `collect --attempt NUMER --include-checkpoint --output /.../candidate-80.zip`
   odbiera konkretny wynik. Odbiór, inspect-result, import-result, świeży lokalny
   reload i ocena są niezależnymi akcjami. Każdy kandydat ma własny plik i wyniki.
6. Dopiero osobne `resume --checkpoint ŚCIEŻKA_Z_HISTORII --until-update 125`
   kontynuuje wagi, optymalizator i RNG. Kolejne resume z checkpointu 125 do 160
   jest następną niezależną decyzją. Można pozostać na 80 albo 125 i wykorzystać
   host do czegoś innego. Wspólny limit czasu nie zeruje się przy wznowieniu.

Do akcji zdalnych dodaj przed nazwą akcji dotychczasowe parametry hosta, SSH,
remote-root i remote-python. Żadne polecenie planowania nie wynajmuje hosta.

`status=succeeded` dotyczy celu bieżącej próby, a nie wszystkich kroków planu.
Postęp pokazuje cel etapu oraz pełny budżet wejścia. Zakończone próby otrzymują
trwałe metadane i hashe artefaktów. Awaria następnego kroku nie zmienia poprzednich
wag. Wynik wcześniejszej próby można odebrać także podczas działania kolejnej.
Ocena modelem na tej samej karcie nadal wymaga wolnej rezerwacji GPU.

Wznowienie przerwanego kroku bez nowego celu zachowuje jego dotychczasowy cel;
nie przeskakuje samoczynnie do 160. `retry` zaczyna próbę od nowa, natomiast
`resume` wymaga jawnego, poprawnego checkpointu. Zmiana aktywnego żądania jest
odrzucana. Pełny checkpoint jest przenośnym archiwum, lecz jego użycie do wznowienia
nadal wymaga zgodnego hosta i kwalifikacji. Host i wyniki nie są usuwane automatycznie.

Obsługa wyższej sumy aktualizacji nie zmienia silnika uczenia ani fingerprintu
starszych adapterów: natywne podetapy zachowują limit 128, a flow składa je w całość.

Osobna komenda `python -m scripts.granite_operator.dialogue_cases --material ...
--output ...` przygotowuje zamrożony benchmark z rezerwy G03, bez zmiany materiału
treningowego. Runner po needs_input podaje przygotowaną odpowiedź użytkownika
z pola followups. Ocena sprawdza zarówno potrzebne pytanie, jak i późniejszą
poprawną składnię lub wykonanie; samo needs_input nie zalicza całej rozmowy.
Równoważne cytowanie, kolejność flag i zapis --flaga=wartość są akceptowane.
Zmienione, brakujące, nadmiarowe lub powielone argumenty są odrzucane.
To ocena diagnostyczna; odtworzenie odpowiedzi referencyjnych nie dowodzi jakości modelu.
