import http from "node:http";
import https from "node:https";
import { isIP } from "node:net";
import { Transform } from "node:stream";
import { configuredLanOrigins } from "./transport-config.mjs";

const HOP_HEADERS = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailer", "transfer-encoding", "upgrade",
]);
const IDENTITY_HEADERS = new Set([
  "forwarded", "x-real-ip", "x-authenticated-user", "x-user", "x-user-id", "x-actor",
]);

export function normalizeAddress(value = "") {
  return value.startsWith("::ffff:") ? value.slice(7) : value;
}

export function isPrivateAddress(value) {
  const address = normalizeAddress(value);
  if (isIP(address) === 4) {
    const [a, b] = address.split(".").map(Number);
    return a === 127 || a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
  }
  return address === "::1" || /^(fc|fd)[0-9a-f]{2}:/i.test(address);
}

/** @param {Record<string, string | undefined>} [env] */
export function proxySettings(env = process.env) {
  const profile = env.VENOM_OPERATOR_ACCESS || "secure";
  if (!["secure", "trusted_lan"].includes(profile)) throw new Error("Invalid VENOM_OPERATOR_ACCESS");
  const origins = configuredLanOrigins(env);
  if (profile === "trusted_lan" && !origins.length) throw new Error("trusted_lan requires VENOM_LAN_ORIGINS");
  const target = new URL(env.API_PROXY_TARGET || "http://127.0.0.1:8800");
  if (!["http:", "https:"].includes(target.protocol) || target.username || target.password || target.pathname !== "/" || target.search || target.hash) {
    throw new Error("Invalid API_PROXY_TARGET");
  }
  const maxBodyBytes = Number(env.VENOM_PROXY_MAX_BODY_BYTES || 67108864);
  if (!Number.isSafeInteger(maxBodyBytes) || maxBodyBytes <= 0) throw new Error("Invalid proxy body limit");
  return { profile, origins, target, maxBodyBytes };
}

export function sanitizeHeaders(headers, connectionTokens = "") {
  const blocked = new Set([...HOP_HEADERS, ...connectionTokens.toLowerCase().split(",").map((value) => value.trim())]);
  return Object.fromEntries(Object.entries(headers).filter(([key]) => {
    const name = key.toLowerCase();
    return !blocked.has(name) && !IDENTITY_HEADERS.has(name) &&
      !name.startsWith("x-forwarded-") && !name.startsWith("x-venom-");
  }));
}

function accessAllowed(request, settings) {
  if (settings.profile !== "trusted_lan") return true;
  const host = request.headers.host?.toLowerCase();
  const allowedHost = settings.origins.some((origin) => new URL(origin).host.toLowerCase() === host);
  const origin = request.headers.origin;
  return allowedHost && (!origin || settings.origins.includes(origin)) &&
    isPrivateAddress(request.socket.remoteAddress);
}

function outboundHeaders(request, settings, api) {
  const headers = sanitizeHeaders(request.headers, request.headers.connection);
  if (api) {
    headers["x-venom-proxy"] = "1";
    headers["x-venom-client-address"] = normalizeAddress(request.socket.remoteAddress);
    headers["x-venom-shared-entry"] = settings.profile === "trusted_lan" ? "1" : "0";
  }
  return headers;
}

function transport(target) {
  return target.protocol === "https:" ? https : http;
}

function isApiPath(path = "") {
  const pathname = path.split("?")[0];
  return pathname.startsWith("/api/") || pathname === "/ws" || pathname.startsWith("/ws/");
}

export function createTransportProxy({ uiTarget, settings = proxySettings() }) {
  const ui = new URL(uiTarget);
  const requestHandler = (request, response) => {
    if (!accessAllowed(request, settings)) {
      response.writeHead(403, { "content-type": "application/json" });
      response.end('{"detail":{"reason_code":"PROXY_ORIGIN_DENIED"}}');
      return;
    }
    const api = isApiPath(request.url);
    const target = api ? settings.target : ui;
    const declaredSize = Number(request.headers["content-length"] || 0);
    if (api && (!Number.isFinite(declaredSize) || declaredSize > settings.maxBodyBytes)) {
      response.writeHead(413);
      response.end();
      return;
    }
    const upstream = transport(target).request(target, {
      method: request.method,
      path: request.url,
      headers: outboundHeaders(request, settings, api),
    }, (incoming) => {
      const headers = sanitizeHeaders(incoming.headers, incoming.headers.connection);
      if (api) headers["x-accel-buffering"] = "no";
      if (!response.headersSent) response.writeHead(incoming.statusCode || 502, headers);
      incoming.pipe(response);
      incoming.on("error", () => response.destroy());
    });
    upstream.on("error", () => {
      if (!response.headersSent) {
        response.writeHead(502);
        response.end();
      } else response.destroy();
    });
    response.on("close", () => upstream.destroy());
    request.on("aborted", () => upstream.destroy());
    let bytes = 0;
    const limit = new Transform({
      transform(chunk, encoding, callback) {
        bytes += chunk.length;
        if (api && bytes > settings.maxBodyBytes) {
          if (!response.headersSent) response.writeHead(413);
          response.end();
          upstream.destroy();
          callback(new Error("Proxy request body too large"));
          return;
        }
        callback(null, chunk);
      },
    });
    limit.on("error", () => request.unpipe(limit));
    request.pipe(limit).pipe(upstream);
  };

  const upgradeHandler = (request, socket, head) => {
    if (!accessAllowed(request, settings)) {
      socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
      return;
    }
    const api = isApiPath(request.url);
    const target = api ? settings.target : ui;
    const headers = outboundHeaders(request, settings, api);
    headers.connection = "Upgrade";
    headers.upgrade = "websocket";
    const upstream = transport(target).request(target, { method: "GET", path: request.url, headers });
    const timer = setTimeout(() => { upstream.destroy(); socket.destroy(); }, 15000);
    upstream.on("upgrade", (incoming, remote, remoteHead) => {
      clearTimeout(timer);
      const responseHeaders = sanitizeHeaders(incoming.headers, incoming.headers.connection);
      responseHeaders.connection = "Upgrade";
      responseHeaders.upgrade = "websocket";
      const lines = Object.entries(responseHeaders).map(([key, value]) => `${key}: ${value}`);
      socket.write(`HTTP/1.1 101 Switching Protocols\r\n${lines.join("\r\n")}\r\n\r\n`);
      if (remoteHead.length) socket.write(remoteHead);
      if (head.length) remote.write(head);
      remote.on("error", () => socket.destroy());
      socket.on("error", () => remote.destroy());
      socket.on("close", () => remote.destroy());
      remote.on("close", () => socket.destroy());
      socket.pipe(remote).pipe(socket);
    });
    upstream.on("response", (incoming) => {
      clearTimeout(timer);
      socket.end(`HTTP/1.1 ${incoming.statusCode || 502} Upgrade rejected\r\nConnection: close\r\n\r\n`);
      incoming.resume();
    });
    upstream.on("error", () => { clearTimeout(timer); socket.destroy(); });
    socket.on("close", () => { clearTimeout(timer); upstream.destroy(); });
    upstream.end();
  };
  return { requestHandler, upgradeHandler };
}
