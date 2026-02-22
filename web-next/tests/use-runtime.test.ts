import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildInstalledBuckets,
  resolveModelsForServer,
} from "../components/models/hooks/use-runtime";

describe("use-runtime helpers", () => {
  it("normalizes provider buckets and keeps fallback models", () => {
    const buckets = buildInstalledBuckets({
      success: true,
      models: [
        { name: "llama3:8b", provider: "ollama" },
        { name: "phi3.onnx", provider: null, source: "onnx" },
      ],
      count: 2,
      providers: {
        Ollama: [{ name: "llama3:8b", provider: "ollama" }],
      },
    });

    assert.deepStrictEqual(
      Object.keys(buckets).sort(),
      ["ollama", "onnx"],
    );
    assert.ok(buckets.ollama.some((model) => model.name === "llama3:8b"));
    assert.ok(buckets.onnx.some((model) => model.name === "phi3.onnx"));
  });

  it("resolves models by selected server using normalized provider", () => {
    const selected = resolveModelsForServer({
      selectedServer: "ollama",
      llmServers: [{ name: "onnx", provider: "onnx" }],
      installedBuckets: {
        ollama: [{ name: "llama3:8b", provider: "ollama" }],
      },
      installedModels: [
        { name: "llama3:8b", provider: "ollama" },
        { name: "phi3.onnx", provider: "onnx" },
      ],
    });

    assert.deepStrictEqual(selected.map((model) => model.name), ["llama3:8b"]);
  });
});
