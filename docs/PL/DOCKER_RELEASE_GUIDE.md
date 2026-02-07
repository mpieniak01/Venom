# Przewodnik Wydawania Paczek Docker (Minimal MVP)

Ten dokument opisuje oficjalny proces publikacji obrazów Docker dla Venom Minimal MVP.

## Szybka odpowiedź

- Tak: w trybie manualnym masz przycisk w GitHub UI: `Actions` -> `Docker Publish (Minimal)` -> `Run workflow`.
- W trybie tagu: commit musi być na `main`, potem tworzysz i wysyłasz tag `vX.Y.Z`. Sam push taga uruchamia publikację.

## Zakres

- Obraz backendu: `ghcr.io/<owner>/venom-backend`
- Obraz frontendu: `ghcr.io/<owner>/venom-frontend`
- Workflow: `.github/workflows/docker-publish.yml`

## Zasady bezpieczeństwa (obowiązkowe)

1. Nie publikujemy paczek z gałęzi feature.
2. Stabilny release robimy tagiem semver: `vMAJOR.MINOR.PATCH` (np. `v1.2.3`).
3. Manualny publish działa tylko z `main`.
4. Manualny publish wymaga jawnego potwierdzenia: `confirm_publish=true`.

Te reguły są egzekwowane przez preflight checks w workflow.

## Tryby wydania

### Tryb A: release tagiem (zalecany dla oficjalnej paczki)

Używaj tego trybu do stabilnego wydania.

1. Upewnij się, że `main` jest zielony i aktualny:
```bash
git checkout main
git pull --ff-only
```
2. Jeśli trzeba, wypchnij najnowszy commit na `main`:
```bash
git push origin main
```
3. Utwórz i wypchnij tag release:
```bash
git tag v1.0.0
git push origin v1.0.0
```
4. GitHub Actions automatycznie uruchomi `Docker Publish (Minimal)`.

Tagi publikowane do GHCR:
- `sha-<short_sha>`
- `v1.0.0`
- `latest`

### Tryb B: manualny publish (build testowy/RC)

Używaj tego trybu, gdy chcesz wypchnąć paczkę bez tworzenia tagu release.

1. Otwórz repozytorium w GitHub.
2. Wejdź w zakładkę `Actions`.
3. Wybierz workflow: `Docker Publish (Minimal)`.
4. Kliknij `Run workflow` (prawy górny róg).
5. Wybierz branch: `main`.
6. Ustaw wymagane pole: `confirm_publish=true`.
7. Opcjonalnie ustaw: `custom_tag`, `push_latest`.
8. Kliknij zielony przycisk `Run workflow`, aby uruchomić publikację.

Typowe tagi w trybie manualnym:
- zawsze: `sha-<short_sha>`
- opcjonalnie: `<custom_tag>`
- opcjonalnie: `latest` (tylko gdy `push_latest=true`)

## Checklista po publikacji

1. Workflow ma status zielony (`preflight` + 2 joby obrazów).
2. W GHCR są oba obrazy:
   - `venom-backend`
   - `venom-frontend`
3. Widać oczekiwane tagi.
4. Szybki smoke pull z czystego hosta:
```bash
docker pull ghcr.io/<owner>/venom-backend:<tag>
docker pull ghcr.io/<owner>/venom-frontend:<tag>
```

## Uruchomienie dla użytkownika końcowego (z gotowych obrazów)

Po publikacji użytkownik końcowy powinien używać compose release i skryptu pomocniczego:

```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom

# opcjonalne nadpisania:
# export BACKEND_IMAGE=ghcr.io/<owner>/venom-backend:vX.Y.Z
# export FRONTEND_IMAGE=ghcr.io/<owner>/venom-frontend:vX.Y.Z
# export OLLAMA_MODEL=gemma3:1b
# export VENOM_ENABLE_GPU=auto

scripts/docker/run-release.sh start
```

Ten flow używa gotowych obrazów backend/frontend z GHCR i przy pierwszym starcie dociąga lokalny model Ollama.

## Rollback / recovery

Jeśli wypchniesz błędną paczkę:

1. Nie kasuj nerwowo tagów.
2. Od razu wydaj poprawny tag (np. `v1.0.1`).
3. W razie potrzeby przypnij deployment do konkretnego tagu (nie `latest`).

## Uwagi

- `docker-sanity` waliduje build i smoke na PR; nie publikuje obrazów.
- Polityka LAN/trusted network oraz runtime są opisane w `docs/PL/DEPLOYMENT_NEXT.md`.
- Praktyczna instalacja na Windows z WSL trzymanym na `D:` (poza dyskiem systemowym) jest opisana w `docs/PL/WINDOWS_WSL_D_DRIVE_INSTALL.md`.
