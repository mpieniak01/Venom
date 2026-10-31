# Studio: odbiór lokalny

2026-10-31. Historyczny lokalny odbiór kodu aplikacji `c446c262`; gałąź dostawy `codex/group-b-venom-chat-2`.
S01–S04 odebrane lokalnie. Recenzja wewnętrzna zamknęła potwierdzone P1/P2.
W chwili tego odbioru nie wykonano publikacji GH, zewnętrznego CI i Sonara.
Poniższe pomiary są historycznym zapisem, a nie ponowną kwalifikacją późniejszego kodu.
Dalszą kwalifikację wydania zapisano w [PR #574](https://github.com/mpieniak01/Venom/pull/574).
[Instrukcja](STUDIO.md),
[ADR-004](adr/ADR-004-studio-runtime-composition.md).

## Zakres i weryfikacja

Studio ma własny web, build i cache, tylko Chat 2.0, przekierowanie z `/` i trasy
błędów. Wspólne komponenty rozmowy oraz 22 ścieżki / 27 operacji API korzystają
z tych samych handlerów i schematów co Full. Historia, materiały, wybór modelu,
bazy, kolejki i pliki modeli pozostają współdzielone w obrębie środowiska.

Cele Make `start/stop-venom` i `start/stop-studio` wymagają zatrzymania poprzedniego
właściciela. Stop i rollback sprawdzają pierwotną tożsamość procesów, zachowują
podmienione pliki ownership i wycofują tylko własne nowe zasoby. Nie adoptują
wcześniej działających procesów ani ponownie użytego UI.

- `make pr-fast`: PASS; 1468 przypadków backendu, 342 komponentowe i zestawy jednostkowe web; 10 testów standalone. Pokrycie zmienionych linii 93,68% przy progu 80%, wszystkie 14 progów plikowych PASS. Porównanie gałęzi obejmuje też wcześniejszy Chat 2.0.
- `make test-ci-lite`: 898 PASS; krytyczne regresje API/lifecycle/shell: 146 PASS; lifecycle UI: 18 PASS, również rzeczywiste lekkie procesy i podmiana ownership.
- `mypy venom_core`: 479 plików PASS; typowanie kontrolera/rollbacku PASS. Architektura, katalog/grupy testów, PL/EN/DE i normalne hooki PASS.
- Produkcyjny build Studio z Turbopack PASS: wyłącznie root, Chat 2.0 i trasy błędów. Przeglądarka: 58 asercji PASS na atrapach API/audio, bez prawdziwego modelu i mikrofonu oraz bez błędów hydratacji/aplikacji.
- Wszystkie 18 różnych operacji użytych przez przeglądarkę ma odpowiednik w rzeczywistym OpenAPI Studio. Worklet nagrywania HTTP 200 i identyczne bajty ze wspólnym źródłem. Pięć starych tras UI zwraca 404; brak starego menu/linku.
- Rzeczywisty start Full/dev/Turbo i DOM starego czatu PASS. Start Studio/dev/Turbo oraz pasywny DOM/API i zachowany model PASS. Oba polecenia stop wyłączyły własne UI/API/Ollamę i modele. Studio uruchomiono ponownie i pozostawiono działające lokalnie.
- Istniejącą historię odczytano przez Studio z tego samego SessionStore. Skróty prywatnych `.env` i wybrany model pozostały bez zmian.

Odbiór wykrył zagnieżdżony alias npm gubiący port UI; poprawkę dla Turbo/debug
pokrywają regresje rzeczywistego npm. Zastaną systemową Ollamę z modelami tego
projektu zatrzymano po potwierdzeniu właściciela; dalsze start/stop używają już
skonfigurowanej usługi użytkownika. Nie podmieniano konfiguracji usług ani modeli.

## Obserwacja pamięci

Ta sama lokalna instalacja Full, dev/Turbo, ten sam zapisany model Ollama;
odczyty metadanych czatu, bez załadowanych wag LLM i generacji w obu próbach.
PSS listenera i potomków, zaokrąglone MiB:

| Grupa | Venom | Studio |
| --- | ---: | ---: |
| UI/proxy | 455,2 | 564,5 |
| API | 2466,2 | 172,7 |
| Serwer Ollama bez modelu | 35,2 | 35,4 |
| Razem | 2956,6 | 772,6 |

Zaobserwowano spadek sumy o około 2,13 GiB (74%), głównie przy starcie API.
Sam web developerski nie wykazał poprawy w tej próbie. Migawki całego Windows:
25,22 i 23,57 GiB zajętego RAM; tło, cache WSL i stan przeglądarek nie pozwalają
traktować różnicy jako kontrolowanego benchmarku aplikacji.

To stan bezczynności/startu. Istniejący ingest pamięci Direct, Normal/MAF i pierwsze
użycie audio mogą doładować wspólne cięższe usługi. Nie dodawano nowego RAG,
treningu ani ekranów diagnostycznych. Live provider test zero, realny mikrofon,
ruch robota, osobna instalacja Light i pełny odbiór preprod/prod pozostają poza
odbiorem. Pasywna przeglądarka zgłosiła wyłącznie brak favicon, bez błędu aplikacji
lub hydratacji. Inicjalizacja Rider pozostaje osobną naprawą.
