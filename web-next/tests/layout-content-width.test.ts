import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("the content flex item can shrink within the sidebar viewport", () => {
  const source = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const layout = source.split("\n").find(line => line.includes("lg:pl-[var(--sidebar-width)]"));
  assert.ok(layout?.includes("min-w-0"));
});
