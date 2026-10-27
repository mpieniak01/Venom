import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import { evaluateE2ePreflight } from "../scripts/check-e2e-env.mjs";
import { playwrightReportStatus, summarizeProfiles } from "../scripts/e2e-profile-status.mjs";

type FakePayload = Record<string, unknown>;
function fakeFetch(options: {
  api?: FakePayload | null;
  panel?: boolean;
  active?: FakePayload;
  runtime?: FakePayload;
}) {
  const calls: Array<{ url: string; method: string }> = [];
  const fetcher = async (url: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const address = String(url);
    calls.push({ url: address, method: init?.method || "GET" });
    if (address.endsWith("/healthz")) {
      if (options.api === null) throw new Error("connection refused");
      return Response.json(options.api ?? { status: "ok", component: "venom-core" });
    }
    if (address.endsWith("/api/v1/system/llm-servers/active")) {
      return Response.json(options.active ?? { active_server: "ollama", active_model: "model" });
    }
    if (address.endsWith("/api/v1/system/models/resources")) {
      return Response.json({ runtime: options.runtime ?? { status: "available", active_operations: 0 } });
    }
    if (options.panel === false) throw new Error("connection refused");
    return new Response("<html>Venom</html>", { status: 200 });
  };
  return { calls, fetcher: fetcher as typeof fetch };
}
const bases = { nextBase: "http://127.0.0.1:3300", apiBase: "http://127.0.0.1:8800" };

test("E2E preflight pomija fizyczny przebieg, gdy API Venoma nie działa", async () => {
  const fake = fakeFetch({ api: null });
  const result = await evaluateE2ePreflight({ ...bases, requireModel: true, fetcher: fake.fetcher });
  assert.equal(result.reasonCode, "stack_not_started");
  assert.deepEqual(fake.calls, [{ url: "http://127.0.0.1:8800/healthz", method: "GET" }]);
});

test("E2E odrzuca obcą usługę pod portem API", async () => {
  const fake = fakeFetch({ api: { status: "ok", component: "other" } });
  const result = await evaluateE2ePreflight({ ...bases, fetcher: fake.fetcher });
  assert.equal(result.reasonCode, "stack_degraded");
  assert.equal(fake.calls.length, 1);
});

test("odczyt panelu i API nie wymaga aktywnego modelu", async () => {
  const fake = fakeFetch({ active: {} });
  const result = await evaluateE2ePreflight({ ...bases, fetcher: fake.fetcher });
  assert.equal(result.reasonCode, "ready");
  assert.equal(fake.calls.length, 2);
});

test("brak panelu pomija E2E nawet gdy API działa", async () => {
  const fake = fakeFetch({ panel: false });
  const result = await evaluateE2ePreflight({ ...bases, fetcher: fake.fetcher });
  assert.equal(result.reasonCode, "stack_not_started");
});

test("brak modelu nie wywołuje aktywacji ani POST", async () => {
  const fake = fakeFetch({ active: {} });
  const result = await evaluateE2ePreflight({ ...bases, requireModel: true, fetcher: fake.fetcher });
  assert.equal(result.reasonCode, "runtime_model_unavailable");
  assert.equal(fake.calls.some((call) => call.method !== "GET"), false);
  assert.equal(fake.calls.some((call) => call.url.includes("llm-runtime/options")), false);
});

test("zajęty runtime blokuje fizyczny test generacji", async () => {
  const fake = fakeFetch({ runtime: { status: "busy", active_operations: 1 } });
  const result = await evaluateE2ePreflight({ ...bases, requireModel: true, fetcher: fake.fetcher });
  assert.equal(result.reasonCode, "runtime_busy");
  assert.equal(fake.calls.every((call) => call.method === "GET"), true);
});

test("gotowy runtime bez dowodu powiązania i nieznany stan pozostają zablokowane", async () => {
  const ready = fakeFetch({});
  assert.equal((await evaluateE2ePreflight({ ...bases, requireModel: true, fetcher: ready.fetcher })).reasonCode, "proxy_identity_unverified");
  const unknown = fakeFetch({ runtime: { status: "disabled" } });
  assert.equal((await evaluateE2ePreflight({ ...bases, requireModel: true, fetcher: unknown.fetcher })).reasonCode, "stack_degraded");
  assert.equal(ready.calls.every((call) => call.method === "GET"), true);
});

