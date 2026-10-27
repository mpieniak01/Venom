import type { PlaywrightTestConfig } from "@playwright/test";

// A simulated UI server is permitted only on a dedicated GitHub Actions runner.
// Normal/local execution always uses the existing Venom UI and never starts Next.
const simulatedCi = process.env.GITHUB_ACTIONS === "true" &&
  process.env.CI === "true" && process.env.RUNNER_ENVIRONMENT === "github-hosted" &&
    process.env.E2E_SIMULATED_SERVER === "1";
const devHost = process.env.PLAYWRIGHT_HOST || "127.0.0.1";
const devPort = Number(process.env.PLAYWRIGHT_PORT || (simulatedCi ? 3000 : 3300));
const baseURL = process.env.BASE_URL || `http://${devHost}:${devPort}`;
if (simulatedCi) {
  const url = new URL(baseURL);
  if (!["http:", "https:"].includes(url.protocol) ||
      !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) ||
      url.username || url.password || url.search || url.hash) {
    throw new Error("Simulated CI UI must use a local URL without credentials.");
  }
}
const isProdServer = process.env.PLAYWRIGHT_MODE === "prod";
const devServerEnv = [
  "NEXT_MODE=dev",
  "NEXT_DISABLE_TURBOPACK=1",
  "NEXT_TELEMETRY_DISABLED=1",
  "NEXT_PLAYWRIGHT_DISABLE_SSR_API=1",
  "WATCHPACK_POLLING=true",
  "WATCHPACK_POLLING_INTERVAL=1000",
  "CHOKIDAR_USEPOLLING=1",
].join(" ");
const webServerCommand = isProdServer
  ? [
    `mkdir -p .next/standalone/web-next/.next`,
    `cp -r .next/static .next/standalone/web-next/.next/static`,
    `PORT=${devPort} HOSTNAME=${devHost} node .next/standalone/web-next/server.js`,
  ].join(" && ")
  : `${devServerEnv} npx next dev --webpack --hostname ${devHost} --port ${devPort}`;

const config: PlaywrightTestConfig = {
  globalSetup: "./scripts/e2e-global-setup.mjs",
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  fullyParallel: true,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL,
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  ...(simulatedCi ? { webServer: {
    command: webServerCommand,
    url: baseURL,
    timeout: 120_000,
    reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER !== "false",
  } } : {}),
};

export default config;
