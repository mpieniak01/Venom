# Rzeczywiste instalacje i stany modeli — 2026-11-01

Zmiana lokalna na `feat/light-model-maintenance-comparison`, bez publikacji GH.

## Wynik

- Katalog roboczy nie jest modelem: wymagane są niepuste wagi. Same nazwy katalogów, metadane ONNX lub pliki konfiguracji nie wystarczają.
- Dla checkpointów dzielonych sprawdzane są wszystkie części; normalne dowiązania snapshotów HF są obsługiwane.
- Offline lista Ollamy pochodzi z obecnych manifestów i odpowiadających im blobów o właściwych rozmiarach. Historyczny cache uzupełnia tylko metadane identycznego digestu, nie obecność ani aktywność.
- `selected` opisuje wybór operatora, `loaded` jest trójstanowym odczytem potwierdzonego załadowania, a `installed` obecnością plików. Zapamiętany `HYBRID_LOCAL_MODEL` nie dowodzi aktywności.
- Stan silników pochodzi z odczytu metadata GET: Ollama `/api/ps`, vLLM `/v1/models`, ONNX `/health` i `/v1/models`. Nieobsługiwany/niedostępny odczyt pozostaje niepotwierdzony.
- Obserwacje runtime należą do warstwy usług; nie zmieniano reguł kontraktu importów API.
- Czwarta kolumna „Inne modele” obejmuje checkpointy Transformers, CTranslate2 oraz badawcze RWKV/Huginn/HRM. Zachowuje nazwy backendów i rewizje.
- Nieobsługiwane przez ogólny przełącznik modele nie dostają przycisku aktywacji do vLLM. Modele głosu/wizji nie są przedstawiane jako zgodne z czatem.
- Lista odświeża się co 15 s. Błąd odczytu jest widoczny; podczas odświeżania ostatni widok pozostaje na ekranie.
- Poprawiono licznik i tłumaczenia PL/EN/DE, z regresją renderowania przez rzeczywisty provider języka.

## Odczyt działającego stosu

| Kolumna | Pozycje |
|---|---:|
| vLLM | 3 |
| ONNX | 3 |
| Ollama | 11 |
| Inne modele | 15 |

Łącznie 32 pozycje. Są to wpisy instalacji, tagów i rewizji, nie liczba unikalnych zestawów wag.
W odczycie nie potwierdzono żadnego załadowanego lokalnego LLM; brak odczytu pamięci nie jest zgadywany na podstawie konfiguracji.
Nie usuwano katalogów roboczych ani historii eksperymentów. Zniknęły wyłącznie ich błędne pozycje na liście modeli.
Selektor silników także używa rzeczywistych lokalnych instalacji.

## Weryfikacja

- `npm --prefix web-next ci`: PASS.
- Celowane `pytest` menedżera, discovery, instalacji i przełączania: 78 PASS; pozostałe jednostkowe regresje menedżera: 21 PASS.
- `pytest -q tests/test_model_manager_discovery.py tests/test_api_routes_import_guard.py`: 28 PASS.
- Ruff i isort zmienionych plików: PASS.
- `mypy venom_core/core/model_inventory.py venom_core/core/model_manager_discovery.py venom_core/services/model_runtime_inventory.py venom_core/api/routes/models_install.py`: PASS.
- `npx --no-install tsc --noEmit`: PASS.
- Testy grupowania UI: 8 PASS; karty/licznik: 4 PASS. Regresja licznika potwierdzona fail → pass.
- `make test-web-unit`: PASS.
- `make test-ci-lite`: 898 PASS.
- `make test-catalog-check`, `make test-groups-check`, `make check-new-code-coverage-diagnostics`: PASS.
- `make pr-fast` finalnego kodu: PASS, **197,24 s**; 1371 testów backendu bez błędów, testy jednostkowe frontendu, 358 testów komponentowych i 12 Studio.
- Pokrycie zmienionych linii **87,54%**; progi wszystkich 14 sprawdzanych plików spełnione. Nowe moduły: instalacje 85,71% linii, stany runtime 91,49%.
- Ponowna diagnostyka po wygenerowaniu aktualnego XML pokrycia: PASS.
- Rzeczywiste API i frontend: HTTP 200. Playwright na Windows potwierdził cztery kolumny, pozycje i końcowy licznik „Pozycje: 32”, bez błędów JS.

Testy używają atrap HTTP, tymczasowych plików i renderera komponentów.
Nie wykonywano testów zadań/jakości modeli, generacji, Test Zero, wynajmu VAST ani uruchamiania dodatkowego stosu.
W sesji odczytu przeglądarki zablokowano POST i automatyczne tłumaczenie newsów. Aktywacji modeli na prawdziwym silniku nie sprawdzano zgodnie z dyspozycją operatora.
Brak danych w silniku bez endpointu metadata pozostaje jawnym ograniczeniem odczytu.
Kontrola zrzutu: `output/playwright/model-inventory-viewport.png` (artefakt lokalny, ignorowany przez Git).

Końcowy raport dodano po bramkach; kod wykonawczy pozostał ten sam.
