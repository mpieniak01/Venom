# Eksperymenty Omni w Academy

Eksperyment porównuje odpowiedzi przypiętego modelu `LiquidAI/LFM3-Omni-2B` i adaptera LoRA na tym samym polskim zestawie dev. Profil operatora wiąże snapshot, środowisko i hashe danych. Academy oraz CLI odczytują wspólny stan przebiegu.

## Przygotowanie profilu

Backend działa w lokalnym Linuxie z NVIDIA CUDA i BF16. Launcher montuje dane i snapshot tylko do odczytu w izolowanej przestrzeni nazw. Przygotuj osobne środowisko treningowe oraz pełny snapshot zgodny z przypiętym manifestem. Próba techniczna korzystała z Python 3.14.8, PyTorch 2.15.0, Transformers 5.22.2, PEFT 0.21.2 i Accelerate 1.15.0. W profilu wskaż rzeczywisty katalog venv. [Manifest snapshotu](../../scripts/llm/omni_native_snapshot.json)

Panel **Academy → Trening → Eksperymenty** używa `<ACADEMY_TRAINING_DIR>/experiments`. Ustaw `ENABLE_ACADEMY=1` w konfiguracji lokalnego backendu. Interfejs eksperymentów przyjmuje żądania przez localhost. W CLI ustaw `--root` na ten sam katalog, jeśli konfiguracja lokalna wybiera inną ścieżkę niż domyślna.

Utwórz plik `profiles/polski-czat.json` w katalogu eksperymentów. Zastąp ścieżki i symbole hashy poniżej danymi lokalnymi. Ścieżki względne liczą się od katalogu eksperymentów. Oblicz hashe plików train i dev przez `sha256sum`.

```json
{
  "schema_version": 1,
  "label": "Polski czat Omni",
  "model": "LiquidAI/LFM3-Omni-2B",
  "dataset": "Polskie dialogi v1",
  "snapshot": "/srv/models/lfm3-omni-pinned",
  "training_venv": "/srv/venv/omni-training",
  "train": "datasets/chat-v1/train.jsonl",
  "dev": "datasets/chat-v1/dev.jsonl",
  "train_sha256": "SHA256_PLIKU_TRAIN",
  "dev_sha256": "SHA256_PLIKU_DEV",
  "recipe": {
    "steps": 8,
    "save_every": 2,
    "rank": 4,
    "alpha": 8,
    "learning_rate": 0.0002,
    "target_modules": ["q_proj", "v_proj"],
    "max_tokens": 1024
  },
  "max_seconds": 1800,
  "min_free_bytes": 1073741824
}
```

`max_seconds` ogranicza czas próby od kolejki do zakończenia generacji i zapisu dowodów. `min_free_bytes` określa wymagane wolne miejsce. W WSL można dodać `backing_volume` z zamontowaną ścieżką dysku Windows zawierającego VHDX. Parametr `max_supervised_tokens` ogranicza konserwatywną górną granicę ekspozycji na tokeny nadzoru. Zapisz checkpoint przed wyczerpaniem budżetu, wybierając odpowiednie `save_every`. [Pola profilu](../../venom_core/services/training_experiments/profiles.py) · [Parametry receptury](../../scripts/academy/omni_pl_chat_recipe.py)

Plik **train** zawiera rekordy `split: "train"` oraz `language: "pl"`. Każdy ma `record_id`, `group_id`, uporządkowane `messages` zakończone turą asystenta i `supervision` z indeksami zatwierdzonych tur asystenta, liczonymi od zera. Uzupełnij `quality_status: "accepted"`, `source_repo`, `source_revision`, `source_record_id`, `license` oraz `review_note`. [Walidacja i maskowanie danych](../../scripts/academy/omni_pl_chat_data.py)

