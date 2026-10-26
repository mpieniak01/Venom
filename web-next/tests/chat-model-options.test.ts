import assert from "node:assert/strict";
import { it } from "node:test";
import { SALUKI_GGUF, chatModelLabel, preferChatModelAliases } from "../lib/chat-model-options";
const alias = { name: "saluki:latest", provider: "ollama" };
const source = { name: SALUKI_GGUF, provider: "ollama" };
it("prefers installed alias regardless of list order without changing model identities", () => {
  for (const models of [[alias, source], [source, alias]]) {
    assert.deepEqual(preferChatModelAliases(models), [alias]);
    assert.equal(models.length, 2);
  }
});
it("preserves selected and active GGUF variant instead of switching presets", () => {
  assert.deepEqual(preferChatModelAliases([alias, source], SALUKI_GGUF), [source]);
  const active = { ...source, active: true };
  assert.deepEqual(preferChatModelAliases([alias, active]), [active]);
  assert.deepEqual(preferChatModelAliases([alias, active], alias.name), [alias]);
});
it("keeps raw-only installations, unrelated variants and other providers", () => {
  assert.deepEqual(preferChatModelAliases([source]), [source]);
  assert.deepEqual(preferChatModelAliases([alias]), [alias]);
  const other = { ...source, provider: "vllm" };
  const variant = { ...source, name: SALUKI_GGUF + "-other" };
  assert.deepEqual(preferChatModelAliases([alias, other, variant]), [alias, other, variant]);
});
it("shortens only the exact known GGUF label, retaining its activation identifier", () => {
  assert.equal(chatModelLabel(SALUKI_GGUF), "saluki:IQ2-mix.gguf");
  assert.equal(source.name, SALUKI_GGUF);
  assert.equal(chatModelLabel(alias.name), alias.name);
});