function inspectPlaywrightConfig(env: Record<string, string | undefined>) {
  const script = 'const m = await import("./playwright.config.ts"); const c = m.default.default ?? m.default; process.stdout.write(JSON.stringify({server: Boolean(c.webServer), url: c.use.baseURL}))';
  const result = spawnSync(process.execPath, ["--import", "tsx", "--input-type=module", "-e", script], {
    cwd: process.cwd(), encoding: "utf8", env: { ...process.env, BASE_URL: "", PLAYWRIGHT_PORT: "", ...env },
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout) as { server: boolean; url: string };
}

test("Playwright nie uruchamia Next lokalnie nawet po ustawieniu samego CI", () => {
  for (const env of [
    { CI: "", GITHUB_ACTIONS: "", E2E_SIMULATED_SERVER: "" },
    { CI: "true", GITHUB_ACTIONS: "", E2E_SIMULATED_SERVER: "1" },
    { CI: "true", GITHUB_ACTIONS: "true", RUNNER_ENVIRONMENT: "self-hosted", E2E_SIMULATED_SERVER: "1" },
  ]) {
    assert.deepEqual(inspectPlaywrightConfig(env), { server: false, url: "http://127.0.0.1:3300" });
  }
  assert.deepEqual(inspectPlaywrightConfig({ CI: "true", GITHUB_ACTIONS: "true", RUNNER_ENVIRONMENT: "github-hosted", E2E_SIMULATED_SERVER: "1" }), {
    server: true, url: "http://127.0.0.1:3000",
  });
});

test("komenda smoke pomija test bez uruchamiania przeglądarki gdy API nie działa", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-test-"));
  try {
    const state = join(work, "state.json");
    const telemetry = join(work, "telemetry.json");
    const result = spawnSync(process.execPath, [resolve("scripts/run-playwright-e2e.mjs"), "smoke"], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "true", GITHUB_ACTIONS: "", E2E_SIMULATED_SERVER: "1", PERF_API_BASE: "http://127.0.0.1:0", E2E_PREFLIGHT_STATE_FILE: state, E2E_SKIP_TELEMETRY_FILE: telemetry, E2E_PREFLIGHT_STRICT: "0" },
    });
    assert.equal(result.status, 2, result.stderr);
    assert.match(result.stdout, /SKIPPED/);
    assert.equal(JSON.parse(readFileSync(state, "utf8")).reason_code, "stack_not_started");
    assert.equal(JSON.parse(readFileSync(telemetry, "utf8")).by_reason_code.stack_not_started, 1);
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("lokalny turbo smoke nie uruchamia Next i nie czyści katalogu", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-turbo-test-"));
  try {
    const result = spawnSync(process.execPath, [resolve("scripts/check-dev-turbo.mjs")], {
      cwd: work, encoding: "utf8", timeout: 5_000,
      env: { ...process.env, CI: "true", GITHUB_ACTIONS: "", TURBO_SMOKE_CLEAN_NEXT: "1" },
    });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /SKIPPED/);
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("bezpośrednie profile npm korzystają ze wspólnego runnera", () => {
  const pkg = JSON.parse(readFileSync(resolve("package.json"), "utf8"));
  assert.equal(pkg.scripts["test:e2e:prod"], "node scripts/run-playwright-e2e.mjs prod");
  assert.equal(pkg.scripts["test:perf"], "node scripts/run-playwright-e2e.mjs perf");
  assert.equal(pkg.scripts["test:perf:ci:backend"], "node scripts/run-playwright-e2e.mjs perf-backend");
});

test("bezpośrednie profile performance także w symulowanym CI wymagają żywego Venoma", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-perf-test-"));
  try {
    for (const profile of ["perf", "perf-backend", "latency"]) {
      const state = join(work, `${profile}-state.json`);
      const telemetry = join(work, `${profile}-telemetry.json`);
      const result = spawnSync(process.execPath, [resolve("scripts/run-playwright-e2e.mjs"), profile], {
        cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
        env: { ...process.env, CI: "true", GITHUB_ACTIONS: "true", RUNNER_ENVIRONMENT: "github-hosted", E2E_SIMULATED_SERVER: "1", PERF_API_BASE: "http://127.0.0.1:0", E2E_PREFLIGHT_STATE_FILE: state, E2E_SKIP_TELEMETRY_FILE: telemetry, E2E_PREFLIGHT_STRICT: "0" },
      });
      assert.equal(result.status, 2, result.stderr);
      assert.match(result.stdout, /SKIPPED/);
      assert.equal(JSON.parse(readFileSync(state, "utf8")).reason_code, "stack_not_started");
      assert.equal(JSON.parse(readFileSync(telemetry, "utf8")).by_reason_code.stack_not_started, 1);
    }
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("lokalny profil prod wykonuje preflight, ale nie buduje ani nie uruchamia Next", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-prod-local-test-"));
  try {
    const preload = join(work, "fetch-mock.mjs");
    const marker = join(work, "npm-invoked");
    const npm = join(work, "npm");
    const state = join(work, "state.json");
    const telemetry = join(work, "telemetry.json");
    writeFileSync(preload, `globalThis.fetch = async (url) => {
      const value = String(url);
      if (value.endsWith('/healthz')) return Response.json({status: 'ok', component: 'venom-core'});
      if (value.endsWith('/api/v1/system/llm-servers/active')) return Response.json({active_server: 'ollama', active_model: 'test'});
      if (value.endsWith('/api/v1/system/models/resources')) return Response.json({runtime: {status: 'available', active_operations: 0}});
      return new Response('Mock UI', {status: 200});
    };`);
    writeFileSync(npm, '#!/bin/sh\n: > "$E2E_TEST_NPM_MARKER"\nexit 23\n');
    chmodSync(npm, 0o700);
    const result = spawnSync(process.execPath, [resolve("scripts/run-playwright-e2e.mjs"), "prod"], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "true", GITHUB_ACTIONS: "", E2E_SIMULATED_SERVER: "1", NODE_OPTIONS: `--import=${pathToFileURL(preload).href}`, PATH: `${work}:${process.env.PATH || ""}`, E2E_TEST_NPM_MARKER: marker, PERF_API_BASE: "http://127.0.0.1:8800", PERF_NEXT_BASE_URL: "http://127.0.0.1:3300", E2E_PREFLIGHT_STATE_FILE: state, E2E_SKIP_TELEMETRY_FILE: telemetry, E2E_PREFLIGHT_STRICT: "0" },
    });
    assert.equal(result.status, 2, result.stderr);
    assert.equal(JSON.parse(readFileSync(state, "utf8")).reason_code, "proxy_identity_unverified");
    assert.equal(JSON.parse(readFileSync(telemetry, "utf8")).by_reason_code.proxy_identity_unverified, 1);
    assert.match(result.stdout, /SKIPPED \(proxy_identity_unverified\)/);
    assert.equal(existsSync(marker), false);
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("odizolowany profil prod w CI zachowuje krok build", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-prod-ci-test-"));
  try {
    const marker = join(work, "npm-invoked");
    const npm = join(work, "npm");
    writeFileSync(npm, '#!/bin/sh\n: > "$E2E_TEST_NPM_MARKER"\nexit 23\n');
    chmodSync(npm, 0o700);
    const result = spawnSync(process.execPath, [resolve("scripts/run-playwright-e2e.mjs"), "prod"], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "true", GITHUB_ACTIONS: "true", RUNNER_ENVIRONMENT: "github-hosted", E2E_SIMULATED_SERVER: "1", PATH: `${work}:${process.env.PATH || ""}`, E2E_TEST_NPM_MARKER: marker },
    });
    assert.equal(result.status, 23, result.stderr);
    assert.equal(existsSync(marker), true);
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("preflight odrzuca zdalny panel, zdalne API i poświadczenia URL bez kontaktu z siecią", async () => {
  for (const pair of [
    { nextBase: "https://remote.example", apiBase: bases.apiBase },
    { nextBase: bases.nextBase, apiBase: "http://192.168.1.100:8800" },
    { nextBase: "http://localhost.attacker.example:3300", apiBase: bases.apiBase },
    { nextBase: "http://user:secret@127.0.0.1:3300", apiBase: bases.apiBase },
  ]) {
    const fake = fakeFetch({});
    const result = await evaluateE2ePreflight({ ...pair, requireModel: true, fetcher: fake.fetcher });
    assert.equal(result.reasonCode, "target_not_local");
    assert.equal(fake.calls.length, 0);
  }
});

test("podobne odpowiedzi zdrowych lokalnych usług nie dowodzą połączenia panelu z API", async () => {
  const fake = fakeFetch({});
  const result = await evaluateE2ePreflight({ ...bases, requireModel: true, fetcher: fake.fetcher });
  assert.equal(result.ok, false);
  assert.equal(result.reasonCode, "proxy_identity_unverified");
  assert.equal(fake.calls.every((call) => call.method === "GET"), true);
});

test("pełny profil z pominiętą latencją jest PARTIAL, nigdy PASS", () => {
  const expected = ["smoke", "academy", "latency", "functional"];
  const records = [
    { profile: "smoke", status: "passed" },
    { profile: "academy", status: "passed" },
    { profile: "latency", status: "skipped" },
    { profile: "functional", status: "passed" },
  ];
  assert.equal(summarizeProfiles(expected, records), "partial");
  assert.equal(summarizeProfiles(expected, records.slice(0, 3)), "failed");
  assert.equal(summarizeProfiles(["latency"], [{ profile: "latency", status: "skipped" }]), "skipped");
  assert.equal(playwrightReportStatus({ suites: [{ specs: [{ tests: [
    { results: [{ status: "passed" }] }, { results: [{ status: "skipped" }] },
  ] }] }] }), "partial");
  assert.equal(playwrightReportStatus({ suites: [] }), "failed");
});

test("pełny profil w CI z pominiętą latencją zapisuje PARTIAL i nie kończy się zielonym wynikiem", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-full-test-"));
  try {
    const npm = join(work, "npm");
    const summary = join(work, "summary.json");
    writeFileSync(npm, `#!/bin/sh
case "$2" in
 test:e2e:smoke) name=smoke; status=passed;;
 test:e2e:smoke:academy) name=academy; status=passed;;
 test:e2e:latency) name=latency; status=skipped;;
 test:e2e:functional) name=functional; status=passed;;
 *) exit 11;;
esac
printf '{"profile":"%s","status":"%s"}\\n' "$name" "$status" >> "$E2E_PROFILE_RESULT_FILE"
`);
    chmodSync(npm, 0o700);
    const result = spawnSync(process.execPath, [resolve("scripts/run-e2e.mjs")], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "true", GITHUB_ACTIONS: "true", RUNNER_ENVIRONMENT: "github-hosted", E2E_SIMULATED_SERVER: "1", E2E_PROFILE: "full", E2E_FORCE_PREFLIGHT: "0", E2E_PROFILE_SUMMARY_FILE: summary, PATH: `${work}:${process.env.PATH || ""}` },
    });
    assert.equal(result.status, 2, result.stderr);
    assert.match(result.stdout, /E2E full: PARTIAL/);
    const report = JSON.parse(readFileSync(summary, "utf8"));
    assert.equal(report.status, "partial");
    assert.equal(report.records.length, 4);
    assert.equal(report.records.find((record: { profile: string }) => record.profile === "latency").status, "skipped");
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("bezpośredni Playwright kończy jako SKIPPED, gdy Venom jest wyłączony", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-direct-playwright-test-"));
  try {
    const config = join(work, "playwright.config.cjs");
    const spec = join(work, "guard.spec.cjs");
    const state = join(work, "global-state.json");
    const playwrightModule = resolve("node_modules/@playwright/test");
    const setup = resolve("scripts/e2e-global-setup.mjs");
    writeFileSync(config, `module.exports = { testDir: ${JSON.stringify(work)}, testMatch: '**/*.spec.cjs', globalSetup: ${JSON.stringify(setup)}, use: { baseURL: 'http://127.0.0.1:0' } };`);
    writeFileSync(spec, `const {test} = require(${JSON.stringify(playwrightModule)}); test('must not execute', () => { throw new Error('guard bypassed'); });`);
    const result = spawnSync(process.execPath, [resolve("node_modules/@playwright/test/cli.js"), "test", "--config", config, "--reporter=dot"], {
      cwd: work, encoding: "utf8", timeout: 15_000,
      env: { ...process.env, CI: "", GITHUB_ACTIONS: "", RUNNER_ENVIRONMENT: "", E2E_SIMULATED_SERVER: "", PERF_API_BASE: "http://127.0.0.1:0", E2E_GLOBAL_PREFLIGHT_FILE: state },
    });
    assert.equal(result.status, 2, result.stderr);
    assert.match(result.stderr, /E2E SKIPPED \(stack_not_started\)/);
    assert.equal(JSON.parse(readFileSync(state, "utf8")).status, "skipped");
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});


test("lokalny profil pojedynczy zwraca kod 2 dla pominięcia", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-local-skip-"));
  try {
    const summary = join(work, "summary.json");
    const result = spawnSync(process.execPath, [resolve("scripts/run-playwright-e2e.mjs"), "smoke"], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "", GITHUB_ACTIONS: "", E2E_SIMULATED_SERVER: "", PERF_API_BASE: "http://127.0.0.1:0", E2E_PREFLIGHT_STATE_FILE: join(work, "state.json"), E2E_PROFILE_SUMMARY_FILE: summary, E2E_SKIP_TELEMETRY_FILE: join(work, "telemetry.json"), E2E_PROFILE_RESULT_FILE: "", E2E_PREFLIGHT_STRICT: "0" },
    });
    assert.equal(result.status, 2, result.stderr);
    assert.equal(JSON.parse(readFileSync(summary, "utf8")).status, "skipped");
  } finally { rmSync(work, { recursive: true, force: true }); }
});

test("wrapper zachowuje raport pominięcia globalnego preflightu", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-global-skip-"));
  try {
    const preload = join(work, "preload.mjs");
    const summary = join(work, "summary.json");
    writeFileSync(preload, `globalThis.fetch = async (url) => {
      url = String(url);
      if (url.endsWith('/healthz')) return Response.json({status:'ok', component:'venom-core'});
      if (url.endsWith('/api/v1/system/llm-servers/active')) return Response.json({active_server:'ollama', active_model:'model'});
      if (url.endsWith('/api/v1/system/models/resources')) return Response.json({runtime:{status:'available', active_operations:0}});
      return new Response('Mock UI', {status:200});
    };`);
    const result = spawnSync(process.execPath, [resolve("scripts/run-playwright-e2e.mjs"), "smoke"], {
      cwd: process.cwd(), encoding: "utf8", timeout: 15_000,
      env: { ...process.env, CI: "", GITHUB_ACTIONS: "", RUNNER_ENVIRONMENT: "", E2E_SIMULATED_SERVER: "", NODE_OPTIONS: `--import=${pathToFileURL(preload).href}`, PERF_API_BASE: "http://127.0.0.1:8800", PERF_NEXT_BASE_URL: "http://127.0.0.1:3300", E2E_PREFLIGHT_STATE_FILE: join(work, "state.json"), E2E_PROFILE_SUMMARY_FILE: summary, E2E_SKIP_TELEMETRY_FILE: join(work, "telemetry.json"), E2E_PROFILE_RESULT_FILE: "", E2E_PREFLIGHT_STRICT: "0" },
    });
    assert.equal(result.status, 2, result.stderr);
    const payload = JSON.parse(readFileSync(summary, "utf8"));
    assert.equal(payload.status, "skipped");
    assert.equal(payload.reason, "proxy_identity_unverified");
  } finally { rmSync(work, { recursive: true, force: true }); }
});

