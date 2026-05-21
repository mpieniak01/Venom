import assert from "node:assert/strict";
import test from "node:test";
import * as fs from "node:fs";
import * as path from "node:path";

const EXTENSION_TS_PATH = path.join(__dirname, "..", "..", "src", "extension.ts");

function loadExtensionSource(): string {
  return fs.readFileSync(EXTENSION_TS_PATH, "utf8");
}

test("extension keeps agentic loop tool roundtrip primitives", () => {
  const src = loadExtensionSource();
  assert.ok(src.includes("request.model.sendRequest"), "missing request.model.sendRequest");
  assert.ok(src.includes("LanguageModelToolCallPart"), "missing LanguageModelToolCallPart");
  assert.ok(src.includes("LanguageModelToolResultPart"), "missing LanguageModelToolResultPart");
});

test("extension declares repo-truth tool anchors", () => {
  const src = loadExtensionSource();
  assert.ok(src.includes("venom_git_status"), "missing venom_git_status tool anchor");
  assert.ok(src.includes("REPO_ROOT="), "missing REPO_ROOT evidence anchor");
});

test("extension allowlist includes safe read-only git inventory commands", () => {
  const src = loadExtensionSource();
  assert.ok(src.includes("'git ls-files'"), "missing git ls-files allowlist entry");
  assert.ok(src.includes("'git ls-tree HEAD'"), "missing git ls-tree HEAD allowlist entry");
});

test("extension asks for confirmation when git command is outside allowlist", () => {
  const src = loadExtensionSource();
  assert.ok(src.includes("Komenda poza allowlistą"), "missing outside-allowlist warning message");
  assert.ok(src.includes("Uruchom mimo to"), "missing confirmation action for outside allowlist");
});

test("extension parses git args with quoted values", () => {
  const src = loadExtensionSource();
  assert.ok(src.includes("tokenizeCommandArgs"), "missing quoted-args tokenizer");
  assert.ok(!src.includes("normalized.split(' ')"), "legacy split parser should not be used");
});
