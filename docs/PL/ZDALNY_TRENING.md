# Zdalny trening Granite

REMOTE-TRAINING-01 rozszerza G01 o pełny obieg zadania: pakowanie → upload →
weryfikacja → smoke → trening → status/logi → stop/resume → odbiór → lokalny reload.
Vast dostarcza host; kontrakt SSH działa też na innym przygotowanym Linuksie.
Wynajem, status kosztów i destroy pozostają w istniejącym kontrolerze Vast.
Nie ma automatycznego treningu, wynajmu ani aktywacji po starcie aplikacji/CI.

## Prosta ścieżka operatora

Stan kodu: pętla REMOTE-TRAINING-01 scalona w PR #578. Przygotowanie natywnego
hosta i bieżący podgląd są w `scripts/remote_training_host/prepare.py` oraz
`remote_training.py watch`. Gotowość kodu nie oznacza kwalifikacji realnego GPU.

1. Dla treningu i oceny na tej samej maszynie wybierz ofertę **VM** i oficjalny
   polecany szablon Ubuntu VM Vast, z dyskiem **100 GB**. Najpierw filtruj
   oferty przez `vms_enabled: {eq: true}`; zwykły kontener treningowy nie zapewnia
   wymaganej izolacji Docker. Zarejestruj używany klucz publiczny przed
   utworzeniem VM, zweryfikuj fingerprint i ustaw alias SSH `gpu-training`.
   [Lista kontroli startu i odzyskiwania](VAST_START_I_ODZYSKIWANIE.md).
2. Na hoście przygotuj czysty checkout tego samego, zrecenzowanego commita co
   lokalnie w `/workspace/venom`. Potrzebny jest istniejący Python 3.14.8 albo
   operatorowo zainstalowany `uv`; skrypt nie pobiera instalatorów przez curl.
3. Na hoście uruchom plan (bez instalacji i pobierania modelu):

```bash
python3 /workspace/venom/scripts/remote_training_host/prepare.py \
  --code-root /workspace/venom --commit <PEŁNY_SHA_COMMITA> --uv /usr/local/bin/uv
```

Po sprawdzeniu planu uruchom tę samą komendę z `--apply`. Wariant `--python
/ścieżka/bin/python3.14` zastępuje `--uv`, gdy interpreter 3.14.8 już istnieje.
Skrypt tworzy osobny `/workspace/training-venv`, instaluje oba locki z hashami,
sprawdza środowisko, pobiera przypiętą rewizję modelu i wykonuje `host-init`.
Nie zmienia venv aplikacji i nie rozpoczyna treningu. `--offline-model` ponownie
wykorzystuje snapshot z potwierdzonym pochodzeniem i hashami przygotowany przez
skrypt; samo przemianowanie katalogu na SHA nie wystarcza. Ewentualne uprawnienia
Hugging Face pozostają w istniejącym środowisku operatora, poza manifestem zadania.

Skrypt zwraca `remote_python`: domyślnie
`/workspace/data/remote-training/rpc-python`. Ten wrapper ustawia właściwy kod
i interpreter dla RPC przez SSH. Nie używaj domyślnego `python3` obrazu do modelu.
Przy innych usługach GPU przekaż `--admission-db` wskazujący ich wspólną bazę.
Wymagane są działający sterownik NVIDIA, `nvidia-smi`, `setpriv` i dostęp SSH.

Lokalnie, w repo z aktywnym venv, można skrócić powtarzane opcje:

```bash
remote_training() {
  python scripts/remote_training.py --host gpu-training \
    --remote-python /workspace/data/remote-training/rpc-python "$@"
}
```

