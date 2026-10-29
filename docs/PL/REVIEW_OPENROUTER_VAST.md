# Przegląd wewnętrzny OpenRouter i VAST przed publikacją

Gałąź: `codex/openrouter-chat-mvp`. Przegląd obejmuje cały zakres względem
odświeżonego `origin/main` (`a3212b56`), nie tylko ostatni panel VAST.
Kod po poprawkach i końcowej bramce: `02505c1f`.

Rekomendacja: publikacja gałęzi jako PR do recenzji kodu. Przegląd lokalny nie
zastępuje bramek GitHub/Sonar ani odbioru rzeczywistego płatnego wdrożenia.

## Znalezione i poprawione

| Priorytet | Problem | Poprawka i dowód |
| --- | --- | --- |
| P2 | Worker VAST mógł zakończyć się po krótkim konflikcie blokady z odświeżaniem, pozostawiając jedyne zamówienie w kolejce. | Worker czeka na blokadę; administracyjne HTTP nadal odpowiada konfliktem zamiast czekać na długą instalację. Test z konkurencyjną blokadą potwierdza gotowość i dokładnie jeden zakup na atrapach. |
| P2 | Status dostawcy o typie innym niż tekst trafiał do stanu i zdarzeń, uszkadzając przyszły odczyt dziennika. | Walidacja przed zapisem zdarzenia: jawny błąd i poprawny stan `unknown`, z zachowaniem ID instancji. Odtworzono problem dla czterech nieprawidłowych typów. |
| P3 | Kategorie OpenRouter wyświetlały surowe kody zamiast tłumaczeń. | Etykiety pl/en/de przy zachowaniu identyfikatorów API, z testem każdej lokalizacji i kontrolą rzeczywistego DOM. |
| P3 | Długa lista ofert VAST odsuwała formularz zamówienia o wiele ekranów. | Ograniczona wysokość przewijanej tabeli i przyklejony nagłówek. |
| Dokumentacja | Część instrukcji opisywała starszy przepływ i wersję biblioteki. | Aktualny rejestr do 100 modeli, core 0.2.0 i dedykowany panel VAST; ręczne podanie ID planu pozostaje trybem zaawansowanym. |

Poprawki zapisano w `d46c8d32` i `02505c1f`.

## Sprawdzone granice rozwiązania

- OpenRouter: wybór dokładnego modelu, brak cichego fallbacku i ponowień płatnego
  POST, ważność cen, wycena związana z konfiguracją/treścią, rezerwacje budżetu,
  niepewne rozliczenia i STOP. Obsługa w Venomie pozostaje ograniczona do Direct.
- VAST: serwerowy profil i ścieżki SSH, ocena ofert, odświeżenie ceny przed zakupem,
  pojedyncze create, niejednoznaczny wynik bez ponownego najmu, instalacja i kontrola
  digestu modelu, podpinanie, odtwarzanie po restarcie, stop/destroy i potwierdzanie
  zakończenia przez dostawcę. Instalacja w toku musi zakończyć się lub nie powieść,
  zanim dostępne będą operacje sprzątania tego procesu.
- Dostawcy zewnętrzni pozostają opcjonalni: brak API/biblioteki/połączenia nie
  blokuje startu Venoma. Wybrana niedostępna tożsamość nie przechodzi na inny model.
- Brak rzeczywistych Test Zero w automatycznych workflow. Jednostkowe testy kodu
  Test Zero wykorzystują atrapy. Nie wykonano nowego najmu ani generacji.
- Odświeżono `origin/main`: brak zaległych commitów main. Kontrola wzorców kluczy
  w dodanych liniach nie znalazła trafień; nie jest to zastępstwo skanu Sonara.
