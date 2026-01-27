#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/venom

# Optimized Playwright E2E sequence for this environment.
npm --prefix web-next run test:e2e:preflight
npm --prefix web-next run test:e2e:latency
npm --prefix web-next run test:e2e:functional -- --workers=4