Przed pierwszą oceną GPU wykonaj test CPU kontenerów opisany w
[liście kontroli](VAST_START_I_ODZYSKIWANIE.md#kontenery-przed-oceną-gpu).
Pakowanie danych wykonaj komendą `pack` opisaną niżej. Następnie:

```bash
remote_training upload --bundle data/training/remote-01/input.zip
remote_training start --run-id granite-remote-01 --stage smoke
remote_training watch --run-id granite-remote-01
# Dopiero po rzeczywistym smoke PASS dla tego hosta/danych/kodu:
remote_training start --run-id granite-remote-01 --stage train
remote_training watch --run-id granite-remote-01 --interval 5 --max-seconds 3600
remote_training collect --run-id granite-remote-01 \
  --output data/training/remote-01/result.zip --include-checkpoint
```

`watch` pokazuje numer próby, stan, fazę, wykonane/planowane kroki, procent i loss.
Wariant `--json-lines` daje kolejne rekordy statusu do automatycznego odczytu.
Takie same dane są w jednorazowym `status`, pod kluczem `progress`.
Procent dotyczy **kroków optymalizatora**, nie całej operacji: przy 100% mogą
jeszcze trwać ewaluacja, testy i zapis (`finalizing`). Sukcesem jest dopiero
`status=succeeded`. Przed pierwszym krokiem wyświetlany jest brak pomiaru.
Dla smoke mianownik wynosi 20; wznowienie zachowuje globalny numer kroku.
Każda próba czyta własny log, więc retry nie pokazuje postępu poprzedniej próby.
Odczyt jest ograniczony do końcówki logu i nie ładuje modelu.

Ctrl+C, limit czasu podglądu i utrata SSH kończą tylko podgląd. Przy przejściowym
błędzie połączenia viewer ponawia odczyt; po trzech błędach można ponownie
wywołać `watch`. Zatrzymanie treningu wymaga osobnego `stop`.
Zakończenie `watch` samo w sobie nie potwierdza udanego treningu.

Po odbiorze wykonaj opisane niżej `inspect-result` i `import-result --verify-local
--host-root <LOKALNA_KONFIGURACJA_HOSTA>`. Lokalny reload wymaga lokalnego
środowiska modelowego/GPU, tego samego snapshotu i rzeczywistego admission ledger.
Nie wystarcza samo poprawne rozpakowanie ZIP ani zdalny PASS.

## Odbiór na rzeczywistym hoście — osobne zlecenie

Po jawnym zleceniu próby zapisz run_id, SHA kodu, wersje/host/GPU, ofertę i koszt.
Wykonaj smoke, uruchom krótki trening, odłącz SSH i wróć przez `status/watch`,
sprawdź kontrolowany stop oraz resume z istniejącego checkpointu. Pobierz wynik,
zweryfikuj hashe i kompletność, a następnie przeprowadź świeży lokalny reload.
Zachowaj logi, metryki i lokalne potwierdzenie w ignorowanym katalogu sesji.
Jakość adaptera oceń osobno na zamrożonym zbiorze porównawczym.
Dopiero po potwierdzonym odbiorze można osobno zlecić zakończenie najmu.

Testy offline nie wykonują tych kroków na realnym GPU. Automatyczne postawienie
stosu również nie stanowi smoke PASS. Ta ścieżka dotyczy adapterów Granite;
pełny trening wszystkich wag nie jest częścią natywnego REMOTE-TRAINING-01.

## Środowisko i dane

Granite używa natywnego encodera i workera G01 oraz locka Linux amd64/Python
3.14.8. Ogólny obraz Axolotl/Python 3.12 z scripts/vast_training nie jest tym
samym środowiskiem. Kontroler SSH może mieć inny interpreter; model uruchamiany
jest jawnie skonfigurowanym Pythonem komponentu. Instaluj wspólnie hash-lock
treningu i requirements-remote-training-control.txt w osobnym venv hosta.
Preflight sprawdza rzeczywiste wersje/importy/pip check, źródła i natywne tokeny.
Dysk pozostaje 100 GB; niedobór miejsca kończy preflight błędem.

Model: ibm-granite/granite-4.2-3b, rewizja
4e9c275e232f10211ec88644d106a1f6a1b60e06. Snapshot wag musi już być na hoście;
RPC nie przenosi wag ani sekretów. Brak cichego fallbacku CPU, text/completion
lub starego spłaszczania instruction/input/output. Zachowane są messages/tools,
natywny szablon, końce tur oraz maski asystenta; lokalne i zdalne input_ids/labels
muszą być identyczne. Do paczki wchodzą tylko dopuszczone train/validation obu
źródeł, manifest pochodzenia/licencji i profil. Bez testów końcowych, surowych
chatów, Git i historycznych logów.

## Użycie operatora

Pełne polecenia host-init, pack, upload, start, status, logs, stop, resume, collect,
inspect-result i import-result: [instrukcja wykonawcza](../REMOTE_TRAINING.md).
CLI: python scripts/remote_training.py --help. Ścieżki sesji przechowuj w
ignorowanym data/training/. Przygotowanie paczki nie wysyła danych.

Poświadczenia i weryfikacja klucza hosta pozostają w istniejącym SSH config.
Konfiguracja hosta wskazuje zaufany checkout, interpreter, snapshot i rzeczywisty
wspólny admission ledger. Manifest nie może ustawić polecenia wykonywanego przez
workera. Transfer odbywa się porcjami, z hashem, ponowieniem i atomowym odbiorem.
Idempotentny start i blokady katalogu/GPU zapobiegają drugiemu zadaniu po utracie SSH.
Stan procesu obejmuje identyfikator uruchomienia, nie sam PID. Limit czasu jest
sumowany dla kolejnych prób tego samego run_id; stop i timeout zachowują dowody.

Smoke 32 train + 8 validation / 16+4 kroki musi faktycznie przejść przed treningiem.
PASS jest związany z hostem/bootem/GPU, kodem, środowiskiem, danymi i profilem.
Wznowienie smoke kontynuuje ukończony checkpoint po 16 krokach, bez resetu do bazy.
Po błędzie zachowane są logi i dostępne artefakty. Brak checkpointu do wznowienia
jest błędem, nie powodem do ponownego treningu od zera pod tą samą nazwą.

## Wyniki i bezpieczne zakończenie

Pakiet wynikowy zawiera adapter safetensors/config, tożsamość bazy i tokenizera,
profil, manifest danych, środowisko, kwalifikację, metryki i logi. Pełny stan
resume odbierany jest opcjonalnie. Raport rozróżnia kompletność, stan zadania,
niezmierzony koszt i jakość modelu. Nieudane próby można pobrać jako niepełne
dowody; brak adaptera nie jest zaliczeniem.

Domyślny import zatrzymuje pliki w kwarantannie pending_local_reload.
Dopiero jawne --verify-local --host-root KONFIG wywołuje nowy proces GPU na
lokalnym, offline hoście i porównuje rzeczywisty efekt adaptera. Import nie zmienia
obcego training-state.pt ani nie nadaje mu prawa lokalnego resume. Opcjonalne
--academy-models KATALOG zapisuje kanoniczne metadane Academy po tym sprawdzeniu;
bez automatycznej aktywacji i podpisu chat. Przed i po reloadzie sprawdzane są hashe.

Przed osobno zleconym destroy potwierdź kompletny lokalny odbiór i zachowaj kopię
poza hostem. Eksport metadanych Vast nie jest backupem modelu; stop może zostawić
płatny dysk. Odczyt statusu najmu i kosztów pozostaje osobnym poleceniem kontrolera.

## Walidacja

Testy automatyczne są offline: atrapowy transport, nieszkodliwe subprocessy,
dublery modelu, uszkodzone transfery i tożsamości, utrata SSH, stop/resume,
blokady, odbiór błędów oraz rejestracja metadanych bez aktywacji. Nie kwalifikują
GPU. Rzeczywisty krótki test z kosztem, rozłączeniem SSH, zapisem/odczytem,
wznowieniem i odbiorem wymaga osobnego zlecenia. Pełny trening i ocena na nowym
holdoucie następują później. Poza zakresem: trening od losowych wag, wielowęzłowy,
automatyczny wynajem i przebudowa UI Academy.

Odbiór zachowuje osobno stan workera i końcowy stan/kod wyjścia supervisora.
Kompletność wymaga sukcesu obu. Niepełna paczka zawiera ograniczony log
koordynatora oraz, z --include-checkpoint, ostatni zapisany checkpoint etapu
z oryginalnym receipt. CLI pokazuje też logi modelu. Archiwa i pliki transferu
mają tryb 0600 niezależnie od umask. Kwarantanna ma układ run_id/archive_sha256:
kolejne próby zachowują wcześniejsze dowody, a identyczny import używa tego samego
katalogu. Lokalny reload sprawdza hash manifestu danych i skonfigurowany interpreter
workera przed zajęciem GPU.

Po błędzie przed powstaniem checkpointu użyj jawnego retry, np.
`python scripts/remote_training.py --host gpu-training retry --run-id granite-remote-01 --from-attempt 1`.
Numer pochodzi z statusu nieudanej próby. Powtórzenie tego samego żądania jest
idempotentne; historia prób i zużyty budżet pozostają zachowane.
Offset logów jest logiczny i rośnie mimo obcinania bufora. Odpowiedź zawiera
base_offset oraz truncated/reset, gdy starsze bajty przepadły albo trzeba
odtworzyć kursor po przerwanym zapisie.

Ścieżki operatora są sprawdzane przed operacjami plikowymi. Obsługiwane miejsca
to bieżący workspace, katalog domowy/tymczasowy oraz /srv, /opt, /models, /mnt
i /workspace. Odrzucane są przejścia przez .., prywatne katalogi poświadczeń
oraz symlinki w ścieżce. Interpreter zachowuje ścieżkę virtualenv; alias
snapshotu musi wskazywać do dopuszczonego miejsca. Lokalny worker wyznacza
receipt.json obok własnego żądania i odrzuca podmienioną ścieżkę wyniku.

## Ocena oczekiwanej zmiany zachowania

Po zweryfikowanym odbiorze można osobno uruchomić
`scripts.granite_operator.remote_comparison`: zdalne GPU wykonuje inferencję,
a lokalny Docker izoluje narzędzia i ocenia rzeczywisty wynik. Parametry,
postęp i ograniczenia interpretacji opisuje
[instrukcja porównania](GRANITE_OPERATOR_EXPERIMENT.md#porównanie-adaptera-trenowanego-na-zdalnym-hoście).


### Kolejność próbek i przygotowanie kolejnej generacji danych

Profil może jawnie włączyć `"row_order": "family_epoch_v1"`. W każdej epoce
każda próbka występuje raz; rodziny są przeplatane proporcjonalnie do ich
liczebności, a kolejność wewnątrz rodzin zmienia się z numerem epoki i seedem.
Checkpoint zapisuje politykę, seed, liczbę wykorzystanych próbek i hash kolejności
rodzin. Wznowienie odrzuca inne metadane. Osobny generator kolejności nie zużywa
RNG modelu. Profile bez tego pola zachowują dotychczasowy układ i tożsamość.

Przy poszerzaniu danych zachowaj poprzednią generację i jej wyniki. Nowe rozmowy
muszą mieć sprawdzone obserwacje narzędzi, zakres zmian i poprawną odpowiedź
końcową. Warianty językowe i rozmowy z doprecyzowaniem należą do tego samego
podziału co ich scenariusz. Sprawdź duplikaty, przecieki, maski asystenta, limit
kontekstu oraz długość pojedynczej generacji. Zarezerwowane warianty syntetyczne
służą diagnostyce; wspólna rodzina szablonów ogranicza niezależność takiej oceny.
Surowe dane, prywatne receptury i dowody wykonania pozostają w ignorowanym
`data/training/`.

Budżet porównuj także przez liczbę epok i tokenów docelowych. Dla 640 próbek
i akumulacji 4 jedna epoka oznacza 160 aktualizacji. Plan 160 → 210 → 250 jest
planem dla koordynatora `remote_training`, który dzieli pracę na osobne procesy
z zachowaniem limitu 128 aktualizacji na proces. Każdy punkt można osobno odebrać,
sprawdzić i ocenić przed decyzją o kontynuacji. Samo przygotowanie planu nie
uruchamia hosta ani treningu. Nowe dane, profil i kod wymagają nowej paczki
wejściowej oraz nowego smoke na docelowym GPU.


### Jeden wybrany adapter i porównanie QLoRA / LoRA

`data/training/selected-adapter.json` jest pojedynczym wyborem kandydata do
zastosowania. Dla G03 wybrano checkpoint 125; 80 i 160 pozostają archiwum,
bez nowych wpisów w Academy. Wybór na CPU nie oznacza lokalnego reloadu ani
aktywacji czatu. Import nadal wymaga rzeczywistego sprawdzenia na GPU.

Przykład przygotowania (wszystkie operacje są lokalne i na CPU):

```bash
source .venv/bin/activate
python scripts/granite_experiments.py select \
  --archive /path/candidate-125.zip --adapter-root /path/candidate-125 \
  --sha256 EXPECTED_ARCHIVE_SHA256 --step 125 \
  --output data/training/selected-adapter.json
python scripts/granite_experiments.py prepare \
  --source data/training/granite-g04-material-20261102 \
  --manifest data/training/granite-g04-material-20261102/pilot-manifest.json \
  --snapshot /path/to/4e9c275e232f10211ec88644d106a1f6a1b60e06 \
  --selection data/training/selected-adapter.json \
  --run-prefix granite-g04-ab-20261102 \
  --output data/training/granite-g04-ab-20261102
```

Profile `config/granite_operator_qlora.json` i `config/granite_operator_lora.json`
różnią się wyłącznie NF4/BF16. Zachowują rank 16, q/k/v/o, alpha 32, dropout 0,05,
LR 0,0001, akumulację 4, seed 17, kontekst 2048 i family_epoch_v1. Każdy trening
zaczyna od tej samej oryginalnej bazy z nowym adapterem, bez wznowienia 125.
Przy 640 rozmowach 250 aktualizacji oznacza 1,5625 epoki, tyle samo przejść przez
zbiór co 125 aktualizacji G03. Zachowujemy po jednym końcowym kandydacie metody.
Checkpointy optymalizatora pozostają do odzyskania po awarii, bez publikowania
każdego pośredniego adaptera jako osobnego modelu.

Każda metoda ma osobne `input.zip`, `plan.json`, `operator-commands.json` i `READY.json`.
`suite.json` powstaje po sprawdzeniu obu metod. Jeżeli przygotowanie drugiej się
nie uda, pierwsza nadal jest gotowa; ponowne wywołanie przyjmuje niezmienione
pliki. Treningi uruchamiamy kolejno na tym samym hoście VM, planując 24 GB VRAM,
32 GB RAM i 100 GB dysku. Każdy musi przejść własny smoke. Skrypt nie wynajmuje
hosta, nie uruchamia treningu i nie usuwa zasobów.

Po odebraniu i sprawdzeniu wyniku wygeneruj polecenia oceny:

```bash
python scripts/granite_experiments.py evaluation-commands \
  --result /path/verified-result --host /path/configured-host \
  --cases /path/frozen-benchmark/manifest.json \
  --output /path/evaluation --expected-step 250 --precision nf4
```

Oba adaptery najpierw oceniamy przy tej samej precyzji wdrożeniowej NF4. BF16
można zmierzyć osobno, z innym katalogiem wyników. Profil i hashe historycznego
artefaktu pozostają bez zmian. Zdalna ocena zaczyna od 4 sesji, adaptacyjnie do 8;
lokalna od 1. Nie publikujemy i nie aktywujemy automatycznie wyników eksperymentu.

Dla G03/125 przygotowany kontekst weryfikatora jest w
`data/training/granite-selected-125-20261102/application-plan.json`.
Używa niezmienionego oryginalnego źródła i istniejącego venv, ponieważ bieżący
sampler zmienił hash kodu treningowego. Nie przepisuj fingerprintów. Zastosuj
procedurę offline i wspólny rejestr GPU przed rzeczywistym reloadem. Rejestracja
w Academy oraz aktywacja w obsługiwanym runtime są oddzielnymi krokami.
