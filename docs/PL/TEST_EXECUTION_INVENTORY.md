# Statyczny inwentarz testów backendu

`scripts/test_execution_inventory.py` zestawia pliki `tests/**/test_*.py` z
katalogiem `config/testing/test_catalog.json` i wygenerowanymi grupami pytest.
Odczytuje kod przez parser AST; nie importuje ani nie uruchamia analizowanych
modułów. Wynik pomaga przygotować ręczny przegląd klasyfikacji T1.

```bash
source .venv/bin/activate
python scripts/test_execution_inventory.py --summary
python scripts/test_execution_inventory.py --review signals \
  --output test-results/testing-strategy-review/signals.json
python scripts/test_execution_inventory.py --review unknown \
  --output test-results/testing-strategy-review/unknown.json
python scripts/test_execution_inventory.py --review unregistered \
  --output test-results/testing-strategy-review/unregistered.json
python scripts/test_execution_inventory.py --review declared-live \
  --output test-results/testing-strategy-review/declared-live.json
```

Bez `--output` szczegółowy JSON trafia na standardowe wyjście. `--summary`
pokazuje zbiorcze liczniki; `--review` ogranicza wiersze szczegółowe, ale
podsumowanie dotyczy całego zbioru. `--fail-on-unregistered` zwraca kod 1,
gdy odkryty plik nie występuje w katalogu. Błędy katalogu i parsowania zwracają
kod 2. Flaga jest używana także w CI i sprawdza wyłącznie rejestrację, której
wymagają już istniejące kontrole katalogu. Jej zielony wynik nie zatwierdza
klasyfikacji `unknown` ani bezpieczeństwa wykonania testów.

Każdy wiersz zawiera ścieżkę, domenę i typ katalogu, grupy fast/long/heavy i
ci-lite/sonar-new-code, wskazówkę warstwy oraz markery i znalezione wywołania.
`e2e_candidate` to wskazówka oparta na nazwie ścieżki; typ unit, integration
lub perf odzwierciedla istniejące metadane, a grupy nie są pomiarem czasu ani
zużycia zasobów.

Środowisko ma trzy wartości:

- `declared_live`: na poziomie pliku wykryto jawny marker testów fizycznych.
- `partly_declared_live`: marker znajduje się na części metod lub klas.
- `unknown`: brak rozpoznanej deklaracji. Nie jest to potwierdzenie izolacji.

Sygnały `network_candidate`, `socket_candidate`, `process_candidate` i
`collection_probe_candidate` wskazują wywołania do sprawdzenia wraz z linią i
fazą kolekcji/wykonania. Mogą wskazywać atrapy, a nie faktyczne połączenie lub
uruchomienie procesu. Analiza nie śledzi wszystkich aliasów, wywołań pośrednich,
importów z efektami ubocznymi, operacji z podprocesów ani dynamicznych markerów.
Brak sygnału nie dowodzi braku dostępu do usług. Wszystkie wiersze są oznaczone
`manual_review_required`; klasyfikacja nie jest automatycznie zmieniana.

Przy przeglądzie sprawdź kod testu oraz fixture i helpery: rzeczywistą granicę
API, zasoby i operacje zapisu, używane atrapy, skutki importu, markery, koszt
oraz docelowy zestaw PR/main/release. Zapisz decyzję wraz z rewizją i dowodem;
nie przenoś testu do automatycznej grupy wyłącznie na podstawie tego raportu.
Nowy plik bez wpisu katalogu jest widoczny jako `catalogued=false`, z nieznaną
klasyfikacją, i wymaga rejestracji zgodnej z polityką repozytorium.

Inwentarz obejmuje Python z katalogu `tests`; testy frontendowe, workflow GitHub,
podprocesy i skan Sonara wymagają oddzielnego przeglądu. Raport nie zastępuje
wykonania testów, pomiaru grup ani dowodu bezpiecznego dostępu do fizycznego
Venoma. Pliki wynikowe w `test-results` są lokalne i ignorowane przez Git.