Plik **dev** zawiera rekordy `split: "dev"` z `record_id`, `group_id`, `language: "pl"`, `task`, `messages` zakończonymi turą użytkownika oraz `criteria`. Kryterium ma `id`, `kind` równe `content` albo `format` i `description`. Każdy przypadek potrzebuje kryterium treści. Rozdziel rekordy i grupy między train i dev. Zachowaj zbiór końcowy do niezależnej oceny. [Walidacja dev](../../scripts/academy/omni_pl_chat_evaluate.py)

## Uruchomienie i wznowienie

Academy wymaga wspólnej dzierżawy GPU. Włącz ustawienie `RUNTIME_ADMISSION_ENABLED=true` przed startem hosta. CLI i API muszą używać tego samego pliku środowiska oraz tej samej ścieżki `MEMORY_ROOT`. Przy pracy z osobnego checkoutu ustaw `ENV_FILE` i bezwzględną ścieżkę do wspólnego katalogu pamięci.

Przed uruchomieniem modelu Academy weryfikuje zwolnienie lokalnych modeli. Przy działającym Full lub Studio zwalnianie obsługuje ich backend, który musi zawierać tę samą obsługę dzierżawy. Błąd zwolnienia przerywa zadanie przed ładowaniem wag. Dzierżawa pozostaje aktywna do wyjścia procesów treningu i oceny. Zapis zwolnienia i pomiar końcowy znajdują się w plikach `gpu-release-*.json` i `gpu-after-*.json` katalogu przebiegu.

Z katalogu repozytorium uruchom poniższe polecenia. Dopasuj ścieżkę `experiment_root` do konfiguracji Academy.

```bash
source .venv/bin/activate
experiment_root="$PWD/data/training/experiments"
python -m scripts.academy.experiments --root "$experiment_root" profiles
python -m scripts.academy.experiments --root "$experiment_root" validate polski-czat
python -m scripts.academy.experiments --root "$experiment_root" run polski-czat polski-czat-01
python -m scripts.academy.experiments --root "$experiment_root" status polski-czat-01
python -m scripts.academy.experiments --root "$experiment_root" logs polski-czat-01
```

`validate` sprawdza profil, recepturę, hashe i podział plików. Przy starcie izolowany preflight sprawdza pełny snapshot i maski tekstowe, a trening sprawdza zgodność z procesorem modelu. Możesz dodać `--recipe ścieżka.json` do `validate` i `run`, żeby nadpisać wybrane parametry. Użyj nowego `run_id` przy zmianie receptury. Powtórne wywołanie z identycznym manifestem zwraca istniejący przebieg.

`stop` prosi o zatrzymanie procesu. `resume` korzysta z kompletnego zweryfikowanego checkpointu i tego samego profilu. `evaluate` ponawia samą generację po nieudanej lub przerwanej próbie, jeśli istnieje zweryfikowany adapter. Stan udostępnia aktualnie dostępne akcje. Artefakty i logi są w `runs/<run_id>/`, a indeks SQLite w `runs.sqlite3`. [CLI](../../scripts/academy/experiments.py)

## Ręczna ocena

Bez kalibracji przebieg czeka w `awaiting_review`. Polecenie `review` zwraca przypadki i anonimowe odpowiedzi. Możesz zapisać ten pakiet do lokalnego pliku, ocenić każdą odpowiedź według kryteriów i przesłać oceny w Academy albo przez CLI.

```bash
python -m scripts.academy.experiments --root "$experiment_root" review polski-czat-01 > review.json
python -m scripts.academy.experiments --root "$experiment_root" judgments polski-czat-01 judgments.jsonl
python -m scripts.academy.experiments --root "$experiment_root" report polski-czat-01
```

W `judgments.jsonl` zapisz jeden obiekt na każdą parę rekordu i etykiety z pakietu. Wypełnij wszystkie identyfikatory kryteriów z danego przypadku wartościami logicznymi. Poniższy wiersz pokazuje jedną z wymaganych ocen.

```json
{"record_id":"dev-01","label":"A","criteria":{"treść":true,"format":false},"polish_ok":true,"natural_ok":true,"critical_error":false,"reason":"Odpowiedź zachowuje wymagane fakty, ale pomija format."}
```

