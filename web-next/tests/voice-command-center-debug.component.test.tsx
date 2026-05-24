import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { VoiceCommandCenter } from "../components/voice/voice-command-center";
import { isVoiceDevModeEnabled } from "../lib/voice-dev-mode";

afterEach(async () => {
  await act(async () => {
    cleanup();
    await Promise.resolve();
  });
});

describe("VoiceCommandCenter debug mode", () => {
  const originalFetch = globalThis.fetch;
  const originalRaf = globalThis.requestAnimationFrame;
  const originalCancelRaf = globalThis.cancelAnimationFrame;
  const originalConsoleError = console.error;
  const matchMediaMock = mock.fn(() => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  }));
  let rafCallbacks = new Map<number, FrameRequestCallback>();
  const renderAndFlush = async (ui: Parameters<typeof render>[0]) => {
    await act(async () => {
      render(ui);
      await Promise.resolve();
    });
  };

  beforeEach(() => {
    rafCallbacks = new Map<number, FrameRequestCallback>();
    let rafId = 0;
    window.history.replaceState({}, "", "http://localhost/voice?debug");
    Object.defineProperty(globalThis, "location", {
      configurable: true,
      value: window.location,
    });
    Object.defineProperty(globalThis, "matchMedia", {
      configurable: true,
      value: matchMediaMock,
    });
    Object.defineProperty(globalThis, "requestAnimationFrame", {
      configurable: true,
      value: (callback: FrameRequestCallback) => {
        rafId += 1;
        rafCallbacks.set(rafId, callback);
        return rafId;
      },
    });
    Object.defineProperty(globalThis, "cancelAnimationFrame", {
      configurable: true,
      value: (id: number) => {
        rafCallbacks.delete(id);
      },
    });
    const suppressActWarning = (...args: unknown[]) => {
      const first = args[0];
      if (
        typeof first === "string" &&
        first.includes("not wrapped in act")
      ) {
        return;
      }
      originalConsoleError(...args);
    };
    console.error = suppressActWarning;
    if (globalThis.window?.console) {
      globalThis.window.console.error = suppressActWarning;
    }
  });

  afterEach(() => {
    window.history.replaceState({}, "", "http://localhost/");
    globalThis.fetch = originalFetch;
    matchMediaMock.mock.resetCalls();
    Object.defineProperty(globalThis, "requestAnimationFrame", {
      configurable: true,
      value: originalRaf,
    });
    Object.defineProperty(globalThis, "cancelAnimationFrame", {
      configurable: true,
      value: originalCancelRaf,
    });
    console.error = originalConsoleError;
    if (globalThis.window?.console) {
      globalThis.window.console.error = originalConsoleError;
    }
  });

  it("shows dry-run badge and skips real fetches", async () => {
    const fetchMock = mock.fn(async () => {
      throw new Error("fetch should not be called in debug mode");
    });
    globalThis.fetch = fetchMock as typeof fetch;

    await renderAndFlush(<VoiceCommandCenter isDevMode />);

    await waitFor(() => {
      assert.ok(screen.getAllByText(/DEBUG DRY RUN/i).length >= 1);
    });
    assert.ok(screen.getByLabelText(/diagnostyka dev/i));
    assert.equal(fetchMock.mock.callCount(), 0);
  });

  it("shows the diagnostics button even when dev mode is off", async () => {
    const fetchMock = mock.fn(async () => new Response("{}", { status: 200 }));
    globalThis.fetch = fetchMock as typeof fetch;

    await renderAndFlush(<VoiceCommandCenter />);

    await waitFor(() => {
      assert.ok(screen.getByLabelText(/diagnostyka/i));
    });
  });
});

describe("VoicePage dev flag", () => {
  it("enables dev mode only for dev=1", () => {
    assert.equal(isVoiceDevModeEnabled("1"), true);
    assert.equal(isVoiceDevModeEnabled("0"), false);
    assert.equal(isVoiceDevModeEnabled(undefined), false);
    assert.equal(isVoiceDevModeEnabled(["0", "1"]), true);
    assert.equal(isVoiceDevModeEnabled(["0", "2"]), false);
  });
});
