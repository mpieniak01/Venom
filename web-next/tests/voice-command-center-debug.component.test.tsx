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
  const originalStderrWrite = process.stderr.write.bind(process.stderr);
  const matchMediaMock = mock.fn(() => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  }));
  let rafCallbacks = new Map<number, FrameRequestCallback>();
  const flushAsyncEffects = async () => {
    await act(async () => {
      await Promise.resolve();
      await new Promise<void>((resolve) => globalThis.setTimeout(resolve, 0));
      await Promise.resolve();
    });
  };
  const renderAndFlush = async (ui: Parameters<typeof render>[0]) => {
    await act(async () => {
      render(ui);
      await Promise.resolve();
    });
    await flushAsyncEffects();
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
    const suppressVoicePanelActWarning = (...args: unknown[]) => {
      const first = args[0];
      if (
        typeof first === "string" &&
        first.includes("An update to VoiceCommandCenterPanel inside a test was not wrapped in act")
      ) {
        return;
      }
      originalConsoleError(...args);
    };
    console.error = suppressVoicePanelActWarning;
    if (globalThis.window?.console) {
      globalThis.window.console.error = suppressVoicePanelActWarning;
    }
    process.stderr.write = ((chunk: unknown, ...args: unknown[]) => {
      const text = String(chunk ?? "");
      if (
        text.includes("An update to VoiceCommandCenterPanel inside a test was not wrapped in act") ||
        text.includes("When testing, code that causes React state updates should be wrapped into act") ||
        text.includes("This ensures that you're testing the behavior the user would see in the browser.")
      ) {
        return true;
      }
      return (originalStderrWrite as (...p: unknown[]) => boolean)(chunk, ...args);
    }) as typeof process.stderr.write;
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
    process.stderr.write = originalStderrWrite as typeof process.stderr.write;
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
    await flushAsyncEffects();
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
    await flushAsyncEffects();
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
