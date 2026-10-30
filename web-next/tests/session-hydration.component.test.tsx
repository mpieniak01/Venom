import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { hydrateRoot, type Root } from "react-dom/client";
import { SessionProvider, useSession } from "../lib/session";

const originalFetch = globalThis.fetch;
const ID_KEY = "venom-session-id";
const BUILD_KEY = "venom-next-build-id";
const BOOT_KEY = "venom-backend-boot-id";
let bootId = "boot-one";

function Probe() {
  const { sessionId, resetSession } = useSession();
  return <><output data-testid="session">{sessionId}</output><button onClick={resetSession}>reset</button></>;
}

function Session() {
  return <SessionProvider><Probe /></SessionProvider>;
}

beforeEach(() => {
  window.localStorage.clear();
  bootId = "boot-one";
  globalThis.fetch = async () => Response.json({ boot_id: bootId });
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  Reflect.deleteProperty(window, "__NEXT_DATA__");
  globalThis.fetch = originalFetch;
  mock.restoreAll();
});

describe("SessionProvider hydration and continuity", () => {
  for (const stored of [false, true]) {
    it(`hydrates the same empty snapshot with ${stored ? "a saved" : "a new"} session`, async () => {
      if (stored) {
        window.localStorage.setItem(ID_KEY, "session-saved");
        window.localStorage.setItem(BUILD_KEY, "unknown");
      }
      const html = renderToString(<Session />);
      assert.ok(!html.includes("session-saved"));
      assert.equal(window.localStorage.getItem(ID_KEY), stored ? "session-saved" : null);
      const container = document.createElement("div");
      container.innerHTML = html;
      document.body.append(container);
      const errors: unknown[] = [];
      let root: Root | undefined;
      try {
        await act(async () => {
          root = hydrateRoot(container, <Session />, { onRecoverableError: (error) => errors.push(error) });
        });
        await waitFor(() => assert.ok(container.querySelector("output")?.textContent));
        assert.deepEqual(errors, []);
        const id = container.querySelector("output")?.textContent;
        assert.equal(id, window.localStorage.getItem(ID_KEY));
        if (stored) assert.equal(id, "session-saved");
        else assert.match(id ?? "", /^session-\d+-/);
      } finally {
        await act(async () => { root?.unmount(); });
        container.remove();
      }
    });
  }

  it("keeps an initialized ID across a reload and replaces it on an explicit reset", async () => {
    const first = render(<Session />);
    const id = screen.getByTestId("session").textContent;
    assert.ok(id);
    first.unmount();
    render(<Session />);
    assert.equal(screen.getByTestId("session").textContent, id);
    fireEvent.click(screen.getByRole("button", { name: "reset" }));
    const resetId = screen.getByTestId("session").textContent;
    assert.ok(resetId && resetId !== id);
    assert.equal(window.localStorage.getItem(ID_KEY), resetId);
  });

  it("retains the existing build invalidation rule without reading storage during render", async () => {
    window.localStorage.setItem(ID_KEY, "old-build-session");
    window.localStorage.setItem(BUILD_KEY, "old-build");
    window.__NEXT_DATA__ = { buildId: "new-build", props: {}, page: "/chat", query: {} };
    const html = renderToString(<Session />);
    assert.ok(!html.includes("old-build-session"));
    assert.equal(window.localStorage.getItem(ID_KEY), "old-build-session");
    render(<Session />);
    assert.notEqual(screen.getByTestId("session").textContent, "old-build-session");
    assert.equal(window.localStorage.getItem(BUILD_KEY), "new-build");
  });

  it("still initializes one usable in-memory session when storage throws", () => {
    const storagePrototype = Object.getPrototypeOf(window.localStorage);
    mock.method(storagePrototype, "getItem", () => { throw new Error("storage denied"); });
    mock.method(storagePrototype, "setItem", () => { throw new Error("storage denied"); });
    render(<Session />);
    const id = screen.getByTestId("session").textContent;
    assert.match(id ?? "", /^session-\d+-/);
    fireEvent.click(screen.getByRole("button", { name: "reset" }));
    assert.ok(screen.getByTestId("session").textContent !== id);
  });

  it("rotates the current session once after a changed backend boot and keeps the boot marker", async () => {
    window.localStorage.setItem(ID_KEY, "before-restart");
    window.localStorage.setItem(BUILD_KEY, "unknown");
    window.localStorage.setItem(BOOT_KEY, "boot-old");
    render(<Session />);
    await waitFor(() => assert.notEqual(screen.getByTestId("session").textContent, "before-restart"));
    const id = screen.getByTestId("session").textContent;
    assert.equal(window.localStorage.getItem(BOOT_KEY), "boot-one");
    fireEvent.focus(window);
    await act(async () => { await Promise.resolve(); });
    assert.equal(screen.getByTestId("session").textContent, id);
  });

  it("does not write a delayed boot response after provider unmount", async () => {
    let release!: (response: Response) => void;
    globalThis.fetch = () => new Promise<Response>((resolve) => { release = resolve; });
    window.localStorage.setItem(BOOT_KEY, "boot-old");
    const view = render(<Session />);
    const id = window.localStorage.getItem(ID_KEY);
    view.unmount();
    await act(async () => {
      release(Response.json({ boot_id: "boot-new" }));
      await Promise.resolve();
    });
    assert.equal(window.localStorage.getItem(ID_KEY), id);
    assert.equal(window.localStorage.getItem(BOOT_KEY), "boot-old");
  });
});
