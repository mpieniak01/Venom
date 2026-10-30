# Docker: ten sam podział Full/Light i dev/preprod

Docker jest technicznym sposobem wdrożenia. `minimal` (lokalny build) oraz `release` (gotowe obrazy) są przepisami budowania/dystrybucji, nie dodatkowymi profilami aplikacji.

```bash
PROFILE=light ENVIRONMENT=dev scripts/docker/stack.sh start
PROFILE=full ENVIRONMENT=preprod ACTIVE_LLM_SERVER=none scripts/docker/stack.sh start
PROFILE=light ENVIRONMENT=preprod scripts/docker/run-release.sh status
```

`run-release.sh` deleguje do tego samego skryptu. Domyślny profil tego historycznego przepisu Docker pozostaje Light. Codzienny host Full/dev nie jest przełączany na Docker. Środowisko prod jest obecnie odrzucane przez adapter.

## Dane i izolacja

Dev zachowuje dotychczasowe nazwy projektów `venom-minimal`/`venom-release`, kontenerów oraz klucze wolumenów `ollama-data`, `venom-data`, `venom-workspace`, `venom-logs`. Nie ma automatycznej migracji ani usuwania danych.

Preprod używa osobnych projektów `venom-minimal-preprod`/`venom-release-preprod`, prefiksu kontenerów `venom-preprod`, portów API/UI/Ollama 8810/3310/11435 oraz przestrzeni `preprod` dla bazy, cache, kolejki i storage. `ALLOW_DATA_MUTATION=0` jest wymuszone. Wolumeny Compose są związane z projektem, więc bazy i logi preprod nie trafiają do wolumenów dev. Polecenia stop/restart nie usuwają wolumenów.

Bezpośrednie używanie pliku Compose wymaga jawnego ustawienia tych zmiennych; wygodne i sprawdzone kontraktowo wejście zapewnia adapter. Nie uruchamiać dwóch przepisów tego samego środowiska jednocześnie na tych samych portach.

## Silnik i zakres kwalifikacji

Full/Light nie wybiera providera, modelu ani GPU. Light wstrzymuje zadania tła i automatyczną dokumentację/gardening; ustawienia interaktywne zachowuje aplikacja. Wybrany lokalny lub zdalny provider musi mieć odpowiednią konfigurację i poświadczenia. Przy innym wyborze niż Ollama adapter uruchamia wyłącznie backend/frontend, bez zależności Ollama.

Start nie wykonuje `ollama list`, pobierania modelu ani próbnej generacji. Warmup domyślnie jest wyłączony; Full zachowuje jawne `LLM_WARMUP_ON_STARTUP`; Light zawsze pomija warmup, zgodnie z launcherem hostowym. Alias `llm_off` jest przejściowo tłumaczony na Light i `ACTIVE_LLM_SERVER=none`, z komunikatem migracji; należy usunąć go po migracji konfiguracji A10. `pull` jest osobną operacją dla obrazów, a nie modeli.

**Nie jest to kwalifikacja uruchomionego Dockera ani pełnej funkcjonalności Full.** Obecny backend Docker instaluje lock Light; samo ustawienie Full nie dodaje pakietów głosu, RAG lub innych brakujących zależności. Obrazy Full i moduły wymagają osobnego odbioru instalacyjnego. Gotowe obrazy release muszą zawierać obsługę bieżącego kontraktu; stary obraz nie staje się zgodny przez samo przekazanie nowych zmiennych.

Regresje adapterów korzystają wyłącznie z atrapy Docker CLI oraz parsowania szablonów. Nie wykonują build/run/pull kontenerów, nie kwalifikują GPU ani ruchu SSE/WebSocket w kontenerach i nie wywołują rzeczywistych providerów.

Start pobiera brakujące obrazy zgodnie z VENOM_DOCKER_PULL_POLICY=missing. Tryb offline wymaga jawnego VENOM_DOCKER_PULL_POLICY=never; always wymusza odświeżenie obrazów. Nie dotyczy to pobierania wag modeli.
