import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  filterRuntimeBaseModels,
  isRuntimeAdapterArtifactModel,
} from "../lib/runtime-model-filters";

describe("runtime model filters", () => {
  it("treats API adapter artifacts as non-base models", () => {
    assert.equal(
      isRuntimeAdapterArtifactModel({
        model_kind: "adapter_artifact",
      }),
      true,
    );
    assert.equal(
      isRuntimeAdapterArtifactModel({
        is_adapter_artifact: true,
      }),
      true,
    );
  });

  it("keeps only base runtime models for selectors", () => {
    const filtered = filterRuntimeBaseModels([
      { name: "gemma3:4b", model_kind: "base_model" as const },
      { name: "venom-adapter-self_learning_x:latest", model_kind: "adapter_artifact" as const },
      { name: "qwen3:4b", is_adapter_artifact: false },
    ]);
    assert.deepEqual(
      filtered.map((item) => item.name),
      ["gemma3:4b", "qwen3:4b"],
    );
  });
});
