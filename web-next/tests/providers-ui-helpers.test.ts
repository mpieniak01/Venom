import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { canActivateProvider, providerTypeToTranslationKey } from "../components/providers/provider-list";
import {
  providerStatusColors,
  shouldShowProviderLatency,
  shouldShowProviderMessage,
} from "../components/providers/provider-status-indicator";
import type { ProviderInfo } from "../lib/types";

function buildProvider(overrides: Partial<ProviderInfo> = {}): ProviderInfo {
  return {
    name: "ollama",
    display_name: "Ollama",
    provider_type: "catalog_integrator",
    runtime: "ollama",
    capabilities: {
      install: true,
      search: true,
      activate: true,
      inference: true,
      trainable: false,
    },
    connection_status: {
      status: "connected",
      message: null,
      latency_ms: 42,
    },
    is_active: false,
    endpoint: "http://localhost:11434",
    ...overrides,
  };
}

describe("providers ui helpers", () => {
  it("maps provider type to i18n key", () => {
    assert.equal(
      providerTypeToTranslationKey("catalog_integrator"),
      "providers.types.catalogIntegrator",
    );
    assert.equal(
      providerTypeToTranslationKey("cloud_provider"),
      "providers.types.cloudProvider",
    );
    assert.equal(
      providerTypeToTranslationKey("local_runtime"),
      "providers.types.localRuntime",
    );
  });

  it("computes provider activation visibility", () => {
    const base = buildProvider();
    assert.equal(canActivateProvider(base, true), true);
    assert.equal(canActivateProvider({ ...base, is_active: true }, true), false);
    assert.equal(
      canActivateProvider(
        {
          ...base,
          connection_status: { ...base.connection_status, status: "offline" },
        },
        true,
      ),
      false,
    );
    assert.equal(canActivateProvider(base, false), false);
    assert.equal(
      canActivateProvider(
        {
          ...base,
          capabilities: { ...base.capabilities, activate: false },
        },
        true,
      ),
      false,
    );
  });

  it("exposes stable colors for all provider statuses", () => {
    assert.equal(providerStatusColors.connected, "bg-green-500");
    assert.equal(providerStatusColors.degraded, "bg-yellow-500");
    assert.equal(providerStatusColors.offline, "bg-red-500");
    assert.equal(providerStatusColors.unknown, "bg-gray-400");
  });

  it("shows latency only for connected status with value", () => {
    assert.equal(shouldShowProviderLatency("connected", 12), true);
    assert.equal(shouldShowProviderLatency("connected", 0), true);
    assert.equal(shouldShowProviderLatency("connected", null), false);
    assert.equal(shouldShowProviderLatency("offline", 12), false);
  });

  it("shows message only for non-connected status with non-empty message", () => {
    assert.equal(shouldShowProviderMessage("offline", "Timeout"), true);
    assert.equal(shouldShowProviderMessage("degraded", "Slow"), true);
    assert.equal(shouldShowProviderMessage("connected", "OK"), false);
    assert.equal(shouldShowProviderMessage("offline", ""), false);
    assert.equal(shouldShowProviderMessage("offline", null), false);
  });
});
