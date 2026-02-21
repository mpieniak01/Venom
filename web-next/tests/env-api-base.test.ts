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
    assert.equal(mod.getApiBaseUrl(), "http://127.0.0.1:8000");
  });

  it("prefers explicit api base over localhost fallback policy", async () => {
    process.env.NEXT_PUBLIC_API_BASE = "https://api.example.test/";
    process.env.NEXT_PUBLIC_API_LOCALHOST_FALLBACK = "true";
    setWindowLocation("http://localhost:3000");

    const mod = await loadEnvModule("explicit-base");
    assert.equal(mod.getApiBaseUrl(), "http://api.example.test");
  });
});
