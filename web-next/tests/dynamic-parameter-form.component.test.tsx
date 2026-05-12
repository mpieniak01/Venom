import "./component-test-setup";

import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DynamicParameterForm } from "../components/ui/dynamic-parameter-form";

afterEach(() => cleanup());

describe("DynamicParameterForm", () => {
  it("does not emit onChange on mount", () => {
    const onChange = mock.fn(() => undefined);

    render(
      <DynamicParameterForm
        schema={{
          temperature: {
            type: "float",
            default: 0.7,
            min: 0,
            max: 2,
            desc: "Controls randomness",
          },
        }}
        onChange={onChange}
      />,
    );

    assert.equal(onChange.mock.callCount(), 0);
  });

  it("emits onChange after user interaction", () => {
    const onChange = mock.fn(() => undefined);

    render(
      <DynamicParameterForm
        schema={{
          top_k: {
            type: "int",
            default: 64,
            min: 1,
            max: 128,
            desc: "Top-k sampling",
          },
        }}
        onChange={onChange}
      />,
    );

    const [spinbox] = screen.getAllByRole("spinbutton");
    fireEvent.change(spinbox, { target: { value: "32" } });

    assert.equal(onChange.mock.callCount(), 1);
    const call = onChange.mock.calls[0];
    assert.ok(call);
    const [payload] = ((call.arguments ?? []) as unknown) as [Record<string, unknown>];
    assert.equal(payload.top_k, 32);
  });
});
