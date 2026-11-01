# Zbiorcza naprawa recenzji i Sonara PR #575 — 2026-11-01

Punkt wyjściowy: `f0aa3a7e9e74af59de409fd1ea88804446b2af0d`.
Zebrano 10 wątków recenzji (4 Copilot, 6 CodeRabbit), dotyczących 9 różnych
przyczyn, oraz wszystkie 13 otwartych zgłoszeń Sonara i zero hotspotów.
Recenzje i skan dotyczyły tego samego SHA. Oba workflow E2E były zielone;
CI zatrzymało się na ocenach reliability/security Sonara.

Wszystkie uwagi uznano za zasadne i przygotowano wspólną poprawkę kodu.
Nie zmieniano ręcznie statusów zgłoszeń ani nie publikowano częściowych napraw.

## Recenzje i rozwiązania

| Wątek | Rozwiązanie i dowód |
|---|---|
| Copilot `4435276988` | Zadania są powiązane z run ID. Usuwanie czeka na proces, kontenery i dzierżawę; anulowanie przed startem nie uruchamia procesu. Sześć deterministycznych regresji delete/clear dla kolejki, spawnu i pracy oraz osobna odmowa usunięcia przy niepotwierdzonym cleanup. |
| Copilot `4435277018`, Rabbit `4435281246` | Oracle wymaga unikalnego potwierdzenia po asercjach; pytest musi rzeczywiście ukończyć testy. Niezerowy wynik negatywnej kontroli musi oznaczać wykonaną porażkę testu. Regresje obejmują exit podczas importu, wywołania funkcji i kolekcji pytest. |
| Copilot `4435277039` | Najpierw pełne identyfikatory i ścieżki, skróty wyłącznie jednoznaczne. Nierozróżnione rewizje mają loaded=null. Regresje namespace, aliasów, rewizji i braku wyboru. |
| Copilot `4435277057` | Jawny profil oraz instrukcja zawierają RUNTIME_ADMISSION_ENABLED=true. Domyślny profil hosta pozostaje bez zmian. |
| Rabbit `4435281241` | Poprawiono pisownię „rewizja”. |
| Rabbit `4435281245` | Błąd pojedynczej rejestracji snapshotu/research jest logowany i nie przerywa pozostałych wpisów. Wydzielono odpowiedzialności discovery. |
| Rabbit `4435281249` | Rozpoznawanie rzeczywistych poleceń rg, grep i git grep; samo wypisanie „rg” nie jest dowodem. |
| Rabbit `4435281251` | Błędy adresu, połączenia i metadanych preflightu dają kontrolowany maintenance_local_llm_runtime_unverified; dodano PL/EN/DE i regresje. |
| Rabbit `4435281253` | Raport końcowy musi być obiektem JSON; błędne typy są odrzucane jako błąd modelu. |

## Komplet zgłoszeń Sonara

| Zgłoszenie | Reguła | Naprawa |
|---|---|---|
| `AaGWrdTjJDrY7EFXKhLb` | `python:S3776` | Rozdzielenie walidacji indeksów/shardów, rejestracji modeli i dekodowania generacji na spójne funkcje. |
| `AaGWrdT_JDrY7EFXKhLf` | `python:S9073` | Osobne asercje dla niezależnych stanów i własności żądania. |
| `AaGWrdT_JDrY7EFXKhLg` | `python:S9073` | Osobne asercje dla niezależnych stanów i własności żądania. |
| `AaGWrdT_JDrY7EFXKhLh` | `python:S9073` | Osobne asercje dla niezależnych stanów i własności żądania. |
| `AaGWrdT_JDrY7EFXKhLi` | `python:S9073` | Osobne asercje dla niezależnych stanów i własności żądania. |
| `AaGWrdTiJDrY7EFXKhLa` | `python:S7504` | Usunięcie zbędnej kopii listy przy przebudowie dopasowania identyfikatorów. |
| `AaGWrdTzJDrY7EFXKhLd` | `typescript:S4043` | Sortowanie jako osobna instrukcja wewnątrz bloku. |
| `AaGWrdT3JDrY7EFXKhLe` | `typescript:S3358` | Etykieta stanu obliczana przed renderowaniem. |
| `AaGWrdTqJDrY7EFXKhLc` | `python:S3776` | Rozdzielenie walidacji indeksów/shardów, rejestracji modeli i dekodowania generacji na spójne funkcje. |
| `AaGWrdUBJDrY7EFXKhLj` | `python:S3415` | Jednolita kolejność actual → expected. |
| `AaGWrdOlJDrY7EFXKhLX` | `python:S3776` | Rozdzielenie walidacji indeksów/shardów, rejestracji modeli i dekodowania generacji na spójne funkcje. |
| `AaGWrdTgJDrY7EFXKhLZ` | `python:S7497` | Anulowanie spawnu propagowane po uzyskaniu dziecka do sprzątania; oczekiwanie na anulowane zadanie nie przechwytuje anulowania wywołującego. |
| `AaGWrdTOJDrY7EFXKhLY` | `python:S5443` | Prywatne tmpfs: chroniony katalog runtime 0750 i osobny katalog użytkownika 0700; właściciel nadawany przy montowaniu, bez dodawania capabilities. |

## Walidacja

Kod wykonawczy finalnej kontroli: `b4aa69e8cafca2598620a5fd212658085efcad27`.
Po bramkach dodano wyłącznie ten raport.

