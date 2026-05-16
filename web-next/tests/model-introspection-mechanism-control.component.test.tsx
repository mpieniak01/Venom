import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ModelIntrospectionMechanismProvider, ModelIntrospectionMechanismControl } from "../components/inspector/model-introspection-mechanism";

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

    const switches = screen.getAllByRole("switch", { name: "Toggle live analysis mechanism" });
    assert.equal(switches.length, 2);
    assert.equal(switches[0].getAttribute("aria-checked"), "false");
    assert.equal(switches[1].getAttribute("aria-checked"), "false");
    assert.equal(screen.getAllByText("disabled").length, 2);

    fireEvent.click(switches[0]);

    await waitFor(() => {
      const updatedSwitches = screen.getAllByRole("switch", { name: "Toggle live analysis mechanism" });
      assert.equal(updatedSwitches[0].getAttribute("aria-checked"), "true");
      assert.equal(updatedSwitches[1].getAttribute("aria-checked"), "true");
      assert.equal(screen.getAllByText("enabled").length, 2);
    });
  });
});
