import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

function parseHex(color: string) {
  const value = color.trim().toLowerCase();
  const match = value.match(/^#([0-9a-f]{6})$/);
  if (!match) {
    return null;
  }
  const raw = match[1];
  return {
    r: Number.parseInt(raw.slice(0, 2), 16),
    g: Number.parseInt(raw.slice(2, 4), 16),
    b: Number.parseInt(raw.slice(4, 6), 16),
  };
}

function srgbToLinear(v: number) {
  const c = v / 255;
  if (c <= 0.03928) return c / 12.92;
  return ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(color: { r: number; g: number; b: number }) {
  return (
    0.2126 * srgbToLinear(color.r) +
    0.7152 * srgbToLinear(color.g) +
    0.0722 * srgbToLinear(color.b)
  );
}

function contrastRatio(foregroundHex: string, backgroundHex: string) {
  const fg = parseHex(foregroundHex);
  const bg = parseHex(backgroundHex);
  assert.ok(fg, `Unsupported color format: ${foregroundHex}`);
  assert.ok(bg, `Unsupported color format: ${backgroundHex}`);

  const l1 = luminance(fg);
  const l2 = luminance(bg);
  const brighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (brighter + 0.05) / (darker + 0.05);
}

function extractThemeBlock(css: string, selector: string, expectedVar: string) {
  const blocks = [...css.matchAll(new RegExp(`${selector}\\s*\\{([\\s\\S]*?)\\n\\}`, "g"))];
  const block = blocks.find((entry) => entry[1].includes(expectedVar));
  assert.ok(block, `Missing CSS block for selector ${selector}`);
  return block[1];
}

function extractVar(block: string, name: string) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = block.match(new RegExp(`${escaped}:\\s*([^;]+);`));
  assert.ok(match, `Missing variable ${name}`);
  return match[1].trim();
}

describe("theme contrast a11y", () => {
  const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");
  const rootBlock = extractThemeBlock(css, ":root", "--bg-dark");
  const lightBlock = extractThemeBlock(
    css,
    'html\\[data-theme="venom-light"\\],\\s*html\\[data-theme="venom-light-dev"\\]',
    "--bg-dark",
  );

  it("defines required semantic tokens for dark and light theme", () => {
    for (const [name, block] of [
      ["venom-dark", rootBlock],
      ["venom-light", lightBlock],
    ] as const) {
      assert.ok(extractVar(block, "--bg-dark"), `Missing --bg-dark in ${name}`);
      assert.ok(extractVar(block, "--text-primary"), `Missing --text-primary in ${name}`);
      assert.ok(extractVar(block, "--ui-muted"), `Missing --ui-muted in ${name}`);
    }
  });

  it("keeps primary text contrast at AA level", () => {
    const darkRatio = contrastRatio(
      extractVar(rootBlock, "--text-primary"),
      extractVar(rootBlock, "--bg-dark"),
    );
    const lightRatio = contrastRatio(
      extractVar(lightBlock, "--text-primary"),
      extractVar(lightBlock, "--bg-dark"),
    );

    assert.ok(darkRatio >= 4.5, `venom-dark ratio too low: ${darkRatio.toFixed(2)}`);
    assert.ok(lightRatio >= 4.5, `venom-light ratio too low: ${lightRatio.toFixed(2)}`);
  });

  it("keeps muted text contrast at readable level", () => {
    const darkRatio = contrastRatio(
      extractVar(rootBlock, "--ui-muted"),
      extractVar(rootBlock, "--bg-dark"),
    );
    const lightRatio = contrastRatio(
      extractVar(lightBlock, "--ui-muted"),
      extractVar(lightBlock, "--bg-dark"),
    );

    assert.ok(darkRatio >= 3.0, `venom-dark muted ratio too low: ${darkRatio.toFixed(2)}`);
    assert.ok(lightRatio >= 3.0, `venom-light muted ratio too low: ${lightRatio.toFixed(2)}`);
  });
});
