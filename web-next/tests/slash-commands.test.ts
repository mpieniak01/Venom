import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  parseSlashCommand,
  parseAgentMention,
  parseInputCommand,
  filterSlashSuggestions,
  filterAgentSuggestions,
  AGENT_COMMANDS,
  SLASH_COMMANDS,
} from "../lib/slash-commands";

describe("AGENT_COMMANDS", () => {
  it("contains @gem and @gpt", () => {
    assert.ok(AGENT_COMMANDS.some((c) => c.command === "@gem" && c.value === "gem"));
    assert.ok(AGENT_COMMANDS.some((c) => c.command === "@gpt" && c.value === "gpt"));
  });

  it("does not contain gem or gpt in SLASH_COMMANDS", () => {
    assert.ok(!SLASH_COMMANDS.some((c) => c.value === "gem"));
    assert.ok(!SLASH_COMMANDS.some((c) => c.value === "gpt"));
  });
});

describe("parseAgentMention", () => {
  it("parses @gpt and sets forcedProvider=gpt", () => {
    const result = parseAgentMention("@gpt Write a plan");
    assert.equal(result.forcedProvider, "gpt");
    assert.equal(result.cleaned, "Write a plan");
    assert.equal(result.forcedTool, undefined);
  });

  it("parses @gem and sets forcedProvider=gem", () => {
    const result = parseAgentMention("@gem Hello");
    assert.equal(result.forcedProvider, "gem");
    assert.equal(result.cleaned, "Hello");
  });

  it("returns cleaned=input for unknown @mention", () => {
    const result = parseAgentMention("@unknown text");
    assert.equal(result.cleaned, "@unknown text");
    assert.equal(result.forcedProvider, undefined);
  });

  it("returns cleaned=input when no @ prefix", () => {
    const result = parseAgentMention("plain text");
    assert.equal(result.cleaned, "plain text");
  });

  it("handles leading spaces before @", () => {
    const result = parseAgentMention("  @gpt task");
    assert.equal(result.forcedProvider, "gpt");
    assert.equal(result.cleaned, "task");
  });
});

describe("parseInputCommand", () => {
  it("delegates @gpt to parseAgentMention", () => {
    const result = parseInputCommand("@gpt Do something");
    assert.equal(result.forcedProvider, "gpt");
    assert.equal(result.cleaned, "Do something");
  });

  it("delegates /shell to parseSlashCommand", () => {
    const result = parseInputCommand("/shell ls -la");
    assert.equal(result.forcedTool, "shell");
    assert.equal(result.cleaned, "ls -la");
  });

  it("handles /clear with sessionReset", () => {
    const result = parseInputCommand("/clear");
    assert.equal(result.sessionReset, true);
  });

  it("returns cleaned=input for plain text", () => {
    const result = parseInputCommand("hello world");
    assert.equal(result.cleaned, "hello world");
    assert.equal(result.forcedProvider, undefined);
    assert.equal(result.forcedTool, undefined);
  });

  it("gem/gpt no longer work as slash commands", () => {
    const result = parseInputCommand("/gpt text");
    assert.equal(result.forcedProvider, undefined);
    assert.equal(result.cleaned, "/gpt text");
  });
});

describe("filterAgentSuggestions", () => {
  it("returns agent suggestions when input starts with @", () => {
    const results = filterAgentSuggestions("@");
    assert.ok(results.length > 0);
    assert.ok(results.every((r) => r.command.startsWith("@")));
  });

  it("filters by partial match", () => {
    const results = filterAgentSuggestions("@gp");
    assert.ok(results.some((r) => r.value === "gpt"));
    assert.ok(!results.some((r) => r.value === "gem"));
  });

  it("returns empty when input starts with /", () => {
    assert.deepEqual(filterAgentSuggestions("/shell"), []);
  });

  it("returns empty when @mention is complete with space", () => {
    assert.deepEqual(filterAgentSuggestions("@gpt "), []);
  });
});

describe("filterSlashSuggestions", () => {
  it("does not suggest gem or gpt", () => {
    const all = filterSlashSuggestions("/", 100);
    assert.ok(!all.some((r) => r.value === "gem"));
    assert.ok(!all.some((r) => r.value === "gpt"));
  });

  it("suggests /shell when input is /sh", () => {
    const results = filterSlashSuggestions("/sh");
    assert.ok(results.some((r) => r.value === "shell"));
  });

  it("returns empty when input starts with @", () => {
    assert.deepEqual(filterSlashSuggestions("@gem"), []);
  });
});

describe("parseSlashCommand (unchanged behaviour)", () => {
  it("parses /shell correctly", () => {
    const result = parseSlashCommand("/shell ls");
    assert.equal(result.forcedTool, "shell");
    assert.equal(result.cleaned, "ls");
  });

  it("parses /clear as sessionReset", () => {
    const result = parseSlashCommand("/clear");
    assert.equal(result.sessionReset, true);
  });
});