test("agregator lokalny zwraca kod 2 dla pominiętego preflightu", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-aggregate-skip-"));
  try {
    const npm = join(work, "npm");
    const summary = join(work, "summary.json");
    writeFileSync(npm, '#!/bin/sh\nprintf "{\\"reason_code\\":\\"stack_not_started\\"}" > "$E2E_PREFLIGHT_STATE_FILE"\nexit 2\n');
    chmodSync(npm, 0o700);
    const result = spawnSync(process.execPath, [resolve("scripts/run-e2e.mjs")], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "", GITHUB_ACTIONS: "", E2E_SIMULATED_SERVER: "", E2E_PROFILE: "full", E2E_PREFLIGHT_STATE_FILE: join(work, "state.json"), E2E_PROFILE_SUMMARY_FILE: summary, E2E_SKIP_TELEMETRY_FILE: join(work, "telemetry.json"), PATH: `${work}:${process.env.PATH || ""}` },
    });
    assert.equal(result.status, 2, result.stderr);
    assert.equal(JSON.parse(readFileSync(summary, "utf8")).status, "skipped");
  } finally { rmSync(work, { recursive: true, force: true }); }
});

test("skrypt optymalny zwraca kod 2 gdy preflight pomija E2E", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-shell-skip-"));
  try {
    const npm = join(work, "npm");
    writeFileSync(npm, "#!/bin/sh\nexit 2\n");
    chmodSync(npm, 0o700);
    const result = spawnSync("bash", [resolve("../scripts/run-e2e-optimal.sh")], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "", GITHUB_ACTIONS: "", RUNNER_ENVIRONMENT: "", E2E_SIMULATED_SERVER: "", E2E_FUNCTIONAL_WORKERS: "1", PATH: `${work}:${process.env.PATH || ""}` },
    });
    assert.equal(result.status, 2, result.stderr);
    assert.match(result.stdout, /E2E SKIPPED/);
  } finally { rmSync(work, { recursive: true, force: true }); }
});


