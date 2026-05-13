import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parseVoiceDebugEnabled } from "../components/voice/use-voice-debug-mode";

describe("voice debug mode", () => {
  it("enables dry run when debug query flag is present", () => {
    assert.equal(parseVoiceDebugEnabled("?debug"), true);
    assert.equal(parseVoiceDebugEnabled("?debug=1"), true);
    assert.equal(parseVoiceDebugEnabled("?debug=true"), true);
  });

  it("disables dry run for explicit false-like values", () => {
    assert.equal(parseVoiceDebugEnabled("?debug=0"), false);
    assert.equal(parseVoiceDebugEnabled("?debug=false"), false);
    assert.equal(parseVoiceDebugEnabled("?debug=off"), false);
  });

  it("does not enable dry run without the debug flag", () => {
    assert.equal(parseVoiceDebugEnabled("?voiceDiag=full_ready"), false);
    assert.equal(parseVoiceDebugEnabled(""), false);
  });
});
