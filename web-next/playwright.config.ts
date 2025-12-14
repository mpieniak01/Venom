import type { PlaywrightTestConfig } from "@playwright/test";

const baseURL = process.env.BASE_URL || "http://localhost:3000";

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
};

export default config;
