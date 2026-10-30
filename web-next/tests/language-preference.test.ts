import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isLanguageCode, languageFromCookie, languageFromHeader } from "../lib/i18n/preferences";
import { isPriorityNavigation } from "../lib/navigation-prefetch";

describe("locale and navigation loading policy", () => {
  it("accepts only supported locale cookie values", () => {
    assert.equal(languageFromCookie("other=x; venom-language=de; theme=dark"), "de");
    assert.equal(languageFromCookie("venom-language=unknown"), null);
    assert.equal(languageFromCookie("not-venom-language=en"), null);
    assert.equal(isLanguageCode(undefined), false);
  });
  it("resolves supported regional headers and ignores explicitly rejected languages", () => {
    assert.equal(languageFromHeader("de-DE,de;q=0.9,en;q=0.8"), "de");
    assert.equal(languageFromHeader("fr-FR,en-US;q=0.8"), "en");
    assert.equal(languageFromHeader("de;q=0,en;q=0.7"), "en");
    assert.equal(languageFromHeader(null), "pl");
  });
  it("prefetches frequent conversation transitions and waits for intent elsewhere", () => {
    for (const href of ["/", "/chat", "/models", "/voice"]) assert.equal(isPriorityNavigation(href), true);
    for (const href of ["/academy", "/inspector", "/brain", "/workflow-control", "/rider", "/cooperation-lab"]) {
      assert.equal(isPriorityNavigation(href), false, href);
    }
  });
});