- Kontrakt ograniczeń ceny porównano z [oficjalnym opisem routingu OpenRouter](https://github.com/OpenRouterTeam/docs/blob/main/guides/routing/provider-selection.mdx).

## Walidacja lokalna

| Polecenie / zestaw | Wynik |
| --- | --- |
| `pytest -q tests/test_vast*.py tests/test_remote_provider_control.py` | 517 PASS; tylko atrapy i izolowana sieć |
| Publiczne kontrakty OpenRouter/VAST z zablokowanym importem prywatnego core | 140 PASS, 7 jawnych SKIP wymagających rzeczywistego wheel |
| `python scripts/qualify_openrouter_local.py ...` | PASS: hash, instalacja bez sieci, pochodzenie importu i testy faktycznego wheel 0.2.0; zgodność z istniejącym dowodem Windows |
| `mypy` zmienianych modułów, TypeScript `--noEmit`, ESLint, `lint:locales` | PASS |
| `make test-ci-lite` | PASS |
| `make test-catalog-check`, `make test-groups-check`, `make check-new-code-coverage-diagnostics` | PASS |
| `make test-web-unit` | PASS |
| Końcowy `make pr-fast` | PASS, 176,07 s; 1413 testów backendu i 242 testy komponentów UI |
| Pokrycie zmienionych linii | 94,80%; wszystkie 14 progów plikowych zaliczone |
| `mypy venom_core` (460 plików) | FAIL: jeden błąd środowiska, brak stubów `scipy.signal` w `ollama_audio.py:57` |

Ostatni błąd odtworzono na czystych źródłach tego modułu z `origin/main`, w tym
samym interpreterze i konfiguracji mypy. Nie wprowadzono wyciszenia, obniżenia
progów ani zmian zależności audio. Lokalny pełny mypy pozostaje niezaliczony;
nie przedstawiamy go jako zielonego wyniku tej gałęzi.

## Warunki wdrożenia i nieprzeprowadzone odbiory

1. `agent-execution-core==0.2.0` jest nadal osobnym prywatnym artefaktem z lokalnego
   repozytorium orkiestracji. Nowa instalacja potrzebuje jego zweryfikowanego wheel.
   Repo Venoma i publiczne CI nie pobierają go automatycznie. Trzeba ustalić kanał
   dystrybucji przed niezależnym wdrożeniem funkcji OpenRouter.
2. VAST wymaga własnego zatwierdzonego profilu oraz poświadczeń i konfiguracji SSH.
   Prywatnego profilu lokalnej instancji nie dołączono do repozytorium.
3. Realny płatny przebieg VAST i odpowiedź modelu nie były uruchamiane. Test Zero
   jest wyłącznie ręczny, na osobne żądanie operatora. Pełnego E2E nie uruchamiano.
4. Limity VAST kontrolują wycenę, nie ciągły wydatek ani automatyczny czas usunięcia.
   Nieudana instalacja może pozostawić płatny host do jawnego sprzątnięcia.
5. Jeden starszy, uszkodzony lokalny wpis historii pozostaje ostrzeżeniem. Przegląd
   nie przepisał historycznych danych operatora; poprawka zapobiega nowemu zapisowi
   tego samego rodzaju błędnego stanu.
6. Nie opublikowano kodu ani nie uruchomiono bramek GitHub/Sonar dla nowej rewizji.


## Poprawka po Sonarze i CodeRabbit — PR #566

Raport dla `26c591ee` zawierał 81 zgłoszeń: 78 utrzymaniowych, 2 błędy i 1
podatność. Bramkę blokowały reliability D i security C; pokrycie 92,4%, duplikacja
0% i przegląd hotspotów 100% były zaliczone. Nie zmieniamy progów ani statusów
zgłoszeń, aby odblokować wynik.

Naprawa ogranicza wybór klucza SSH do regularnych plików z zaufanych magazynów
`~/.ssh` i `secrets/ssh`; odrzuca tożsamości przez symlink i ścieżki poza tymi
magazynami. `known_hosts` również musi pozostać w tych magazynach po rozwiązaniu
ścieżki. Profil jest serwerowy. Testy nie czytają rzeczywistych kluczy.

Pozostałe poprawki Sonara obejmują sortowanie, warunek długości, złożoność
funkcji, semantykę i dostępność HTML, nazwy stanu React, stałe, obsługę kontekstów,
dokumentację odpowiedzi API i jednoznaczne asercje/wywołania w testach wyjątków.
Rozdzielenie logiki wysyłania ma regresje STOP podczas wyceny oraz odrzucenia
wyceny bez fallbacku. Anulowanie przed przechwyceniem wyceny nie przygotowuje
żądania ani rezerwacji.

Recenzja CodeRabbit dla tej samej rewizji została odebrana przed publikacją
poprawki. Uwzględniono wszystkie 5 uwag i dodatkowy test ścieżki `generate()`:

- Jawne odświeżenie wybranego modelu aktualizuje hash selekcji. Stara wycena
  nadal jest odrzucana; odświeżenie innego modelu nie zmienia selekcji.
- Limit 256 tokenów pozostaje celowym ograniczeniem małego budżetu MVP na
  wcześniejsze żądanie operatora. Karta modelu pokazuje rzeczywisty limit;
  dokumentacja odróżnia go od możliwości modelu.
- Status dostępnego VAST pomija historyczny błąd sondy; przy niedostępności
  zachowuje informację o błędzie bez automatycznego odpytania dostawcy.
- Akcja operatora oczekuje na świeży odczyt dostawców, także jeśli wcześniejszy
  polling nadal trwa. Nie może zwolnić przycisków na podstawie starego odczytu.
- Kwalifikacja wheel nie dziedziczy pliku poświadczeń OpenRouter ani klucza VAST
  i nie ładuje `.env.dev`; test sprawdza izolację źródeł sekretów.
- Testy `generate()` na atrapach obejmują sukces, brak markera, błędny model,
  koszt ponad rezerwację, niedokończony strumień i HTTP 429 bez ponowienia.

Wyniki końcowej lokalnej bramki i ponownej analizy GitHub/Sonar należy odnosić
do rewizji zawierającej tę poprawkę, nie do pierwotnego raportu powyżej.
Rzeczywiste Test Zero i najem VAST pozostają poza zakresem tej walidacji.