Po walidacji kompletu ocen kontroler zapisuje wynik i hashe dowodów. Raport pokazuje osobno zgodność treści, użyteczność, format, błędy krytyczne i nieukończone generacje. Stan `succeeded` oznacza ukończoną ocenę. Porównaj wyniki bazy i adaptera przed podjęciem decyzji o jego użyciu.

## Ocena automatyczna exact-v1

Dla przypadków o określonych odpowiedziach możesz przygotować `profiles/polski-czat.calibration.json` i dodać jego SHA-256 jako `calibration_sha256` do profilu. Plik kalibracji zawiera:

- `schema_version` równy `1`, `judge` równy `exact-v1`, `dev_sha256` równy hashowi dev z profilu oraz niepuste `reviewer`.
- Obiekt `cases` ze wszystkimi identyfikatorami rekordów dev.
- Dla każdego rekordu obiekt `outputs` mapujący zatwierdzone teksty odpowiedzi na kompletne oceny i ocenę `fallback` dla pozostałych tekstów. Kluczem jest dokładny tekst po odcięciu zewnętrznych białych znaków. Każda ocena zawiera pola `criteria`, `polish_ok`, `natural_ok`, `critical_error` i `reason`.

Zweryfikuj mapowania i `fallback` na przykładach ocenionych przez operatora przed dodaniem hasha do profilu. Dla zadań wymagających oceny znaczenia otwartej wypowiedzi użyj ślepej oceny ręcznej. Recepturę i zestaw kryteriów porównuj w ramach tej samej wersji danych. [Agregacja ocen](../../scripts/academy/omni_pl_chat_scoring.py) · [Wykonanie kalibracji](../../venom_core/services/training_experiments/evidence.py)

Import zachowanego raportu pilota: `import-results historyczny-01 sciezka/do/scores.json`. Zachowane metryki można przeglądać w historii. Stan artefaktu wskazuje brak dostępnych wag i wznowienia.


## Kampania na stałej liście wariantów

W Academy otwórz **Trening → Kampania**. Wybierz profil i przygotuj warianty receptury, limity czasu, aktualizacji, tokenów, ponowień i miejsca. Podgląd planu zawiera listę prób. Start wiąże ją z zapisanym hashem planu.

Kampania wykonuje po jednej próbie. W trybie ręcznym otwórz oczekującą próbę i wczytaj anonimowe oceny. Po ich przyjęciu kampania przechodzi do kolejnego wariantu. Tryb automatyczny używa profilu z hashowaną kalibracją. Ranking porównuje zmiany użyteczności i błędów krytycznych względem bazy na tym samym dev.

Polityka `discard_rejected` obejmuje zarządzane pliki checkpointów odrzuconych, zakończonych prób. Zachowuje raporty i wybrany adapter. Panel udostępnia też plan retencji z rozmiarem plików i jego hash. Brak wybranego artefaktu wstrzymuje sprzątanie alternatyw. Ustaw `keep_all`, jeśli potrzebujesz zachować wagi do analizy.

CLI korzysta z tego samego katalogu. Podaj plik z kontraktem CampaignSpec do `plan`, a odczytany `plan.plan_sha256` do `start`.

```bash
python -m scripts.academy.campaigns --root "$experiment_root" plan kampania.json
python -m scripts.academy.campaigns --root "$experiment_root" start polski-czat PLAN_SHA256
python -m scripts.academy.campaigns --root "$experiment_root" status polski-czat
python -m scripts.academy.campaigns --root "$experiment_root" report polski-czat
```

`stop` zatrzymuje kampanię. `resume` podejmuje ją z zachowanym stanem oraz pozostałym budżetem. [Kontrakt kampanii](../../venom_core/services/training_experiments/campaign_schema.py) · [CLI kampanii](../../scripts/academy/campaigns.py)


## Ocena kilku checkpointów z jednej próby