- Ruff i hooki lokalnych commitów: PASS.
- `npm --prefix web-next ci`: PASS; `make test-web-unit`: PASS.
- `pytest -q tests/test_maintenance_catalog.py tests/test_maintenance_checks.py tests/test_maintenance_fixtures.py tests/test_maintenance_host.py tests/test_maintenance_loop.py tests/test_maintenance_protocol.py tests/test_maintenance_records.py tests/test_maintenance_safety.py tests/test_model_manager_discovery.py tests/test_coding_run_routes.py tests/test_coding_run_service.py`: PASS, 7.20 s.
- `mypy venom_core/services/maintenance_comparison venom_core/core/model_inventory.py venom_core/core/model_manager_discovery.py venom_core/services/model_runtime_inventory.py venom_core/api/routes/models_install.py venom_core/services/benchmark_coding.py`: PASS, 55.38 s.
- `make test-ci-lite`: PASS, 80.56 s.
- `make test-catalog-check`: PASS, 0.05 s.
- `make test-groups-check`: PASS, 0.04 s.
- `make pr-fast`: PASS, 190.97 s.
- `make check-new-code-coverage-diagnostics`: PASS, 0.11 s.

Celowane testy: **275 PASS**. Mypy: **20 plików źródłowych**.
Końcowe `make pr-fast`: **190,97 s**, 1411 testów backendu, 358 komponentowych,
12 Studio i wymagane kontrole frontendu. Pokrycie zmienionych linii: **88,49%**;
progi plików i końcowa diagnostyka PASS.

Sekwencja końcowych kontroli backendu i pr-fast: **334.31 s**.

Dodatkowe rzeczywiste kontrole, bez modeli:

- Prywatny katalog tmp działa dla UID 1000 z prawami 0700. Zapis i usunięcie
  chronionego oracle są odrzucane. Sieć wyłączona, root filesystem read-only.
- Osiem kontrolowanych usterek: wszystkie negatywne kontrole FAIL, wszystkie
  wzorcowe poprawki PASS. Przedwczesne zakończenie procesu zostało odrzucone.
- Pierwsza kontrola rzeczywista ujawniła niedziałające nadawanie właściciela
  po uruchomieniu ograniczonego kontenera. Finalny wariant używa właścicieli
  tmpfs nadanych przy montowaniu i przeszedł ponowną kontrolę.
- Istniejące kontenery i ich stany zostały zachowane; kontenery testowe usunięto.

## Ograniczenia i publikacja

Nie wykonywano generacji ani ponownego porównania modeli, Test Zero, operacji
VAST, treningu, restartu stosu ani drugiej instancji API/UI. Kontrole wzorcowych
napraw są sprawdzianem wykonawcy, nie próbami modeli; nie doliczamy ich do
historycznego baseline. Historyczne wyniki zachowują wcześniejszą wersję
sprawdzianu i nie zostały po cichu przeliczone.

Źródła, testy i raport są przygotowane do jednej zbiorczej aktualizacji tego
samego PR. Wymagany hook pre-push ponownie sprawdza publikowany SHA. Zamknięcie
13 zgłoszeń musi potwierdzić świeży skan Sonara; recenzje pozostają do ponownej
oceny. Nie akceptowano zgłoszeń jako false positive i nie obniżano progów.
Prywatne logi i JSON kontroli pozostają w ignorowanym test-results.


## Uzupełnienie po świeżym skanie i pełnej ponownej recenzji

Skan SHA `06d3738e` zamknął 13 poprzednich zgłoszeń, ale wskazał trzy kolejne
uwagi. Zebrano je z jedyną nową uwagą zakończonej recenzji CodeRabbit i
przygotowano jeden wspólny komplet, bez wysyłek dla pojedynczych uwag.

| Zgłoszenie | Naprawa |
|---|---|
| `AaGW89vHS_nD4WvEhbh1`, S5707 | Wynik Task.exception zapisano i sprawdzono jako BaseException przed użyciem jako przyczyny wyjątku. |
| `AaGW89qIS_nD4WvEhbhz`, S5443 | Analizator reagował na dosłowny fragment /tmp w prywatnej ścieżce. Katalog nazywa się teraz /run/venom-maintenance/temporary; uprawnienia i izolacja pozostają potwierdzone kontrolą rzeczywistą. Nie zastosowano wyłączenia reguły. |
| `AaGW89u1S_nD4WvEhbh0`, S5713 | TimeoutError jest podklasą OSError; usunięto redundantny element except, zachowując regresję obsługi timeoutu. |
| Rabbit `PRRT_kwDOQjrUfs6yZ44O` | clear_all_runs zachowuje przebieg w kwarantannie, usuwa pozostałe i po zakończeniu zgłasza pierwszy błąd. Test potwierdza zachowanie artefaktów kwarantanny i usunięcie niezależnego ukończonego przebiegu. |

Końcowa kontrola kodu `433771d38ad3c1dc3424c1f48f7430ee753c32f4`:

- Celowane pytest: **275 PASS**; mypy 20 plików: PASS; Ruff/hooki: PASS.
- `make test-ci-lite`, `make test-catalog-check`, `make test-groups-check`: PASS.
- `make pr-fast`: **190,18 s**, 1411 testów backendu, 358 komponentowych,
  12 Studio i kontrole frontendu: PASS.
- Pokrycie zmienionych linii: **88,45%**; końcowa diagnostyka PASS.
- Prywatny katalog pod finalną nazwą: rzeczywista kontrola PASS, UID 1000,
  prawa 0700, oracle chroniony przed zapisem/usunięciem, brak sieci i zmian
  istniejących kontenerów. Nie wykonywano generacji modeli.

CodeRabbit podaje także automatyczny wskaźnik pokrycia docstrings dla całego
PR. To zalecenie dokumentacyjne; lokalny kontrakt bramek nie ustanawia jego
progu 80%. Nie rozszerzano napraw defektów o masowe kosmetyczne zmiany funkcji
i testów. Nie zmieniano konfiguracji tego wskaźnika ani nie uznawano go za
zaliczony. Zamknięcie nowych trzech zgłoszeń wymaga świeżego skanu GitHub.
