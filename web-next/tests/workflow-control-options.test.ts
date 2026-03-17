import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildPropertyPanelOptions } from "../lib/workflow-control-options";

describe("workflow control property panel options", () => {
  it("includes full catalogs from control options", () => {
    const options = buildPropertyPanelOptions(
      {
        decision_strategies: ["standard", "advanced"],
        intent_modes: ["simple", "advanced", "expert"],
        kernels: ["standard", "optimized"],
        providers: {
          local: ["ollama"],
          cloud: ["openai"],
        },
        embeddings: {
          local: ["sentence-transformers"],
          cloud: ["openai-embeddings"],
        },
        provider_sources: ["local", "cloud"],
        embedding_sources: ["local", "cloud"],
        active: {
          provider_source: "local",
          embedding_source: "local",
        },
      },
      null,
      null
    );

    assert.deepEqual(options.strategies, ["standard", "advanced"]);
    assert.deepEqual(options.intentModes, ["simple", "advanced", "expert"]);
    assert.deepEqual(options.kernels, ["standard", "optimized"]);
    assert.deepEqual(options.providersBySource.local, ["ollama"]);
    assert.deepEqual(options.providersBySource.cloud, ["openai"]);
    assert.deepEqual(options.modelsBySource.local, ["sentence-transformers"]);
    assert.deepEqual(options.modelsBySource.cloud, ["openai-embeddings"]);
  });

  it("keeps effective provider and embedding visible when missing in catalog", () => {
    const options = buildPropertyPanelOptions(
      {
        decision_strategies: ["standard"],
        intent_modes: ["simple"],
        kernels: ["standard"],
        providers: {
          local: ["ollama"],
          cloud: ["openai"],
        },
        embeddings: {
          local: ["sentence-transformers"],
          cloud: ["openai-embeddings"],
        },
        provider_sources: ["local", "cloud"],
        embedding_sources: ["local", "cloud"],
        active: {
          provider_source: "cloud",
          embedding_source: "cloud",
        },
      },
      {
        provider: { active: "azure-openai", sourceType: "cloud" },
        embedding_model: "text-embedding-3-large",
        embedding_source: "cloud",
      },
      null
    );

    assert.equal(options.providersBySource.cloud[0], "azure-openai");
    assert.equal(options.modelsBySource.cloud[0], "text-embedding-3-large");
  });
});
