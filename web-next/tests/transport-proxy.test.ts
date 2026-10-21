import assert from "node:assert/strict";
import http from "node:http";
import net from "node:net";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { afterEach, describe, it } from "node:test";
import { createTransportProxy, isPrivateAddress, proxySettings, sanitizeHeaders } from "../scripts/transport-proxy.mjs";

const servers: http.Server[] = [];
const sockets = new Set<net.Socket>();
afterEach(async () => {
  for (const socket of sockets) socket.destroy();
  sockets.clear();
  await Promise.all(servers.splice(0).map((server) => new Promise<void>((resolve) => server.close(() => resolve()))));
});
async function listen(server: http.Server) {
  servers.push(server);
  server.on("connection", (socket) => { sockets.add(socket); socket.on("close", () => sockets.delete(socket)); });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return `http://127.0.0.1:${(server.address() as net.AddressInfo).port}`;
}
async function fixture(handler: http.RequestListener) {
  const upstream = http.createServer(handler);
  const target = await listen(upstream);
  const settings = proxySettings({ API_PROXY_TARGET: target });
  const proxy = createTransportProxy({ uiTarget: target, settings });
  const edge = http.createServer(proxy.requestHandler);
  edge.on("upgrade", proxy.upgradeHandler);
  return { upstream, settings, edge, origin: await listen(edge) };
}
describe("managed streaming HTTP/WS entry", () => {
  it("defaults to the current internal API port and validates explicit origins", () => {
    assert.equal(proxySettings({}).target.href, "http://127.0.0.1:8800/");
    assert.throws(() => proxySettings({ VENOM_OPERATOR_ACCESS: "trusted_lan" }));
    assert.throws(() => proxySettings({ VENOM_OPERATOR_ACCESS: "other" }));
    assert.throws(() => proxySettings({ VENOM_LAN_ORIGINS: "http://venom.test/path" }));
    assert.throws(() => proxySettings({ API_PROXY_TARGET: "http://user:pass@localhost/" }));
    assert.throws(() => proxySettings({ VENOM_PROXY_MAX_BODY_BYTES: "-1" }));
    assert.equal(isPrivateAddress("203.0.113.8"), false);
    assert.equal(isPrivateAddress("::ffff:192.168.1.8"), true);
    assert.equal(isPrivateAddress("fd12::1"), true);
  });
  it("removes client-supplied forwarding and user identity headers", () => {
    assert.deepEqual(sanitizeHeaders({
      host: "venom.test", forwarded: "for=127.0.0.1", "x-forwarded-for": "127.0.0.1",
      "x-real-ip": "127.0.0.1", "x-venom-shared-entry": "0", "x-authenticated-user": "admin",
      "x-user": "admin", connection: "custom", custom: "hidden", authorization: "Bearer robot",
    }, "custom"), { host: "venom.test", authorization: "Bearer robot" });
  });
  it("normalizes provenance while retaining tokens, Host, Origin and the same-origin API path", async () => {
    const { origin } = await fixture((req, res) => res.end(JSON.stringify({ path: req.url, headers: req.headers })));
    const response = await fetch(`${origin}/api/v1/transport/identity?x=1`, {
      headers: { "x-forwarded-for": "127.0.0.1", "x-user": "admin", "x-venom-shared-entry": "0", authorization: "Bearer robot", origin },
    });
    const data = await response.json();
    assert.equal(data.path, "/api/v1/transport/identity?x=1");
    assert.equal(data.headers.authorization, "Bearer robot");
    assert.equal(data.headers.origin, origin);
    assert.equal(data.headers["x-forwarded-for"], undefined);
    assert.equal(data.headers["x-user"], undefined);
    assert.equal(data.headers["x-venom-client-address"], "127.0.0.1");
    assert.equal(response.headers.get("x-accel-buffering"), "no");
  });
  it("rejects unknown Host/Origin and always marks a trusted LAN relay as shared", async () => {
    const { origin, settings } = await fixture((req, res) => res.end(JSON.stringify(req.headers)));
    settings.profile = "trusted_lan";
    settings.origins = [origin];
    assert.equal((await fetch(`${origin}/api/status`, { headers: { origin: "http://evil.test" } })).status, 403);
    const wrongHost = await new Promise<number>((resolve, reject) => {
      http.get(`${origin}/api/status`, { headers: { host: "evil.test" } }, (res) => { res.resume(); resolve(res.statusCode!); }).on("error", reject);
    });
    assert.equal(wrongHost, 403);
    const response = await fetch(`${origin}/api/status`, { headers: { origin, "x-venom-shared-entry": "0" } });
    assert.equal((await response.json())["x-venom-shared-entry"], "1");
  });
  for (const contentType of ["text/event-stream", "multipart/x-mixed-replace; boundary=frame"]) {
    it(`streams ${contentType} before the upstream finishes and closes on cancellation`, async () => {
      let upstreamResponse: http.ServerResponse | undefined;
      let cancelled = false;
      const { origin } = await fixture((req, res) => {
        upstreamResponse = res;
        res.writeHead(200, { "content-type": contentType, "x-rider-source": "camera", "content-encoding": "identity" });
        res.write("first-frame\n");
        req.on("close", () => { cancelled = true; });
      });
      const response = await fetch(`${origin}/api/media`);
      const reader = response.body!.getReader();
      const first = await reader.read();
      assert.equal(new TextDecoder().decode(first.value), "first-frame\n");
      assert.equal(response.headers.get("content-type"), contentType);
      assert.equal(response.headers.get("x-rider-source"), "camera");
      upstreamResponse!.write("second-frame\n");
      assert.equal(new TextDecoder().decode((await reader.read()).value), "second-frame\n");
      await reader.cancel();
      for (let attempt = 0; attempt < 30 && !cancelled; attempt++) await new Promise((resolve) => setTimeout(resolve, 10));
      assert.equal(cancelled, true);
    });
  }
  it("enforces upload limits without buffering the body", async () => {
    const { origin, settings } = await fixture((req, res) => { req.resume(); req.on("end", () => res.end("done")); });
    settings.maxBodyBytes = 4;
    assert.equal((await fetch(`${origin}/api/upload`, { method: "POST", body: "12345" })).status, 413);
    const body = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode("12345")); controller.close(); } });
    assert.equal((await fetch(`${origin}/api/upload`, { method: "POST", body, duplex: "half" } as RequestInit)).status, 413);
  });
  it("performs a real WebSocket101 upgrade and transfers a frame", async () => {
    const { origin, upstream } = await fixture((_req, res) => res.end("http"));
    upstream.on("upgrade", (req, socket) => {
      assert.equal(req.headers["x-venom-proxy"], "1");
      assert.equal(req.headers["x-forwarded-for"], undefined);
      const accept = createHash("sha1").update(String(req.headers["sec-websocket-key"]) + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest("base64");
      socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
      socket.write(Buffer.from([0x81, 0x02, 0x6f, 0x6b]));
    });
    const socket = new WebSocket(origin.replace("http:", "ws:") + "/ws/events");
    const message = await new Promise<MessageEvent>((resolve, reject) => {
      socket.addEventListener("message", resolve, { once: true });
      socket.addEventListener("error", reject, { once: true });
    });
    assert.equal(message.data, "ok");
    socket.close();
  });
});
