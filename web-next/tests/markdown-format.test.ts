import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  formatComputationContent,
  isComputationContent,
  looksLikeMathLine,
  softlyWrapMathLines,
  tokenizeMath,
} from "@/lib/markdown-format";

describe("markdown-format", () => {
  it("formats plain JSON arrays and objects", () => {
    const tableOutput = formatComputationContent("[[1,2],[3,4]]");
    assert.match(tableOutput, /\|\s*Col 1\s*\|\s*Col 2\s*\|/);
    assert.match(tableOutput, /\|\s*1\s*\|\s*2\s*\|/);

    const objectOutput = formatComputationContent('{"name":"venom","ok":true}');
    assert.match(objectOutput, /\|\s*name\s*\|\s*ok\s*\|/);
    assert.match(objectOutput, /\|\s*venom\s*\|\s*true\s*\|/);

    const listOutput = formatComputationContent("[1,2,3]");
    assert.match(listOutput, /- 1/);
    assert.match(listOutput, /- 2/);
  });

  it("formats JSON inside code fences and leaves invalid fence content unchanged", () => {
    const validFence = "```json\n[{\"a\":1}]\n```";
    const validOutput = formatComputationContent(validFence);
    assert.match(validOutput, /\|\s*a\s*\|/);

    const invalidFence = "```json\n{not-json}\n```";
    assert.equal(formatComputationContent(invalidFence), invalidFence);
  });

  it("detects computation content only for valid JSON candidates", () => {
    assert.equal(isComputationContent('{"a":1}'), true);
    assert.equal(isComputationContent("```json\n[1,2]\n```"), true);
    assert.equal(isComputationContent("```json\nnot-json\n```"), false);
    assert.equal(isComputationContent("plain text"), false);
  });

  it("detects likely math lines and avoids natural language lines", () => {
    assert.equal(looksLikeMathLine("x^2 + y^2 = z^2"), true);
    assert.equal(looksLikeMathLine("To jest zwykłe zdanie."), false);
    assert.equal(looksLikeMathLine("To jest za długie wyrażenie matematyczne z wieloma słowami"), false);
  });

  it("wraps math lines but does not touch code fences", () => {
    const content = [
      "x^2 + y^2 = z^2",
      "```",
      "a = b + c",
      "```",
      "normal text.",
    ].join("\n");

    const wrapped = softlyWrapMathLines(content);

    assert.match(wrapped, /\$\$x\^2 \+ y\^2 = z\^2\$\$/);
    assert.match(wrapped, /```\na = b \+ c\n```/);
    assert.match(wrapped, /normal text\./);
  });

  it("tokenizes math expressions outside code fences", () => {
    const source = [
      "Inline \\(x+1\\)",
      "Display \\[y^2\\]",
      "$$z^3$$",
      "```",
      "\\(do-not-tokenize\\)",
      "```",
    ].join("\n");

    const result = tokenizeMath(source);

    assert.equal(result.tokens.length, 3);
    assert.match(result.text, /__MATH_INLINE_\d+__/);
    assert.match(result.text, /__MATH_DISPLAY_\d+__/);
    assert.match(result.text, /__MATH_BLOCK_\d+__/);
    assert.match(result.text, /```\n\\\(do-not-tokenize\\\)\n```/);
  });
});
