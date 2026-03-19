import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildPropertyPanelOptions,
  getCompatibleEmbeddings,
  getCompatibleIntentModes,
  getCompatibleKernels,
  getCompatibleProviders,
} from "../lib/workflow-control-options";

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
        kernel_runtimes: {
          standard: ["python", "docker"],
          optimized: ["python"],
        },
        intent_requirements: {
          simple: { requires_embedding: false },
          advanced: { requires_embedding: true },
          expert: { requires_embedding: true },
        },
        provider_embeddings: {
          ollama: ["sentence-transformers"],
          openai: ["openai-embeddings"],
        },
        embedding_providers: {
          "sentence-transformers": ["ollama"],
          "openai-embeddings": ["openai"],
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
    assert.deepEqual(options.kernelRuntimes.standard, ["python", "docker"]);
    assert.equal(options.intentRequirements.advanced.requires_embedding, true);
    assert.deepEqual(options.providerEmbeddings.ollama, ["sentence-transformers"]);
    assert.deepEqual(options.embeddingProviders["openai-embeddings"], ["openai"]);
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
        kernel_runtimes: {
          standard: ["python", "docker"],
        },
        intent_requirements: {
          simple: { requires_embedding: false },
        },
        provider_embeddings: {
          ollama: ["sentence-transformers"],
          openai: ["openai-embeddings"],
        },
        embedding_providers: {
          "sentence-transformers": ["ollama"],
          "openai-embeddings": ["openai"],
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

  it("filters provider and embedding choices to compatible combinations", () => {
    const options = buildPropertyPanelOptions(
      {
        decision_strategies: ["standard"],
        intent_modes: ["simple"],
        kernels: ["standard"],
        providers: {
          local: ["ollama", "onnx"],
          cloud: ["openai", "google"],
        },
        embeddings: {
          local: ["sentence-transformers"],
          cloud: ["openai-embeddings", "google-embeddings"],
        },
        kernel_runtimes: {
          standard: ["python", "docker"],
          optimized: ["python"],
          minimal: ["python"],
        },
        intent_requirements: {
          simple: { requires_embedding: false },
          advanced: { requires_embedding: true },
        },
        provider_embeddings: {
          ollama: ["sentence-transformers"],
          onnx: [],
          openai: ["openai-embeddings"],
          google: ["google-embeddings"],
        },
        embedding_providers: {
          "sentence-transformers": ["ollama"],
          "openai-embeddings": ["openai"],
          "google-embeddings": ["google"],
        },
        provider_sources: ["local", "cloud"],
        embedding_sources: ["local", "cloud"],
        active: {
          provider_source: "local",
          embedding_source: "local",
        },
      },
      null,
      null,
    );

    assert.deepEqual(getCompatibleProviders(options, "cloud", "openai-embeddings"), ["openai"]);
    assert.deepEqual(getCompatibleEmbeddings(options, "cloud", "google"), ["google-embeddings"]);
    assert.deepEqual(getCompatibleProviders(options, "local", null), ["ollama", "onnx"]);
    assert.deepEqual(getCompatibleKernels(options, "docker"), ["standard"]);
    assert.deepEqual(getCompatibleIntentModes(options, false), ["simple"]);
  });
});