W kampanii na stałej liście wypełnij **Kroki oceny checkpointów** albo dodaj do manifestu pole, np. `"checkpoint_steps": [7, 14, 21, 28]`. Podaj od jednego do czterech różnych, rosnących kroków. Każdy musi odpowiadać zapisowi wszystkich receptur w planie. Ostatni krok receptury jest zapisywany także przy niepełnym interwale `save_every`. Zapisany plan wiąże listę kroków i protokół oceny z sumą kontrolną.

Wykonawca trenuje raz na wariant. Następnie na wspólnym roboczym dev generuje odpowiedzi bazy raz i po jednej odpowiedzi z każdego checkpointu. Przerwanie oceny pozwala wznowić brakujące generacje z zachowaniem zweryfikowanych odpowiedzi. W ręcznej ocenie Academy otwiera kolejno anonimowe pakiety A/B. Zachowaj jednakowy werdykt dla tej samej odpowiedzi bazy.

Pobierz pakiet i zapisz jego `checkpoint_step` razem z kompletem ocen w pliku JSON. W panelu wybierz plik dla bieżącego kroku albo użyj polecenia `judgments RUN_ID judgments.json` z CLI eksperymentów.

```json
{
  "checkpoint_step": 7,
  "judgments": [
    {"record_id":"dev-01","label":"A","criteria":{"treść":true,"format":false},"polish_ok":true,"natural_ok":true,"critical_error":false,"reason":"Zachowuje fakty, pomija format."}
  ]
}
```

W szczegółach kampanii przy ocenionym kroku wybierz **Pokaż wynik kroku**. Sekcja **Wnioski i następna próba** od razu wyświetla ocenę i przelicza porównanie po zmianie kandydata lub odniesienia. Szczegółowa analiza kroków jest dostępna po zamknięciu ślepej oceny przebiegu.

Jeśli kampanii została już tylko ślepa ocena ostatniej próby i jej przebieg zwolnił zasoby, możesz uruchomić następną kampanię z tego samego katalogu. Kampania z kolejnymi próbami nadal rezerwuje kolejkę do czasu zakończenia lub zatrzymania.

Raport pokazuje wyniki osobno dla każdej pary przebieg i krok. Wybór wymaga spełnienia progów kampanii oraz jej opcjonalnych kryteriów względem referencji i chronionych przypadków. Wynik może wskazać wcześniejszy checkpoint albo brak kandydata. Status `succeeded` oznacza zakończenie procedury. Dla eksperymentów z otwartymi polskimi odpowiedziami jakość potwierdź ślepą oceną według właściwej rubryki oraz osobnym testem końcowym.

Przy `discard_rejected` retencja chroni cały przebieg, w którym znajduje się wybrany checkpoint, i sprawdza dostępność jego wag przed usunięciem plików odrzuconych prób. Brak kandydata zachowuje pliki do analizy.


## Kampania Optuna

Optuna jest opcjonalnym narzędziem uruchamianym przez kontroler kampanii. Utwórz środowisko CPU z Pythonem 3.12 i zainstaluj przypięte wersje.

```bash
python3.12 -m venv /srv/venv/academy-optuna
/srv/venv/academy-optuna/bin/python -m pip install -r requirements/optuna.txt
export VENOM_OPTUNA_PYTHON=/srv/venv/academy-optuna/bin/python
```

Ustaw tę samą bezwzględną ścieżkę w konfiguracji uruchomieniowej backendu, żeby opcja pojawiła się w Academy. CLI odczytuje zmienną z otoczenia. Kampanie na stałej liście działają bez tej zależności. Środowisko LoRA pozostaje zdefiniowane w profilu eksperymentu.

W **Trening → Kampania** wybierz strategię **Optuna** i podaj zakresy co najmniej jednego z parametrów `rank`, `alpha`, `learning_rate` i `dropout`. W manifeście CLI ustaw `strategy` na `optuna`, `variants` na pustą listę oraz `sampler_seed` i `search_space`. Przykładowa przestrzeń to `{"rank":{"low":2,"high":8},"learning_rate":{"low":0.00001,"high":0.0001,"log":true}}`. Parametry spoza przestrzeni pochodzą z receptury profilu. Podgląd wiąże zakresy, ziarno, wersję Optuny, ocenę i limity z hashem planu.