test("pełny lokalny profil z pominiętą latencją zwraca PARTIAL i kod 2", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-local-partial-"));
  try {
    const npm = join(work, "npm");
    const summary = join(work, "summary.json");
    writeFileSync(npm, `#!/bin/sh
case "$2" in
 test:e2e:preflight) exit 0;;
 test:e2e:smoke) name=smoke; status=passed;;
 test:e2e:smoke:academy) name=academy; status=passed;;
 test:e2e:latency) name=latency; status=skipped;;
 test:e2e:functional) name=functional; status=passed;;
 *) exit 11;;
esac
printf '{"profile":"%s","status":"%s"}\\n' "$name" "$status" >> "$E2E_PROFILE_RESULT_FILE"
`);
    chmodSync(npm, 0o700);
    const result = spawnSync(process.execPath, [resolve("scripts/run-e2e.mjs")], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "", GITHUB_ACTIONS: "", RUNNER_ENVIRONMENT: "", E2E_SIMULATED_SERVER: "", E2E_PROFILE: "full", E2E_PROFILE_SUMMARY_FILE: summary, PATH: `${work}:${process.env.PATH || ""}` },
    });
    assert.equal(result.status, 2, result.stderr);
    const payload = JSON.parse(readFileSync(summary, "utf8"));
    assert.equal(payload.status, "partial");
    assert.equal(payload.records.length, 4);
  } finally { rmSync(work, { recursive: true, force: true }); }
});

