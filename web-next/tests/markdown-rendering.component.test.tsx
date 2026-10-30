import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { MarkdownPreview } from "../components/ui/markdown";

type Loader = NonNullable<ComponentProps<typeof MarkdownPreview>["loadMath"]>;
type Renderer = Awaited<ReturnType<Loader>>;

afterEach(() => { cleanup(); mock.restoreAll(); });

describe("on demand Markdown math", () => {
  it("renders plain Markdown, code and sources without requesting mathematics", () => {
    let imports = 0;
    const loadMath: Loader = async () => { imports++; throw new Error("must not load"); };
    const content = "**Hello**\n\n```txt\n$$literal$$\n```\n\nŹródła:\nhttps://example.test";
    const view = render(<MarkdownPreview content={content} loadMath={loadMath} />);
    assert.equal(view.container.querySelector("strong")?.textContent, "Hello");
    assert.match(view.container.querySelector("code")?.textContent ?? "", /literal/);
    assert.ok(view.container.querySelector(".chat-sources-label"));
    assert.equal(imports, 0);
  });

  it("loads final mathematics while keeping readable content and sanitization", async () => {
    let resolve!: (renderer: Renderer) => void;
    const pending = new Promise<Renderer>((done) => { resolve = done; });
    const view = render(<MarkdownPreview content="Wzór: $$x^2$$" loadMath={() => pending} />);
    assert.match(view.container.textContent ?? "", /x\^2/);
    assert.doesNotMatch(view.container.textContent ?? "", /__MATH/);
    await act(async () => resolve({
      renderToString: () => '<span class="katex">formatted</span><img src=x onerror="alert(1)"><script>alert(2)</script>',
    }));
    await waitFor(() => assert.equal(view.container.querySelector(".katex")?.textContent, "formatted"));
    assert.equal(view.container.querySelector("script"), null);
    assert.equal(view.container.querySelector("[onerror]"), null);
  });

  it("never loads math for stream updates and renders it only on finalization", async () => {
    let imports = 0;
    const loadMath: Loader = async () => {
      imports++;
      return { renderToString: () => '<span class="katex">result</span>' };
    };
    const view = render(<MarkdownPreview content="$$x^2$$" mode="stream" loadMath={loadMath} />);
    view.rerender(<MarkdownPreview content="$$x^2+y^2$$" mode="stream" loadMath={loadMath} />);
    assert.equal(imports, 0);
    view.rerender(<MarkdownPreview content="$$x^2+y^2$$" mode="final" loadMath={loadMath} />);
    await waitFor(() => assert.ok(view.container.querySelector(".katex")));
    assert.equal(imports, 1);
  });

  it("retains the escaped expression when a math chunk fails", async () => {
    mock.method(console, "warn", () => {});
    const view = render(<MarkdownPreview content="$$x^2 < 4$$" loadMath={() => Promise.reject(new Error("offline"))} />);
    await act(async () => { await Promise.resolve(); });
    assert.match(view.container.textContent ?? "", /x\^2 < 4/);
    assert.doesNotMatch(view.container.textContent ?? "", /__MATH/);
  });

  it("contains late math resolution and rejection after unmount", async () => {
    const warning = mock.method(console, "warn", () => {});
    let reject!: (error: Error) => void;
    const pending = new Promise<Renderer>((_done, fail) => { reject = fail; });
    const view = render(<MarkdownPreview content="$$x^2$$" loadMath={() => pending} />);
    view.unmount();
    await act(async () => { reject(new Error("late failure")); await Promise.resolve(); });
    assert.equal(warning.mock.callCount(), 0);
  });

  it("sanitizes ordinary HTML without a math renderer", () => {
    const view = render(<MarkdownPreview content={'<img src=x onerror="alert(1)"><script>alert(2)</script> **safe**'} />);
    assert.equal(view.container.querySelector("script"), null);
    assert.equal(view.container.querySelector("[onerror]"), null);
    assert.match(view.container.textContent ?? "", /safe/);
  });
});
