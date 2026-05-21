import assert from "node:assert/strict";
import test from "node:test";
import * as fs from "node:fs";
import * as path from "node:path";

type PackageJson = {
  contributes?: {
    chatParticipants?: Array<{ id?: string }>;
    languageModelTools?: Array<{ name?: string; modelDescription?: string; inputSchema?: unknown }>;
  };
  scripts?: Record<string, string>;
};

const PACKAGE_JSON_PATH = path.join(__dirname, "..", "..", "package.json");

function loadPackageJson(): PackageJson {
  const raw = fs.readFileSync(PACKAGE_JSON_PATH, "utf8");
  return JSON.parse(raw) as PackageJson;
}

test("package.json declares required chat participant and scripts", () => {
  const pkg = loadPackageJson();
  const participants = pkg.contributes?.chatParticipants ?? [];
  const participantIds = participants.map((item) => String(item.id ?? "").trim());
  assert.ok(participantIds.includes("venom.agent"), "missing chat participant venom.agent");

  const scripts = pkg.scripts ?? {};
  assert.ok(typeof scripts["test"] === "string", "missing npm script: test");
  assert.ok(typeof scripts["test:contract"] === "string", "missing npm script: test:contract");
  assert.ok(typeof scripts["test:unit"] === "string", "missing npm script: test:unit");
});

test("package.json declares required language model tools", () => {
  const pkg = loadPackageJson();
  const tools = pkg.contributes?.languageModelTools ?? [];
  const byName = new Map<string, { modelDescription?: string; inputSchema?: unknown }>();
  for (const tool of tools) {
    const name = String(tool.name ?? "").trim();
    byName.set(name, tool);
  }

  const required = ["venom_git_status", "venom_search_code", "venom_read_file", "venom_exec_safe"];
  for (const name of required) {
    assert.ok(byName.has(name), `missing languageModelTool: ${name}`);
    const spec = byName.get(name) ?? {};
    assert.ok(String(spec.modelDescription ?? "").trim().length > 0, `${name}: missing modelDescription`);
    assert.ok(spec.inputSchema, `${name}: missing inputSchema`);
  }
});
