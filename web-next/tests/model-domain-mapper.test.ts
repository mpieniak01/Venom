/**
 * Unit tests for model domain mapper
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  inferSourceType,
  inferModelRole,
  inferTrainability,
  enrichCatalogModel,
  enrichInstalledModel,
} from "../lib/model-domain-mapper";
import type { ModelCatalogEntry, ModelInfo } from "../lib/types";
import type { TrainableModelInfo } from "../lib/academy-api";

describe("model-domain-mapper", () => {
  describe("inferSourceType", () => {
    it("should return 'cloud-api' for OpenAI provider", () => {
      assert.strictEqual(inferSourceType("openai", "vllm"), "cloud-api");
      assert.strictEqual(inferSourceType("OpenAI", "vllm"), "cloud-api");
    });

    it("should return 'cloud-api' for Gemini provider", () => {
      assert.strictEqual(inferSourceType("gemini", "vllm"), "cloud-api");
      assert.strictEqual(inferSourceType("Gemini", "vllm"), "cloud-api");
    });

    it("should return 'integrator-catalog' for HuggingFace", () => {
      assert.strictEqual(inferSourceType("huggingface", "vllm"), "integrator-catalog");
      assert.strictEqual(inferSourceType("hf", "vllm"), "integrator-catalog");
    });

    it("should return 'integrator-catalog' for Ollama", () => {
      assert.strictEqual(inferSourceType("ollama", "ollama"), "integrator-catalog");
    });

    it("should return 'local-runtime' for vLLM provider", () => {
      assert.strictEqual(inferSourceType("vllm", "vllm"), "local-runtime");
    });

    it("should return 'local-runtime' for unknown providers", () => {
      assert.strictEqual(inferSourceType("unknown", "unknown"), "local-runtime");
    });

    it("should return 'local-runtime' when provider is null", () => {
      assert.strictEqual(inferSourceType(null, "vllm"), "local-runtime");
    });
  });

  describe("inferModelRole", () => {
    it("should return 'intent-embedding' for embedding models", () => {
      assert.strictEqual(inferModelRole("bge-large-en-v1.5"), "intent-embedding");
      assert.strictEqual(inferModelRole("e5-base-v2"), "intent-embedding");
      assert.strictEqual(inferModelRole("sentence-transformers/all-MiniLM-L6-v2"), "intent-embedding");
    });

    it("should return 'intent-embedding' for models with embedding tags", () => {
      assert.strictEqual(inferModelRole("some-model", ["embedding"]), "intent-embedding");
      assert.strictEqual(inferModelRole("some-model", ["sentence-similarity"]), "intent-embedding");
      assert.strictEqual(inferModelRole("some-model", ["feature-extraction"]), "intent-embedding");
    });

    it("should return 'llm-engine' for LLM models", () => {
      assert.strictEqual(inferModelRole("llama-2-7b"), "llm-engine");
      assert.strictEqual(inferModelRole("gpt-4"), "llm-engine");
      assert.strictEqual(inferModelRole("mistral-7b-instruct"), "llm-engine");
    });

    it("should return 'llm-engine' by default", () => {
      assert.strictEqual(inferModelRole("unknown-model"), "llm-engine");
    });
  });

  describe("inferTrainability", () => {
    const trainableModels: TrainableModelInfo[] = [
      {
        model_id: "llama-2-7b",
        label: "Llama 2 7B",
        provider: "huggingface",
        trainable: true,
        recommended: true,
        installed_local: false,
      },
      {
        model_id: "gpt-4",
        label: "GPT-4",
        provider: "openai",
        trainable: false,
        reason_if_not_trainable: "Model is not in Academy trainable families list",
        recommended: false,
        installed_local: false,
      },
    ];

    it("should return 'trainable' for trainable models", () => {
      const result = inferTrainability("llama-2-7b", trainableModels);
      assert.strictEqual(result.status, "trainable");
      assert.strictEqual(result.reason, null);
    });

    it("should return 'not-trainable' with reason for non-trainable models", () => {
      const result = inferTrainability("gpt-4", trainableModels);
      assert.strictEqual(result.status, "not-trainable");
      assert.strictEqual(result.reason, "Model is not in Academy trainable families list");
    });

    it("should return 'not-trainable' for models not in catalog", () => {
      const result = inferTrainability("unknown-model", trainableModels);
      assert.strictEqual(result.status, "not-trainable");
      assert.strictEqual(result.reason, "Model not in Academy trainable catalog");
    });

    it("should handle case-insensitive model names", () => {
      const result = inferTrainability("LLAMA-2-7B", trainableModels);
      assert.strictEqual(result.status, "trainable");
    });

    it("should return 'not-trainable' when trainableModels is null", () => {
      const result = inferTrainability("some-model", null);
      assert.strictEqual(result.status, "not-trainable");
      assert.strictEqual(result.reason, "Trainability information not available");
    });

    it("should return 'not-trainable' when trainableModels is empty", () => {
      const result = inferTrainability("some-model", []);
      assert.strictEqual(result.status, "not-trainable");
      assert.strictEqual(result.reason, "Trainability information not available");
    });
  });

  describe("enrichCatalogModel", () => {
    const catalogModel: ModelCatalogEntry = {
      provider: "huggingface",
      model_name: "meta-llama/Llama-2-7b-hf",
      display_name: "Llama 2 7B",
      size_gb: 13.5,
      runtime: "vllm",
      tags: ["text-generation", "llm"],
      downloads: 500000,
      likes: 1200,
    };

    const trainableModels: TrainableModelInfo[] = [
      {
        model_id: "meta-llama/Llama-2-7b-hf",
        label: "Llama 2 7B",
        provider: "huggingface",
        trainable: true,
        recommended: true,
        installed_local: false,
      },
    ];

    it("should enrich catalog model with domain information", () => {
      const enriched = enrichCatalogModel(catalogModel, trainableModels);

      assert.strictEqual(enriched.name, "meta-llama/Llama-2-7b-hf");
      assert.strictEqual(enriched.display_name, "Llama 2 7B");
      assert.strictEqual(enriched.source_type, "integrator-catalog");
      assert.strictEqual(enriched.model_role, "llm-engine");
      assert.strictEqual(enriched.academy_trainable, "trainable");
      assert.strictEqual(enriched.installed, false);
      assert.strictEqual(enriched.active, false);
    });

    it("should preserve original catalog data", () => {
      const enriched = enrichCatalogModel(catalogModel, trainableModels);

      assert.strictEqual(enriched.size_gb, 13.5);
      assert.strictEqual(enriched.provider, "huggingface");
      assert.strictEqual(enriched.runtime, "vllm");
      assert.deepStrictEqual(enriched.tags, ["text-generation", "llm"]);
      assert.strictEqual(enriched.downloads, 500000);
      assert.strictEqual(enriched.likes, 1200);
    });
  });

  describe("enrichInstalledModel", () => {
    const installedModel: ModelInfo = {
      name: "llama-2-7b",
      size_gb: 13.5,
      installed: true,
      active: true,
      provider: "vllm",
      type: "vllm",
      quantization: "int8",
      path: "/models/llama-2-7b",
    };

    const trainableModels: TrainableModelInfo[] = [
      {
        model_id: "llama-2-7b",
        label: "Llama 2 7B",
        provider: "vllm",
        trainable: true,
        recommended: true,
        installed_local: true,
      },
    ];

    it("should enrich installed model with domain information", () => {
      const enriched = enrichInstalledModel(installedModel, trainableModels);

      assert.strictEqual(enriched.name, "llama-2-7b");
      assert.strictEqual(enriched.source_type, "local-runtime");
      assert.strictEqual(enriched.model_role, "llm-engine");
      assert.strictEqual(enriched.academy_trainable, "trainable");
      assert.strictEqual(enriched.installed, true);
      assert.strictEqual(enriched.active, true);
    });

    it("should preserve original installed model data", () => {
      const enriched = enrichInstalledModel(installedModel, trainableModels);

      assert.strictEqual(enriched.size_gb, 13.5);
      assert.strictEqual(enriched.provider, "vllm");
      assert.strictEqual(enriched.runtime, "vllm");
      assert.strictEqual(enriched.quantization, "int8");
      assert.strictEqual(enriched.path, "/models/llama-2-7b");
    });
  });
});
