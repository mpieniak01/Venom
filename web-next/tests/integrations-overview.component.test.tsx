import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, it } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { resetIntegrationInventory } from "../lib/integration-inventory";
import { ApiMap } from "../components/config/api-map";

const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); resetIntegrationInventory(); globalThis.fetch = originalFetch; });

function entry(id: string, label: string, extra: Record<string, unknown> = {}) {
  return { id, label, scope: "external", kind: "infrastructure", location: "cloud", state: "configured", configuration: "configured", activation: "enabled", connectivity: "unknown", source: "configuration", reason_code: "not_probed", capabilities: [], configuration_keys: [], access: [], resources: [], resources_complete: false, resource_count: null, active_resource_count: null, ...extra };
}
function payload(entries: ReturnType<typeof entry>[]) {
  return { schema_version: 2, integrations: entries, internal_connections: [], external_connections: [] };
}

it("shows Vast capabilities without pretending its resources or API health are known", async () => {
  const requests: string[] = [];
  globalThis.fetch = async (input) => {
    requests.push(String(input));
    return new Response(JSON.stringify(payload([entry("core:vast", "Vast.ai", { access: ["cli"] })])));
  };
  render(<ApiMap />);
  await screen.findByRole("heading", { name: "Vast.ai" });
  assert.ok(screen.getByText("Obsługa przez CLI"));
  assert.ok(screen.getByText(/Lista nie potwierdza pełnej liczby/));
  assert.equal(screen.queryByText("Połączono"), null);
  assert.deepEqual(requests, ["/api/v1/system/api-map"]);
});

it("preserves selected integration across reorder and keeps observations on refresh failure", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    if (calls > 2) return new Response("unavailable", { status: 503 });
    const entries = [entry("core:github", "GitHub"), entry("core:vast", "Vast.ai")];
    return new Response(JSON.stringify(payload(calls === 2 ? entries.reverse() : entries)));
  };
  render(<ApiMap />);
  const vast = await screen.findByRole("button", { name: /Vast.ai/ });
  fireEvent.click(vast);
  fireEvent.click(screen.getByRole("button", { name: "Odśwież mapę" }));
  await waitFor(() => assert.equal(calls, 2));
  await waitFor(() => assert.equal(screen.getByRole("button", { name: /Vast.ai/ }).getAttribute("aria-pressed"), "true"));
  await waitFor(() => assert.ok(screen.getByRole("button", { name: "Odśwież mapę" })));
  fireEvent.click(screen.getByRole("button", { name: "Odśwież mapę" }));
  await screen.findByRole("alert");
  assert.ok(screen.getByRole("heading", { name: "Vast.ai" }));
});

it("keeps an unavailable optional module local and shows unconfigured integrations in the catalog", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify(payload([
    entry("module:missing", "Optional module", { scope: "internal", kind: "module", state: "unavailable", activation: "unavailable", reason_code: "manifest_unavailable" }),
    entry("core:vast", "Vast.ai", { configuration: "unconfigured", state: "unconfigured" }),
  ])));
  render(<ApiMap />);
  await screen.findByRole("heading", { name: "Optional module" });
  assert.equal(screen.queryByRole("button", { name: /Vast.ai/ }), null);
  fireEvent.change(screen.getByLabelText("Widoczność"), { target: { value: "all" } });
  assert.ok(screen.getByRole("button", { name: /Vast.ai/ }));
  assert.equal(screen.queryByRole("alert"), null);
});


it("checks Vast only after an explicit click and then refreshes inventory", async () => {
  const methods: string[] = [];
  globalThis.fetch = async (_input, init) => {
    methods.push(init?.method ?? "GET");
    return new Response(JSON.stringify(payload([entry("core:vast", "Vast.ai", { can_probe: true })])));
  };
  render(<ApiMap />);
  const button = await screen.findByRole("button", { name: "Sprawdź API i instancje" });
  assert.deepEqual(methods, ["GET"]);
  fireEvent.click(button);
  await waitFor(() => assert.deepEqual(methods, ["GET", "POST", "GET"]));
});


