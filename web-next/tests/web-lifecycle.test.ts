import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, existsSync, chmodSync, unlinkSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import net from "node:net";
import { fileURLToPath } from "node:url";
import http from "node:http";
import { afterEach, test } from "node:test";
import { lifecycleConfig, buildArtifact, verifyArtifact, startUI, stopUI, uiStatus } from "../scripts/web-lifecycle.mjs";

const scratch: string[] = [];
const pids: number[] = [];
afterEach(async () => {
  for (const pid of pids.splice(0)) { try { process.kill(-pid, "SIGTERM"); } catch {} }
  await new Promise((resolve) => setTimeout(resolve, 60));
  for (const dir of scratch.splice(0)) rmSync(dir, { recursive: true, force: true });
});
function fixture() {
  const dir = mkdtempSync(path.join(os.tmpdir(), "venom-web-life-")); scratch.push(dir);
  const app = path.join(dir, "web-next"); mkdirSync(app);
  writeFileSync(path.join(app, "page.tsx"), "initial");
  execFileSync("git", ["init", "-q"], { cwd: dir });
  execFileSync("git", ["add", "web-next/page.tsx"], { cwd: dir });
  execFileSync("git", ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], { cwd: dir });
  const npm = path.join(dir, "fake-npm");
  writeFileSync(npm, `#!${process.execPath}\n` + `
const fs = require('node:fs'); const path = require('node:path'); const http = require('node:http');
if (process.argv[3] === 'build') {
  if (process.env.FAKE_BUILD_FAIL) process.exit(7);
  const dist = process.env.NEXT_DIST_DIR || '.next';
  fs.mkdirSync(path.join(dist, 'standalone'), {recursive:true});
  fs.writeFileSync(path.join(dist, 'BUILD_ID'), 'test');
  fs.writeFileSync(path.join(dist, 'standalone/server.js'), '// test');
  process.exit(0);
}
if (process.env.FAKE_EXIT) process.exit(6);
const port = Number(process.argv[process.argv.indexOf('--port')+1]);
const host = process.argv[process.argv.indexOf('--hostname')+1];
const server = http.createServer((req,res) => {
  if (!process.env.FAKE_NOT_READY && req.url === '/_venom/ready' && req.headers['x-venom-start-token'] === process.env.VENOM_UI_START_TOKEN) res.end(process.env.VENOM_UI_START_TOKEN);
  else { res.statusCode = 503; res.end('starting'); }
});
server.listen(port, host);
process.on('SIGTERM', () => server.close(() => process.exit(0)));
`);
  chmodSync(npm, 0o700);
  const env = { ...process.env, WEB_DIR: "web-next", WEB_PID_FILE: "run/ui.pid", WEB_LOG: "logs/ui.log", WEB_HOST: "127.0.0.1", ENVIRONMENT_ROLE: "dev", NEXT_DIST_DIR: ".next", NPM: npm, WEB_READY_TIMEOUT_SEC: "0.6" };
  return { dir, app, env };
}
async function unusedPort() {
  const server = net.createServer(); await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as net.AddressInfo).port;
  await new Promise<void>((resolve) => server.close(() => resolve())); return port;
}
function config(f: ReturnType<typeof fixture>, port = 3300) {
  return lifecycleConfig({ ...f.env, WEB_PORT: String(port) }, f.dir);
}
test("relative and absolute web/PID/log paths normalize without changing cwd", () => {
  const f = fixture(); const c = config(f);
  assert.equal(c.root, f.app); assert.equal(c.pidFile, path.join(f.dir, "run/ui.pid"));
  assert.equal(lifecycleConfig({ ...f.env, WEB_DIR: f.app }, f.dir).root, f.app);
  assert.equal(c.log, path.join(f.dir, "logs/ui.log"));
  for (const NEXT_DIST_DIR of ["../other", "/tmp/build", ".next/../../other"]) assert.throws(() => lifecycleConfig({ ...f.env, NEXT_DIST_DIR }, f.dir));
});
test("prepared artifact rejects changed source, modules, public config, role and revision", () => {
  const f = fixture(); const c = config(f);
  buildArtifact(c, f.env); verifyArtifact(c, f.env);
  assert.throws(() => verifyArtifact(c, { ...f.env, NEXT_PUBLIC_FEATURE_RIDER: "false" }), /Stale/);
  assert.throws(() => verifyArtifact({ ...c, role: "preprod" }, f.env), /Stale/);
  writeFileSync(path.join(f.app, "page.tsx"), "changed"); assert.throws(() => verifyArtifact(c, f.env), /Stale/);
  buildArtifact(c, f.env);
  mkdirSync(path.join(f.app, "optional-modules")); writeFileSync(path.join(f.app, "optional-modules", "module.js"), "changed module");
  assert.throws(() => verifyArtifact(c, f.env), /Stale/);
  buildArtifact(c, f.env);
  execFileSync("git", ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "revision"], { cwd: f.app });
  assert.throws(() => verifyArtifact(c, f.env), /Stale/);
});
test("failed build invalidates last good stamp; missing artifacts are rejected", () => {
  const f = fixture(); const c = config(f);
  assert.throws(() => verifyArtifact(c, f.env));
  buildArtifact(c, f.env);
  assert.throws(() => buildArtifact(c, { ...f.env, FAKE_BUILD_FAIL: "1" }), /build failed/);
  assert.equal(existsSync(path.join(c.dist, "venom-build.json")), false);
  buildArtifact(c, f.env); unlinkSync(path.join(c.dist, "standalone/server.js"));
  assert.throws(() => verifyArtifact(c, f.env), /Missing standalone/);
});
test("environment builds stay in distinct dist directories and stamp has no plaintext config", () => {
  const f = fixture(); const c = config(f);
  buildArtifact(c, { ...f.env, NEXT_PUBLIC_TEST_KEY: "public-value", PRIVATE_TOKEN: "do-not-store" });
  const pre = lifecycleConfig({ ...f.env, ENVIRONMENT_ROLE: "preprod", NEXT_DIST_DIR: ".next-preprod" }, f.dir);
  buildArtifact(pre, { ...f.env, ENVIRONMENT_ROLE: "preprod", NEXT_DIST_DIR: ".next-preprod" });
  assert.ok(existsSync(path.join(c.dist, "BUILD_ID")) && existsSync(path.join(pre.dist, "BUILD_ID")));
  const text = readFileSync(path.join(c.dist, "venom-build.json"), "utf8");
  assert.ok(!text.includes("public-value") && !text.includes("do-not-store"));
});
test("occupied unmanaged port is rejected without terminating owner", async () => {
  const f = fixture(); const server = http.createServer((_req, res) => res.end("foreign"));
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    await assert.rejects(startUI(config(f, (server.address() as net.AddressInfo).port), "turbo", f.env), /EADDRINUSE/);
    assert.ok(server.listening); assert.equal(existsSync(config(f).pidFile), false);
  } finally { await new Promise<void>((resolve) => server.close(() => resolve())); }
});
test("readiness requires owned token; identical UI reuses, another environment is rejected", async () => {
  const f = fixture(); const c = config(f, await unusedPort());
  const started = await startUI(c, "turbo", f.env); pids.push(started.pid);
  assert.equal(started.reused, false); assert.equal(Number(readFileSync(c.pidFile, "utf8")), started.pid);
  assert.equal((await startUI(c, "turbo", f.env)).reused, true);
  await assert.rejects(startUI(c, "turbo", { ...f.env, API_PROXY_TARGET: "http://127.0.0.1:9999" }), /another mode\/environment/);
  await assert.rejects(startUI({ ...c, role: "preprod" }, "turbo", f.env), /another mode\/environment/);
});
test("early exit and never-ready UI fail and clean only owned PID", async () => {
  for (const flag of ["FAKE_EXIT", "FAKE_NOT_READY"]) {
    const f = fixture(); const c = config(f, await unusedPort());
    await assert.rejects(startUI(c, "turbo", { ...f.env, [flag]: "1" }), /exited before readiness|readiness timeout/);
    assert.equal(existsSync(c.pidFile), false); assert.equal(existsSync(`${c.pidFile}.identity.json`), false);
  }
});
test("unverified live PID is not reused or killed", async () => {
  const f = fixture(); const c = config(f, await unusedPort());
  mkdirSync(path.dirname(c.pidFile), { recursive: true }); writeFileSync(c.pidFile, String(process.pid));
  await assert.rejects(startUI(c, "turbo", f.env), /unverified/);
  assert.equal(readFileSync(c.pidFile, "utf8"), String(process.pid));
  assert.throws(() => buildArtifact(c, f.env), /Stop the owning UI/);
});

