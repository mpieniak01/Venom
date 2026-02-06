# Przewodnik Wydawania Paczek Docker (Minimal MVP)

Ten dokument opisuje oficjalny proces publikacji obrazów Docker dla Venom Minimal MVP.

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
2. Utwórz i wypchnij tag release:
```bash
git tag v1.0.0
git push origin v1.0.0
```
3. GitHub Actions automatycznie uruchomi `Docker Publish (Minimal)`.

Tagi publikowane do GHCR:
- `sha-<short_sha>`
- `v1.0.0`
- `latest`

### Tryb B: manualny publish (build testowy/RC)

Używaj tego trybu, gdy chcesz wypchnąć paczkę bez tworzenia tagu release.

1. Otwórz: GitHub `Actions` -> `Docker Publish (Minimal)` -> `Run workflow`.
2. Gałąź musi być `main`.
3. Wymagane wejście:
   - `confirm_publish=true`
4. Opcjonalne wejścia:
   - `custom_tag` (np. `rc1`, `mvp-test`)
   - `push_latest=true` tylko jeśli świadomie chcesz przesunąć `latest`.

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

## Rollback / recovery

Jeśli wypchniesz błędną paczkę:

1. Nie kasuj nerwowo tagów.
2. Od razu wydaj poprawny tag (np. `v1.0.1`).
3. W razie potrzeby przypnij deployment do konkretnego tagu (nie `latest`).

## Uwagi

- `docker-sanity` waliduje build i smoke na PR; nie publikuje obrazów.
- Polityka LAN/trusted network oraz runtime są opisane w `docs/PL/DEPLOYMENT_NEXT.md`.
