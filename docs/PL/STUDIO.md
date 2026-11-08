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
a zmianę buildu lub restart przeżywa wątek z historią zapisaną na serwerze.
Lista rozmów w Studio także należy do originu przeglądarki.
Storage przeglądarki nie jest kopią zapasową historii serwera.

Studio współdzieli komponenty Chat 2.0, fonty i globalne style, lecz ma własne
drzewo tras, artefakt Next, cache dev i zasoby publiczne. Korzysta z istniejącego
`web-next/node_modules`, bez drugiej instalacji. Przygotowanie tworzy metadane
Studio i kopiuje wymagany worklet nagrywania ze wspólnego źródła, odświeżając go
po zmianie. Obie aplikacje używają wspólnego proxy i mechanizmu obsługi artefaktów.

Jawny build wykonuj z katalogu repozytorium, gdy to UI jest zatrzymane:

```bash
make web-build VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=dev
LLM_MODEL_NAME=gemma4:e4b make start-studio PROFILE=full ENVIRONMENT=dev START_WEB_MODE=standalone
```

Ten wybór jest dostępny dla Studio w dev. Zwykłe `make start-studio` używa
Turbopacka do pracy nad kodem. Obie komendy korzystają z danych dev.

Artefakt musi odpowiadać źródłom/wspólnym wejściom, konfiguracji publicznej,
wersji Node i środowisku. Start nie wykonuje ukrytego rebuilda. Nie przebudowuj
artefaktu aktywnego UI. Zobacz [cykl życia UI](WEB_LIFECYCLE.md).

## Studio do codziennej pracy

Studio ładuje jeden wybrany lokalny model Ollamy przed zgłoszeniem gotowości
API, jeśli `LLM_WARMUP_ON_STARTUP` jest włączone. Próba trwa maksymalnie 30 s.
Jeżeli model jest niedostępny, start kończy się z komunikatem w logu, a silnik
można wybrać w czacie. Uruchomienie nie rozgrzewa dostawców zdalnych.

Domyślne strojenie launchera Studio to 4096 tokenów kontekstu, jedna generacja
naraz i jeden załadowany model Ollamy. Jawne ustawienia mają pierwszeństwo.
Venom również zaczyna z jedną generacją naraz i korzysta ze swojego profilu
kontekstu dla dłuższych zadań. Środowiska dev i preprod zachowują własne dane
i zasady zapisu.

| Tryb | Użycie zasobów |
|---|---|
| Direct | Wspólny strumień i historia w SessionStore. Obrazy i pliki po dołączeniu. Indeksowanie przez jawny zapis notatki. |
| Normal | Lekka rozmowa tekstowa z historią przez lokalną Ollamę. Notatki na żądanie, z wyszukaniem jednoznacznego źródła po nazwie w LanceDB. Dopasowanie semantyczne ładuje embeddingi. |
| Głos | AudioEngine uruchamia się przy pierwszej transkrypcji lub syntezie. Kolejne tury korzystają z rozgrzanego audio. |
| MAF i narzędzia | Orchestrator i agenci uruchamiają się przy pierwszym takim żądaniu. |
| Venom Full | Pełne ekrany i API do zadań wieloetapowych, rozwoju i diagnostyki. Wspólne notatki i historia w tym samym środowisku. |

Do codziennej pracy wystarczy:

```bash
make start-studio PROFILE=full ENVIRONMENT=dev
```

Dla porównania można jawnie przywrócić wcześniejsze zachowanie webu przez
`NEXT_PUBLIC_STUDIO_DIRECT_AUTO_INDEX=1` lub `NEXT_PUBLIC_STUDIO_LIGHT_NORMAL=0`.
Ustaw te flagi również podczas budowania prekompilowanego UI.

### Embeddingi w osobnym procesie

Przy sporadycznym wyszukiwaniu semantycznym można w Linuksie lub WSL wybrać
`STUDIO_EMBEDDING_PROCESS=1`. Proces uruchamia się na żądanie i kończy po
`STUDIO_EMBEDDING_IDLE_SECONDS`. W tym trybie zero oznacza 120 s. Po wygaśnięciu
pierwsze wyszukiwanie semantyczne czeka na załadowanie modelu. Opcja jest
domyślnie wyłączona, żeby kolejne wyszukania w sesji były płynne.

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
