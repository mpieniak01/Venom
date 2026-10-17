import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, it } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ConfigHome } from "../components/config/config-home";
import { IntegrationMatrix } from "../components/cockpit/integration-matrix";
import { resetIntegrationInventory } from "../lib/integration-inventory";

const originalFetch = globalThis.fetch;
const originalDisable = process.env.NEXT_PUBLIC_DISABLE_WS_EVENTS;
const writes: { path: string; body: unknown }[] = [];
const entry = { id: "core:openai", label: "OpenAI", scope: "external", kind: "api", location: "cloud", state: "configured", configuration: "configured", activation: "enabled", connectivity: "unknown", source: "configuration", reason_code: "not_probed", configuration_keys: ["OPENAI_API_KEY"], capabilities: [], access: [], resources: [], resource_count: null, active_resource_count: null };
function setup(search = "?tab=parameters") {
  window.history.replaceState({}, "", `/config${search}`);
  writes.length = 0;
  process.env.NEXT_PUBLIC_DISABLE_WS_EVENTS = "true";
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    if (init?.method === "POST") { writes.push({ path, body: JSON.parse(String(init.body ?? "{}")) }); return Response.json({ success: true, message: "saved", restart_required: [] }); }
    if (path.includes("api-map")) return Response.json({ schema_version: 2, integrations: [entry], internal_connections: [], external_connections: [] });
    if (path.includes("config/runtime")) return Response.json({ status: "success", config: { OPENAI_API_KEY: "********", LLM_MODEL_NAME: "baseline", ENABLE_IOT_BRIDGE: "false", RIDER_PI_HOST: "private-host", EXTRA_RUNTIME_KEY: "hiddenvalue" }, config_sources: {} });
    if (path.includes("runtime/status")) return Response.json({ status: "success", services: [] });
    if (path.includes("runtime/history")) return Response.json({ status: "success", history: [] });
    if (path.includes("storage")) return Response.json({ status: "success", items: [] });
    return Response.json({});
  };
}
afterEach(() => {
  cleanup(); resetIntegrationInventory(); globalThis.fetch = originalFetch;
  if (originalDisable === undefined) delete process.env.NEXT_PUBLIC_DISABLE_WS_EVENTS; else process.env.NEXT_PUBLIC_DISABLE_WS_EVENTS = originalDisable;
  window.history.replaceState({}, "", "/");
});

it("preserves a parameter draft across tabs, saves only changed keys, and resets locally", async () => {
  setup(); render(<ConfigHome />);
  const section = await screen.findByRole("button", { name: /Tryb AI Konfiguracja/ });
  fireEvent.click(section);
  const model = await screen.findByRole("textbox", { name: "LLM_MODEL_NAME" });
  fireEvent.change(model, { target: { value: "edited" } });
  fireEvent.click(screen.getByRole("tab", { name: "Integracje i węzły" }));
  await screen.findByRole("heading", { name: "OpenAI" });
  fireEvent.click(screen.getByRole("tab", { name: "Parametry" }));
  assert.equal((screen.getByRole("textbox", { name: "LLM_MODEL_NAME" }) as HTMLInputElement).value, "edited");
  assert.equal(writes.length, 0);
  fireEvent.click(screen.getByRole("button", { name: "Zapisz konfigurację" }));
  await waitFor(() => assert.equal(writes.length, 1));
  assert.deepEqual(writes[0], { path: "/api/v1/config/runtime", body: { updates: { LLM_MODEL_NAME: "edited" } } });
  await screen.findByText("saved");
  fireEvent.change(screen.getByRole("textbox", { name: "LLM_MODEL_NAME" }), { target: { value: "discard" } });
  fireEvent.click(screen.getByRole("button", { name: "Resetuj" }));
  assert.equal((screen.getByRole("textbox", { name: "LLM_MODEL_NAME" }) as HTMLInputElement).value, "edited");
});

it("restores integration filters from URL and handles removed IDs without fabricating state", async () => {
  setup("?tab=apiMap&integration=core%3Aremoved&resource=old-device&scope=external&visibility=all"); render(<ConfigHome />);
  await screen.findByText(/Wybrana integracja nie jest już dostępna/);
  assert.equal((screen.getByLabelText("Widoczność") as HTMLSelectElement).value, "all");
  assert.equal((screen.getByLabelText("Typ") as HTMLSelectElement).value, "external");
  fireEvent.click(screen.getByRole("button", { name: /OpenAI/ }));
  assert.equal(new URLSearchParams(window.location.search).get("integration"), "core:openai");
  assert.equal(new URLSearchParams(window.location.search).get("resource"), null);
  const link = screen.getByRole("link", { name: "OPENAI_API_KEY" });
  assert.ok(link.getAttribute("href")?.includes("parameter=OPENAI_API_KEY"));
  assert.equal(link.getAttribute("href")?.includes("********"), false);
  act(() => { window.history.replaceState({}, "", "/config?tab=integrations&integration=core%3Aopenai&scope=internal"); window.dispatchEvent(new Event("popstate")); });
  await screen.findByText(/Wybrana integracja jest poza bieżącymi filtrami/);
  assert.ok(screen.getByRole("heading", { name: "OpenAI" }));
});

