# Vast: sprawny start i odzyskiwanie po błędach

Ta procedura dotyczy natywnego Granite: trening 80 → 125 → 160 i ocena na
tej samej maszynie. Nie uruchamia wynajmu ani testu dostawcy automatycznie.
Każda rzeczywista sesja wymaga zlecenia operatora. Diagnostyka zaczyna się od
logu konkretnego kroku i testu celowego. Kod i locki repo są źródłem prawdy.

## 1. Wybór właściwego hosta przed wynajmem


Do listowania hostów bieżącej przygotowanej kampanii używaj istniejącego skryptu:

```bash
source .venv/bin/activate
python scripts/cloud/vast/offers_table.py --training
```

Czyta on wskaźnik `data/training/current-experiment.json` i wymagania kampanii,
więc nie buduj przy każdym uruchomieniu jednorazowego wyszukiwania. Wymagania
kampanii mają pierwszeństwo przed historycznym przykładem GPU poniżej.
Polityka sterownika/CUDA jest w `config/granite_operator_host.json`, a ostatni
odczyt w `.venom_runtime/vast/latest-training-offers.json`. Dostępność wybranej
oferty trzeba odświeżyć przed wynajmem.

- Pełna ocena używa izolowanych kontenerów narzędzi i oracle. W Vast wybierz
  **VM**, oficjalny polecany szablon Ubuntu VM i tryb SSH. Filtr wyszukiwania
  ofert musi zawierać `"vms_enabled": {"eq": true}`. Dostępność samego GPU nie wystarcza.
  Zwykły nieuprzywilejowany kontener może trenować, lecz nie uruchomić sandboxu.
  `vms_enabled` jest filtrem ofert; `vm: true` jest odrębnym polem create.
- Dla Granite 3B punktem odniesienia jest jeden RTX 4090 24 GB, około 64 GB RAM,
  16 efektywnych CPU i **100 GB dysku**. Sprawdź sterownik wymagany przez bieżący
  lock CUDA, szybkość dysku i pobierania modelu. Cena samego GPU nie wyznacza
  kosztu ukończenia zadania. Nie poluzowuj wymagań tylko po to, aby uzyskać listę.
- Pokaż krótką listę z ceną GPU + 100 GB dysku, RAM, CPU, siecią, sterownikiem
  i dostępnością VM. Operator wybiera host. Przed create odśwież wybraną ofertę.
  ID ofert i hashe szablonów z poprzedniej sesji są historycznym dowodem,
  nie domyślnym wyborem następnej sesji.
- Definitywne `400 no_such_ask` oznacza nieaktualną ofertę: przejdź do następnej
  wcześniej autoryzowanej pozycji. Nie powtarzaj create tej samej oferty ze
  zmienianymi wariantami runtype. Po timeout/niejednoznacznym wyniku najpierw
  uzgodnij stan po jednoznacznej etykiecie instancji; nie twórz duplikatu.

