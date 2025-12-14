import type { PlaywrightTestConfig } from "@playwright/test";

const devHost = process.env.PLAYWRIGHT_HOST || "127.0.0.1";
const devPort = Number(process.env.PLAYWRIGHT_PORT || 3001);
const baseURL = process.env.BASE_URL || `http://${devHost}:${devPort}`;

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
    command: `npm run dev -- --hostname ${devHost} --port ${devPort}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
  },
};

export default config;
