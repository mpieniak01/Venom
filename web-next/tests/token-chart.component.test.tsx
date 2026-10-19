import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import type { ComponentProps } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";

import { TokenChart } from "../components/cockpit/token-chart";
import { LanguageProvider } from "../lib/i18n";

type Loader = NonNullable<ComponentProps<typeof TokenChart>["loadChart"]>;
type ChartModule = Awaited<ReturnType<Loader>>;
const history = [{ timestamp: "12:00", value: 10 }];

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function fakeModule(failure?: "constructor" | "update" | "destroy") {
  const instances: FakeChart[] = [];
  class FakeChart {
    data: { labels?: unknown[]; datasets: { data: unknown[] }[] };
    updates = 0;
    destroys = 0;
    constructor(_canvas: unknown, config: { data: FakeChart["data"] }) {
      if (failure === "constructor") throw new Error("constructor unavailable");
      this.data = config.data;
      instances.push(this);
    }
    update() {
      this.updates += 1;
      if (failure === "update") throw new Error("update unavailable");
    }
    destroy() {
      this.destroys += 1;
      if (failure === "destroy") throw new Error("destroy unavailable");
    }
  }
  return { module: { default: FakeChart } as unknown as ChartModule, instances };
}

function chart(historyValue = history, loadChart: Loader) {
  return <LanguageProvider><TokenChart history={historyValue} loadChart={loadChart} /></LanguageProvider>;
}

afterEach(() => {
  cleanup();
  mock.restoreAll();
});

describe("TokenChart lifecycle", () => {
  it("updates one chart and destroys that instance on unmount", async () => {
    const fake = fakeModule();
    let imports = 0;
    const loader = () => { imports += 1; return Promise.resolve(fake.module); };
    const view = render(chart(history, loader));
    await waitFor(() => assert.equal(fake.instances.length, 1));
    view.rerender(chart([{ timestamp: "12:01", value: 21 }], loader));
    await waitFor(() => assert.equal(fake.instances[0].updates, 1));
    assert.deepEqual(fake.instances[0].data.labels, ["12:01"]);
    assert.deepEqual(fake.instances[0].data.datasets[0].data, [21]);
    assert.equal(imports, 1);
    view.unmount();
    assert.equal(fake.instances[0].destroys, 1);
  });

  it("shows the original samples when the dynamic import rejects", async () => {
    mock.method(console, "warn", () => {});
    render(chart(history, () => Promise.reject(new Error("chunk unavailable"))));
    const fallback = await screen.findByRole("list");
    assert.match(fallback.textContent ?? "", /12:00: 10/);
    assert.equal(document.querySelector("canvas"), null);
  });

  it("shows samples when the chart constructor fails", async () => {
    mock.method(console, "warn", () => {});
    const fake = fakeModule("constructor");
    render(chart(history, () => Promise.resolve(fake.module)));
    await screen.findByRole("list");
    assert.equal(fake.instances.length, 0);
  });

  it("destroys a failed update once and keeps current samples visible", async () => {
    mock.method(console, "warn", () => {});
    const fake = fakeModule("update");
    const loader = () => Promise.resolve(fake.module);
    const view = render(chart(history, loader));
    await waitFor(() => assert.equal(fake.instances.length, 1));
    view.rerender(chart([{ timestamp: "12:02", value: 30 }], loader));
    const fallback = await screen.findByRole("list");
    assert.match(fallback.textContent ?? "", /12:02: 30/);
    assert.equal(fake.instances[0].destroys, 1);
    view.unmount();
    assert.equal(fake.instances[0].destroys, 1);
  });

  it("does not create a chart when an import resolves after unmount", async () => {
    const fake = fakeModule();
    const pending = deferred<ChartModule>();
    const view = render(chart(history, () => pending.promise));
    view.unmount();
    await act(async () => { pending.resolve(fake.module); await pending.promise; });
    assert.equal(fake.instances.length, 0);
  });

  it("contains import rejection after unmount", async () => {
    const warning = mock.method(console, "warn", () => {});
    const pending = deferred<ChartModule>();
    const view = render(chart(history, () => pending.promise));
    view.unmount();
    await act(async () => { pending.reject(new Error("late failure")); await Promise.resolve(); });
    assert.equal(warning.mock.callCount(), 0);
  });

  it("contains cleanup errors without retaining the failed chart", async () => {
    const warning = mock.method(console, "warn", () => {});
    const fake = fakeModule("destroy");
    const view = render(chart(history, () => Promise.resolve(fake.module)));
    await waitFor(() => assert.equal(fake.instances.length, 1));
    view.unmount();
    assert.equal(fake.instances[0].destroys, 1);
    assert.equal(warning.mock.callCount(), 1);
  });
});
