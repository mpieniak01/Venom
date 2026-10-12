import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("the content flex item can shrink within the sidebar viewport", () => {
  const source = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const layout = source.split("\n").find(line => line.includes("lg:pl-[var(--sidebar-width)]"));
  assert.ok(layout?.includes("min-w-0"));
});

test("the shell does not create an unused vertical scroll container around sticky controls", () => {
  const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  assert.match(layout, /min-h-screen overflow-x-clip/);
  assert.doesNotMatch(layout, /min-h-screen overflow-x-hidden/);
  assert.match(css, /overflow-x: clip;/);
});

test("the host toolbar wraps its actions instead of clipping language and theme controls", () => {
  const bar = readFileSync(new URL("../components/layout/top-bar.tsx", import.meta.url), "utf8");
  assert.match(bar, /flex w-full flex-wrap/);
  assert.match(bar, /min-w-0 flex-1 flex-wrap/);
});
