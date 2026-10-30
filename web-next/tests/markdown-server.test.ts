import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { MarkdownPreview } from "../components/ui/markdown";

describe("Markdown without a browser DOM", () => {
  it("renders nonempty history as escaped text without invoking browser sanitization", () => {
    assert.equal(typeof window, "undefined");
    const html = renderToString(createElement(MarkdownPreview, {
      content: '<img src=x onerror="alert(1)"> **history** $$x^2$$',
    }));
    assert.match(html, /&lt;img/);
    assert.match(html, /history/);
    assert.doesNotMatch(html, /<img/);
  });
});
