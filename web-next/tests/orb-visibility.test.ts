import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  isActiveVoiceOrbState,
  isIdleVoiceOrbState,
  resolveVisualVoiceOrbState,
} from "../components/voice/orb-visibility";

describe("orb-visibility", () => {
  it("maps thinking to stt for visual rendering", () => {
    assert.equal(resolveVisualVoiceOrbState("thinking", ""), "stt");
    assert.equal(resolveVisualVoiceOrbState("thinking", "transcribed text"), "thinking");
  });

  it("keeps technical states intact for idle and active checks", () => {
    assert.equal(isIdleVoiceOrbState("ready"), true);
    assert.equal(isIdleVoiceOrbState("thinking"), false);
    assert.equal(isActiveVoiceOrbState("thinking"), true);
  });
});
