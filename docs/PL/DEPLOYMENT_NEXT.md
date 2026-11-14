# Wdrożenie Venoma 1.10.0 w Linuksie lub WSL2

[English version](../DEPLOYMENT_NEXT.md) · [README projektu](../../README_PL.md)

Używaj `dev` do pracy jednego operatora i rozwoju. Środowisko `preprod` służy do odizolowanego odbioru w trybie tylko do odczytu. Środowisko `prod` pozostaje zarezerwowane. Jeśli masz już launcher instancji, zachowaj jego ścieżkę do repozytorium, pliki środowiskowe, katalogi danych i porty. [Wsparcie środowisk](ENVIRONMENTS_SUPPORT.md)

## Instalacja ze źródeł

W Linuksie x86-64, w tym w dystrybucji WSL2 na x86-64, użyj **Pythona 3.14.8**, **Node.js 24.22.0** i **npm 11.19.1**. Zainstaluj Git, GNU Make i curl. Full potrzebuje też kompilatora C i nagłówków wejścia Linuksa do zbudowania `evdev`. W Debianie lub Ubuntu zapewniają je pakiety `build-essential` i `linux-libc-dev`. Zainstaluj wskazane wersje Pythona i Node.js przed wykonaniem poniższych poleceń.

```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom
python3.14 --version
node --version
npm --version
python3.14 scripts/bootstrap_dependency_profile.py --profile full --venv "$PWD/.venv"
npm --prefix web-next ci
make ensure-env-file ENVIRONMENT=dev
```

Skrypt tworzy nowe środowisko wirtualne przy użyciu uruchamiającego go interpretera i instaluje zależności z locka Full. Sprawdza też wolne miejsce. Instalacja Full wymaga co najmniej 16 GiB wolnych w miejscu instalacji. Zostaw dodatkowe miejsce na modele Ollamy, dane i artefakty web. Obie aplikacje używają jednej instalacji `web-next/node_modules`. Przy aktualizacji istniejącej instancji sprawdź nowy profil w osobnym środowisku wirtualnym przed przełączeniem. [Profile zależności i stan kwalifikacji](../DEPENDENCY_PROFILES.md)

## Konfiguracja Ollamy i modelu lokalnego

Uruchom Ollamę na hoście z Linuksem i przygotuj Gemmę 4 E4B. Jeśli Ollama używa innego adresu, ustaw `OLLAMA_HOST` dla poleceń CLI.

```bash
curl -fsS http://127.0.0.1:11434/api/version
ollama pull gemma4:e4b
ollama list
```

Dla domyślnego adresu Ollamy wpisz poniższe ustawienia do `.env.dev`. Trzymaj dane dostępowe i ustawienia konkretnej maszyny w prywatnym pliku środowiskowym.

```dotenv
ACTIVE_LLM_SERVER=ollama
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://127.0.0.1:11434/v1
LLM_MODEL_NAME=gemma4:e4b
```

## Uruchomienie Studio lub Venom Full

Studio uruchamia osobną aplikację Next.js (`web-studio`) i podzbiór wspólnego API FastAPI (`venom_core.studio_main:app`). Venom Full uruchamia `web-next` i `venom_core.main:app`. Oba w domyślnym starcie dev korzystają z Turbopacka. Aby ograniczyć nasłuchiwanie do interfejsu lokalnego, wykonaj `export HOST=127.0.0.1 WEB_HOST=127.0.0.1` w powłoce używanej do startu, sprawdzania statusu i zatrzymywania.

Wykonaj blok dla wybranej aplikacji. Launcher wypisuje adresy interfejsu i API. Domyślne porty repozytorium dla dev to `3000` dla interfejsu i `8000` dla API.

### Studio

```bash
make stack-plan VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=dev
make start-studio PROFILE=full ENVIRONMENT=dev
make status-studio PROFILE=full ENVIRONMENT=dev
curl -fsS http://127.0.0.1:8000/healthz
```

