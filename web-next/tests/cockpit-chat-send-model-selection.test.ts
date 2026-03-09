import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { resolveEffectiveChatModelSelection } from "../components/cockpit/cockpit-chat-send";

describe("resolveEffectiveChatModelSelection", () => {
  it("prefers explicitly selected model", () => {
    const resolved = resolveEffectiveChatModelSelection(
      "gemma2:2b",
      "venom-adapter-self-learning:latest",
    );
    assert.equal(resolved, "gemma2:2b");
  });

  it("falls back to active runtime model when selector is empty", () => {
    const resolved = resolveEffectiveChatModelSelection(
      "",
      "venom-adapter-self-learning:latest",
    );
    assert.equal(resolved, "venom-adapter-self-learning:latest");
  });

  it("returns empty string when both selected and active model are missing", () => {
    const resolved = resolveEffectiveChatModelSelection("", "");
    assert.equal(resolved, "");
  });
});
