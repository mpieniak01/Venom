import type { PlaywrightTestConfig } from "@playwright/test";

const devHost = process.env.PLAYWRIGHT_HOST || "127.0.0.1";
// Domyślnie używamy istniejącej instancji Next.js na porcie 3000.
// Next.js proksuje żądania API do backendu (FastAPI) zgodnie z konfiguracją w next.config.ts.
const devPort = Number(process.env.PLAYWRIGHT_PORT || 3000);
const baseURL = process.env.BASE_URL || `http://${devHost}:${devPort}`;

const isProdServer = process.env.PLAYWRIGHT_MODE === "prod";
const reuseExistingServer = process.env.PLAYWRIGHT_REUSE_SERVER !== "false";
const devServerEnv = [
  "NEXT_MODE=dev",
  "NEXT_DISABLE_TURBOPACK=1",
  "NEXT_TELEMETRY_DISABLED=1",
  "WATCHPACK_POLLING=true",
  "WATCHPACK_POLLING_INTERVAL=1000",
  "CHOKIDAR_USEPOLLING=1",
].join(" ");
const webServerCommand = isProdServer
  ? [
    // Zapewnia dostępność zasobów statycznych dla standalone builda.
    `mkdir -p .next/standalone/web-next/.next`,
    `cp -r .next/static .next/standalone/web-next/.next/static`,
    `PORT=${devPort} HOSTNAME=${devHost} node .next/standalone/web-next/server.js`,
  ].join(" && ")
  : `${devServerEnv} npm run dev -- --hostname ${devHost} --port ${devPort}`;

const config: PlaywrightTestConfig = {
  testDir: "./tests",
  fullyParallel: true,
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL,
    headless: true,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: webServerCommand,
    url: baseURL,
    timeout: 120_000,
    reuseExistingServer,
  },
};

export default config;