Otwórz [Chat 2.0](http://localhost:3000/chat2) i wyślij krótką wiadomość w Direct. Po zakończeniu zatrzymaj Studio z tego samego katalogu i z tymi samymi ustawieniami.

```bash
make stop-studio PROFILE=full ENVIRONMENT=dev
```

### Venom Full

```bash
make stack-plan VENOM_VARIANT=venom PROFILE=full ENVIRONMENT=dev
make start-venom PROFILE=full ENVIRONMENT=dev
make status-venom PROFILE=full ENVIRONMENT=dev
curl -fsS http://127.0.0.1:8000/healthz
```

Otwórz [czat](http://localhost:3000/chat) lub [głos](http://localhost:3000/voice). Po zakończeniu zatrzymaj Venom Full.

```bash
make stop-venom PROFILE=full ENVIRONMENT=dev
```

Zatrzymaj działający wariant przed uruchomieniem drugiego. W tym samym środowisku launchery zachowują historię po stronie serwera, materiały i notatki. Szkice przeglądarki zależą od adresu interfejsu. Polecenia zatrzymania dla konkretnego wariantu zamykają także lokalny silnik, gdy launcher nim zarządza i może potwierdzić jego tożsamość. Osobno zarządzana Ollama działa dalej jako niezależna usługa. Jeśli zmieniasz porty, ścieżki lub adresy nasłuchiwania, podawaj te same ustawienia przy statusie i zatrzymaniu. [Własność procesów i przełączanie](STUDIO.md)

## Konfiguracja głosu

Po instalacji zależności Full ustaw `ENABLE_AUDIO_INTERFACE=true` w `.env.dev`. Do syntezy w ścieżce Gemmy wpisz w `TTS_MODEL_PATH` bezwzględną ścieżkę do pliku `.onnx` z głosem Piper i umieść odpowiadający mu `.onnx.json` obok. Rozmiar modelu Whispera wybierz przez `WHISPER_MODEL_SIZE`. Aby używać CPU do głosu, ustaw jednocześnie `AUDIO_DEVICE=cpu` i `TTS_USE_CUDA=false`. Do pracy na GPU zainstaluj biblioteki CUDA wymagane przez wybrane zależności. [Zależności audio](../DEPENDENCY_PROFILES.md)

Aby wypróbować Omni, wykonaj `ollama pull lfm3-omni:2b` dla Ollamy nasłuchującej na interfejsie lokalnym hosta Venoma. Użyj wersji Ollamy obsługującej natywne wejście i wyjście audio dla tego modelu. Wybierz go w Chat 2.0 lub na ekranie głosu w Full. Dla natywnej ścieżki pozostaw automatyczny routing (`VOICE_ROUTE_PROFILE=auto`, `AUDIO_DECODER_PROFILE=auto` i pusty `AUDIO_DECODER_CHAIN`). Zastosuj ustawienia startowe przez ponowne uruchomienie aktywnego wariantu, zezwól przeglądarce na dostęp do mikrofonu i sprawdź transkrypcję oraz odtwarzanie. Pomiary konkretnego hosta zachowaj w prywatnym raporcie lokalnym.

## Profile uruchomieniowe i odizolowany odbiór

`PROFILE=light` wstrzymuje zadania tła i pomija rozgrzewanie modelu. Może korzystać z już zainstalowanych zależności Full. Lock Light służy do API i podstawowego czatu. Jeśli potrzebujesz obu zestawów zależności, zainstaluj Light w osobnym środowisku wirtualnym i podawaj ten sam `VENV` przy starcie, sprawdzaniu statusu i zatrzymaniu. Dla Studio z zależnościami Light zatrzymaj działający wariant i przygotuj `.env.dev` oraz wspólne zależności web, a następnie wykonaj poniższe polecenia.

```bash
python3.14 scripts/bootstrap_dependency_profile.py --profile light --venv "$PWD/.venv-light"
make start-studio PROFILE=light ENVIRONMENT=dev VENV=.venv-light
make status-studio PROFILE=light ENVIRONMENT=dev VENV=.venv-light
```

```bash
make stop-studio PROFILE=light ENVIRONMENT=dev VENV=.venv-light
```

[Profile stosu](STACK_PROFILES.md) · [Profile zależności](../DEPENDENCY_PROFILES.md)

Do odbioru tylko do odczytu zatrzymaj działający wariant i utwórz `.env.preprod` z jego własnego szablonu.

```bash
make ensure-env-file ENVIRONMENT=preprod
```

Skonfiguruj dostawcę w `.env.preprod`, jeśli próba wymaga inferencji. Preprod ma własne dane, cache, kolejki, logi i artefakty web. Domyślne porty interfejsu i API to `3100` i `8100`.

```bash
make stack-plan VENOM_VARIANT=venom PROFILE=full ENVIRONMENT=preprod
make start-venom PROFILE=full ENVIRONMENT=preprod
make status-venom PROFILE=full ENVIRONMENT=preprod
curl -fsS http://127.0.0.1:8100/healthz
make stop-venom PROFILE=full ENVIRONMENT=preprod
```

Dla Studio w preprod wybierz `VENOM_VARIANT=studio` w planie oraz polecenia `*-studio` z `ENVIRONMENT=preprod`. Przy niestandardowych portach korzystaj z adresów wskazanych przez launcher. [Zasady preprod](ENVIRONMENTS_SUPPORT.md)

## Budowanie Studio do uruchomienia standalone

Zatrzymaj interfejs przed budowaniem. Użyj tego samego profilu, środowiska i ustawień publicznych przy budowaniu i starcie. Po zmianie źródeł, ustawień publicznych lub wersji Node.js zbuduj aplikację ponownie.

```bash
make web-build VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=dev
make start-studio PROFILE=full ENVIRONMENT=dev START_WEB_MODE=standalone
```

[Cykl budowania i uruchamiania web](WEB_LIFECYCLE.md)

## Odbiór i obsługa

- Sprawdź status wybranego wariantu i `/healthz`. Wyślij wiadomość w Direct, aby sprawdzić model i dostawcę. Endpoint zdrowia potwierdza działanie procesu.
- Jeśli głos jest włączony, nagraj krótkie pytanie i sprawdź, czy przeglądarka odtwarza odpowiedź.
- Użyj `make stack-plan`, aby odczytać porty oraz ścieżki danych i logów. Przy błędzie startu sprawdź logi backendu i web. Domyślne katalogi to `logs/` w dev i `logs/preprod/` w preprod.
- Użyj `make runtime-log-policy-audit`, aby sprawdzić ustawienia retencji i rotacji. [Kopie zapasowe i izolacja środowisk](ENVIRONMENTS_SUPPORT.md)
- Obecne obrazy kontenerowe używają zestawu zależności Light. [Profile Dockera](DOCKER_PROFILES.md) opisują budowanie lokalne, a [przewodnik wydań Dockera](DOCKER_RELEASE_GUIDE.md) pracę z obrazami oznaczonymi tagami.
