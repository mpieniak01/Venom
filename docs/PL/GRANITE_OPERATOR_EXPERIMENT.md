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
