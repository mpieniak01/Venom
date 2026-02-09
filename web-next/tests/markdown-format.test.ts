import assert from "node:assert/strict";
import test from "node:test";

import {
  formatComputationContent,
  looksLikeMathLine,
  softlyWrapMathLines,
} from "@/lib/markdown-format";

test("formats JSON matrix into markdown table", () => {
  const tableInput = "[[1,2],[3,4]]";
  const tableOutput = formatComputationContent(tableInput);
  assert.match(tableOutput, /\|\s*Col 1\s*\|\s*Col 2\s*\|/);
  assert.match(tableOutput, /\|\s*1\s*\|\s*2\s*\|/);
});

test("formats JSON list into markdown bullets", () => {
  const listInput = "[1,2,3]";
  const listOutput = formatComputationContent(listInput);
  assert.match(listOutput, /- 1/);
  assert.match(listOutput, /- 2/);
});

test("detects math-like lines", () => {
  assert.equal(looksLikeMathLine("x^2 + y^2 = z^2"), true);
  assert.equal(looksLikeMathLine("To jest zwykłe zdanie."), false);
});

test("softly wraps math line with display delimiters", () => {
  const wrapped = softlyWrapMathLines("x^2 + y^2 = z^2");
  assert.match(wrapped, /^\$\$.*\$\$$/);
});
