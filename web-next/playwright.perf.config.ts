import { defineConfig, devices } from "@playwright/test";

const nextBase = process.env.PERF_NEXT_BASE_URL ?? "http://localhost:3000";
const legacyBase = process.env.PERF_LEGACY_BASE_URL ?? "http://localhost:8000";

export default defineConfig({
  testDir: "./tests/perf",
  timeout: 30_000,
  expect: {
    timeout: 20_000,
  },
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report/perf", open: "never" }],
  ],
  use: {
    baseURL: nextBase,
    viewport: { width: 1440, height: 900 },
    trace: "off",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    extraHTTPHeaders: {
      "x-venom-perf": "true",
    },
  },
  metadata: {
    nextBase,
    legacyBase,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chat-latency",
      testMatch: /chat-latency\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
