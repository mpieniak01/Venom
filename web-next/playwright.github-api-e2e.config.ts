import type { PlaywrightTestConfig } from "@playwright/test";

// Separate from the local/physical suite; the setup enforces hosted isolation.
const config: PlaywrightTestConfig = {
  globalSetup: "./scripts/github-api-e2e-setup.mjs",
  testDir: "./tests/github-real-api",
  testMatch: "**/*.e2e.ts",
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: "http://127.0.0.1:13300",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
};
export default config;
