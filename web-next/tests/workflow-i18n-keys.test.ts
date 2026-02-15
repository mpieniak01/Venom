import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { pl } from "../lib/i18n/locales/pl";
import { en } from "../lib/i18n/locales/en";
import { de } from "../lib/i18n/locales/de";

function resolvePath(locale: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, locale);
}

const REQUIRED_WORKFLOW_KEYS = [
  "workflowControl.status.draft",
  "workflowControl.actions.planChanges",
  "workflowControl.actions.reset",
  "workflowControl.labels.systemStatus",
  "workflowControl.labels.strategy",
  "workflowControl.labels.intentMode",
  "workflowControl.labels.activeProvider",
  "workflowControl.labels.rawData",
  "workflowControl.messages.selectNode",
  "workflowControl.messages.connectionRejected",
  "workflowControl.sections.intent",
  "workflowControl.sections.embedding",
  "workflowControl.sections.provider",
] as const;

describe("workflow i18n keys", () => {
  it("contains required keys in all supported locales", () => {
    const locales: Array<[string, Record<string, unknown>]> = [
      ["pl", pl as Record<string, unknown>],
      ["en", en as Record<string, unknown>],
      ["de", de as Record<string, unknown>],
    ];

    for (const [name, locale] of locales) {
      for (const key of REQUIRED_WORKFLOW_KEYS) {
        const value = resolvePath(locale, key);
        assert.equal(typeof value, "string", `Missing key ${key} in locale ${name}`);
      }
    }
  });
});
