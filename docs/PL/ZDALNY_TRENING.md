# Zdalny trening Granite

REMOTE-TRAINING-01 rozszerza G01 o pełny obieg zadania: pakowanie → upload →
weryfikacja → smoke → trening → status/logi → stop/resume → odbiór → lokalny reload.
Vast dostarcza host; kontrakt SSH działa też na innym przygotowanym Linuksie.
Wynajem, status kosztów i destroy pozostają w istniejącym kontrolerze Vast.
Nie ma automatycznego treningu, wynajmu ani aktywacji po starcie aplikacji/CI.

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
