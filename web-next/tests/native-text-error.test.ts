import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError } from "../lib/api-client";
import { chatMaterialError } from "../lib/chat-error";
import { chat2 as pl } from "../lib/i18n/locales/chat2/pl";
import { chat2 as en } from "../lib/i18n/locales/chat2/en";
import { chat2 as de } from "../lib/i18n/locales/chat2/de";

test("native adapter errors use translated decisions without echoing upstream content", () => {
  const expected: Record<string, string> = {
    context_limit: "context", token_limit: "context", feature_unsupported: "unsupported",
    selection_changed: "changed", runtime_changed: "changed", runtime_conflict: "changed",
    not_configured: "unavailable", generation_failed: "failed", adapter_invalid: "failed",
  };
  for (const [reason, key] of Object.entries(expected)) {
    const error = new ApiError("sensitive", 409, { detail: { reason_code: `omni_native_text_${reason}` } });
    assert.equal(chatMaterialError(error, value => value), `chat2.nativeText.${key}`);
    assert.equal(chatMaterialError(new Error(`omni_native_text_${reason}`), value => value), `chat2.nativeText.${key}`);
  }
  assert.equal(chatMaterialError(new Error("arbitrary upstream failure"), value => value), null);
  assert.deepEqual(Object.keys(pl.nativeText).sort(), Object.keys(en.nativeText).sort());
  assert.deepEqual(Object.keys(pl.nativeText).sort(), Object.keys(de.nativeText).sort());
});
