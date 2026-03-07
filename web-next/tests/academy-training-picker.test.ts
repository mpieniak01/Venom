import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { TrainableModelInfo } from "../lib/academy-api";
import {
  buildTrainingModelPickerOptions,
  resolveTrainingBaseModelSelection,
} from "../components/academy/training-panel";

function t(key: string): string {
  const dict: Record<string, string> = {
    "academy.training.modelSections.localFirst": "Local",
    "academy.training.modelSections.cloudFree": "Cloud Free",
    "academy.training.modelSections.cloudOther": "Cloud Other",
    "academy.training.modelSectionMeta.localFirst": "meta local",
    "academy.training.modelSectionMeta.cloudFree": "meta free",
    "academy.training.modelSectionMeta.cloudOther": "meta other",
  };
  return dict[key] ?? key;
}

describe("academy training model picker options", () => {
  it("groups models in deterministic local -> cloud free -> cloud other order", () => {
    const models: TrainableModelInfo[] = [
      {
        model_id: "google/gemma-3-4b-it",
        label: "gemma",
        provider: "huggingface",
        trainable: true,
        recommended: false,
        installed_local: false,
        source_type: "cloud",
        cost_tier: "paid",
        priority_bucket: 4,
        runtime_compatibility: {},
        recommended_runtime: null,
      },
      {
        model_id: "gemma-3-4b-it",
        label: "gemma local",
        provider: "vllm",
        trainable: true,
        recommended: true,
        installed_local: true,
        source_type: "local",
        cost_tier: "free",
        priority_bucket: 0,
        runtime_compatibility: { vllm: true },
        recommended_runtime: "vllm",
      },
      {
        model_id: "unsloth/Phi-3-mini-4k-instruct",
        label: "phi mini",
        provider: "unsloth",
        trainable: true,
        recommended: false,
        installed_local: false,
        source_type: "cloud",
        cost_tier: "free",
        priority_bucket: 2,
        runtime_compatibility: { vllm: true },
        recommended_runtime: "vllm",
      },
    ];

    const options = buildTrainingModelPickerOptions(models, t);
    const sectionOptions = options.filter((option) => option.kind === "section");
    assert.deepEqual(
      sectionOptions.map((option) => option.sectionKey),
      ["localFirst", "cloudFree", "cloudOther"],
    );

    const localSectionIndex = options.findIndex(
      (option) => option.value === "__section__localFirst",
    );
    const localModelIndex = options.findIndex(
      (option) => option.value === "gemma-3-4b-it",
    );
    const cloudFreeSectionIndex = options.findIndex(
      (option) => option.value === "__section__cloudFree",
    );
    const cloudOtherSectionIndex = options.findIndex(
      (option) => option.value === "__section__cloudOther",
    );
    assert.ok(localSectionIndex >= 0);
    assert.ok(localModelIndex > localSectionIndex);
    assert.ok(cloudFreeSectionIndex > localModelIndex);
    assert.ok(cloudOtherSectionIndex > cloudFreeSectionIndex);
  });

  it("treats non-installed local-source catalog entries as non-local section", () => {
    const models: TrainableModelInfo[] = [
      {
        model_id: "unsloth/Phi-3-mini-4k-instruct",
        label: "phi mini",
        provider: "unsloth",
        trainable: true,
        recommended: false,
        installed_local: false,
        source_type: "local",
        cost_tier: "free",
        priority_bucket: 1,
        runtime_compatibility: { vllm: true },
        recommended_runtime: "vllm",
      },
    ];
    const options = buildTrainingModelPickerOptions(models, t);
    const sectionOption = options.find((option) => option.kind === "section");
    assert.equal(sectionOption?.sectionKey, "cloudFree");
  });

  it("does not auto-select a new base model when current selection is missing", () => {
    const models: TrainableModelInfo[] = [
      {
        model_id: "gemma-3-4b-it",
        label: "gemma local",
        provider: "vllm",
        trainable: true,
        recommended: true,
        installed_local: true,
        source_type: "local",
        cost_tier: "free",
        priority_bucket: 0,
        runtime_compatibility: { vllm: true, ollama: true },
        recommended_runtime: "vllm",
      },
    ];

    assert.equal(resolveTrainingBaseModelSelection("", models), "");
    assert.equal(
      resolveTrainingBaseModelSelection("missing-model", models),
      "",
    );
    assert.equal(
      resolveTrainingBaseModelSelection("gemma-3-4b-it", models),
      "gemma-3-4b-it",
    );
  });
});