Kolejne propozycje korzystają z ukończonych ocen dev. Optuna maksymalizuje zmianę użyteczności względem bazy i osobno uwzględnia progi użyteczności i błędów krytycznych. W ocenie ręcznej kontroler czeka na komplet ocen. Błąd techniczny i pominięta powtórzona receptura nie dostają wyniku jakości. Wczesne odcinanie prób jest wyłączone, ponieważ jakość oceniamy po generacji. Kontroler nadal egzekwuje limity AUT-02 oraz chroni wybrany adapter przy retencji.

Katalog kampanii zawiera prywatny dziennik SQLite z przydziałami i wynikami prób. Zachowaj go wraz ze stanem kampanii, żeby wznowienie po restarcie użyło tych samych propozycji i zapisanych ocen. Wybraną konfigurację można potwierdzić drugim ziarnem treningu i niezależnym zbiorem końcowym.


## Sterowanie kampanią z czatu Venom

W lokalnym czacie pełnego Venoma wpisz `/academy`, aby zobaczyć polecenia. Czaty z wybranym modelem chmurowym wykonują te polecenia lokalnie. Odpowiedź zawiera identyfikator wykonania równy identyfikatorowi kampanii oraz odnośnik do jej widoku w Academy.

`/academy validate <JSON>` sprawdza roboczy manifest. `/academy plan <JSON>` zapisuje plan i pokazuje profil, recepturę lub przestrzeń Optuny, ocenę dev, progi selekcji, limity i retencję. Wklej manifest jako JSON w treści komendy. Identyfikatory profilu i kampanii wybierz jawnie. Dla strategii stałej komendy czatu pozwalają zmieniać `rank`, `alpha`, `learning_rate` i `dropout` w wariantach. Pozostałe parametry treningu pochodzą z profilu operatora.

Po sprawdzeniu planu wpisz komendę startu, którą zwrócił Venom. W panelu zapisanego planu znajdziesz ją pod **Polecenie startu w czacie**.

```text
/academy start polski-czat PLAN_SHA256
/academy status polski-czat
/academy stop polski-czat
/academy resume polski-czat
/academy compare polski-czat
/academy report polski-czat
```

`start` i `resume` czekają na wznowienie kolejki Venoma i dostępne miejsce w ramach limitu równoległych zadań. `stop` działa także podczas pauzy kolejki. Powtórzenie startu z tym samym identyfikatorem i hashem zwraca stan tej samej kampanii. Przerwanie rozmowy pozostawia kampanię pod kontrolą jej wykonawcy. Po ponownym otwarciu czatu odczytaj stan przez `status`. Aby zatrzymać pracę, użyj `stop`. Polecenia korzystają z tego samego budżetu i stanu co przyciski Academy.

`compare` i `report` odczytują zapisane oceny bazy i adapterów oraz dostępność zweryfikowanych wag. Porównanie pokazuje liczbę przypadków dev, poprawę lub regresję oraz parametry kandydata do ponownego sprawdzenia, gdy użyteczność wzrosła bez wzrostu błędów krytycznych. Nowa receptura, dane, reguły oceny lub budżet wymagają nowego identyfikatora kampanii. W strategii Optuna kolejne konfiguracje wybiera sampler z zatwierdzonej przestrzeni.


## Wnioski i następna próba

W **Academy → Trening → Kampania → Wnioski i następna próba** wybierz zakończony przebieg. Dodaj przebieg referencyjny, aby zobaczyć zyski i regresje na tych samych przypadkach. Porównanie wymaga tej samej bazy, danych dev, protokołu i kategorii przypadków. Raport uwzględnia oceny zapisane przed sprzątaniem adaptera. Brak dowodów lub zmiana sum kontrolnych wstrzymuje porównanie.

Przebiegi utworzone przez Academy pojawiają się po zapisaniu ocen. Wyniki spoza Academy można wczytać poleceniem:

