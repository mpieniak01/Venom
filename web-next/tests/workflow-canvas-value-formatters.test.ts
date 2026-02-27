import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  readSourceTag,
  resolveConnectionReasonText,
  resolveDisplayValue,
  runtimeBadgeValue,
  type TranslateFn,
} from "../components/workflow-control/canvas/value-formatters";

const createTranslator = (dictionary: Record<string, string>): TranslateFn => {
  return (path, replacements) => {
    const template = dictionary[path] ?? path;
    if (!replacements) {
      return template;
    }
    return Object.entries(replacements).reduce((value, [key, replacement]) => {
      return value.replace(`{{${key}}}`, String(replacement));
    }, template);
  };
};

describe("workflow canvas value formatters", () => {
  it("normalizes source tags to local/cloud", () => {
    assert.equal(readSourceTag(undefined), "local");
    assert.equal(readSourceTag({}), "local");
    assert.equal(readSourceTag({ sourceTag: "local" }), "local");
    assert.equal(readSourceTag({ sourceTag: "cloud" }), "cloud");
    assert.equal(readSourceTag({ sourceTag: "unsupported" }), "local");
  });

  it("resolves display value using localized fallback maps", () => {
    const t = createTranslator({
      "workflowControl.common.missing": "missing",
      "workflowControl.strategies.advanced": "Advanced",
    });

    assert.equal(
      resolveDisplayValue("advanced", t, "workflowControl.strategies"),
      "Advanced",
    );
    assert.equal(
      resolveDisplayValue("custom-strategy", t, "workflowControl.strategies"),
      "custom-strategy",
    );
    assert.equal(resolveDisplayValue("", t, "workflowControl.strategies"), "missing");
    assert.equal(resolveDisplayValue(undefined, t), "missing");
  });

  it("renders runtime badge value from runtime services", () => {
    const t = createTranslator({
      "workflowControl.common.auto": "auto",
      "workflowControl.canvas.servicesCount": "{{count}} services",
    });

    assert.equal(runtimeBadgeValue(undefined, t), "auto");
    assert.equal(runtimeBadgeValue({ runtime: { services: [] } }, t), "auto");
    assert.equal(runtimeBadgeValue({ runtime: { services: ["backend"] } }, t), "backend");
    assert.equal(
      runtimeBadgeValue({ runtime: { services: ["backend", "ui"] } }, t),
      "2 services",
    );
  });

  it("maps connection validation reasons to stable i18n texts", () => {
    const translated = createTranslator({
      "workflowControl.messages.invalid_connection": "Invalid connection",
      "workflowControl.common.unknown": "Unknown",
    });
    const untranslated = createTranslator({
      "workflowControl.common.unknown": "Unknown",
    });

    assert.equal(
      resolveConnectionReasonText("invalid_connection", "detail", translated),
      "Invalid connection: detail",
    );
    assert.equal(
      resolveConnectionReasonText("invalid_connection", "detail", untranslated),
      "detail",
    );
    assert.equal(
      resolveConnectionReasonText("unknown_node_type", undefined, untranslated),
      "unknown_node_type",
    );
    assert.equal(resolveConnectionReasonText(undefined, undefined, translated), "Unknown");
  });
});
