# Backlog

## REMOTE-TRAINING-01 — kompletna pętla treningu na zdalnym hoście

**Status:** zaplanowane, osobny PR po lokalnym eksperymencie Granite.
**Proponowany tytuł PR:** `feat(training): complete remote training lifecycle and artifact collection`

### Cel

Operator przygotowuje lokalne zlecenie, wysyła je na host, obserwuje i wznawia
trening, pobiera adapter oraz statystyki, a następnie weryfikuje wynik lokalnie.
Cały obieg ma zachować stan po utracie SSH i umożliwić powtarzanie operacji bez
uruchamiania drugiego treningu ani nadpisania wyników. VAST jest pierwszym
dostawcą hosta; kontrakt wykonania i transferu obsługuje również inne hosty SSH.

Punkty wyjścia: [eksperyment Granite](GRANITE_OPERATOR_EXPERIMENT.md),
[zestaw VAST](../../scripts/vast_training/README.md),
lokalny loader i maski Granite oraz istniejące metadane adapterów Academy.

### Zakres implementacji

- [ ] **Manifest zlecenia i identyfikacja sesji.** Unikalny `run_id`, model
  i przypięta rewizja, tokenizer/szablon, profil, train/validation, wersja kodu,
  zależności, limity oraz SHA-256. Oddzielić przenośną tożsamość artefaktu od
  poświadczenia środowiska i GPU konkretnego hosta.
- [ ] **Pakowanie i transfer wejścia.** Jawna lista dozwolonych plików,
  licencje/pochodzenie, kontrola ścieżek, manifest, transfer z ponowieniem,
  zdalne sprawdzenie hashy i atomowe oznaczenie gotowości.
  Nie wysyłać całego katalogu eksperymentu: wykluczyć surowe chaty, archiwa Git,
  logi poprzednich sesji i zamrożone testy porównawcze.
- [ ] **Przenośny backend SSH.** Operacje prepare/upload/start/status/logs/stop/
  resume/collect, identyfikacja procesów i trwały rejestr stanów.
  Provisioning VAST oddzielić od sterowania zadaniem na gotowym hoście.
  Zachować weryfikację host key i poświadczenia poza manifestami/logami.
- [ ] **Środowisko i worker Granite.** Zakwalifikować przypięty zestaw zależności
  zdalnego obrazu; rozstrzygnąć różnicę Python lokalny/chmurowy.
  Zachować pełne `tools + messages`, natywny szablon, selektywne maskowanie
  asystenta i końce tur. Wybrać i zintegrować jeden silnik dla tego kontraktu;
  nie zastępować go obecnym ogólnym `text/completion`.
- [ ] **Kwalifikacja przed pełnym treningiem.** Intake danych, porównanie
  `input_ids/labels` z lokalnym encoderem, smoke na minimalnej próbce,
  checkpoint, świeży reload i resume. Nowy host/dane/profil/środowisko wymagają
  nowej kwalifikacji; nie przenosić starego PASS jako zgody na pełny trening.
- [ ] **Trwałe wykonanie.** Praca po rozłączeniu SSH, heartbeat i kod zakończenia,
  kontrolowane zatrzymanie, wznowienie z właściwego checkpointu, blokada GPU
  i katalogu wyjściowego. Ponowienie startu nie tworzy drugiej sesji.
  Oddzielne katalogi oraz logi preflight dla każdego `run_id`.
- [ ] **Metryki i raport.** Ujednolicony JSON/JSONL: train/eval loss na właściwych
  maskach, step/epoch, learning rate, gradient norm, nadzorowane tokeny i tokeny/s,
  czasy ładowania/treningu/ewaluacji, pamięć GPU, stan i błędy.
  Zapisywać konfigurację, środowisko oraz pochodzenie i zakres danych.
  Rozdzielić zmierzony koszt od oszacowania; podać jego źródło i okres.
- [ ] **Pakiet wynikowy i odbiór.** Adapter safetensors, adapter_config,
  identyfikacja tokenizera/bazy, profil, manifest danych, konfiguracja,
  logi, metryki, wersje i wynik kwalifikacji. Pełny checkpoint resume jako
  osobny opcjonalny artefakt. Pobieranie z ponowieniem, SHA-256, atomowe
  zakończenie oraz raport kompletności także dla sesji nieudanych.
- [ ] **Import lokalny.** Kwarantanna, bezpieczne rozpakowanie, kontrola
  kompletności/hashy i zgodności bazy, rewizji, tokenizera oraz konfiguracji
  adaptera. Osobny świeży reload na runtime docelowym i rejestracja metadanych
  w Academy. Nie osłabiać kontroli lokalnego resume; nie aktywować adaptera
  automatycznie po pobraniu.
- [ ] **Zakończenie pracy hosta.** Jawne limity czasu/kosztu i kontrola statusu
  najmu. Potwierdzenie kompletnego, lokalnie zweryfikowanego odbioru przed
  usunięciem instancji. Nie utożsamiać stop z zakończeniem kosztów dysku.
  Wynajem i destroy pozostają oddzielnymi, jawnie autoryzowanymi operacjami.
- [ ] **Dokumentacja i higiena.** Instrukcja pełnego obiegu i odzyskiwania po
  awarii. Zlecenia, dane, logi, metryki i checkpointy wyłącznie w ignorowanych
  katalogach. Do repo trafiają kod, schematy, syntetyczne testy i instrukcje.

### Kryteria odbioru

1. Offline przechodzi obieg: pack → upload → verify → start → status/logs →
   stop → resume → collect → local verify, na atrapie transportu lub izolowanym
   środowisku testowym, bez wywołań płatnego dostawcy.
2. Testy wykrywają uszkodzony/niepełny transfer, niezgodny model i tokenizer,
   niedozwolone ścieżki, zmianę danych, błędny proces i brak metryk.
   Rozłączenie SSH i ponowienie operacji nie tracą stanu ani nie dublują zadania.
3. Tokeny i maski Granite są zgodne z lokalnym kontraktem, w tym dla błędnego
   prefiksu naprawczego i poprawnej komendy wykrywającej błąd.
4. Błąd treningu pozostawia rzeczywisty status, logi i możliwość odbioru
   dostępnych artefaktów; brak adaptera nie jest oznaczany jako sukces.
5. Odebrany adapter ma zweryfikowany manifest i pochodzenie; import nie zmienia
   aktywnego modelu. Raport rozróżnia poprawność procesu i skuteczność operatora.
6. Testy są zarejestrowane w katalogu/grupach repo, a wymagane kontrole jakości
   i `make pr-fast` przechodzą.

### Osobna kwalifikacja na rzeczywistym hoście

Po wyraźnym zleceniu operatora: jeden krótki smoke z zapisem, reload/resume,
rozłączeniem SSH i odbiorem adaptera oraz metryk. Zachować dowody i koszt sesji.
Ten test nie jest automatycznym elementem CI ani skutkiem zapisu tego backlogu.

Pełny trening i ocena na świeżym holdoucie następują dopiero po kwalifikacji
i osobnym zleceniu. Publikacja danych, wdrożenie adaptera, trening wielowęzłowy
oraz przebudowa UI Academy nie są zakresem tego PR.