test("profil simulated na GitHub wykonuje wyłącznie zakwalifikowane profile bez modelu", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-simulated-test-"));
  try {
    const npm = join(work, "npm");
    const summary = join(work, "summary.json");
    writeFileSync(npm, `#!/bin/sh
case "$2" in
 test:e2e:smoke) name=smoke;;
 test:e2e:functional) name=functional;;
 *) exit 11;;
esac
printf '{"profile":"%s","status":"passed"}\\n' "$name" >> "$E2E_PROFILE_RESULT_FILE"
cp "$FAKE_REPORT_DIR/$name.json" "$PLAYWRIGHT_JSON_OUTPUT_NAME"
mkdir -p "$E2E_PLAYWRIGHT_OUTPUT_DIR"
printf trace > "$E2E_PLAYWRIGHT_OUTPUT_DIR/trace.txt"
`);
    chmodSync(npm, 0o700);
    const fakeReport = (count: number, flaky = 0) => ({ suites: [{ specs: [{ tests: Array.from({ length: count }, (_, index) => ({ results: index < flaky ? [{ status: "failed" }, { status: "passed" }] : [{ status: "passed" }] })) }] }] });
    writeFileSync(join(work, "smoke.json"), JSON.stringify(fakeReport(5)));
    writeFileSync(join(work, "functional.json"), JSON.stringify(fakeReport(8)));
    const result = spawnSync(process.execPath, [resolve("scripts/run-e2e.mjs")], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "true", GITHUB_ACTIONS: "true", RUNNER_ENVIRONMENT: "github-hosted", E2E_SIMULATED_SERVER: "1", E2E_PROFILE: "simulated", E2E_PROFILE_SUMMARY_FILE: summary, E2E_SIMULATED_REPORT_DIR: join(work, "published"), FAKE_REPORT_DIR: work, PATH: `${work}:${process.env.PATH || ""}` },
    });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /fizyczne E2E z modelem nie jest wykonywane/);
    const report = JSON.parse(readFileSync(summary, "utf8"));
    assert.equal(report.status, "passed");
    assert.equal(report.scope, "mocked_ui_without_physical_model");
    assert.deepEqual(report.records.map((item: { profile: string }) => item.profile), ["smoke", "functional"]);
    for (const name of ["smoke", "functional"]) {
      assert.equal(existsSync(join(work, "published", `results-${name}.json`)), true);
      assert.equal(existsSync(join(work, "published", `flakiness-summary-${name}.json`)), true);
      assert.equal(existsSync(join(work, "published", `playwright-${name}`, "trace.txt")), true);
    }

    for (const [name, count, flaky] of [["smoke", 4, 0], ["functional", 7, 0], ["smoke", 5, 1], ["functional", 8, 1]] as const) {
      writeFileSync(join(work, "smoke.json"), JSON.stringify(fakeReport(name === "smoke" ? count : 5, name === "smoke" ? flaky : 0)));
      writeFileSync(join(work, "functional.json"), JSON.stringify(fakeReport(name === "functional" ? count : 8, name === "functional" ? flaky : 0)));
      const rejected = spawnSync(process.execPath, [resolve("scripts/run-e2e.mjs")], {
        cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
        env: { ...process.env, CI: "true", GITHUB_ACTIONS: "true", RUNNER_ENVIRONMENT: "github-hosted", E2E_SIMULATED_SERVER: "1", E2E_PROFILE: "simulated", E2E_PROFILE_SUMMARY_FILE: summary, E2E_SIMULATED_REPORT_DIR: join(work, "published"), FAKE_REPORT_DIR: work, PATH: `${work}:${process.env.PATH || ""}` },
      });
      assert.equal(rejected.status, 1, `${name}: ${rejected.stdout} ${rejected.stderr}`);
      assert.equal(JSON.parse(readFileSync(summary, "utf8")).status, "failed");
    }
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("profil simulated nie uruchamia serwera na lokalnym komputerze", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-simulated-local-test-"));
  try {
    const summary = join(work, "summary.json");
    const result = spawnSync(process.execPath, [resolve("scripts/run-e2e.mjs")], {
      cwd: process.cwd(), encoding: "utf8", timeout: 10_000,
      env: { ...process.env, CI: "", GITHUB_ACTIONS: "", RUNNER_ENVIRONMENT: "", E2E_SIMULATED_SERVER: "", E2E_PROFILE: "simulated", E2E_PROFILE_SUMMARY_FILE: summary },
    });
    assert.equal(result.status, 1, result.stderr);
    const report = JSON.parse(readFileSync(summary, "utf8"));
    assert.equal(report.reason, "simulated_profile_requires_github_hosted");
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("GitHub E2E nie uruchamia profilu po błędzie izolacji sieci", () => {
  const work = mkdtempSync(join(tmpdir(), "venom-e2e-workflow-isolation-"));
  try {
    const workflow = readFileSync(resolve("../.github/workflows/web-next-playwright-e2e.yml"), "utf8");
    const start = "      - name: Run E2E profile in an isolated network namespace\n        run: |\n";
    const end = "      - name: Build flaky trend summary";
    assert.ok(workflow.includes(start));
    const body = workflow.split(start)[1].split(end)[0].split("\n").map((line) => line.replace(/^ {10}/, "")).join("\n");
    const sudo = join(work, "sudo");
    const npm = join(work, "npm");
    writeFileSync(sudo, '#!/bin/sh\nprintf attempted > "$GITHUB_WORKSPACE/sudo-called"\nexit 77\n');
    writeFileSync(npm, '#!/bin/sh\nprintf called > "$GITHUB_WORKSPACE/npm-called"\n');
    chmodSync(sudo, 0o700);
    chmodSync(npm, 0o700);
    const result = spawnSync("bash", ["-c", body], {
      cwd: work, encoding: "utf8", timeout: 10_000,
      env: { ...process.env, GITHUB_WORKSPACE: work, E2E_PROFILE: "smoke", PATH: `${work}:${process.env.PATH || ""}` },
    });
    assert.equal(result.status, 77, result.stderr);
    assert.equal(existsSync(join(work, "sudo-called")), true);
    assert.equal(existsSync(join(work, "npm-called")), false);
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});
