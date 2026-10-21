import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

const ORIGINAL_ENV = { ...process.env };
const ORIGINAL_WINDOW = globalThis.window;

function restoreEnv() {
  for (const key of Object.keys(process.env)) {
    if (!(key in ORIGINAL_ENV)) {
      delete process.env[key];
    }
  }
  for (const [key, value] of Object.entries(ORIGINAL_ENV)) {
    process.env[key] = value;
  }
}

function setWindowLocation(origin: string): void {
  const parsed = new URL(origin);
  const fakeWindow = {
    location: {
      origin,
      hostname: parsed.hostname,
      port: parsed.port,
    },
  };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: fakeWindow,
  });
}

async function loadEnvModule(tag: string) {
  return import(`../lib/env.ts?scenario=${tag}-${Date.now()}`);
}

describe("env api base policy", () => {
  beforeEach(() => {
    restoreEnv();
  });

  afterEach(() => {
    restoreEnv();
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      writable: true,
      value: ORIGINAL_WINDOW,
    });
  });

  it("does not fallback to localhost by default", async () => {
    delete process.env.NEXT_PUBLIC_API_BASE;
    delete process.env.API_PROXY_TARGET;
    delete process.env.NEXT_PUBLIC_API_URL;
    delete process.env.NEXT_PUBLIC_API_LOCALHOST_FALLBACK;
    delete process.env.API_LOCALHOST_FALLBACK;
    setWindowLocation("http://localhost:3000");

    const mod = await loadEnvModule("fallback-disabled");
    assert.equal(mod.getApiBaseUrl(), "");
  });

  it("enables localhost fallback only when feature flag is set", async () => {
    delete process.env.NEXT_PUBLIC_API_BASE;
    delete process.env.API_PROXY_TARGET;
    delete process.env.NEXT_PUBLIC_API_URL;
    process.env.NEXT_PUBLIC_API_LOCALHOST_FALLBACK = "true";
    setWindowLocation("http://localhost:3000");

    const mod = await loadEnvModule("fallback-enabled");
    assert.equal(mod.getApiBaseUrl(), "http://127.0.0.1:8800");
  });

  it("prefers explicit api base over localhost fallback policy", async () => {
    process.env.NEXT_PUBLIC_API_BASE = "https://api.example.test/";
    process.env.NEXT_PUBLIC_API_LOCALHOST_FALLBACK = "true";
    setWindowLocation("http://localhost:3000");

    const mod = await loadEnvModule("explicit-base");
    assert.equal(mod.getApiBaseUrl(), "http://api.example.test");
  });

  it("preserves explicit wss websocket bases for audio", async () => {
    process.env.NEXT_PUBLIC_AUDIO_WS_BASE = "wss://audio.example.test";
    setWindowLocation("https://app.example.test");

    const mod = await loadEnvModule("audio-wss-base");
    assert.equal(mod.getAudioWsUrl(), "wss://audio.example.test/ws/audio");
  });

  it("normalizes websocket bases without scheme", async () => {
    process.env.NEXT_PUBLIC_AUDIO_WS_BASE = "localhost:8000";
    setWindowLocation("http://localhost:3000");

    const mod = await loadEnvModule("audio-host-base");
    assert.equal(mod.getAudioWsUrl(), "ws://localhost:8000/ws/audio");
  });
  it("uses an explicit event websocket on a separate development port", async () => {
    process.env.NEXT_PUBLIC_WS_BASE = "ws://127.0.0.1:8800";
    setWindowLocation("http://127.0.0.1:3300");

    const mod = await loadEnvModule("explicit-events-port");
    assert.equal(mod.getWsBaseUrl(), "ws://127.0.0.1:8800");
  });

  it("uses the panel origin for default event and audio WebSockets", async () => {
    delete process.env.NEXT_PUBLIC_API_BASE;
    delete process.env.NEXT_PUBLIC_API_URL;
    delete process.env.API_PROXY_TARGET;
    delete process.env.NEXT_PUBLIC_WS_BASE;
    delete process.env.NEXT_PUBLIC_AUDIO_WS_BASE;
    setWindowLocation("http://venom.test:3300");
    const mod = await loadEnvModule("same-origin-defaults");
    assert.equal(mod.getWsBaseUrl(), "ws://venom.test:3300");
    assert.equal(mod.getAudioWsUrl(), "ws://venom.test:3300/ws/audio");
  });

  it("trusted LAN ignores old absolute browser API/WS targets", async () => {
    process.env.NEXT_PUBLIC_TRANSPORT_PROFILE = "trusted_lan";
    process.env.NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000";
    process.env.NEXT_PUBLIC_WS_BASE = "ws://127.0.0.1:8000";
    process.env.NEXT_PUBLIC_AUDIO_WS_BASE = "ws://127.0.0.1:8000";
    process.env.NEXT_PUBLIC_API_LOCALHOST_FALLBACK = "true";
    setWindowLocation("http://venom.test:3300");
    const mod = await loadEnvModule("same-origin-lan");
    assert.equal(mod.getApiBaseUrl(), "");
    assert.equal(mod.getWsBaseUrl(), "ws://venom.test:3300");
    assert.equal(mod.getAudioWsUrl(), "ws://venom.test:3300/ws/audio");
  });

  it("trusted LAN server requests use the configured internal API instead of stale public URLs", async () => {
    process.env.NEXT_PUBLIC_TRANSPORT_PROFILE = "trusted_lan";
    process.env.NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000";
    process.env.API_PROXY_TARGET = "http://127.0.0.1:8800";
    process.env.URL_SCHEME_POLICY = "force_https";
    const mod = await loadEnvModule("lan-server-api");
    assert.equal(mod.getServerApiBaseUrl(), "http://127.0.0.1:8800");
  });

});
