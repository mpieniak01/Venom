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

window.HTMLCanvasElement.prototype.getContext = function getContext() {
  return {
    canvas: this,
    clearRect() {},
    fillRect() {},
    getImageData() {
      return { data: [] };
    },
    putImageData() {},
    createImageData() {
      return [];
    },
    setTransform() {},
    drawImage() {},
    save() {},
    restore() {},
    beginPath() {},
    moveTo() {},
    lineTo() {},
    closePath() {},
    stroke() {},
    fillText() {},
    strokeText() {},
    translate() {},
    scale() {},
    rotate() {},
    arc() {},
    fill() {},
    measureText() {
      return { width: 0 };
    },
    setLineDash() {},
    getLineDash() {
      return [];
    },
    transform() {},
    rect() {},
    clip() {},
    font: "10px sans-serif",
    textAlign: "start",
    textBaseline: "alphabetic",
  } as unknown as CanvasRenderingContext2D;
};

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
