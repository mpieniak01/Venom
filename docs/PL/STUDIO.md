# Venom i Studio: warianty aplikacji

Venom i Studio to dwa warianty aplikacji w tym samym repozytorium. Venom zachowuje
obecne ekrany i pełne API. Studio udostępnia Chat 2.0 z własnej aplikacji Next.js
i mniejszego punktu wejścia FastAPI. Oba używają wspólnego kodu rozmowy, adapterów
dostawców i danych wybranego środowiska.

Instrukcja obejmuje API Studio, osobny frontend, uruchamianie/przełączanie
oraz zweryfikowane zatrzymanie. Zobacz [ADR-004](adr/ADR-004-studio-runtime-composition.md)
i [funkcje oraz limity rozmowy](CHAT_2.md).

## Wybór i przełączanie

Polecenia wykonuj w skonfigurowanym repozytorium z istniejącymi zależnościami.
Przykłady zakładają zatrzymaną instancję developerską i domyślne ustawienia repo.
Zainstalowany launcher może mieć własne narzędzia, porty i rekordy właścicieli:
stosuj jego procedurę, bez zastępowania tych ustawień.

```bash
make start-venom PROFILE=full ENVIRONMENT=dev
make status-venom ENVIRONMENT=dev
make stop-venom ENVIRONMENT=dev

make start-studio PROFILE=full ENVIRONMENT=dev
make status-studio ENVIRONMENT=dev
make stop-studio ENVIRONMENT=dev
```

Przed uruchomieniem drugiego wariantu zatrzymaj obecnego właściciela. Oba warianty
używają danych tego samego środowiska i wspólnych lokalnych zasobów runtime.
Aktywny inny właściciel lub niezweryfikowany listener blokuje zmianę. Powrót:
zatrzymaj Studio i uruchom Venoma w tym samym środowisku; bez migracji i kasowania.

| Wybór | Venom | Studio |
| --- | --- | --- |
| Katalog UI | `web-next` | `web-studio` |
| Wejście ASGI | `venom_core.main:app` | `venom_core.studio_main:app` |
| Trasy web | Dotychczasowa aplikacja | `/` przekierowuje na `/chat2`; tylko Chat 2.0 |
| Flaga Chat 2.0 | Jawny wariant ustawia `false` | Wariant włącza własne wejście rozmowy |
| Dane serwera | Wybrane środowisko | To samo środowisko, bez drugiego katalogu danych |

Otwórz adres UI podany przez launcher. Domyślne porty repo to UI/API 3000/8000
w dev oraz 3100/8100 w preprod. Studio nie ma klasycznego `/chat` ani linku do
niego. Opcjonalne `/chat2` wewnątrz obecnego frontendu Venoma pozostaje osobną
ścieżką zgodności opisaną w [Chat 2.0](CHAT_2.md).

Wariant aplikacji, Full/Light i środowisko są niezależnymi wyborami:

```bash
make start-studio PROFILE=light ENVIRONMENT=dev
make start-studio PROFILE=full ENVIRONMENT=preprod
make stack-plan VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=preprod
```

Przed zmianą środowiska lub profilu zatrzymaj aktywnego właściciela. Dev/preprod
zachowują oddzielne konfiguracje, bazy, logi, storage, namespace cache/kolejek
i stan dostawców. Preprod nadal działa tylko do odczytu; Studio nie zmniejsza
tej ochrony. Prod pozostaje nieużywany. Nie kopiuj prywatnych plików ani sekretów.

## Wspólne kontrakty, osobne artefakty

Studio montuje podzbiór istniejących funkcji endpointów, schematów i zależności.
Direct, obsługiwane Normal/MAF, wybór runtime/modelu, wyceny OpenRouter,
materiały, historia sesji, Stop rozmowy i STT/TTS zachowują wspólne reguły
admission, origin, budżetów i anulowania. Pozostałe endpointy Full są nieobecne;
Studio nie przekazuje ich po cichu do innego API.
Wspólny zapis motywu nadal używa `GET`/`POST /api/v1/config/runtime` z obecną
ochroną localhost Full; nie kopiujemy osobnego ekranu konfiguracji.

`MEMORY_ROOT`, pliki stanu, SessionStore, identyfikatory materiałów i stan dostawcy
pozostają własnością środowiska. Przełączenie nie migruje, nie klonuje i nie kasuje
danych. Frontend korzysta ze wspólnych providerów/kontrolera i kluczy przeglądarki.
Szkice i aktywna sesja należą do originu: inny adres UI ma osobny storage,
a nowy build może utworzyć nowy bieżący wątek. Zapisaną sesję wybierz z listy
rozmów; storage przeglądarki nie jest kopią zapasową historii serwera.

