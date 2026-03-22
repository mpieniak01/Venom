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
    assert.ok(firstCall);
    const [updatedField, updatedValue] = ((firstCall.arguments ?? []) as unknown) as [
      { key: string },
      unknown,
    ];
    assert.equal(updatedField.key, "AI_MODE");
    assert.equal(updatedValue, "advanced");
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

  it("updates selectable config field through compact option pills", () => {
    const onUpdateField = mock.fn(() => undefined);

    render(
      <ConfigFieldsEditor
        configFields={[
          {
            entity_id: "config:INTENT_MODE",
            field: "INTENT_MODE",
            key: "INTENT_MODE",
            value: "simple",
            effective_value: "simple",
            source: "env",
            editable: true,
            restart_required: false,
            affected_services: ["backend"],
            options: ["simple", "advanced", "expert"],
          },
        ]}
        onUpdateField={onUpdateField}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /INTENT_MODE/i }));
    fireEvent.click(screen.getByRole("button", { name: "advanced" }));

    assert.equal(onUpdateField.mock.callCount(), 1);
    const firstCall = onUpdateField.mock.calls[0];
    assert.ok(firstCall);
    const [updatedField, updatedValue] = ((firstCall.arguments ?? []) as unknown) as [
      { key: string },
      unknown,
    ];
    assert.equal(updatedField.key, "INTENT_MODE");
    assert.equal(updatedValue, "advanced");
  });

  it("disables controls for read-only config fields", () => {
    const onUpdateField = mock.fn(() => undefined);

    render(
      <ConfigFieldsEditor
        configFields={[
          {
            entity_id: "config:ACTIVE_PROVIDER",
            field: "ACTIVE_PROVIDER",
            key: "ACTIVE_PROVIDER",
            value: "ollama",
            effective_value: "ollama",
            source: "env",
            editable: false,
            restart_required: false,
            affected_services: ["backend"],
          },
        ]}
        onUpdateField={onUpdateField}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /ACTIVE_PROVIDER/i }));
    const input = screen.getByLabelText("Set Value") as HTMLInputElement;
    assert.equal(input.disabled, true);
    assert.equal(onUpdateField.mock.callCount(), 0);
  });
});
