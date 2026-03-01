import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { sanitizeMermaidDiagram } from "../app/inspector/inspector-utils";
import { formatUptime } from "../components/config/services-panel-utils";
import { cockpitLocale as cockpitPl } from "../lib/i18n/locales/cockpit/pl";
import { cockpitLocale as cockpitEn } from "../lib/i18n/locales/cockpit/en";
import { cockpitLocale as cockpitDe } from "../lib/i18n/locales/cockpit/de";

function resolvePath(locale: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, locale);
}

describe("inspector/config helpers", () => {
  it("preserves mermaid syntax tokens used by generated diagrams", () => {
    const input = 'graph TD\nA -->|ok| B\nclassDef success fill:#22c55e,stroke:#111';
    const output = sanitizeMermaidDiagram(input);
    assert.equal(output, input);
  });

  it("formats uptime for 0 and null values correctly", () => {
    assert.equal(formatUptime(0), "0h 0m");
    assert.equal(formatUptime(null), "—");
  });
});

describe("cockpit locale additions", () => {
  it("contains queue/model action keys in pl/en/de", () => {
    const requiredKeys = [
      "queueActions.queuePurged",
      "queueActions.emergencyStopped",
      "queueActions.operationError",
      "queueActions.queueResumed",
      "queueActions.queuePaused",
      "queueActions.toggleError",
      "modelActivation.providerMissing",
      "modelActivation.activated",
      "modelActivation.failed",
      "modelActivation.unknownError",
    ] as const;

    const locales: Array<[string, Record<string, unknown>]> = [
      ["pl", cockpitPl as Record<string, unknown>],
      ["en", cockpitEn as Record<string, unknown>],
      ["de", cockpitDe as Record<string, unknown>],
    ];

    for (const [name, locale] of locales) {
      for (const key of requiredKeys) {
        assert.equal(
          typeof resolvePath(locale, key),
          "string",
          `Missing cockpit key ${key} in locale ${name}`,
        );
      }
    }
  });
});