```bash
source .venv/bin/activate
python -m scripts.academy.quality --root "$experiment_root" import pakiet.json
python -m scripts.academy.quality --root "$experiment_root" analyze history:kandydat --reference-id history:porownanie
```

Importowane identyfikatory w panelu i w poleceniu analizy mają przedrostek `history:`. Identyfikatory zapisanych przebiegów Academy zachowują pierwotną postać.

Pakiet zawiera `schema_version: 1` i listę `records`. Każdy rekord zawiera identyfikator, rodzaj zbioru (`dev` albo `holdout`), tożsamość bazy, zbioru i protokołu, źródło z SHA-256 oraz przypadki z kategorią i sparowanymi ocenami `usable` i `critical`. Gdy w źródle brakuje etykiet krytyczności, zapisz `critical: null`. Można dołączyć recepturę, hash treningu, środowisko, chronione ID i decyzję operatora. [Schemat](../../venom_core/services/training_experiments/quality_schema.py)

Przy zgodnych ocenach dev i udokumentowanej różnicy konfiguracji Academy proponuje próbę kontrolną i zmianę jednego parametru. Zbiór końcowy służy do osobnego potwierdzenia. Jeśli potrzebna zmiana wykracza poza obsługiwane parametry profilu, przygotuj odpowiedni profil i wykonawcę przed zapisaniem kampanii.

Formularz kampanii może wiązać referencję, chronione przypadki, progi różnic użyteczności w kategoriach i zakaz nowych błędów krytycznych. Academy zapisuje kryteria z hashem planu. Wynik próby pokazuje utracone chronione przypadki, nowe błędy krytyczne i różnice per kategoria. Tylko kandydaci spełniający kryteria mogą zostać wybrani do retencji. Porównanie z wcześniejszym adapterem odbywa się na podstawie zapisanych ocen, więc nie wymaga załadowania jego wag.


## Próba zakresu LoRA po P14

W historii jakości porównaj `history:p14-02` z `history:p13-on-p14-dev` i przenieś rekomendację do formularza. Wybierz profil z przypiętymi danymi P14 i środowiskiem wskazanym w szkicu. Academy wstępnie uzupełnia limit tokenów dla obu wariantów. Zapisz plan, sprawdź budżet i użyj osobnego przycisku startu.

Wariant kontrolny używa `q_proj` i `v_proj`. Wariant porównawczy obejmuje również `k_proj`, `o_proj`, `in_proj`, `out_proj`, `w1`, `w2` i `w3`, jeśli występują w części językowej przypiętego modelu. Academy rozpoznaje zapis tego zakresu w historycznej recepturze P13 i wystawia listę nazw do planu. Wykonawca sprawdza rzeczywiste warstwy adaptera i zapisuje ich listę w raporcie treningu. Porównanie zachowuje dane, sposób obliczania straty i pozostałe parametry P14.

Zapisany rekord jakości P13 zawiera wyniki, ale może nie zawierać receptury ani sumy danych treningowych. W takim przypadku Academy nie tworzy z niego automatycznie porównywalnej próby. Przygotuj dwa świeże warianty od tej samej przypiętej bazy i na tym samym zbiorze; historyczne P13 służy do kontroli jakości, nie do przypisywania przyczyny różnicy. Nie dopisuj do zapieczętowanego rekordu parametrów odtworzonych z pamięci.

Receptura tekstowego Omni ma jawne `loss_mode`: `model_default` zachowuje dotychczasowe uśrednianie straty modelu dla mikroserii, a `supervised_token` waży każdą mikroserię udziałem nadzorowanych tokenów w całym kroku akumulacji. Oba ramiona próby zakresu LoRA muszą mieć ten sam tryb. Wykonawca raportuje nazwy, kształty i grupy dopasowanych modułów, liczbę parametrów adaptera oraz parametry optymalizatora. Zmianę `loss_mode` testuj osobno od zmiany modułów. Opcjonalne `gradient_checkpointing` zmniejsza szczyt zużycia pamięci GPU kosztem czasu treningu; domyślnie jest wyłączone. Przy porównaniu ramion ustaw tę samą wartość i zapisz ją w profilu.

