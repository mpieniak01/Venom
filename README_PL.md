# Venom 1.10.0

[![GitGuardian](https://img.shields.io/badge/security-GitGuardian-blue)](https://www.gitguardian.com/)
[![OpenAPI Contract](https://img.shields.io/github/actions/workflow/status/mpieniak01/Venom/ci.yml?branch=main&logo=swagger&logoColor=white&label=OpenAPI%20Contract)](https://github.com/mpieniak01/Venom/actions/workflows/ci.yml)
[![SonarCloud Quality](https://sonarcloud.io/api/project_badges/measure?project=mpieniak01_Venom&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=mpieniak01_Venom)
[![Known Vulnerabilities](https://snyk.io/test/github/mpieniak01/Venom/badge.svg)](https://snyk.io/test/github/mpieniak01/Venom)

[English version](README.md) · [Opublikowane wydania](https://github.com/mpieniak01/Venom/releases)

Venom to otwarty stos AI dla jednego operatora. Pozwala lokalnie prowadzić czat, analizować dokumenty i obrazy oraz rozmawiać głosowo. Pełna aplikacja obsługuje również pracę agentów, narzędzia i diagnostykę. Gałąź `main` używa wersji **1.10.0**. Paczki oznaczone tagami i opis zmian znajdziesz w opublikowanych wydaniach.

## Wybór aplikacji

| | Venom Studio | Venom Full |
| --- | --- | --- |
| Gdzie zacząć | Chat 2.0 pod `/chat2` | Czat pod `/chat`, głos pod `/voice` |
| Co uruchamia | Osobny frontend i podzbiór wspólnego API do czatu, materiałów, głosu i wyboru modelu | Pełny frontend i API z obsługą agentów, narzędzi, konfiguracji i diagnostyki |
| Tryby czatu | Direct i Normal | Direct, Normal i Complex |

**Direct** przekazuje bieżącą rozmowę do wybranego modelu. **Normal** dodaje routing, a **Complex** obsługuje wieloetapową pracę agentów. W Chat 2.0 możesz włączyć **Użyj notatek** dla bieżącego pytania w Normal lub użyć **Zapisz jako notatkę** przy wybranej odpowiedzi. Historia rozmowy zapisuje się osobno. Obie aplikacje współdzielą dane po stronie serwera w tym samym środowisku. [Instrukcja operatora czatu](docs/PL/CHAT_OPERATOR.md) · [Uruchamianie Studio](docs/PL/STUDIO.md)

Orkiestracja agentów korzysta z Microsoft Agent Framework. Szybki start używa lokalnej Ollamy. Czat tekstowy w Direct może też korzystać z [OpenRoutera](docs/OPENROUTER_LOCAL_MVP.md) lub [Ollamy na Vast](docs/PL/VAST_START_I_ODZYSKIWANIE.md).

## Szybki start w Linuksie lub WSL2

Potrzebujesz Linuksa x86-64, **Pythona 3.14.8**, **Node.js 24.22.0**, **npm 11.19.1** oraz działającej usługi Ollama. [Przewodnik wdrożeniowy](docs/PL/DEPLOYMENT_NEXT.md) opisuje zależności systemowe, uruchamianie głosu i obsługę zainstalowanej instancji.

```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom
python3.14 scripts/bootstrap_dependency_profile.py --profile full --venv "$PWD/.venv"
npm --prefix web-next ci
make ensure-env-file ENVIRONMENT=dev
ollama pull gemma4:e4b
```

Ustaw poniższe wartości w `.env.dev` dla Ollamy działającej na tym samym hoście z Linuksem.

```dotenv
ACTIVE_LLM_SERVER=ollama
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://127.0.0.1:11434/v1
LLM_MODEL_NAME=gemma4:e4b
```

Uruchom **Studio** i otwórz `/chat2` pod adresem interfejsu wypisanym przez launcher. Domyślna konfiguracja repozytorium używa [http://localhost:3000/chat2](http://localhost:3000/chat2).

```bash
make start-studio PROFILE=full ENVIRONMENT=dev
make status-studio PROFILE=full ENVIRONMENT=dev
```

Aby uruchomić **Venom Full**, najpierw zatrzymaj Studio. Otwórz [czat](http://localhost:3000/chat) lub [głos](http://localhost:3000/voice) pod adresem wskazanym przez launcher.

```bash
make stop-studio PROFILE=full ENVIRONMENT=dev
make start-venom PROFILE=full ENVIRONMENT=dev
make status-venom PROFILE=full ENVIRONMENT=dev
```

```bash
make stop-venom PROFILE=full ENVIRONMENT=dev
```

Przykłady korzystają z pełnego zestawu zależności, żeby można było później skonfigurować głos. Wariant aplikacji, profil uruchomieniowy Full/Light i środowisko dev/preprod to trzy osobne wybory. Do pracy lokalnej służy `dev`, a do odizolowanej weryfikacji tylko do odczytu `preprod`. [Profile stosu](docs/PL/STACK_PROFILES.md) · [Profile zależności](docs/DEPENDENCY_PROFILES.md)

## Wyniki polskiego benchmarku multimodalnego

Porównaliśmy bazową **Gemmę 4 E4B** i **LFM3-Omni-2B** na zamrożonym zbiorze `pl-assistant-v1`. Każdy profil przeszedł 200 scenariuszy z tekstem referencyjnym i 80 dodatkowych prób z nagraniami. Oba korzystały z pakietów Q4_K_M w Ollamie 0.40.14 na tej samej karcie RTX 3060 z 12 GiB VRAM pod WSL2. Gemma w tym pomiarze korzystała z Whispera i Pipera. Omni używał natywnego rozpoznawania i syntezy mowy.

| Pomiar | `gemma4:e4b` | `lfm3-omni:2b` |
| --- | ---: | ---: |
| Ściśle zaliczone próby | **254/280 (90,71%)** | 209/280 (74,64%) |
| Szczytowe użycie pamięci całej karty | 9 741 MiB | **7 962 MiB** |
| Mediana czasu do gotowego WAV dla ośmiu nagranych poleceń | 0,951 s | **0,511 s** |

Gemma częściej spełniała ścisłe kryteria odpowiedzi. Omni w tym pomiarze zużył mniej VRAM i szybciej zwracał plik WAV. Raport zawiera też wyniki według rodzaju zadania, czasy rozpoczęcia odtwarzania w przeglądarce i osobny odbiór Full po zmianach w natywnym rozpoznawaniu mowy Gemmy. [Raport PL](docs/PL/POLISH_MULTIMODAL_ASSISTANT_EXPERIMENT.md) · [Raport EN](docs/EN/POLISH_MULTIMODAL_ASSISTANT_EXPERIMENT.md)

## Dokumentacja

- **Obsługa i wdrożenie** · [Przewodnik wdrożeniowy](docs/PL/DEPLOYMENT_NEXT.md) · [Chat 2.0](docs/PL/CHAT_2.md) · [Wsparcie środowisk](docs/PL/ENVIRONMENTS_SUPPORT.md) · [Wydania Dockera](docs/PL/DOCKER_RELEASE_GUIDE.md)
- **Obsługa pełnej aplikacji** · [Kokpit](docs/PL/DASHBOARD_GUIDE.md) · [Panel konfiguracji](docs/PL/CONFIG_PANEL.md) · [Instrukcja operatora czatu](docs/PL/CHAT_OPERATOR.md)
- **Modele i dostawcy** · [OpenRouter](docs/OPENROUTER_LOCAL_MVP.md) · [Vast i Ollama](docs/PL/VAST_START_I_ODZYSKIWANIE.md) · [Introspekcja modeli](docs/PL/MODEL_INTROSPECTION_GUIDE.md) · [Pilot Gemmy E4B](docs/PL/GEMMA4_E4B_PILOT.md)
- **Narzędzia i rozwój** · [Użycie narzędzi](docs/PL/TOOLS_USAGE_GUIDE.md) · [Integracje](docs/PL/INTEGRATIONS_OVERVIEW.md) · [Architektura backendu](docs/PL/BACKEND_ARCHITECTURE.md) · [Przewodnik po frontendzie](docs/PL/FRONTEND_NEXT_GUIDE.md) · [Akademia](docs/PL/THE_ACADEMY.md)
- **Współtworzenie** · [Zasady współpracy](docs/PL/CONTRIBUTING.md) · [GitHub Actions](https://github.com/mpieniak01/Venom/actions)

## Licencja i współtwórcy

Venom jest udostępniany na [licencji MIT](LICENSE). Copyright © 2025–2026 Maciej Pieniak. [Współtwórcy](https://github.com/mpieniak01/Venom/graphs/contributors)
