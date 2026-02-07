#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/venom

# Optimized Playwright E2E sequence for this environment.
PLAYWRIGHT_CACHE_DIR="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
if ! compgen -G "${PLAYWRIGHT_CACHE_DIR}/chromium*" >/dev/null; then
  echo "⚙️  Brak przeglądarek Playwright w ${PLAYWRIGHT_CACHE_DIR}. Instaluję Chromium..."
  npm --prefix web-next exec playwright install chromium
fi

npm --prefix web-next run test:e2e:preflight
npm --prefix web-next run test:e2e:latency
npm --prefix web-next run test:e2e:functional -- --workers=4