Budżet GPU ma dwa osobne parametry receptury w MiB. `gpu_allocator_reserve_mib` ogranicza udział pamięci przydzielany alokatorowi PyTorch według wolnej pamięci przy starcie; `gpu_step_min_free_mib` zatrzymuje próbę, jeśli wolna pamięć po kroku spadnie poniżej minimum. Domyślne wartości to 1000 i 600 MiB. Zapisz inne wartości jawnie w profilu i porównuj rzeczywisty zapas z potwierdzenia treningu (`gpu_total_mib`, `initial_gpu_free_mib`, `gpu_allocator_limit_mib`, `minimum_gpu_free_mib_at_step`). Pole `min_free_bytes` profilu kampanii dotyczy miejsca na dysku, nie VRAM. Większy budżet pamięci nie zmienia sam w sobie receptury uczenia ani jakości odpowiedzi.


## Kolejka ocen i wyniki historyczne

W **Trening → Eksperymenty** kolejka wskazuje przebiegi z gotowymi generacjami, które wymagają oceny. Otwórz wpis, aby przejść do ślepej oceny. Jeżeli istnieje zweryfikowany werdykt z przeglądu zewnętrznego, jego odnośnik prowadzi do historii jakości. Werdykt zewnętrzny i przyjęcie natywnej oceny to oddzielne zdarzenia. Ukończony trening lub zapisany raport nie oznaczają dopuszczenia adaptera.

Historia obsługuje nakładające się grupy przypadków, np. wszystkie zadania retencji i węższą grupę chronionych przypadków. W porównaniu widać liczebność grupy oraz pokrycie oceną krytyczności. Brak oceny krytyczności pozostaje widoczny. Porównuj wyłącznie zapisy zgodne co do modelu bazowego, zbioru dev, protokołu oraz podziału na grupy.

Operator może zaimportować wersjonowany pakiet przez `scripts.academy.quality import`. Pole `cohorts` wiąże nazwy grup z identyfikatorami przypadków. Pole `reviewed_run` wiąże zewnętrzną decyzję z identyfikatorem przebiegu oraz sumami SHA-256 checkpointu i manifestu generacji. Academy pokazuje odnośnik tylko po sprawdzeniu zgodności zapieczętowanych plików tej próby. Ponowny import tego samego rekordu zachowuje jego tożsamość.

Po zatrzymaniu albo nieudanej generacji użyj ponowienia oceny w przebiegu. Wykonawca odczyta zweryfikowane odpowiedzi zapisane wcześniej w katalogu tego przebiegu, jeśli zgadzają się dane, wagi i protokół. Wygeneruje brakujące odpowiedzi i zapisze nowy kompletny pakiet do ślepej oceny. Kampania używa własnego limitu ponowień i czasu. Jeśli wyczerpała budżet, jej raport wskazuje zatrzymanie.


## Nowy trening od zapisanego adaptera LoRA

W kampanii na stałej liście wybierz dla każdego wariantu model bazowy albo adapter z katalogu Academy. Podgląd zapisuje tożsamość adaptera, sumy kontrolne, rewizję bazy i pochodzenie. Dwa warianty z identyczną recepturą mogą zacząć od różnych wag. Zmiana katalogu lub plików po zapisaniu planu wymaga ponownego planowania.

Operator rejestruje adapter w `<experiment_root>/adapters/<adapter_id>/`. Katalog zawiera `adapter_config.json`, `adapter_model.safetensors`, `hashes.json` z sumami dokładnie tych dwóch plików oraz `adapter.json`. W `adapter.json` wpisz `schema_version: 1`, `adapter_id`, `label`, `model`, `revision`, `snapshot_sha256`, `config_sha256`, `weights_sha256` oraz `source` z polami `identity` i `sha256` identyfikującymi zapieczętowane pochodzenie. Adapter musi pasować do przypiętego modelu Omni i do `rank`, `alpha`, `dropout` oraz modułów LoRA w recepturze. Używaj jedynie zwykłej LoRA dla części językowej.

