import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { VoicePipelinePicker } from "../components/voice/voice-pipeline-picker";
import { LanguageProvider } from "../lib/i18n";

const originalFetch = globalThis.fetch;
const gemma = "gemma4-e4b-ab-qlora85:q8_0";
const omni = "lfm3-omni:2b";
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  window.localStorage.clear();
});

test("switches through the shared runtime control and restores the previous Gemma variant", async () => {
  let active = gemma;
  const changes: string[] = [];
  const applied: string[] = [];
  globalThis.fetch = async (input, init) => {
    if (String(input).includes("/pipelines?")) {
      return Response.json({ active_model: active, gemma_models: ["gemma4:e4b", gemma], omni_model: omni });
    }
    assert.match(String(input), /\/llm-servers\/active$/);
    const body = JSON.parse(String(init?.body));
    assert.equal(body.server_name, "ollama");
    active = body.model;
    changes.push(active);
    return Response.json({ active_server: "ollama", active_model: active });
  };
  const first = render(<LanguageProvider><VoicePipelinePicker surface="chat2" onApplied={model => applied.push(model)} /></LanguageProvider>);
  const gemmaButton = screen.getByRole("button", { name: /Gemma \+ / });
  const omniButton = screen.getByRole("button", { name: /LFM3-Omni/ });
  await waitFor(() => assert.equal(gemmaButton.getAttribute("aria-pressed"), "true"));
  assert.ok(screen.getByText("Active model: " + gemma));
  assert.deepEqual(changes, []);
  fireEvent.click(omniButton);
  await waitFor(() => assert.equal(omniButton.getAttribute("aria-pressed"), "true"));
  assert.ok(screen.getByText("Active model: " + omni));
  first.unmount();

  render(<LanguageProvider><VoicePipelinePicker surface="voice" onApplied={model => applied.push(model)} /></LanguageProvider>);
  const back = screen.getByRole("button", { name: /Gemma \+ / });
  await waitFor(() => assert.equal((back as HTMLButtonElement).disabled, false));
  fireEvent.click(back);
  await waitFor(() => assert.deepEqual(applied, [omni, gemma]));
  assert.deepEqual(changes, [omni, gemma]);
});

test("keeps Omni disabled if the local runtime does not provide both audio capabilities", async () => {
  globalThis.fetch = async () => Response.json({ active_model: gemma, gemma_models: [gemma], omni_model: null });
  render(<LanguageProvider><VoicePipelinePicker surface="voice" /></LanguageProvider>);
  await waitFor(() => assert.equal(screen.getByRole("button", { name: /Gemma \+ / }).getAttribute("aria-pressed"), "true"));
  assert.equal((screen.getByRole("button", { name: /LFM3-Omni/ }) as HTMLButtonElement).disabled, true);
});

for (const surface of ["chat2", "voice"] as const) {
  test(`${surface} does not confirm a switch if Ollama reports another model`, async () => {
    const applied: string[] = [];
    globalThis.fetch = async input => {
      if (String(input).includes("/pipelines?")) {
        return Response.json({ active_model: gemma, gemma_models: [gemma], omni_model: omni });
      }
      assert.match(String(input), /\/llm-servers\/active$/);
      return Response.json({ active_server: "ollama", active_model: gemma });
    };
    render(<LanguageProvider><VoicePipelinePicker surface={surface} onApplied={model => applied.push(model)} /></LanguageProvider>);
    const button = screen.getByRole("button", { name: /LFM3-Omni/ });
    await waitFor(() => assert.equal((button as HTMLButtonElement).disabled, false));
    fireEvent.click(button);
    await screen.findByRole("alert");
    assert.equal(button.getAttribute("aria-pressed"), "false");
    assert.ok(screen.getByText("Active model: " + gemma));
    assert.deepEqual(applied, []);
  });
}

test("offers only advertised native Omni modes and lets the operator return to the existing pipeline", async () => {
  const selections: Array<string | null> = [];
  let modes: string[] = ["interleaved"];
  globalThis.fetch = async input => {
    assert.match(String(input), /\/pipelines\?/);
    return Response.json({
      active_model: omni, gemma_models: [gemma], omni_model: omni, native_dialogue_modes: modes,
    });
  };
  const choose = (mode: string | null) => selections.push(mode);
  const view = render(<LanguageProvider><VoicePipelinePicker surface="voice" onGenerationModeChange={choose} /></LanguageProvider>);
  const picker = await screen.findByRole<HTMLSelectElement>("combobox");
  assert.equal(picker.value, "");
  assert.deepEqual(Array.from(picker.options, option => option.value), ["", "interleaved"]);
  fireEvent.change(picker, { target: { value: "interleaved" } });
  assert.deepEqual(selections, ["interleaved"]);

  modes = [];
  view.rerender(<LanguageProvider><VoicePipelinePicker surface="voice" refreshKey={1}
    generationMode="interleaved" onGenerationModeChange={choose} /></LanguageProvider>);
  const warning = await screen.findByRole("alert");
  assert.match(warning.textContent ?? "", /native Omni mode is unavailable|tryb natywny Omni jest niedostępny/);
  assert.equal(picker.value, "interleaved");
  fireEvent.change(picker, { target: { value: "" } });
  assert.deepEqual(selections, ["interleaved", null]);
});