test("actual streaming entry proves Next readiness and keeps metadata per environment", async () => {
  const f = fixture(); const port = await unusedPort();
  const fakeNext = path.join(f.app, "node_modules/next/dist/bin/next"); mkdirSync(path.dirname(fakeNext), { recursive: true });
  writeFileSync(fakeNext, `const http = require('node:http'); const port = Number(process.argv[process.argv.indexOf('--port')+1]); const server = http.createServer((_req,res) => res.end('actual-child')); server.listen(port,'127.0.0.1'); process.on('SIGTERM',()=>server.close(()=>process.exit(0)));`);
  mkdirSync(path.join(f.app, "public")); writeFileSync(path.join(f.app, "public/meta.json"), JSON.stringify({ environmentRole: "dev", version: "fixture" }));
  const entry = fileURLToPath(new URL("../scripts/serve-with-proxy.mjs", import.meta.url));
  const child = spawn(process.execPath, [entry, "dev", "--turbo", "--hostname", "127.0.0.1", "--port", String(port)], {
    cwd: f.app, env: { ...f.env, ENVIRONMENT_ROLE: "preprod", VENOM_UI_START_TOKEN: "owned-ready-token" }, detached: true, stdio: "ignore",
  });
  assert.ok(child.pid); pids.push(child.pid!);
  const base = `http://127.0.0.1:${port}`;
  let ready = false;
  for (let i = 0; i < 50; i++) {
    try { const response = await fetch(`${base}/_venom/ready`, { headers: { "x-venom-start-token": "owned-ready-token" } }); ready = response.status === 200 && await response.text() === "owned-ready-token"; } catch {}
    if (ready) break;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert.equal(ready, true);
  assert.equal(await (await fetch(`${base}/_venom/ready`)).text(), "actual-child");
  assert.equal((await (await fetch(`${base}/meta.json`)).json()).environmentRole, "preprod");
  writeFileSync(path.join(f.app, "public/meta.json"), JSON.stringify({ environmentRole: "dev" }));
  assert.equal((await (await fetch(`${base}/meta.json`)).json()).environmentRole, "preprod");
});

test("standalone preparation copies selected-environment static and public assets", () => {
  const f = fixture();
  mkdirSync(path.join(f.app, ".next-preprod/static"), { recursive: true });
  writeFileSync(path.join(f.app, ".next-preprod/static/chunk.js"), "preprod chunk");
  mkdirSync(path.join(f.app, "public")); writeFileSync(path.join(f.app, "public/logo.svg"), "logo");
  const script = fileURLToPath(new URL("../scripts/prepare-standalone.mjs", import.meta.url));
  execFileSync(process.execPath, [script], { cwd: f.app, env: { ...f.env, NEXT_DIST_DIR: ".next-preprod" } });
  for (const layout of ["", "web-next"]) {
    assert.equal(readFileSync(path.join(f.app, ".next-preprod/standalone", layout, ".next-preprod/static/chunk.js"), "utf8"), "preprod chunk");
    assert.equal(readFileSync(path.join(f.app, ".next-preprod/standalone", layout, "public/logo.svg"), "utf8"), "logo");
  }
  assert.equal(existsSync(path.join(f.app, ".next")), false);
});

test("Make build/start handles relative WEB_DIR under ONESHELL without rebuilding start", async () => {
  const f = fixture(); const repo = fileURLToPath(new URL("../../", import.meta.url));
  const envFile = path.join(f.dir, "test.env"); writeFileSync(envFile, "ENVIRONMENT_ROLE=dev\n");
  const port = await unusedPort();
  const args = ["--no-print-directory", `WEB_DIR=${path.relative(repo, f.app)}`, `WEB_PID_FILE=${path.join(f.dir, "run/ui.pid")}`, `WEB_LOG=${path.join(f.dir, "logs/ui.log")}`, `NPM=${f.env.NPM}`, `WEB_PORT=${port}`, "WEB_HOST=127.0.0.1", `ENV_FILE=${envFile}`];
  execFileSync("make", [...args, "web-build"], { cwd: repo, env: { ...process.env, ENVIRONMENT_ROLE: "dev" } });
  // A forced build failure proves web starts the existing artifact, without rebuilding it.
  execFileSync("make", [...args, "web"], { cwd: repo, env: { ...process.env, ENVIRONMENT_ROLE: "dev", FAKE_BUILD_FAIL: "1" } });
  const pid = Number(readFileSync(path.join(f.dir, "run/ui.pid"), "utf8")); pids.push(pid);
  assert.ok(pid > 1);
});

test("owned status/stop checks process identity and retires only its group", async () => {
  const f = fixture(); const c = config(f, await unusedPort());
  const started = await startUI(c, "turbo", f.env); pids.push(started.pid);
  assert.equal(uiStatus(c).verified, true);
  await assert.rejects(stopUI({ ...c, role: "preprod" }), /another environment/);
  assert.equal(uiStatus(c).running, true);
  assert.equal((await stopUI(c)).running, false);
  assert.equal(uiStatus(c).running, false);
  assert.equal(existsSync(c.pidFile), false);
  assert.equal(existsSync(`${c.pidFile}.identity.json`), false);
});
