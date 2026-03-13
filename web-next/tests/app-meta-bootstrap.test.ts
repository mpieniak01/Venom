import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { normalizeEnvironmentRole, resolveBootstrappedMeta } from "../lib/app-meta";

describe("app meta bootstrap", () => {
  afterEach(() => {
    delete (globalThis as { __VENOM_APP_META__?: unknown }).__VENOM_APP_META__;
  });

  it("normalizes known environment role aliases", () => {
    assert.equal(normalizeEnvironmentRole("pre-prod"), "preprod");
    assert.equal(normalizeEnvironmentRole("DEVELOPMENT"), "dev");
    assert.equal(normalizeEnvironmentRole("prod"), "prod");
  });

  it("returns null when bootstrap payload is missing", () => {
    const value = resolveBootstrappedMeta();
    assert.equal(value, null);
  });

  it("returns merged bootstrap meta when payload is present", () => {
    (globalThis as { __VENOM_APP_META__?: unknown }).__VENOM_APP_META__ = {
      version: "1.8.0",
      commit: "abc123",
      environmentRole: "preprod",
      appName: "Venom Cockpit",
    };

    const value = resolveBootstrappedMeta();
    assert.ok(value);
    assert.equal(value?.version, "1.8.0");
    assert.equal(value?.commit, "abc123");
    assert.equal(value?.environmentRole, "preprod");
    assert.equal(value?.appName, "Venom Cockpit");
  });
});
