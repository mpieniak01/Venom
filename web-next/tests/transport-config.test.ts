import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { configuredLanOrigins, trustedLanDevOrigins } from "../scripts/transport-config.mjs";

describe("Next trusted LAN development origins", () => {
  it("keeps the secure default closed", () => {
    assert.deepEqual(trustedLanDevOrigins({}), []);
    assert.deepEqual(trustedLanDevOrigins({ VENOM_OPERATOR_ACCESS: "secure", VENOM_LAN_ORIGINS: "http://venom.test:3300" }), []);
  });
  it("uses only explicitly configured hostnames, removes ports and deduplicates", () => {
    assert.deepEqual(trustedLanDevOrigins({
      VENOM_OPERATOR_ACCESS: "trusted_lan",
      VENOM_LAN_ORIGINS: "http://venom.test:3300,https://venom.test:3443,http://192.168.50.10:3300",
    }), ["venom.test", "192.168.50.10"]);
  });
  it("rejects wildcard, credentials and path values instead of widening the list", () => {
    for (const value of ["http://*.test:3300", "http://user:pass@venom.test:3300", "http://venom.test:3300/path", "*"]) {
      assert.throws(() => configuredLanOrigins({ VENOM_LAN_ORIGINS: value }));
    }
  });
  it("wires the hostnames to Next allowedDevOrigins in trusted LAN", async () => {
    const originalAccess = process.env.VENOM_OPERATOR_ACCESS;
    const originalOrigins = process.env.VENOM_LAN_ORIGINS;
    try {
      process.env.VENOM_OPERATOR_ACCESS = "trusted_lan";
      process.env.VENOM_LAN_ORIGINS = "http://venom.test:3300,http://192.168.50.10:3300";
      const { default: config } = await import("../next.config");
      assert.deepEqual(config.allowedDevOrigins, ["venom.test", "192.168.50.10"]);
    } finally {
      if (originalAccess === undefined) delete process.env.VENOM_OPERATOR_ACCESS;
      else process.env.VENOM_OPERATOR_ACCESS = originalAccess;
      if (originalOrigins === undefined) delete process.env.VENOM_LAN_ORIGINS;
      else process.env.VENOM_LAN_ORIGINS = originalOrigins;
    }
  });
});
