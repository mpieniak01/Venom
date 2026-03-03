import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, extname } from "node:path";

function collectSourceFiles(rootDir: string): string[] {
  const files: string[] = [];
  const stack = [rootDir];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current) continue;
    for (const entry of readdirSync(current)) {
      const full = join(current, entry);
      const stat = statSync(full);
      if (stat.isDirectory()) {
        stack.push(full);
        continue;
      }
      if (![".ts", ".tsx", ".js", ".jsx", ".css"].includes(extname(full))) continue;
      if (full.includes(".test.")) continue;
      files.push(full);
    }
  }
  return files;
}

describe("theme legacy guards", () => {
  const globalsPath = join(process.cwd(), "app", "globals.css");
  const globalsCss = readFileSync(globalsPath, "utf8");

  it("removes legacy css selector alias", () => {
    assert.equal(globalsCss.includes("venom-light-dev"), false);
  });

  it("removes temporary transitional compatibility layer", () => {
    assert.equal(globalsCss.includes("Transitional compatibility layer"), false);
  });

  it("does not use dark: utility variants in app/components source", () => {
    const targets = [
      ...collectSourceFiles(join(process.cwd(), "components")),
      ...collectSourceFiles(join(process.cwd(), "app")),
    ];
    const offenders = targets.filter((file) => /\bdark:/.test(readFileSync(file, "utf8")));
    assert.deepEqual(offenders, []);
  });
});
