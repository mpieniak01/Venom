import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, render, screen } from "@testing-library/react";

import { ThemeProvider, useTheme } from "../lib/theme";
import { THEME_STORAGE_KEY } from "../lib/theme-registry";

const originalFetch = globalThis.fetch;

async function flushEffects() {
  await act(async () => {
    await Promise.resolve();
  });
}

function ThemeHarness() {
  const { theme, setTheme, availableThemes } = useTheme();

  return (
    <div>
      <output data-testid="active-theme">{theme}</output>
      <output data-testid="theme-options">{availableThemes.join(",")}</output>
      <button type="button" onClick={() => setTheme("venom-light-dev")}>
        set-light
      </button>
      <button type="button" onClick={() => setTheme("venom-dark")}>
        set-dark
      </button>
    </div>
  );
}

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  window.localStorage.removeItem(THEME_STORAGE_KEY);
  delete document.documentElement.dataset.theme;
});

describe("ThemeProvider", () => {
  it("hydrates from localStorage and applies matching data-theme", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "venom-light-dev");

    render(
      <ThemeProvider>
        <ThemeHarness />
      </ThemeProvider>,
    );

    await flushEffects();

    assert.equal(screen.getByTestId("active-theme").textContent, "venom-light-dev");
    assert.equal(screen.getByTestId("theme-options").textContent, "venom-dark,venom-light-dev");
    assert.equal(document.documentElement.dataset.theme, "venom-light-dev");
  });

  it("falls back to default theme when storage contains invalid value", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "invalid-theme");

    render(
      <ThemeProvider>
        <ThemeHarness />
      </ThemeProvider>,
    );

    await flushEffects();

    assert.equal(screen.getByTestId("active-theme").textContent, "venom-dark");
    assert.equal(document.documentElement.dataset.theme, "venom-dark");
    assert.equal(window.localStorage.getItem(THEME_STORAGE_KEY), null);
  });

  it("persists and applies user-selected theme", async () => {
    const calls: Array<{ url: string; method: string; body: string | null }> = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url: String(input), method, body: init?.body?.toString() ?? null });
      if (method === "POST") {
        return new Response(JSON.stringify({ status: "success" }), { status: 200 });
      }
      return new Response(
        JSON.stringify({ status: "success", config: { UI_THEME_DEFAULT: "venom-dark" } }),
        { status: 200 },
      );
    }) as typeof fetch;

    render(
      <ThemeProvider>
        <ThemeHarness />
      </ThemeProvider>,
    );

    await flushEffects();

    await act(async () => {
      screen.getByRole("button", { name: "set-light" }).click();
    });

    assert.equal(screen.getByTestId("active-theme").textContent, "venom-light-dev");
    assert.equal(document.documentElement.dataset.theme, "venom-light-dev");
    assert.equal(window.localStorage.getItem(THEME_STORAGE_KEY), "venom-light-dev");
    assert.equal(calls.some((entry) => entry.method === "POST"), true);
    assert.equal(calls.some((entry) => entry.body?.includes('"UI_THEME_DEFAULT":"venom-light-dev"')), true);
  });

  it("uses backend default when local override is missing", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          status: "success",
          config: { UI_THEME_DEFAULT: "venom-light-dev" },
        }),
        { status: 200 },
      )) as typeof fetch;

    render(
      <ThemeProvider>
        <ThemeHarness />
      </ThemeProvider>,
    );

    await flushEffects();
    await flushEffects();

    assert.equal(screen.getByTestId("active-theme").textContent, "venom-light-dev");
    assert.equal(document.documentElement.dataset.theme, "venom-light-dev");
    assert.equal(window.localStorage.getItem(THEME_STORAGE_KEY), null);
  });

  it("keeps local override above backend default", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "venom-dark");
    let fetchCalls = 0;
    globalThis.fetch = (async () => {
      fetchCalls += 1;
      return new Response(
        JSON.stringify({
          status: "success",
          config: { UI_THEME_DEFAULT: "venom-light-dev" },
        }),
        { status: 200 },
      );
    }) as typeof fetch;

    render(
      <ThemeProvider>
        <ThemeHarness />
      </ThemeProvider>,
    );

    await flushEffects();
    await flushEffects();

    assert.equal(screen.getByTestId("active-theme").textContent, "venom-dark");
    assert.equal(document.documentElement.dataset.theme, "venom-dark");
    assert.equal(fetchCalls, 0);
  });
});
