import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { SALUKI_GGUF, chatModelLabel, preferChatModelAliases, isSelectableChatModel } from "../lib/chat-model-options";
const alias = { name: "saluki:latest", provider: "ollama" };
const source = { name: SALUKI_GGUF, provider: "ollama" };
it("preserves separate Saluki preset and explicit GGUF instead of guessing identity", () => {
  for (const models of [[alias, source], [source, alias]]) {
    assert.deepEqual(preferChatModelAliases(models), models);
    assert.equal(models.length, 2);
  }
});
it("preserves selected and active GGUF variant instead of switching presets", () => {
  assert.deepEqual(preferChatModelAliases([alias, source], SALUKI_GGUF), [alias,source]);
  const active = { ...source, active: true };
  assert.deepEqual(preferChatModelAliases([alias, active]), [alias,active]);
  assert.deepEqual(preferChatModelAliases([alias, active], alias.name), [alias,active]);
});
it("keeps raw-only installations, unrelated variants and other providers", () => {
  assert.deepEqual(preferChatModelAliases([source]), [source]);
  assert.deepEqual(preferChatModelAliases([alias]), [alias]);
  const other = { ...source, provider: "vllm" };
  const variant = { ...source, name: SALUKI_GGUF + "-other" };
  assert.deepEqual(preferChatModelAliases([alias, other, variant]), [alias, other, variant]);
});
it("labels exact Saluki source with model version and quantization, retaining its identifier", () => {
  assert.equal(chatModelLabel(SALUKI_GGUF), "Underdog Saluki 27B 1.0 IQ2-mix GGUF");
  assert.equal(source.name, SALUKI_GGUF);
  assert.equal(chatModelLabel(alias.name), "saluki:latest (unresolved variant)");
});


describe("explicit Gemma4 choices", () => {
  it("shows distinct E4B and12B precision labels and never infers latest", () => {
    assert.equal(chatModelLabel("gemma4:e4b", undefined, "ollama"), "Gemma4 E4B IT Q4_K_M");
    assert.equal(chatModelLabel("gemma4:12b-it-q4_K_M", undefined, "ollama"), "Gemma4 12B IT Q4_K_M");
    assert.equal(chatModelLabel("gemma4:latest", undefined, "ollama"), "gemma4:latest (unresolved variant)");
  });
  it("uses observed backend precision and leaves other provider IDs alone", () => {
    assert.equal(chatModelLabel("gemma4:e4b", "Gemma4 E4B IT Q8_0", "ollama"), "Gemma4 E4B IT Q8_0");
    assert.equal(chatModelLabel("gemma4:e4b", undefined, "openrouter"), "gemma4:e4b");
    assert.equal(chatModelLabel("organization/gemma4-e4b", undefined, "openai"), "organization/gemma4-e4b");
  });
  it("retains both variants and sends exact explicit tag values", () => {
    const models = [{name:"gemma4:e4b", provider:"ollama"}, {name:"gemma4:12b-it-q4_K_M", provider:"ollama"}];
    assert.deepEqual(preferChatModelAliases(models), models);
    assert.deepEqual(models.map(m => ({value:m.name,label:chatModelLabel(m.name,undefined,m.provider)})).map(o => o.value),
                     ["gemma4:e4b","gemma4:12b-it-q4_K_M"]);
  });
});


it("unresolved Gemma latest is diagnostic only, never an actionable model choice", () => {
  const explicit = [{name:"gemma4:e4b",provider:"ollama"}, {name:"gemma4:12b-it-q4_K_M",provider:"ollama"}];
  const unknown = {name:"gemma4:latest",provider:"ollama"};
  assert.equal(isSelectableChatModel(unknown), false);
  assert.equal(isSelectableChatModel({...unknown,name:"gemma4:Latest"}), false);
  assert.deepEqual(preferChatModelAliases([unknown,...explicit]), explicit);
  assert.equal(isSelectableChatModel({name:"gemma4:latest",provider:"openrouter"}), true);
  assert.equal(isSelectableChatModel({name:"qwen:latest",provider:"ollama"}), true);
  assert.equal(isSelectableChatModel({name:"gemma4:e4b",provider:"ollama",selection_supported:false}), false);
});


it("localizes unresolved diagnostics while preserving the observed alias", () => {
  assert.equal(chatModelLabel("gemma4:latest", "gemma4:latest (unresolved variant)", "ollama", "nierozpoznany wariant"),
               "gemma4:latest (nierozpoznany wariant)");
});


it("does not infer Saluki identity for another provider or rewrite active input records", () => {
  const observed = {...alias, active:true};
  const otherProvider = {...alias, provider:"openrouter"};
  assert.deepEqual(preferChatModelAliases([observed,source,otherProvider], observed.name), [observed,source,otherProvider]);
  assert.equal(observed.name, "saluki:latest");
  assert.equal(observed.active, true);
  assert.equal(chatModelLabel(alias.name,undefined,"openrouter"), "saluki:latest");
});


it("shows observed Saluki preset metadata without attributing an unproven GGUF version", () => {
  const label = "saluki:latest · gemma3 26.9B IQ2_XS · sha256:3497825c";
  assert.equal(chatModelLabel("saluki:latest",label,"ollama"), label);
  assert.equal(isSelectableChatModel({name:"saluki:latest",provider:"ollama",selection_supported:true}), true);
  assert.equal(isSelectableChatModel({name:"saluki:latest",provider:"ollama",selection_supported:false}), false);
});
