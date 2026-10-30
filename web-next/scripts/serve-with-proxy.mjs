#!/usr/bin/env node
import { spawn } from "node:child_process";
import http from "node:http";
import net from "node:net";
import { createTransportProxy, proxySettings } from "./transport-proxy.mjs";

const mode = process.argv[2];
const args = process.argv.slice(3);
function option(name, fallback) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
}
const host = option("--hostname", process.env.HOSTNAME || "0.0.0.0");
const port = Number(option("--port", process.env.PORT || 3000));
const probe = net.createServer();
await new Promise((resolve, reject) => { probe.once("error", reject); probe.listen(0, "127.0.0.1", resolve); });
const innerPort = probe.address().port;
await new Promise((resolve) => probe.close(resolve));
const settings = proxySettings();
const { requestHandler, upgradeHandler } = createTransportProxy({
  uiTarget: `http://127.0.0.1:${innerPort}`, settings,
});
const server = http.createServer(async (request, response) => {
  // A per-launch token proves this entry and its actual Next child are ready.
  // Regular browser traffic continues through the existing streaming proxy.
  const token = process.env.VENOM_UI_START_TOKEN;
  if (token && request.url === "/_venom/ready" && request.headers["x-venom-start-token"] === token) {
    try {
      const result = await fetch(`http://127.0.0.1:${innerPort}/`, { signal: AbortSignal.timeout(2000), redirect: "manual" });
      await result.body?.cancel();
      if (result.status >= 200 && result.status < 400) {
        response.writeHead(200, { "content-type": "text/plain", "cache-control": "no-store" });
        response.end(token);
        return;
      }
    } catch { /* Child is still starting or has failed. */ }
    response.writeHead(503, { "cache-control": "no-store" });
    response.end("UI not ready");
    return;
  }
  requestHandler(request, response);
});
const sockets = new Set();
server.on("connection", (socket) => {
  sockets.add(socket);
  socket.once("close", () => sockets.delete(socket));
});
server.on("upgrade", upgradeHandler);
const childArgs = mode === "start"
  ? ["scripts/start-server.mjs"]
  : ["node_modules/next/dist/bin/next", "dev", args.includes("--turbo") ? "--turbo" : "--webpack", "--hostname", "127.0.0.1", "--port", String(innerPort)];
const child = spawn(process.execPath, childArgs, {
  cwd: process.cwd(), stdio: "inherit",
  env: { ...process.env, PORT: String(innerPort), HOSTNAME: "127.0.0.1" },
});
let stopping = false;
let requestedStop = false;
function stop(signal = "SIGTERM") {
  if (stopping) return;
  stopping = true;
  server.close();
  // HTTP close does not retire active streams or upgraded connections.
  for (const socket of sockets) socket.destroy();
  child.kill(signal);
}
process.on("SIGINT", () => { requestedStop = true; stop("SIGINT"); });
process.on("SIGTERM", () => { requestedStop = true; stop(); });
child.once("error", (error) => { console.error(error); stop(); process.exitCode = 1; });
child.once("exit", (code) => { stop(); process.exitCode = process.exitCode || (code ?? (requestedStop ? 0 : 1)); });
server.once("error", (error) => { console.error(error); stop(); process.exitCode = 1; });
server.listen(port, host, () => console.log(`[transport] ${settings.profile} entry http://${host}:${server.address().port}; API streamed to configured backend`));
