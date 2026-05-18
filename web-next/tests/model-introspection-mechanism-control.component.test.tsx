import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ModelIntrospectionMechanismProvider, ModelIntrospectionMechanismControl } from "../components/inspector/model-introspection-mechanism";

const mechanismStorageKey = "venom.modelIntrospection.liveAnalysisEnabled";

beforeEach(() => {
  globalThis.window.localStorage.removeItem(mechanismStorageKey);
});

afterEach(() => cleanup());

describe("ModelIntrospectionMechanismControl", () => {
  it("shares state across multiple layers", async () => {
    render(
      <ModelIntrospectionMechanismProvider>
        <div className="space-y-4">
          <ModelIntrospectionMechanismControl />
          <ModelIntrospectionMechanismControl variant="compact" />
        </div>
      </ModelIntrospectionMechanismProvider>,
    );

    const switches = screen.getAllByRole("switch");
    assert.equal(switches.length, 2);
    assert.equal(switches[0].getAttribute("aria-checked"), "true");
    assert.equal(switches[1].getAttribute("aria-checked"), "true");

    fireEvent.click(switches[0]);

    await waitFor(() => {
      const updatedSwitches = screen.getAllByRole("switch");
      assert.equal(updatedSwitches[0].getAttribute("aria-checked"), "false");
      assert.equal(updatedSwitches[1].getAttribute("aria-checked"), "false");
    });
  });

  it("reads persisted state after mount without hydrating to a mismatch", async () => {
    globalThis.window.localStorage.setItem(mechanismStorageKey, "true");

    render(
      <ModelIntrospectionMechanismProvider>
        <ModelIntrospectionMechanismControl variant="compact" />
      </ModelIntrospectionMechanismProvider>,
    );

    await waitFor(() => {
      const switchEl = screen.getByRole("switch");
      assert.equal(switchEl.getAttribute("aria-checked"), "true");
    });
  });
});