W manifeście kampanii CLI podaj np. `"variants": [{}, {"initial_adapter_id": "omni-p13-145"}]`. Ustaw recepturę profilu zgodną z obydwoma ramionami. Panel i CLI odczytują ten sam plan. Tryb wyboru adaptera startowego jest dostępny dla strategii stałej.

Dla zarejestrowanego `omni-p13-145` ustaw w obu ramionach `rank: 4`, `alpha: 8`, `dropout: 0.05` i `target_modules: ["q_proj", "k_proj", "v_proj", "o_proj", "in_proj", "out_proj", "w1", "w2", "w3"]`. Jeśli profil ma inny zakres modułów lub inną wartość dropout, Academy odrzuci plan przy walidacji adaptera.

Nowy przebieg rozpoczyna optymalizację od kroku zero. Runner sprawdza wartości wszystkich tensorów wczytanych z adaptera. Po przerwaniu przebieg kontynuuje z własnego pełnego checkpointu wraz ze stanem optymalizatora, harmonogramu i RNG. Retencja usuwa pliki wynikowe kampanii zgodnie z wybraną polityką. Katalog wejściowy jest niezależny od plików wynikowych.


## Audyt mieszanki danych przed treningiem

Najpierw przygotuj i zrecenzuj mapę rekordów train. Plik JSON zawiera `schema_version: 1` oraz `records`. Kluczem mapy jest ID rekordu, a wartością obiekt `{"group":"replay","skill":"state_add"}`. Grupa to `replay` lub `fresh`, a nazwa umiejętności składa się z małych liter ASCII, cyfr, łączników lub podkreśleń. Przypisz dokładnie jedną parę do każdego rekordu. Dla danych strukturalnych sprawdzaj treść nadzorowanej odpowiedzi, żeby odróżnić inicjalizację od aktualizacji, nawet gdy mają wspólną etykietę zadania.

Wygeneruj raport na CPU dla konkretnego limitu wejścia z receptury. Użyj train i roboczego dev właściwego dla tej kampanii.

```bash
bash scripts/academy/omni_pl_chat_audit.sh "$snapshot" "$train" "$dev" \
  "$taxonomy" "$audit_output" "$training_venv" 1280
```

Do katalogu profili wgraj `$profile_id.data-audit.json` (wygenerowany `audit.json`) i `$profile_id.taxonomy.json` (zweryfikowaną mapę rekordów). W profilu ustaw `data_audit` z polami `report_sha256`, `taxonomy_sha256` i `policy`. Przykład progów:

```json
{
  "groups": {
    "replay": {"min_records": 60},
    "fresh": {"min_supervised_tokens": 500}
  },
  "skills": {
    "state_add": {"replay": {"min_records": 1}},
    "state_sub": {"replay": {"min_records": 1}}
  }
}
```

Odczytaj stan przez `python -m scripts.academy.experiments --root "$experiment_root" audit "$profile_id"` lub w Academy. Raport, taksonomia, dane, przypięta baza, tokenizacja i limit wejścia muszą się zgadzać. Audyt blokuje duplikaty train, dokładnie wspólne znormalizowane pytania lub prefiksy train/dev i niespełnione progi. Porównanie tekstu używa normalizacji NFKC, składania wielkości liter i białych znaków. Nie mierzy podobieństwa semantycznego. Po zmianie plików wygeneruj nowy audyt i zapisz nowy plan.

Raport pokazuje liczbę rekordów, liczbę tokenów nadzoru oraz pokrycie umiejętności. Liczniki dotyczą jednego przejścia przez plik train. Trener przed załadowaniem modelu sprawdza sumaryczne pomiary z raportu przy niezależnym kodowaniu. Budżet kroków oraz tryb `loss_mode` określają osobno ekspozycję danych i sposób ważenia straty. Zaliczenie audytu oznacza spełnienie zdefiniowanych warunków składu danych.