Źródła: [VM Vast](https://docs.vast.ai/linux-virtual-machines),
[SSH Vast](https://docs.vast.ai/guides/instances/connect/ssh).
VM mają dłuższy rozruch i mniejszy wybór ofert; uwzględnij to przed wynajmem.

## 2. SSH bez prób na zgadywanych portach

Przed create sprawdź, czy istniejący klucz publiczny jest zarejestrowany w Vast
oraz czy odpowiadający klucz prywatny jest dostępny lokalnie bez interaktywnego
odblokowania. Nie generuj kolejnego klucza, gdy właściwy już istnieje. Nie wysyłaj
klucza prywatnego, tokenów ani `.env.dev` na host.

Rozróżniaj **ID oferty** od **ID utworzonej instancji**. Po create czekaj na
stan instancji i gotowe porty. Dla `ssh_direct` użyj `public_ipaddr` oraz mapowania
`22/tcp → HostPort`; `ssh_host`/`ssh_port` opisują połączenie proxy. Dla proxy
użyj pary zwróconej przez provider. Nazwy flag klienta `ssh_direc` / `ssh_proxy`
nie są zamiennikiem wartości REST `ssh_direct`. Nie składaj endpointu z pól
pochodzących z różnych trybów. Sprawdzaj ograniczoną liczbę prób, z odstępami,
po rzeczywistej zmianie stanu; nie traktuj braku gotowego SSH jako braku klucza.

Zachowaj `BatchMode`, `IdentitiesOnly`, weryfikację klucza hosta i wyłączone
forwardowanie agenta. Dla wielu RPC/SCP użyj dedykowanego ControlMaster i
ControlPersist. Konfiguracja powinna należeć do konkretnej sesji, bez zmiany
ustawień globalnych SSH.

## 3. Bootstrap i zamrożona tożsamość

Przed pobieraniem bibliotek/modelu sprawdź: sterownik i `nvidia-smi`, miejsce,
`setpriv`, działający Docker (`docker info`) oraz możliwość załadowania dokładnego
obrazu benchmarku. Gdy sandbox nie działa w zwykłym kontenerze Vast, wybierz VM;
nie naprawiaj tego przez `chmod 666` na sockecie, globalne zaufanie Git ani
uprzywilejowane uruchamianie kontenerów zadań.

Na hoście ma być czysty checkout dokładnego zatwierdzonego SHA. Użyj
`scripts/remote_training_host/prepare.py`: plan → apply. `uv` i archiwa można
przesłać z lokalnego cache po sprawdzeniu SHA; nie instaluj pełnej aplikacji ani
losowych pakietów do obejścia pojedynczego importu. Generyczny obraz Axolotl
Python 3.12 nie zastępuje natywnego Granite Python 3.14.8 z oboma lockami.

Systemowe `python3` VM może mieć wersję 3.10. Po bootstrapie wszystkie RPC,
pakowanie na hoście, eksporty używające kodu projektu i porównania uruchamiaj
przez zwrócony `remote_python`, zwykle `/workspace/data/remote-training/rpc-python`.
Nie zakładaj dostępności `hashlib.file_digest` w systemowym Pythonie 3.10.

Pakiet wejściowy wiąże dane, profil, tokenizację, locki i kod natywnego workera.
Przy zmianie tego kodu nie naprawiaj hashy ręcznie i nie ponawiaj starego pakietu.
Zbuduj nowy pakiet/run_id, potwierdź identyczność zamierzonych danych i wykonaj
nowe smoke. Zachowaj poprzedni pakiet i logi. Zmiana samego oracle oceny nie
wymaga ponownego treningu; wymaga wersjonowanego dowodu nowej oceny.

Dla Gemmy również sam kontroler `prepare.py` uruchamiaj przez zarządzany Python
3.14.8: `uv run --no-project --python 3.14.8 python scripts/remote_training_host/prepare.py`.
Systemowy Python 3.10 nie obsługuje walidacji hashy snapshotu. Katalog snapshotu
musi kończyć się przypiętym SHA rewizji, a nie aliasem wariantu.

## Kontenery przed oceną GPU

Po przygotowaniu środowiska i przesłaniu zamrożonego benchmarku oraz jego
przypiętego obrazu Docker wykonaj na wybranym hoście:

```bash
cd /workspace/venom
/workspace/data/remote-training/rpc-python -m scripts.remote_training_host.check_sandbox \
  --cases /workspace/benchmarks/dialogue/manifest.json
```

Wymagany wynik: `status=PASS`, `writable=PASS`, `readonly=PASS`. Test sprawdza
utworzenie repozytorium Git w kontenerze, eksport stanu i odczyt przez osobny
kontener tylko do odczytu. Nie ładuje modelu ani GPU, nie zmienia konfiguracji
Git hosta i sprząta własne kontenery. Używa dokładnego obrazu z manifestu.
Po nim odtwórz zaufane referencje benchmarku na tym samym hoście, jeżeli zestaw
je udostępnia; lokalna kwalifikacja manifestu nie sprawdza praw zdalnego hosta.
Dopiero potem uruchom porównania GPU. Test CPU nie zastępuje smoke treningu.

Na VM proces operatora może działać jako root, a kontener jako UID 1000.
Wyeksportowane `.git` należy wtedy do innego użytkownika. `DockerTool` ustawia
`safe.directory=/workspace` wyłącznie wewnątrz kontenera oracle, przez jego
zmienne `GIT_CONFIG_*`. Zachowuje read-only, brak sieci i odebrane capabilities.
Nie stosuj `safe.directory=*` ani `git config --global` na hoście.
Eksport normalizuje prawa katalogów w zweryfikowanym stagingu do `0755`, aby
restrykcyjny `umask 077` hosta nie odciął dostępu kontenerowi oracle. Test
wstępny ustawia jawne prawa wyłącznie własnych sztucznych plików.

## 4. Postęp, odzyskiwanie i zakończenie

- `100%` kroków nie oznacza końca zapisu/walidacji. Czekaj na terminalny sukces.
  Bieżący `status` ma kroki w `progress`; zamknięte `attempts` mają
  `completed_updates` i `result_checkpoint`. Czytaj te pola zamiast zgadywać
  numer próby lub katalog checkpointu.
- Po błędzie czytaj najpierw log workera/stage. Retry jest nową próbą; resume
  wymaga rzeczywistego checkpointu. Nie resetuj budżetu przez ukryty nowy run.
  Każdy etap 80/125/160 odbieraj osobno z pełnym stanem optymalizatora i RNG.
- Ocena zdalna zaczyna od 4 aktywnych zadań i adaptacyjnie przechodzi do 8
  przy zapasie zasobów. Liczba zadań nie jest rozmiarem faktycznego batcha.
  Zachowuj kolejki, aktywny czas, decyzje równoległości i telemetrię GPU.
  Czas porównuj również na tych samych poprawnie rozwiązanych zadaniach;
  szybkie błędne odpowiedzi mogą zaniżać medianę całego zbioru.
- Błąd modelu (np. zła składnia) pozostaje wynikiem. Błąd techniczny oracle
  wymaga poprawki oraz ponownej kontroli stanów i śladów wszystkich dotkniętych
  prób. Zachowaj pierwotne wyniki, nową wersję kodu, hashe i opis korekty.
  Nie zmieniaj oczekiwań benchmarku, aby podnieść wynik.
- Przed destroy sprawdź lokalne sumy pakietów i rozpakowanych plików: 3 adaptery,
  pełne checkpointy, dane wejściowe, rewizję bazy/tokenizer, źródła/locki,
  przypięty obraz, wszystkie raporty, ślady, logi i telemetrię. Poprawny ZIP
  nie jest świeżym lokalnym reloadem GPU ani zgodą na aktywację adaptera.
- Po jawnym zleceniu usunięcia zweryfikuj dokładne ID/etykietę, wykonaj destroy
  raz i potwierdź 404 oraz brak na liście instancji; sprawdź powiązane wolumeny.
  Zapisz potwierdzenie i aktualizuj stan sesji/raport. Historyczny plik połączenia
  nie może ogłaszać usuniętego hosta jako aktywnego. Bez zlecenia host pozostaje.
