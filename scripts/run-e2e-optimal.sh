#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

E2E_FUNCTIONAL_WORKERS="${E2E_FUNCTIONAL_WORKERS:-1}"
if ! [[ "${E2E_FUNCTIONAL_WORKERS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "❌ E2E_FUNCTIONAL_WORKERS musi być dodatnią liczbą całkowitą (otrzymano: ${E2E_FUNCTIONAL_WORKERS})"
  exit 2
fi
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${CI:-}" != "true" || "${RUNNER_ENVIRONMENT:-}" != "github-hosted" || "${E2E_SIMULATED_SERVER:-}" != "1" ]]; then
  if [[ "${E2E_FUNCTIONAL_WORKERS}" != "1" ]]; then
    echo "❌ Lokalny profil E2E korzysta z jednego workera."
    exit 2
  fi
  set +e
  E2E_REQUIRE_MODEL=0 npm --prefix web-next run test:e2e:preflight
  preflight_code=$?
  set -e
  if [[ $preflight_code -eq 2 ]]; then
    echo "⏭️ E2E SKIPPED: brak gotowego Venoma."
    exit 0
  fi
  if [[ $preflight_code -ne 0 ]]; then
    exit "$preflight_code"
  fi
fi

PLAYWRIGHT_CACHE_DIR="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
if ! compgen -G "${PLAYWRIGHT_CACHE_DIR}/chromium*" >/dev/null; then
  echo "❌ Brak Chromium Playwright w ${PLAYWRIGHT_CACHE_DIR}; przygotuj zależności przed testami."
  exit 1
fi

npm --prefix web-next run test:e2e:latency
echo "🧪 E2E functional workers=${E2E_FUNCTIONAL_WORKERS}"
if [[ "${GITHUB_ACTIONS:-}" == "true" && "${CI:-}" == "true" && "${RUNNER_ENVIRONMENT:-}" == "github-hosted" && "${E2E_SIMULATED_SERVER:-}" == "1" ]]; then
  npm --prefix web-next run test:e2e:functional -- --workers="${E2E_FUNCTIONAL_WORKERS}"
else
  npm --prefix web-next run test:e2e:functional
fi
