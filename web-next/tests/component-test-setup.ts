import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
});

const { window } = dom;

Object.assign(globalThis, {
  window,
  self: window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  SVGElement: window.SVGElement,
  Node: window.Node,
  DocumentFragment: window.DocumentFragment,
  MutationObserver: window.MutationObserver,
  Event: window.Event,
  CustomEvent: window.CustomEvent,
  KeyboardEvent: window.KeyboardEvent,
  MouseEvent: window.MouseEvent,
  FocusEvent: window.FocusEvent,
  NodeFilter: window.NodeFilter,
  HTMLInputElement: window.HTMLInputElement,
  HTMLButtonElement: window.HTMLButtonElement,
  HTMLTextAreaElement: window.HTMLTextAreaElement,
  HTMLSelectElement: window.HTMLSelectElement,
  HTMLAnchorElement: window.HTMLAnchorElement,
  getComputedStyle: window.getComputedStyle.bind(window),
});

if (!("ResizeObserver" in globalThis)) {
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserverMock }).ResizeObserver =
    ResizeObserverMock;
}

if (!("requestAnimationFrame" in globalThis)) {
  globalThis.requestAnimationFrame = (callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(Date.now()), 16);
}

if (!("cancelAnimationFrame" in globalThis)) {
  globalThis.cancelAnimationFrame = (id: number) => window.clearTimeout(id);
}

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const originalConsoleError = console.error.bind(console);
console.error = (...args: unknown[]) => {
  const first = args[0];
  if (
    typeof first === "string"
    && first.includes("not wrapped in act")
  ) {
    return;
  }
  originalConsoleError(...args);
};
