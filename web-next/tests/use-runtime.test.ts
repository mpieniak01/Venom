import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildInstalledBuckets,
  resolveRuntimeActivationErrorMessage,
  resolveModelsForServer,
} from "../components/models/hooks/use-runtime";
import { ApiError } from "../lib/api-client";

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
      runtimeModels: [{ id: "llama3:8b", name: "llama3:8b", provider: "ollama", runtime_id: "ollama", source_type: "local-runtime", active: false }],
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

  it("extracts nested api error detail for runtime activation errors", () => {
    const error = new ApiError("Request failed: 500", 500, {
      detail: { reason: "runtime temporarily unavailable" },
    });

    assert.equal(
      resolveRuntimeActivationErrorMessage(error, "activation failed"),
      "runtime temporarily unavailable",
    );
  });

  it("returns localized HTTP fallback when api error has no detail", () => {
    const error = new ApiError("Request failed: 500", 500, { detail: "   " });
    assert.equal(
      resolveRuntimeActivationErrorMessage(error, "activation failed"),
      "activation failed (HTTP 500).",
    );
  });
});