Studio współdzieli komponenty Chat 2.0, fonty i globalne style, lecz ma własne
drzewo tras, artefakt Next, cache dev i zasoby publiczne. Korzysta z istniejącego
`web-next/node_modules`, bez drugiej instalacji. Przygotowanie tworzy metadane
Studio i kopiuje wymagany worklet nagrywania ze wspólnego źródła, odświeżając go
po zmianie. Obie aplikacje używają wspólnego proxy i mechanizmu obsługi artefaktów.

Jawny build wykonuj z katalogu repozytorium, gdy to UI jest zatrzymane:

```bash
make web-build VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=preprod
```

Artefakt musi odpowiadać źródłom/wspólnym wejściom, konfiguracji publicznej,
wersji Node i środowisku. Start nie wykonuje ukrytego rebuilda. Nie przebudowuj
artefaktu aktywnego UI. Zobacz [cykl życia UI](WEB_LIFECYCLE.md).

## Inicjalizacja na żądanie i pamięć

Studio pomija zbędne dla rozmowy usługi startowe Full i rejestrację modułów
opcjonalnych. Nie dodaje RAG, treningu, ekranów, kolejki ani systemu danych.
Dotychczasowa pamięć pozostaje dostępna przez wspólne handlery.

- Direct startuje bez tworzenia orkiestracji. Dotychczasowy memory/ingest po
  zakończonej turze może na żądanie utworzyć istniejący VectorStore.
- Pierwsze obsługiwane Normal/MAF tworzy obecny Orchestrator, dispatcher
  i wymagane zależności pamięci/wykonania. Nie powstaje inny MAF.
- STT/TTS tworzy skonfigurowany AudioEngine przy pierwszym użyciu, bez warmup
  modeli mowy przy starcie. Wejście na stronę nie pyta o mikrofon.
- Lokalne procesy LLM/modele podlegają obecnej konfiguracji i admission. Wybór
  API nie dodaje drugiego automatycznego loadera ani zgody na płatne wywołania.

Start mierz oddzielnie od stanu po ingest, Normal/MAF i głosie: te operacje mogą
doładować cięższe komponenty. Mniejsza liczba tras nie dowodzi oszczędności RAM,
mniejszych opóźnień ani gotowości prod. Wspólne globalne CSS i instalacja
zależności pozostają jawnymi granicami rozwiązania.

## Zweryfikowane zatrzymanie

Używaj stop właściwego wariantu i środowiska. `stop-venom`/`stop-studio` zatrzymują
zweryfikowanych właścicieli UI/API oraz skonfigurowane lub zapisane własne
lokalne silniki. Przed sygnałem sprawdzają tożsamość i rekordy własności.
Obce, podmienione i nieweryfikowalne rekordy powodują błąd zamiast przejęcia po
nazwie procesu lub porcie. Wyjaśnij konflikt przed zmianą wariantu.

Historyczne `make stop` pozostaje węższym zatrzymaniem API/UI środowiska;
nie zastępuje jawnego teardown wariantu. Nie stosuj globalnego zabijania po
nazwie procesu. Lokalny stop nie niszczy kont dostawcy ani wynajętych instancji
chmurowych. Anulowane płatne żądanie może zachować oczekujący koszt dostawcy.

Zamykanie API Studio czeka na istniejącą kolejkę/aktywne zadania i natywne czyszczenie przed
zwolnieniem własnych zasobów. Status PID nie potwierdza oddania pamięci modelu.
Ochrona rekordów zakłada zapisy serializowane przez launcher; nie jest ogólnym
atomowym compare-and-swap systemu plików.

## Granica kwalifikacji

Testy na atrapach sprawdzają kod i lifecycle, nie prawdziwy mikrofon, jakość
modelu, płatnego dostawcę ani wdrożenie prod. Instrukcja nie stwierdza wykonania
buildu, bramek wydania czy kwalifikacji prawdziwego dostawcy. Stosuj zapisany
odbiór badanej rewizji. Każdy prawdziwy Test Zero wymaga osobnego zlecenia według
[polityki dostawców](PROVIDER_TEST_ZERO_POLICY.md).

[English guide](../STUDIO.md)

Wyniki lokalnej kwalifikacji i ograniczenia pomiaru: [odbiór Studio](STUDIO_ACCEPTANCE.md).