it("opens configuration-backed integrations in the existing parameter editor", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify(payload([entry("core:openai", "OpenAI API", { panel_path: "/config", configuration_keys: ["OPENAI_API_KEY"] })])));
  render(<ApiMap />);
  const panel = await screen.findByRole("link", { name: "Otwórz panel" });
  assert.ok(panel.getAttribute("href")?.includes("tab=parameters"));
  assert.ok(panel.getAttribute("href")?.includes("parameter=OPENAI_API_KEY"));
});

const mapConnection = { source_component: "Model Router", target_component: "OpenAI API", protocol: "https", direction: "outbound", auth_type: "api_key", source_type: "cloud", status: "unknown", description: "Existing provider description", is_critical: true, methods: ["POST /v1/chat/completions"] };

it("preserves connection descriptions, criticality, authentication, direction and visible methods alongside inventory", async () => {
  globalThis.fetch = async () => Response.json({ ...payload([entry("core:openai", "OpenAI API")]), external_connections: [mapConnection] });
  render(<ApiMap />);
  await screen.findByRole("heading", { name: "OpenAI API" });
  assert.equal(screen.getAllByText("Existing provider description").length, 2);
  assert.ok(screen.getByText("POST /v1/chat/completions"));
  assert.ok(screen.getByText("Klucz API"));
  assert.ok(screen.getByText("Wychodzące"));
  assert.ok(screen.getByText("Kierunek"));
  assert.ok(screen.getByText("Krytyczne"));
  assert.ok(screen.getByLabelText("Krytyczne"));
  assert.ok(screen.getByText("Konfiguracja", { selector: "dt" }));
});

it("restores source, connectivity and protocol filters without treating configured as healthy", async () => {
  globalThis.fetch = async () => Response.json({ ...payload([
    entry("core:openai", "OpenAI API"), entry("core:local-runtime", "Local LLM", { scope: "internal", location: "local", connectivity: "ok", state: "connected" }),
  ]), internal_connections: [{ ...mapConnection, target_component: "Local LLM", protocol: "http", source_type: "local", status: "ok" }], external_connections: [mapConnection] });
  render(<ApiMap />);
  await screen.findByRole("button", { name: /OpenAI API/ });
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "ok" } });
  assert.equal(screen.queryByRole("button", { name: /OpenAI API/ }), null);
  assert.ok(screen.getByRole("button", { name: /Local LLM/ }));
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "all" } });
  fireEvent.change(screen.getByLabelText("Źródło"), { target: { value: "cloud" } });
  assert.equal(screen.queryByRole("button", { name: /Local LLM/ }), null);
  fireEvent.change(screen.getByLabelText("Protokół"), { target: { value: "http" } });
  assert.ok(screen.getByText("Brak wyników"));
  fireEvent.change(screen.getByLabelText("Protokół"), { target: { value: "https" } });
  assert.ok(screen.getByRole("button", { name: /OpenAI API/ }));
});


it("searches descriptions and applies protocol filters to details while preserving any critical connection", async () => {
  globalThis.fetch = async () => Response.json({ ...payload([entry("core:openai", "OpenAI API")]), external_connections: [
    { ...mapConnection, protocol: "http", description: "Primary visible description", is_critical: false, methods: ["POST /http-only"] },
    { ...mapConnection, protocol: "https", description: "Secondary visible description", is_critical: true, methods: ["POST /https-only"] },
  ] });
  render(<ApiMap />);
  await screen.findByRole("heading", { name: "OpenAI API" });
  assert.ok(screen.getByLabelText("Krytyczne"));
  const search = screen.getByRole("searchbox", { name: "Szukaj integracji" });
  fireEvent.change(search, { target: { value: "Primary visible description" } });
  assert.ok(screen.getByRole("button", { name: /OpenAI API/ }));
  fireEvent.change(search, { target: { value: "Secondary visible description" } });
  assert.ok(screen.getByRole("button", { name: /OpenAI API/ }));
  fireEvent.change(search, { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("Protokół"), { target: { value: "http" } });
  assert.ok(screen.getByText("POST /http-only"));
  assert.equal(screen.queryByText("POST /https-only"), null);
  assert.ok(screen.getByLabelText("Krytyczne"));
  fireEvent.change(screen.getByLabelText("Protokół"), { target: { value: "https" } });
  assert.ok(screen.getByText("POST /https-only"));
  assert.equal(screen.queryByText("POST /http-only"), null);
  assert.ok(screen.getByRole("button", { name: /OpenAI API.*HTTPS/ }));
});
