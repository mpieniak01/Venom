import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { VoiceCommandCenter } from "../components/voice/voice-command-center";

afterEach(() => cleanup());

describe("VoiceCommandCenter debug mode", () => {
  const originalFetch = globalThis.fetch;
  const matchMediaMock = mock.fn(() => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  }));

  beforeEach(() => {
    window.history.replaceState({}, "", "http://localhost/voice?debug");
    Object.defineProperty(globalThis, "location", {
      configurable: true,
      value: window.location,
    });
    Object.defineProperty(globalThis, "matchMedia", {
      configurable: true,
      value: matchMediaMock,
    });
  });

  afterEach(() => {
    window.history.replaceState({}, "", "http://localhost/");
    globalThis.fetch = originalFetch;
    matchMediaMock.mock.resetCalls();
  });

  it("shows dry-run badge and skips real fetches", async () => {
    const fetchMock = mock.fn(async () => {
      throw new Error("fetch should not be called in debug mode");
    });
    globalThis.fetch = fetchMock as typeof fetch;

    render(<VoiceCommandCenter isDevMode />);

    await waitFor(() => {
      assert.ok(screen.getAllByText(/DEBUG DRY RUN/i).length >= 1);
    });
    assert.ok(screen.getByLabelText(/diagnostyka dev/i));
    assert.equal(fetchMock.mock.callCount(), 0);
  });
});
