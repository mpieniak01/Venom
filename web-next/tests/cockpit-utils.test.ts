import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { normalizeAssistantDisplayText } from "../components/cockpit/cockpit-utils";

describe("normalizeAssistantDisplayText", () => {
  it("cleans onnx token artifacts and restores bullet formatting", () => {
    const input =
      '""Kolo" może oznaczać kilka rzeczy! Potrzebuję więcej kontekstu, żeby odpowiedzieć precyzyjnie. Oto kilka możliwych znaczeń:\n\n*▁▁▁Rower: Najbardziej popularne znaczenie - pojazd z kołami. *▁▁▁Figurka do gry: Mała figurka. *▁▁▁Kółko: Mały okrąg.';

    const output = normalizeAssistantDisplayText(input);

    assert.ok(!output.includes("▁"));
    assert.ok(output.startsWith('"Kolo" może oznaczać kilka rzeczy!'));
    assert.ok(output.includes("\n* Rower:"));
    assert.ok(output.includes("\n* Figurka do gry:"));
    assert.ok(output.includes("\n* Kółko:"));
  });

  it("keeps normal markdown emphasis untouched", () => {
    const input = "To jest *ważne* i już poprawnie sformatowane.";
    const output = normalizeAssistantDisplayText(input);
    assert.equal(output, input);
  });
});
