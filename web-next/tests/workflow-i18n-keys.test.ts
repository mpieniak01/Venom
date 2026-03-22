import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { pl } from "../lib/i18n/locales/pl";
import { en } from "../lib/i18n/locales/en";
import { de } from "../lib/i18n/locales/de";
import { workflowControl as workflowControlPl } from "../lib/i18n/locales/workflow-control/pl";
import { workflowControl as workflowControlEn } from "../lib/i18n/locales/workflow-control/en";
import { workflowControl as workflowControlDe } from "../lib/i18n/locales/workflow-control/de";

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
  "workflowControl.labels.domainStepRelation",
  "workflowControl.labels.runtimeStepRelation",
  "workflowControl.labels.stepSequenceRelation",
  "workflowControl.messages.selectNode",
  "workflowControl.messages.connectionRejected",
  "workflowControl.messages.graphRelationDomainHint",
  "workflowControl.messages.graphRelationRuntimeHint",
  "workflowControl.messages.graphRelationSequenceHint",
  "workflowControl.messages.unknown_node_type",
  "workflowControl.messages.invalid_connection",
  "workflowControl.common.unknown",
  "workflowControl.sections.intent",
  "workflowControl.sections.embedding",
  "workflowControl.sections.provider",
] as const;

function collectLeafKeys(
  value: unknown,
  prefix = "",
): string[] {
  if (!value || typeof value !== "object") {
    return [];
  }
  const keys: string[] = [];
  for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (nested && typeof nested === "object") {
      keys.push(...collectLeafKeys(nested, path));
    } else {
      keys.push(path);
    }
  }
  return keys;
}

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

  it("keeps workflowControl leaf keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(workflowControlPl));
    const enKeys = new Set(collectLeafKeys(workflowControlEn));
    const deKeys = new Set(collectLeafKeys(workflowControlDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "workflowControl key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "workflowControl key drift: de vs pl");
  });
});
