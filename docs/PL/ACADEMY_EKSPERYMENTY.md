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

Powtórzenie startu z tym samym identyfikatorem i hashem zwraca stan tej samej kampanii. Przerwanie rozmowy pozostawia kampanię pod kontrolą jej wykonawcy. Po ponownym otwarciu czatu odczytaj stan przez `status`. Aby zatrzymać pracę, użyj `stop`. Polecenia korzystają z tego samego budżetu i stanu co przyciski Academy.

`compare` i `report` odczytują zapisane oceny bazy i adapterów oraz dostępność zweryfikowanych wag. Porównanie pokazuje liczbę przypadków dev, poprawę lub regresję oraz parametry kandydata do ponownego sprawdzenia, gdy użyteczność wzrosła bez wzrostu błędów krytycznych. Nowa receptura, dane, reguły oceny lub budżet wymagają nowego identyfikatora kampanii. W strategii Optuna kolejne konfiguracje wybiera sampler z zatwierdzonej przestrzeni.
