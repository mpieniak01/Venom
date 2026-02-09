import assert from "node:assert/strict";
import test from "node:test";

import {
  formatComputationContent,
  looksLikeMathLine,
  softlyWrapMathLines,
} from "@/lib/markdown-format";

test("formats 2D array as markdown table", () => {
  const tableInput = "[[1,2],[3,4]]";
  const tableOutput = formatComputationContent(tableInput);
  assert.match(tableOutput, /\|\s*Col 1\s*\|\s*Col 2\s*\|/);
  assert.match(tableOutput, /\|\s*1\s*\|\s*2\s*\|/);
});

test("formats flat array as markdown list", () => {
  const listInput = "[1,2,3]";
  const listOutput = formatComputationContent(listInput);
  assert.match(listOutput, /- 1/);
  assert.match(listOutput, /- 2/);
});

test("looksLikeMathLine detects math-like and plain lines", () => {
  assert.ok(looksLikeMathLine("x^2 + y^2 = z^2"));
  assert.ok(!looksLikeMathLine("To jest zwykłe zdanie."));
});

test("softlyWrapMathLines wraps math-like lines in $$ delimiters", () => {
  const wrapped = softlyWrapMathLines("x^2 + y^2 = z^2");
  assert.match(wrapped, /^\$\$.*\$\$$/);
});
