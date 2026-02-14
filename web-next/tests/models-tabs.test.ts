import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { en } from "../lib/i18n/locales/en";
import { pl } from "../lib/i18n/locales/pl";
import { de } from "../lib/i18n/locales/de";

describe("Models page tabs i18n", () => {
  it("has tab keys in all locales (EN/PL/DE)", () => {
    // Test English
    assert.ok(en.models.tabs, "EN locale should have models.tabs");
    assert.strictEqual(typeof en.models.tabs.news, "string", "EN models.tabs.news should be a string");
    assert.strictEqual(typeof en.models.tabs.models, "string", "EN models.tabs.models should be a string");

    // Test Polish
    assert.ok(pl.models.tabs, "PL locale should have models.tabs");
    assert.strictEqual(typeof pl.models.tabs.news, "string", "PL models.tabs.news should be a string");
    assert.strictEqual(typeof pl.models.tabs.models, "string", "PL models.tabs.models should be a string");

    // Test German
    assert.ok(de.models.tabs, "DE locale should have models.tabs");
    assert.strictEqual(typeof de.models.tabs.news, "string", "DE models.tabs.news should be a string");
    assert.strictEqual(typeof de.models.tabs.models, "string", "DE models.tabs.models should be a string");
  });

  it("has description keys for RECOMMENDED and CATALOG sections in all locales", () => {
    // Test English
    assert.ok(en.models.sections.recommended.description, "EN should have recommended.description");
    assert.ok(en.models.sections.catalog.description, "EN should have catalog.description");
    assert.strictEqual(typeof en.models.sections.recommended.description, "string");
    assert.strictEqual(typeof en.models.sections.catalog.description, "string");

    // Test Polish
    assert.ok(pl.models.sections.recommended.description, "PL should have recommended.description");
    assert.ok(pl.models.sections.catalog.description, "PL should have catalog.description");
    assert.strictEqual(typeof pl.models.sections.recommended.description, "string");
    assert.strictEqual(typeof pl.models.sections.catalog.description, "string");

    // Test German
    assert.ok(de.models.sections.recommended.description, "DE should have recommended.description");
    assert.ok(de.models.sections.catalog.description, "DE should have catalog.description");
    assert.strictEqual(typeof de.models.sections.recommended.description, "string");
    assert.strictEqual(typeof de.models.sections.catalog.description, "string");
  });

  it("RECOMMENDED and CATALOG descriptions are different", () => {
    // Ensure descriptions actually differentiate the sections
    assert.notStrictEqual(
      en.models.sections.recommended.description,
      en.models.sections.catalog.description,
      "EN: RECOMMENDED and CATALOG should have different descriptions"
    );
    assert.notStrictEqual(
      pl.models.sections.recommended.description,
      pl.models.sections.catalog.description,
      "PL: RECOMMENDED and CATALOG should have different descriptions"
    );
    assert.notStrictEqual(
      de.models.sections.recommended.description,
      de.models.sections.catalog.description,
      "DE: RECOMMENDED and CATALOG should have different descriptions"
    );
  });

  it("tab labels are properly translated", () => {
    // Verify translations are not just placeholders
    assert.strictEqual(en.models.tabs.news, "News");
    assert.strictEqual(en.models.tabs.models, "Models");

    assert.strictEqual(pl.models.tabs.news, "Nowości");
    assert.strictEqual(pl.models.tabs.models, "Modele");

    assert.strictEqual(de.models.tabs.news, "Neuigkeiten");
    assert.strictEqual(de.models.tabs.models, "Modelle");
  });
});
