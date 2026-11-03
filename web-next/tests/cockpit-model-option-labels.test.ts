import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { formatRuntimeModelOptionLabel } from "../components/cockpit/cockpit-section-props";

describe("cockpit runtime model labels", () => {
  const t = (key: string) => {
    const map: Record<string, string> = {
      "cockpit.models.feedbackLoopPrimaryBadge": "feedback-loop: recommended",
      "cockpit.models.feedbackLoopFallbackBadge": "feedback-loop: fallback",
    };
    return map[key] || key;
  };

  it("adds primary badge label", () => {
    const label = formatRuntimeModelOptionLabel(
      { name: "qwen2.5-coder:7b", feedback_loop_tier: "primary" },
      t,
    );
    assert.equal(label, "qwen2.5-coder:7b · feedback-loop: recommended");
  });

  it("adds fallback badge label", () => {
    const label = formatRuntimeModelOptionLabel(
      { name: "qwen2.5-coder:3b", feedback_loop_tier: "fallback" },
      t,
    );
    assert.equal(label, "qwen2.5-coder:3b · feedback-loop: fallback");
  });

  it("keeps plain model name for non-recommended models", () => {
    const label = formatRuntimeModelOptionLabel(
      { name: "phi3:mini", feedback_loop_tier: "not_recommended" },
      t,
    );
    assert.equal(label, "phi3:mini");
  });

  it("adds runtime tag when runtime id is present", () => {
    const label = formatRuntimeModelOptionLabel(
      { name: "phi3:mini", feedback_loop_tier: "not_recommended", runtime_id: "ollama" },
      t,
    );
    assert.equal(label, "phi3:mini [ollama]");
  });

  it("shows canonical alias for gemma3 ollama tag", () => {
    const label = formatRuntimeModelOptionLabel(
      {
        name: "gemma3:latest",
        canonical_model_id: "gemma-3-4b-it",
        feedback_loop_tier: "not_recommended",
        runtime_id: "ollama",
      },
      t,
    );
    assert.equal(label, "gemma3:latest <-> gemma-3-4b-it [ollama]");
  });
});


describe("Gemma4 operator labels", () => {
  it("uses explicit variant labels without changing request IDs", () => {
    const t = (key: string) => key;
    assert.equal(formatRuntimeModelOptionLabel({name:"gemma4:e4b",runtime_id:"ollama",display_name:"Gemma4 E4B IT Q4_K_M"},t),
                 "Gemma4 E4B IT Q4_K_M [ollama]");
    assert.equal(formatRuntimeModelOptionLabel({name:"gemma4:12b-it-q4_K_M",runtime_id:"ollama"},t),
                 "Gemma4 12B IT Q4_K_M [ollama]");
  });
});
