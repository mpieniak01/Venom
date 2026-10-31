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
export function alive(pid) {
  if (!Number.isSafeInteger(pid) || pid <= 1) return false;
  try { process.kill(pid, 0); return true; } catch (error) { return error?.code !== 'ESRCH'; }
}
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
  for (const key of Object.keys(env).filter((key) => key.startsWith('NEXT_PUBLIC_') || ['API_PROXY_TARGET', 'VENOM_OPERATOR_ACCESS', 'VENOM_LAN_ORIGINS', 'VENOM_VARIANT', 'VENOM_UI_READY_PATH'].includes(key)).sort()) {
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
    // Next rewrites generated declaration imports for each distDir; neither they
    // nor timestamp metadata determine runtime artifact compatibility.
    if (['public/meta.json', 'next-env.d.ts'].includes(file)) continue;
    const absolute = path.join(config.root, file);
    hash.update(file).update(existsSync(absolute) ? readFileSync(absolute) : 'MISSING');
  }
  if (path.basename(config.root) === 'web-studio') {
    const shared = path.join(config.root, '../web-next');
    for (const directory of ['components', 'hooks', 'lib', 'scripts', 'app/fonts']) digestFileTree(hash, path.join(shared, directory));
    for (const file of ['app/layout.tsx', 'app/providers.tsx', 'app/globals.css', 'public/chat2-capture-worklet.js', 'package-lock.json']) {
      const source = path.join(shared, file);
      if (existsSync(source)) hash.update(file).update(readFileSync(source));
    }
  }
  digestFileTree(hash, path.join(config.root, 'optional-modules'));
  hash.update(environmentFingerprint(env)).update(process.versions.node);
  // Store only a digest, never configuration or credentials.
  return hash.digest('hex');
}
function stampPath(config) { return path.join(config.dist, 'venom-build.json'); }
export function verifyArtifact(config, env = process.env) {
  let text;
  try { text = readFileSync(stampPath(config), 'utf8'); } catch (error) {
    if (error?.code === 'ENOENT') throw new Error('Missing build stamp; run make web-build for this environment', { cause: error });
    throw error;
  }
  const stamp = JSON.parse(text);
  const server = [path.join(config.dist, 'standalone', 'server.js'), path.join(config.dist, 'standalone', path.basename(config.root), 'server.js')].some(existsSync);
  if (!server || !existsSync(path.join(config.dist, 'BUILD_ID'))) throw new Error('Missing standalone build; run make web-build');
  if (stamp.fingerprint !== artifactFingerprint(config, env)) throw new Error('Stale or incompatible build; run make web-build for this environment');
}
export function buildArtifact(config, env = process.env) {
  if (existsSync(config.pidFile) && alive(Number(readFileSync(config.pidFile, 'utf8').trim()))) throw new Error('Stop the owning UI before rebuilding its artifact');
  remove(stampPath(config));
  const result = spawnSync(config.npm, ['run', 'build'], { cwd: config.root, env, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`UI build failed (${result.status})`);
  const server = [path.join(config.dist, 'standalone', 'server.js'), path.join(config.dist, 'standalone', path.basename(config.root), 'server.js')].some(existsSync);
  if (!server || !existsSync(path.join(config.dist, 'BUILD_ID'))) throw new Error('Build did not produce standalone artifact');
  writeFileSync(stampPath(config), JSON.stringify({ schema: 1, fingerprint: artifactFingerprint(config, env) }) + '\n', { mode: 0o600 });
}
function identityPath(config) { return `${config.pidFile}.identity.json`; }
function receiptSnapshot(config) {
  return [config.pidFile, identityPath(config)].map((file) => {
    try {
      const stat = lstatSync(file, { bigint: true });
      if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('Unverified UI ownership receipt');
      return { file, text: readFileSync(file, 'utf8'), stamp: [stat.dev, stat.ino, stat.mtimeNs, stat.ctimeNs].join(':') };
    } catch (error) {
      if (error?.code === 'ENOENT') return { file, text: null, stamp: null };
      throw error;
    }
  });
}
function assertReceiptUnchanged(config, snapshot) {
  if (JSON.stringify(receiptSnapshot(config)) !== JSON.stringify(snapshot)) {
    throw new Error('UI ownership receipt changed; preserving replacement files');
  }
}
function removeReceipt(config, snapshot) {
  assertReceiptUnchanged(config, snapshot);
  for (const item of snapshot) remove(item.file);
}

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
/** Retire the token-owned session, even after npm has exited and reparented Next. */
function retireOwned(pid, expectedTicks, root, token) {
  const helper = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../scripts/dev/runtime_teardown.py');
  const result = spawnSync(process.env.PYTHON_BIN || 'python3', [helper, 'retire-launch', String(pid), String(expectedTicks || ''), root, 'VENOM_UI_START_TOKEN', String(token || '')], { encoding: 'utf8', timeout: 35000 });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Owned UI stop incomplete: ${result.stderr || result.stdout}`);
}
async function retire(child, expectedTicks, root, token) {
  if (child.pid) retireOwned(child.pid, expectedTicks, root, token);
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
    const stale = receiptSnapshot(config);
    removeReceipt(config, stale);
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
  const childTicks = child.pid ? ticks(child.pid) : null;
  let spawnError;
  child.once('error', (error) => { spawnError = error; });
  let receipt;
  try {
    if (!child.pid) throw new Error('UI process could not be created');
    writeFileSync(config.pidFile, `${child.pid}\n`, { mode: 0o600 });
    writeFileSync(identityPath(config), JSON.stringify({ pid: child.pid, ticks: childTicks, identity, token, transaction: env.VENOM_UI_TRANSACTION || null }) + '\n', { mode: 0o600 });
    receipt = receiptSnapshot(config);
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
    await retire(child, childTicks, config.root, token);
    if (receipt) removeReceipt(config, receipt);
    throw error;
  }
}
export function uiStatus(config) {
  if (!existsSync(config.pidFile)) return { running: false, verified: false };
  const pid = Number(readFileSync(config.pidFile, 'utf8').trim());
  if (!Number.isSafeInteger(pid) || pid <= 1) throw new Error('Invalid UI PID file');
  const leaderAlive = alive(pid);
  if (!leaderAlive && !existsSync(identityPath(config))) return { running: false, verified: false, pid };
  let record;
  try { record = JSON.parse(readFileSync(identityPath(config), 'utf8')); } catch { throw new Error('Unverified UI identity; refusing process control'); }
  const identity = JSON.parse(record.identity);
  const verified = record.pid === pid && (!leaderAlive || record.ticks === ticks(pid)) && identity.root === config.root && identity.role === config.role && identity.dist === config.dist && identity.port === config.port && identity.host === config.host;
  if (!verified) throw new Error('UI identity belongs to another environment or process');
  return { running: leaderAlive, verified: true, pid, mode: identity.mode, ticks: record.ticks };
}
export async function stopUI(config, expectedTransaction = null) {
  const receipt = receiptSnapshot(config);
  if (expectedTransaction !== null) {
    if (!expectedTransaction) throw new Error('Missing UI startup transaction');
    const record = receipt[1].text === null ? null : JSON.parse(receipt[1].text);
    if (record?.transaction !== expectedTransaction) return { running: null, skipped: true };
  }
  const status = uiStatus(config);
  assertReceiptUnchanged(config, receipt);
  if (!status.running && !status.verified) {
    removeReceipt(config, receipt);
    return status;
  }
  const record = JSON.parse(receipt[1].text);
  await retire({ pid: status.pid }, status.ticks, config.root, record.token);
  removeReceipt(config, receipt);
  return { running: false, verified: true, pid: status.pid };
}
export async function rollbackUI(config, transaction) {
  if (!transaction) throw new Error('Missing UI startup transaction');
  return stopUI(config, transaction);
}
export async function main(args = process.argv.slice(2), env = process.env) {
  const config = lifecycleConfig(env);
  const childEnv = { ...env, NEXT_DIST_DIR: config.distName, ENVIRONMENT_ROLE: config.role, NEXT_MODE: args[0] === 'dev' ? 'dev' : 'prod', NEXT_TELEMETRY_DISABLED: '1' };
  if (args[0] === 'status') console.log(JSON.stringify(uiStatus(config)));
  else if (args[0] === 'stop') console.log(JSON.stringify(await stopUI(config)));
  else if (args[0] === 'rollback') console.log(JSON.stringify(await rollbackUI(config, args[1])));
  else if (args[0] === 'build') buildArtifact(config, childEnv);
  else if (args[0] === 'start') await startUI(config, 'start', childEnv);
  else if (args[0] === 'dev') await startUI(config, args[1] || 'turbo', childEnv);
  else throw new Error('Expected build|start|stop|status|rollback <transaction>|dev [turbo|turbo-debug|webpack]');
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(`[web] ${error.message}`); process.exitCode = 1; });
}
