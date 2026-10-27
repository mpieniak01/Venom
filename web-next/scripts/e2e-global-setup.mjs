import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { evaluateE2ePreflight } from "./check-e2e-env.mjs";

export default async function globalSetup(config) {
  const simulatedCi = process.env.GITHUB_ACTIONS === "true" && process.env.CI === "true" &&
    process.env.RUNNER_ENVIRONMENT === "github-hosted" && process.env.E2E_SIMULATED_SERVER === "1";
  const physical = config.projects.some((project) => project.metadata?.venomPhysical === true);
  if (simulatedCi && !physical) return;

  const nextBase = config.projects[0]?.use?.baseURL || "http://127.0.0.1:3300";
  const apiBase = (process.env.PERF_API_BASE || process.env.VENOM_API_BASE || "http://127.0.0.1:8800").replace(/\/$/, "");
  // Raw Playwright may select any unclassified spec, including real generation.
  // Fail closed until the UI-to-API binding is established for the whole suite.
  const result = await evaluateE2ePreflight({ nextBase, apiBase, requireModel: true });
  if (result.ok) return;
  const stateFile = resolve(process.cwd(), process.env.E2E_GLOBAL_PREFLIGHT_FILE || "test-results/e2e/global-preflight.json");
  mkdirSync(dirname(stateFile), { recursive: true });
  writeFileSync(stateFile, `${JSON.stringify({ status: "skipped", reason_code: result.reasonCode, message: result.message }, null, 2)}\n`);
  console.warn(`E2E SKIPPED (${result.reasonCode}): ${result.message}`);
  // CI must not present an incomplete physical profile as a green qualification.
  process.exit(process.env.CI === "true" ? 2 : 0);
}
