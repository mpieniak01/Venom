import assert from "node:assert/strict";
import test from "node:test";

import {
  LEGACY_TOOL_NAME,
  buildSystemPrompt,
  dispatchTool,
  isPathWithinRoot,
  resolveWorkspacePath,
  type CommandExecutorDeps,
} from "../core/command-execution";

function fakeDeps(): CommandExecutorDeps {
  return {
    runGitCommand: async (_cwd, command) => `git:${command}`,
    searchCode: async (_cwd, query) => `search:${query}`,
    readFileContext: async (file, line, ctx) => `read:${file}:${line}:${ctx}`,
    execSafe: async (_cwd, command) => `exec:${command}`,
  };
}

test("buildSystemPrompt includes no-command-list contract", () => {
  const prompt = buildSystemPrompt("/tmp/repo", false);
  assert.ok(prompt.includes("Nie generuj listy komend jako finalnej odpowiedzi"));
  assert.ok(prompt.includes("venom_git_status"));
});

test("path jail guards workspace root", () => {
  assert.equal(isPathWithinRoot("/tmp/repo", "/tmp/repo/src/a.ts"), true);
  assert.equal(isPathWithinRoot("/tmp/repo", "/tmp/other/a.ts"), false);
  assert.equal(resolveWorkspacePath("/tmp/repo", "../secret.txt"), undefined);
});

test("dispatchTool returns REPO_ROOT evidence for git tools", async () => {
  const out = await dispatchTool("venom_git_status", { command: "git status --short --branch" }, "/tmp/repo", fakeDeps());
  assert.ok(out.startsWith("REPO_ROOT=/tmp/repo"));
  const legacy = await dispatchTool(LEGACY_TOOL_NAME, { command: "git status" }, "/tmp/repo", fakeDeps());
  assert.ok(legacy.startsWith("REPO_ROOT=/tmp/repo"));
});

test("dispatchTool blocks read_file outside workspace", async () => {
  const out = await dispatchTool("venom_read_file", { file_path: "../x", line: 1 }, "/tmp/repo", fakeDeps());
  assert.ok(out.includes("ścieżka poza workspace"));
});

test("dispatchTool rejects empty search query", async () => {
  let searchCalled = false;
  const deps: CommandExecutorDeps = {
    ...fakeDeps(),
    searchCode: async () => {
      searchCalled = true;
      return "search:should-not-run";
    },
  };
  const out = await dispatchTool("venom_search_code", { query: "   " }, "/tmp/repo", deps);
  assert.ok(out.includes("brak parametru query"));
  assert.equal(searchCalled, false);
});
