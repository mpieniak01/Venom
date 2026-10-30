#!/usr/bin/env node
/** One build/start path for Make and the stack launcher; never kills an occupied port. */
import { spawn, spawnSync, execFileSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, openSync, closeSync, readFileSync, writeFileSync, unlinkSync, readdirSync, lstatSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { nextDistDir } from './build-paths.mjs';

function remove(file) { if (existsSync(file)) unlinkSync(file); }
function alive(pid) { try { process.kill(pid, 0); return true; } catch { return false; } }
function ticks(pid) { try { return readFileSync(`/proc/${pid}/stat`, 'utf8').split(') ')[1].split(' ')[19]; } catch { return null; } }
export function lifecycleConfig(env = process.env, cwd = process.cwd()) {
  const root = path.resolve(cwd, env.WEB_DIR || 'web-next');
  const distName = nextDistDir(env);
  const role = env.ENVIRONMENT_ROLE || 'dev';
  if (!['dev', 'preprod', 'prod'].includes(role)) throw new Error('Unknown ENVIRONMENT_ROLE');
  const port = Number(env.WEB_PORT || 3000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid WEB_PORT');
  return { root, distName, dist: path.join(root, distName), role, port,
    host: env.WEB_HOST || '0.0.0.0', pidFile: path.resolve(cwd, env.WEB_PID_FILE || '.web-next.pid'),
    log: path.resolve(cwd, env.WEB_LOG || 'logs/web-next.log'), npm: env.NPM || 'npm' };
}
function digestFileTree(hash, root, rel = '') {
  if (!existsSync(path.join(root, rel))) return;
  for (const name of readdirSync(path.join(root, rel)).sort()) {
    if (name === 'node_modules' || name === '.git' || name.startsWith('.next')) continue;
    const item = path.join(rel, name);
    const stat = lstatSync(path.join(root, item));
    if (stat.isDirectory()) digestFileTree(hash, root, item);
    else if (stat.isFile()) hash.update(item).update(readFileSync(path.join(root, item)));
  }
}
function environmentFingerprint(env) {
  const hash = createHash('sha256');
  for (const key of Object.keys(env).filter((key) => key.startsWith('NEXT_PUBLIC_') || ['API_PROXY_TARGET', 'VENOM_OPERATOR_ACCESS', 'VENOM_LAN_ORIGINS'].includes(key)).sort()) {
    hash.update(key).update('\0').update(env[key] || '').update('\0');
  }
  return hash.digest('hex');
}
export function artifactFingerprint(config, env = process.env) {
  const hash = createHash('sha256');
  const head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: config.root, encoding: 'utf8' }).trim();
  hash.update(head).update(config.role).update(config.distName);
  hash.update(execFileSync('git', ['diff', 'HEAD', '--', '../venom_core'], { cwd: config.root }));
  const files = execFileSync('git', ['ls-files', '-z', '--', '.'], { cwd: config.root });
  for (const file of files.toString().split('\0').filter(Boolean).sort()) {
    // Generated metadata contains a timestamp, and does not determine application compatibility.
    if (file === 'public/meta.json') continue;
    const absolute = path.join(config.root, file);
    hash.update(file).update(existsSync(absolute) ? readFileSync(absolute) : 'MISSING');
  }
  digestFileTree(hash, path.join(config.root, 'optional-modules'));
  hash.update(environmentFingerprint(env)).update(process.versions.node);
  // Store only a digest, never configuration or credentials.
  return hash.digest('hex');
}
function stampPath(config) { return path.join(config.dist, 'venom-build.json'); }
export function verifyArtifact(config, env = process.env) {
  const stamp = JSON.parse(readFileSync(stampPath(config), 'utf8'));
  const server = [path.join(config.dist, 'standalone', 'server.js'), path.join(config.dist, 'standalone', 'web-next', 'server.js')].some(existsSync);
  if (!server || !existsSync(path.join(config.dist, 'BUILD_ID'))) throw new Error('Missing standalone build; run make web-build');
  if (stamp.fingerprint !== artifactFingerprint(config, env)) throw new Error('Stale or incompatible build; run make web-build for this environment');
}
export function buildArtifact(config, env = process.env) {
  if (existsSync(config.pidFile) && alive(Number(readFileSync(config.pidFile, 'utf8').trim()))) throw new Error('Stop the owning UI before rebuilding its artifact');
  remove(stampPath(config));
  const result = spawnSync(config.npm, ['run', 'build'], { cwd: config.root, env, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`UI build failed (${result.status})`);
  const server = [path.join(config.dist, 'standalone', 'server.js'), path.join(config.dist, 'standalone', 'web-next', 'server.js')].some(existsSync);
  if (!server || !existsSync(path.join(config.dist, 'BUILD_ID'))) throw new Error('Build did not produce standalone artifact');
  writeFileSync(stampPath(config), JSON.stringify({ schema: 1, fingerprint: artifactFingerprint(config, env) }) + '\n', { mode: 0o600 });
}
function identityPath(config) { return `${config.pidFile}.identity.json`; }
function launchIdentity(config, mode, env) { return JSON.stringify({ root: config.root, role: config.role, dist: config.dist, port: config.port, host: config.host, mode, configuration: environmentFingerprint(env) }); }
async function ready(config, token) {
  const host = ['0.0.0.0', '::'].includes(config.host) ? '127.0.0.1' : config.host;
  try {
    const response = await fetch(`http://${host.includes(':') ? `[${host}]` : host}:${config.port}/_venom/ready`, {
      headers: { 'x-venom-start-token': token }, signal: AbortSignal.timeout(2500), redirect: 'error',
    });
    return response.status === 200 && (await response.text()) === token;
  } catch { return false; }
}
async function freePort(config) {
  const probe = net.createServer();
  await new Promise((resolve, reject) => { probe.once('error', reject); probe.listen(config.port, config.host, resolve); });
  await new Promise((resolve) => probe.close(resolve));
}
async function retire(child) {
  if (!child.pid) return;
  try { process.kill(-child.pid, 'SIGTERM'); } catch { /* already exited */ }
  for (let i = 0; i < 20 && alive(child.pid); i++) await new Promise((resolve) => setTimeout(resolve, 100));
  try { process.kill(-child.pid, 'SIGKILL'); } catch { /* already exited */ }
}
export async function startUI(config, mode, env = process.env) {
  if (mode === 'start') verifyArtifact(config, env);
  const identity = launchIdentity(config, mode, env);
  if (existsSync(config.pidFile)) {
    const pid = Number(readFileSync(config.pidFile, 'utf8').trim());
    if (Number.isSafeInteger(pid) && pid > 1 && alive(pid)) {
      let owned;
      try { owned = JSON.parse(readFileSync(identityPath(config), 'utf8')); } catch { /* unmanaged process */ }
      if (owned?.pid === pid && owned.ticks === ticks(pid) && owned.identity === identity && await ready(config, owned.token)) {
        console.log(`[web] Already ready: ${config.role}/${mode}, PID ${pid}`);
        return { reused: true, pid };
      }
      throw new Error('UI PID belongs to another mode/environment or is unverified; stop the owning instance explicitly');
    }
    remove(config.pidFile);
    remove(identityPath(config));
  }
  await freePort(config);
  mkdirSync(path.dirname(config.pidFile), { recursive: true });
  mkdirSync(path.dirname(config.log), { recursive: true });
  const fd = openSync(config.log, 'a', 0o600);
  const token = randomUUID();
  const command = { start: 'start', turbo: 'dev:turbo', 'turbo-debug': 'dev:turbo:debug', webpack: 'dev' }[mode];
  if (!command) { closeSync(fd); throw new Error('Unknown UI mode'); }
  const child = spawn(config.npm, ['run', command, '--', '--hostname', config.host, '--port', String(config.port)], {
    cwd: config.root, env: { ...env, VENOM_UI_START_TOKEN: token }, detached: true, stdio: ['ignore', fd, fd],
  });
  closeSync(fd);
  let spawnError;
  child.once('error', (error) => { spawnError = error; });
  try {
    if (!child.pid) throw new Error('UI process could not be created');
    writeFileSync(config.pidFile, `${child.pid}\n`, { mode: 0o600 });
    writeFileSync(identityPath(config), JSON.stringify({ pid: child.pid, ticks: ticks(child.pid), identity, token }) + '\n', { mode: 0o600 });
    const timeout = Number(env.WEB_READY_TIMEOUT_SEC || 90) * 1000;
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      if (spawnError || child.exitCode !== null || child.signalCode !== null) throw spawnError || new Error('UI exited before readiness');
      if (await ready(config, token)) {
        child.unref();
        console.log(`[web] Ready: ${config.role}/${mode}, PID ${child.pid}, http://${config.host}:${config.port}`);
        return { reused: false, pid: child.pid };
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    throw new Error('UI readiness timeout; inspect WEB_LOG');
  } catch (error) {
    await retire(child);
    remove(config.pidFile);
    remove(identityPath(config));
    throw error;
  }
}
export function uiStatus(config) {
  if (!existsSync(config.pidFile)) return { running: false, verified: false };
  const pid = Number(readFileSync(config.pidFile, 'utf8').trim());
  if (!Number.isSafeInteger(pid) || pid <= 1) throw new Error('Invalid UI PID file');
  if (!alive(pid)) return { running: false, verified: false, pid };
  let record;
  try { record = JSON.parse(readFileSync(identityPath(config), 'utf8')); } catch { throw new Error('Unverified UI identity; refusing process control'); }
  const identity = JSON.parse(record.identity);
  const verified = record.pid === pid && record.ticks === ticks(pid) && identity.root === config.root && identity.role === config.role && identity.dist === config.dist && identity.port === config.port && identity.host === config.host;
  if (!verified) throw new Error('UI identity belongs to another environment or process');
  return { running: true, verified: true, pid, mode: identity.mode };
}
export async function stopUI(config) {
  const status = uiStatus(config);
  if (!status.running) {
    remove(config.pidFile); remove(identityPath(config));
    return status;
  }
  await retire({ pid: status.pid });
  // Do not remove a replacement instance's files if another launch raced with stop.
  if (existsSync(config.pidFile) && Number(readFileSync(config.pidFile, 'utf8').trim()) === status.pid) {
    remove(config.pidFile); remove(identityPath(config));
  }
  return { running: false, verified: true, pid: status.pid };
}
export async function main(args = process.argv.slice(2), env = process.env) {
  const config = lifecycleConfig(env);
  const childEnv = { ...env, NEXT_DIST_DIR: config.distName, ENVIRONMENT_ROLE: config.role, NEXT_MODE: args[0] === 'dev' ? 'dev' : 'prod', NEXT_TELEMETRY_DISABLED: '1' };
  if (args[0] === 'status') console.log(JSON.stringify(uiStatus(config)));
  else if (args[0] === 'stop') console.log(JSON.stringify(await stopUI(config)));
  else if (args[0] === 'build') buildArtifact(config, childEnv);
  else if (args[0] === 'start') await startUI(config, 'start', childEnv);
  else if (args[0] === 'dev') await startUI(config, args[1] || 'turbo', childEnv);
  else throw new Error('Expected build|start|stop|status|dev [turbo|turbo-debug|webpack]');
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(`[web] ${error.message}`); process.exitCode = 1; });
}
