import type { PlaywrightTestConfig } from "@playwright/test";

const devHost = process.env.PLAYWRIGHT_HOST || "127.0.0.1";
// Domyślny port 3100, żeby nie kolidować z dev (3000) ani starymi procesami 3001.
const devPort = Number(process.env.PLAYWRIGHT_PORT || 3100);
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
  webServer: {
    command: webServerCommand,
    url: baseURL,
    // Pozwala użyć już działającego serwera na porcie (lokalnie), wymusza restart w CI.
    reuseExistingServer,
    timeout: 120_000,
  },
};

export default config;
