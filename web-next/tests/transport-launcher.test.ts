import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, it } from "node:test";

const wrapperPath = fileURLToPath(new URL("../scripts/serve-with-proxy.mjs", import.meta.url));
const wrappers: ChildProcess[] = [];
const directories: string[] = [];
const servers: http.Server[] = [];
const sockets = new Set<net.Socket>();
type Exit = { code: number | null; signal: NodeJS.Signals | null };

function within<T>(promise: Promise<T>, milliseconds = 5000): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Managed entry did not finish in time")), milliseconds);
    promise.then(
      (value) => { clearTimeout(timer); resolve(value); },
      (error: unknown) => { clearTimeout(timer); reject(error); },
    );
  });
}

afterEach(async () => {
  for (const wrapper of wrappers.splice(0)) {
    if (wrapper.exitCode === null && wrapper.signalCode === null) {
      const closed = once(wrapper, "close");
      wrapper.kill("SIGTERM");
      try { await within(closed, 2000); }
      catch { wrapper.kill("SIGKILL"); await within(closed); }
    }
  }
  for (const socket of sockets) socket.destroy();
  sockets.clear();
  await Promise.all(servers.splice(0).map((server) =>
    new Promise<void>((resolve) => server.close(() => resolve()))));
  await Promise.all(directories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

async function backend() {
  const server = http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "text/event-stream" });
    response.write("data: live\n\n");
  });
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
  });
  server.on("upgrade", (_request, socket) => {
    socket.write("HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\nlive");
  });
  servers.push(server);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return `http://127.0.0.1:${(server.address() as net.AddressInfo).port}`;
}

async function launch(origin: string, childExit?: number) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "venom-managed-entry-"));
  directories.push(directory);
  await mkdir(path.join(directory, "scripts"));
  await writeFile(path.join(directory, "scripts/start-server.mjs"), `
    console.log("fixture-child:" + process.pid);
    if (process.env.FIXTURE_CHILD_EXIT !== undefined) {
      setTimeout(() => process.exit(Number(process.env.FIXTURE_CHILD_EXIT)), 500);
    } else {
      setTimeout(() => process.exit(99), 15000);
    }
  `);
  const env: NodeJS.ProcessEnv = { ...process.env, VENOM_OPERATOR_ACCESS: "secure", API_PROXY_TARGET: origin };
  delete env.FIXTURE_CHILD_EXIT;
  if (childExit !== undefined) env.FIXTURE_CHILD_EXIT = String(childExit);
  const wrapper = spawn(process.execPath, [wrapperPath, "start", "--hostname", "127.0.0.1", "--port", "0"], {
    cwd: directory, env, stdio: ["ignore", "pipe", "pipe"],
  });
  wrappers.push(wrapper);
  const exited = new Promise<Exit>((resolve, reject) => {
    wrapper.once("error", reject);
    wrapper.once("exit", (code, signal) => resolve({ code, signal }));
  });
  let output = "";
  let childPid: number | undefined;
  let entry: string | undefined;
  const ready = new Promise<void>((resolve, reject) => {
    wrapper.stdout!.on("data", (chunk: Buffer) => {
      output += chunk.toString();
      const lines = output.split("\n");
      const child = lines.find((line) => line.startsWith("fixture-child:"));
      const address = lines.find((line) => line.startsWith("[transport]"));
      if (child) childPid = Number(child.slice("fixture-child:".length));
      if (address) entry = address.split(" entry ")[1]?.split(";")[0];
      if (childPid && entry) resolve();
    });
    wrapper.stderr!.on("data", (chunk: Buffer) => { output += chunk.toString(); });
    wrapper.once("error", reject);
    wrapper.once("exit", () => {
      if (!childPid || !entry) reject(new Error(`Entry stopped before readiness: ${output}`));
    });
  });
  await within(ready);
  return { wrapper, exited, childPid: childPid!, origin: entry! };
}

describe("managed entry process lifecycle", () => {
  it("closes active HTTP streams and upgraded sockets when stopped", { timeout: 15000 }, async () => {
    const running = await launch(await backend());
    const response = await within(new Promise<http.IncomingMessage>((resolve, reject) => {
      http.get(`${running.origin}/api/events`, resolve).once("error", reject);
    }));
    await once(response, "data");
    response.on("error", () => { /* An intentional shutdown can reset the stream. */ });
    const streamClosed = new Promise<void>((resolve) => response.once("close", resolve));

    const address = new URL(running.origin);
    const socket = net.connect({ host: address.hostname, port: Number(address.port) });
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
    await once(socket, "connect");
    const upgraded = within(new Promise<void>((resolve, reject) => {
      let received = "";
      socket.on("data", (chunk) => {
        received += chunk.toString();
        if (received.includes("101 Switching Protocols") && received.includes("\r\n\r\nlive")) resolve();
      });
      socket.once("error", reject);
    }));
    socket.write(`GET /ws/events HTTP/1.1\r\nHost: ${address.host}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n`);
    await upgraded;
    const upgradedClosed = new Promise<void>((resolve) => socket.once("close", () => resolve()));

    running.wrapper.kill("SIGTERM");
    await within(Promise.all([streamClosed, upgradedClosed, running.exited]));
    assert.equal(response.destroyed, true);
    assert.equal(socket.destroyed, true);
    // The independent backend remains up; stopping it cannot mask leaks.
    assert.equal(servers[0].listening, true);
  });

  it("reports a child terminated by signal as a failed exit", { timeout: 15000 }, async () => {
    const running = await launch(await backend());
    process.kill(running.childPid, "SIGTERM");
    const exit = await within(running.exited);
    assert.notEqual(exit.code, 0);
    assert.equal(exit.signal, null);
  });

  for (const code of [0, 7]) {
    it(`preserves an ordinary child exit code ${code}`, { timeout: 15000 }, async () => {
      const running = await launch(await backend(), code);
      assert.deepEqual(await within(running.exited), { code, signal: null });
    });
  }
});