it("searches parameter names without exposing values and explains the independent IoT bridge", async () => {
  setup(); render(<ConfigHome />);
  await screen.findByRole("button", { name: /IoT Bridge/ });
  fireEvent.click(screen.getByRole("button", { name: /IoT Bridge/ }));
  assert.ok(screen.getByText(/Starszy mostek IoT używa RIDER_PI_/));
  const search = screen.getByRole("searchbox", { name: "Szukaj parametrów" });
  fireEvent.change(search, { target: { value: "hiddenvalue" } });
  assert.ok(screen.getByText("Brak parametrów dla wybranego filtra."));
  fireEvent.change(search, { target: { value: "EXTRA_RUNTIME_KEY" } });
  assert.ok(screen.getByLabelText("EXTRA_RUNTIME_KEY"));
  assert.equal(window.location.search.includes("hiddenvalue"), false);
  assert.equal(screen.getByLabelText("EXTRA_RUNTIME_KEY").getAttribute("type"), "password");
});

it("supports keyboard tab navigation and a safe unknown-tab fallback", async () => {
  setup("?tab=unknown"); render(<ConfigHome />);
  await screen.findByText("Nieznana zakładka. Wyświetlono Usługi.");
  const services = screen.getByRole("tab", { name: "Usługi" });
  fireEvent.keyDown(services, { key: "ArrowRight" });
  await screen.findByRole("button", { name: /Tryb AI Konfiguracja/ });
  assert.equal(screen.getByRole("tab", { name: "Parametry" }).getAttribute("aria-selected"), "true");
  fireEvent.keyDown(screen.getByRole("tab", { name: "Parametry" }), { key: "End" });
  assert.equal(screen.getByRole("tab", { name: "Uprawnienia" }).getAttribute("aria-selected"), "true");
  assert.equal(writes.length, 0);
});

it("uses inventory identities in cockpit instead of guessing integrations from service names", async () => {
  setup(); render(<IntegrationMatrix services={[{ name: "mysterious daemon", status: "online" }]} events={[]} />);
  const open = await screen.findByRole("link", { name: /OpenAI/ });
  assert.ok(open.getAttribute("href")?.includes("integration=core%3Aopenai"));
  assert.equal(screen.queryByText("mysterious daemon"), null);
  assert.equal(writes.length, 0);
});


it("passes fresh history data so framework URL listeners observe selection changes", async () => {
  setup("?tab=integrations&visibility=all");
  const push = window.history.pushState.bind(window.history);
  const received: unknown[] = [];
  window.history.replaceState({ __NA: true, tree: "existing framework state" }, "", window.location.href);
  window.history.pushState = (data, title, url) => { received.push(data); push(data, title, url); };
  try {
    render(<ConfigHome />);
    fireEvent.click(await screen.findByRole("button", { name: /OpenAI/ }));
    assert.deepEqual(received, [null]);
    assert.equal(new URLSearchParams(window.location.search).get("integration"), "core:openai");
  } finally {
    window.history.pushState = push;
  }
});

it("does not carry integration search into parameters and restores connection filters from URL", async () => {
  setup("?tab=integrations&integration=core%3Aopenai&q=OpenAI&source=cloud&status=unknown&protocol=https"); render(<ConfigHome />);
  await screen.findByRole("heading", { name: "OpenAI" });
  assert.equal((screen.getByLabelText("Źródło") as HTMLSelectElement).value, "cloud");
  assert.equal((screen.getByLabelText("Status") as HTMLSelectElement).value, "unknown");
  assert.equal((screen.getByLabelText("Protokół") as HTMLSelectElement).value, "https");
  fireEvent.click(screen.getByRole("tab", { name: "Parametry" }));
  assert.equal(new URLSearchParams(window.location.search).has("q"), false);
  await screen.findByRole("button", { name: /Tryb AI Konfiguracja/ });
  assert.equal((screen.getByRole("searchbox", { name: "Szukaj parametrów" }) as HTMLInputElement).value, "");
});
