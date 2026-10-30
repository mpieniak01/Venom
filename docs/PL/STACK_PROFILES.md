# Full/Light i środowiska Venoma

Jedno wejście operatora:

```bash
make start PROFILE=full ENVIRONMENT=dev
make start PROFILE=light ENVIRONMENT=dev
make start PROFILE=full ENVIRONMENT=preprod
make start PROFILE=light ENVIRONMENT=preprod
make stack-plan PROFILE=full ENVIRONMENT=preprod
make status ENVIRONMENT=preprod
make stop ENVIRONMENT=preprod
```

Full/dev pozostaje domyślny. Oba profile używają obecnego stosu i Turbopacka.
Środowisko prod pozostaje zarezerwowane i nieużywane; nie jest kwalifikowane
przez samą obecność celu start-prod.

| Ustawienie | Full | Light |
| --- | --- | --- |
| Silnik/model, GPU i jakość głosu | Wybór operatora | Ten sam wybór operatora |
| Funkcje interaktywne i health checks | Konfiguracja środowiska | Konfiguracja środowiska |
| Automatyczna dokumentacja/gardening i zadania tła | Konfiguracja środowiska | Wstrzymane |
| Warmup LLM | Konfiguracja środowiska | Wyłączony |

Light ogranicza pracę tła, nie gwarantuje mniejszego RAM przy tej samej gotowości
audio i modelu. Nie odinstalowuje zależności, nie wybiera Ollamy ani modelu.
Zmiana profilu wymaga zatrzymania i uruchomienia tego samego środowiska.
Panel konfiguracji nie uruchamia przy tej operacji innego silnika.

## Izolacja

Dev zachowuje istniejące ścieżki i dane. Preprod używa własnego pliku .env,
baz, logów, pamięci, workspace, cache, kolejek, stanu providerów oraz PID-ów.
Zapis danych preprod jest wyłączony; backup/restore mają osobną jawną ścieżkę.
Full i Light w tym samym środowisku korzystają z tych samych danych.

Domyślne porty repo: dev API/UI 8000/3000, preprod 8100/3100.
Lokalny launcher instancji może mieć własne porty i narzędzia; nie zastępować
jego konfiguracji domyślnymi portami repo. NEXT_DIST_DIR wynosi .next dla dev
oraz .next-preprod dla preprod. Konflikt ścieżek, namespace, proxy lub listenera
kończy start błędem. API_PROXY_TARGET musi wskazywać API wybranego środowiska;
przeglądarka korzysta z proxy tego samego originu.

Plan pokazuje wyłącznie dozwolone pola konfiguracji, bez kluczy API.
Nie kopiuje danych ani plików z sekretami. Stare wspólne ścieżki w prywatnym
.env.preprod wymagają jawnej korekty przed startem; resolver ich nie przenosi.

Stop dotyczy wyłącznie procesów wybranego środowiska, zweryfikowanych po
tożsamości i czasie utworzenia PID. Nie zatrzymuje współdzielonego LLM,
kontenerów ani innego środowiska. Dwa starty korzystają ze wspólnej blokady
od sprawdzenia silnika do gotowości stosu, a rejestr właścicieli uwzględnia
również niestandardowe ścieżki PID. Inny aktywny lokalny silnik powoduje błąd.
Świadome zarządzanie usługą LLM pozostaje osobną operacją operatora.

Przy pierwszej migracji działających procesów bez rekordów tożsamości nie ma
automatycznej adopcji. Najpierw sprawdzić listener, PID/cwd, właściciela,
komendę oraz aktywne zadania; zatrzymać tylko potwierdzony stary stos i
uruchomić go nowym launcherem. Nie używać starego globalnego kill/stop do
migracji dwóch równoległych środowisk.

## Nazwy przejściowe i narzędzia

| Stara nazwa | Docelowe użycie |
| --- | --- |
| start-dev, start-dev-turbo, start2 | start PROFILE=full ENVIRONMENT=dev |
| start-lowmem i start_stack_low_memory.sh | start PROFILE=light; zachować środowisko |
| start-preprod, startpre | start ENVIRONMENT=preprod |
| stoppre, statuspre, restartpre | stop/status/restart ENVIRONMENT=preprod |
| privacy/local, beast/extended | light, full |
| api/cloud/llm_off jako profil | Light + jawne ACTIVE_LLM_SERVER=none; provider osobno |

Aliasy delegują do wspólnego mechanizmu i mają zostać usunięte po następnym
wydaniu oraz migracji konfiguracji. Webpack i turbo-debug pozostają opcjami
diagnostycznymi tego samego lifecycle, bez dodatkowego profilu aplikacji.
Cele api/web są narzędziami komponentowymi i stosują ten sam resolver
środowiska. [Budowanie UI](WEB_LIFECYCLE.md) oddziela build od startu zgodnego
artefaktu; sam komunikat o utworzeniu PID nie oznacza gotowości.

Manifesty light/full opisują instalowane funkcje. CI i build są dodatkami
narzędziowymi, multi-runtime-cuda osobnym komponentem wymagającym izolacji.
Historyczne pliki requirements-profile-api/web są aliasami instalacyjnymi
Light, nie kolejnymi aplikacjami ani uruchomionymi profilami.
Nie tworzyć nowego venv tylko dla innego środowiska lub nazwy.

[Docker](DOCKER_PROFILES.md) jest recepturą dystrybucji z tym samym podziałem
Full/Light i dev/preprod. Istniejący obraz Light nie staje się pełnym obrazem
Full po zmianie etykiety. Nie kwalifikowano tu jego pełnych funkcji ani prod.

Automaty używają atrap providerów. Rzeczywisty Test Zero wymaga osobnego
zlecenia na każde uruchomienie, także po wdrożeniu.
