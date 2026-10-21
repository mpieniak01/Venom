import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { webcrypto } from "node:crypto";
import { createBrowserUuid, getMicrophoneCapability } from "../lib/optional-modules/transport";

describe("public optional-module browser transport", () => {
  it("uses randomUUID where available", () => {
    assert.equal(createBrowserUuid({ randomUUID: () => "native-uuid" } as unknown as Crypto), "native-uuid");
  });
  it("creates CSPRNG RFC4122 v4 UUIDs over HTTP without randomUUID", () => {
    const crypto = { getRandomValues: webcrypto.getRandomValues.bind(webcrypto) } as Crypto;
    const values = new Set(Array.from({ length: 1000 }, () => createBrowserUuid(crypto)));
    assert.equal(values.size, 1000);
    for (const value of values) assert.match(value, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
  it("fails closed when CSPRNG is unavailable", () => {
    assert.throws(() => createBrowserUuid({} as Crypto));
  });
  it("distinguishes insecure LAN from missing browser capture capability", () => {
    assert.equal(getMicrophoneCapability({ isSecureContext: false, navigator: {} } as Window), "insecure_context");
    assert.equal(getMicrophoneCapability({ isSecureContext: true, navigator: {} } as Window), "unavailable");
    assert.equal(getMicrophoneCapability({
      isSecureContext: true,
      navigator: { mediaDevices: { getUserMedia: () => Promise.resolve() } },
    } as unknown as Window), "available");
  });
});
