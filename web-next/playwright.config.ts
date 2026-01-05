import type { PlaywrightTestConfig } from "@playwright/test";

const devHost = process.env.PLAYWRIGHT_HOST || "127.0.0.1";
// Domyślnie używamy istniejącej instancji Next.js na porcie 3000.
// Next.js proksuje żądania API do backendu (FastAPI) zgodnie z konfiguracją w next.config.ts.
const devPort = Number(process.env.PLAYWRIGHT_PORT || 3000);
const baseURL = process.env.BASE_URL || `http://${devHost}:${devPort}`;

const isProdServer = process.env.PLAYWRIGHT_MODE === "prod";
const reuseExistingServer = process.env.PLAYWRIGHT_REUSE_SERVER === "true";
const webServerCommand = isProdServer
  ? [
      // Zapewnia dostępność zasobów statycznych dla standalone builda.
      `mkdir -p .next/standalone/web-next/.next`,
      `cp -r .next/static .next/standalone/web-next/.next/static`,
      `PORT=${devPort} HOSTNAME=${devHost} node .next/standalone/web-next/server.js`,
    ].join(" && ")
  : `npm run dev -- --hostname ${devHost} --port ${devPort}`;

const config: PlaywrightTestConfig = {
  testDir: "./tests",
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
  webServer: reuseExistingServer
    ? undefined
    : {
        command: webServerCommand,
        url: baseURL,
        timeout: 120_000,
      },
};

export default config;
