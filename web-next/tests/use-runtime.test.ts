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
      ["ollama", "onnx", "other", "vllm"],
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


describe("installed inventory evidence", () => {
  it("groups actual external checkpoints under Other without reassigning their engine", () => {
    const buckets = buildInstalledBuckets({models: [
      {name: "Qwen/Qwen3.5-9B", provider: "transformers", installed: true, activation_supported: false},
      {name: "rwkv", provider: "rwkv", installed: true},
      {name: "deleted", provider: "ollama", installed: false},
    ],count: 3});
    assert.equal(buckets.other.length,2);
    assert.equal(buckets.other[0].provider,"transformers");
    assert.equal(buckets.vllm.length,0);
    assert.equal(buckets.ollama.length,0);
  });
  it("does not duplicate a filesystem entry received through both response shapes", () => {
    const model = {name: "qwen", provider: "transformers", path:"/weights/qwen"};
    const buckets = buildInstalledBuckets({models:[model],providers:{transformers:[model]},count:1});
    assert.equal(buckets.other.length,1);
  });
  it("excludes models without a supported chat path from engine selection", () => {
    const models = resolveModelsForServer({selectedServer:null,runtimeModels:[],installedBuckets:{other:[]},installedModels:[{name:"custom",provider:"research",activation_supported:false},{name:"chat",provider:"ollama"}]});
    assert.deepEqual(models.map(m=>m.name),["chat"]);
  });
});


it("retains distinct Ollama tags that share the registry URI", () => {
  const models=[{name:"first:latest",provider:"ollama",path:"ollama://registry.ollama.ai"},{name:"second:latest",provider:"ollama",path:"ollama://registry.ollama.ai"}];
  const buckets=buildInstalledBuckets({models,providers:{ollama:models},count:2});
  assert.equal(buckets.ollama.length,2);
});
