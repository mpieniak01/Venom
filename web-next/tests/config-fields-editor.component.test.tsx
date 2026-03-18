import "./component-test-setup";

import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ConfigFieldsEditor } from "../components/workflow-control/ConfigFieldsEditor";

afterEach(() => {
  cleanup();
});

describe("ConfigFieldsEditor", () => {
  it("updates editable config field value after expanding card", () => {
    const onUpdateField = mock.fn(() => undefined);

    render(
      <ConfigFieldsEditor
        configFields={[
          {
            entity_id: "config:AI_MODE",
            field: "AI_MODE",
            key: "AI_MODE",
            value: "standard",
            effective_value: "standard",
            source: "env",
            editable: true,
            restart_required: false,
            affected_services: ["backend"],
          },
        ]}
        onUpdateField={onUpdateField}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /AI_MODE/i }));
    const input = screen.getByLabelText("Set Value");
    fireEvent.change(input, { target: { value: "advanced" } });

    assert.equal(onUpdateField.mock.callCount(), 1);
    const firstCall = onUpdateField.mock.calls[0];
    assert.equal(firstCall.arguments[0].key, "AI_MODE");
    assert.equal(firstCall.arguments[1], "advanced");
  });

  it("renders restart and affected services metadata for expanded field", () => {
    const onUpdateField = mock.fn(() => undefined);

    render(
      <ConfigFieldsEditor
        configFields={[
          {
            entity_id: "config:KERNEL",
            field: "KERNEL",
            key: "KERNEL",
            value: "standard",
            effective_value: "standard",
            source: "env",
            editable: true,
            restart_required: true,
            affected_services: ["backend", "ui"],
          },
        ]}
        onUpdateField={onUpdateField}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /KERNEL/i }));

    assert.ok(screen.getByText("Requires Restart"));
    assert.ok(screen.getByText("Affected Services"));
    assert.ok(screen.getByText("backend"));
    assert.ok(screen.getByText("ui"));
  });
});
