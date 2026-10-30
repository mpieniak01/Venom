import "./component-test-setup";
import React from "react";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { VastEnvironmentsSection } from "../components/models/vast-environments-section";
import { formatVastUsd } from "../lib/vast-price";
import { VastAccountBillingPanel } from "../components/models/vast-account-billing";
import { VastEnvironmentRow } from "../components/models/vast-environment-row";
import { useVastEnvironments, VAST_POLL_INTERVAL, type VastEnvironment } from "../components/models/hooks/use-vast-environments";
import { en } from "../lib/i18n/locales/en";
import { pl } from "../lib/i18n/locales/pl";
import { de } from "../lib/i18n/locales/de";

const base = "/api/v1/vast/environments";
const t = (key: string) => key.split(".").reduce<unknown>((value, part) => (value as Record<string, unknown>)[part], en) as string;
const row = (extra: Partial<VastEnvironment> = {}): VastEnvironment => ({ plan_id: "a".repeat(32), model: "model:default", state: "planned", phase: "planned", instance_id: null, hourly_usd: "0.20", total_usd: "0.15", duration_minutes: 30, expires_at: "2099-10-29T23:00:00Z", connected: false, error: null, billing_possible: false, ...extra });
const status = (environments: VastEnvironment[] = []) => ({ configured: true, enabled: true, model: "model:default", duration_minutes: 30, reason: null, environments });
const offer = { offer_id: 123, gpu_name: "Test GPU", country: "PL", gpu_ram_mb: 24000, hourly_usd: "0.20", total_usd: "0.15", status: "eligible", reasons: [] };
const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });

describe("VAST environment management", () => {
  it("requires an offer, reviewed plan and explicit paid-order confirmation", async () => {
    const posts: { path: string; body: unknown }[] = [];
    let environments: VastEnvironment[] = [];
    globalThis.fetch = async (input, init) => {
      const path = String(input);
      if (init?.method !== "POST") return Response.json(status(environments));
      posts.push({ path, body: JSON.parse(String(init.body)) });
      if (path.endsWith("/search")) return Response.json({ offers: [offer], model: "model:default", duration_minutes: 30 });
      if (path.endsWith("/plans")) { environments = [row()]; return Response.json(row()); }
      environments = [row({ phase: "provisioning", state: "running", instance_id: 77, billing_possible: true })];
      return Response.json(environments[0], { status: 202 });
    };
    render(<VastEnvironmentsSection t={t} />);
    await waitFor(() => assert.equal((screen.getByRole("button", { name: "Find environments" }) as HTMLButtonElement).disabled, false));
    assert.equal(posts.length, 0);
    fireEvent.click(screen.getByRole("button", { name: "Find environments" }));
    await waitFor(() => assert.ok(screen.getByRole("button", { name: "Choose: 123" })));
    fireEvent.click(screen.getByRole("button", { name: "Choose: 123" }));
    fireEvent.click(screen.getByRole("button", { name: "Review order" }));
    await waitFor(() => assert.ok(screen.getByRole("button", { name: "Order and install model" })));
    const order = screen.getByRole("button", { name: "Order and install model" }) as HTMLButtonElement;
    assert.equal(order.disabled, true);
    fireEvent.click(order);
    assert.equal(posts.some(post => post.path.endsWith("/order")), false);
    fireEvent.click(screen.getByLabelText(/Allow the first SSH host key/));
    fireEvent.click(screen.getByLabelText(/I confirm this paid rental/));
    fireEvent.click(order);
    await waitFor(() => assert.ok(screen.getByText("Installing model")));
    assert.deepEqual(posts.map(post => post.path), [base + "/search", base + "/plans", base + "/" + "a".repeat(32) + "/order"]);
    assert.deepEqual(posts[2].body, { confirmed: true, accept_new_host_key: true });
    assert.equal(posts.some(post => /zero|activate|chat/.test(post.path)), false);
  });

  it("invalidates the reviewed plan when the budget or duration changes", async () => {
    let plans = 0;
    globalThis.fetch = async (input, init) => {
      const path = String(input);
      if (init?.method !== "POST") return Response.json(status());
      if (path.endsWith("/search")) return Response.json({ offers: [offer] });
      plans++;
      return Response.json(row());
    };
    render(<VastEnvironmentsSection t={t} />);
    await waitFor(() => assert.equal((screen.getByRole("button", { name: "Find environments" }) as HTMLButtonElement).disabled, false));
    fireEvent.click(screen.getByRole("button", { name: "Find environments" }));
    await waitFor(() => assert.ok(screen.getByRole("button", { name: "Choose: 123" })));
    fireEvent.click(screen.getByRole("button", { name: "Choose: 123" }));
    fireEvent.click(screen.getByRole("button", { name: "Review order" }));
    await waitFor(() => assert.ok(screen.getByRole("button", { name: "Order and install model" })));
    fireEvent.click(screen.getByLabelText(/I confirm this paid rental/));
    fireEvent.change(screen.getByLabelText("Maximum USD / hour"), { target: { value: "0.30" } });
    assert.equal(screen.queryByRole("button", { name: "Order and install model" }) === null, true);
    fireEvent.click(screen.getByRole("button", { name: "Review order" }));
    await waitFor(() => assert.ok(screen.getByRole("button", { name: "Order and install model" })));
    assert.equal((screen.getByRole("button", { name: "Order and install model" }) as HTMLButtonElement).disabled, true);
    fireEvent.change(screen.getByLabelText("Estimated use (minutes)"), { target: { value: "60" } });
    assert.equal(screen.queryByRole("button", { name: "Order and install model" }) === null, true);
    assert.equal(screen.queryByRole("button", { name: "Choose: 123" }) === null, true);
    assert.equal(plans, 2);
  });

  it("polls GET only and publishes readiness without a repeated order or generation", async context => {
    context.mock.timers.enable({ apis: ["setInterval"] });
    const calls: { path: string; method: string }[] = [];
    let ready = false; let changed = 0;
    globalThis.fetch = async (input, init) => {
      calls.push({ path: String(input), method: init?.method ?? "GET" });
      return Response.json(status([row(ready ? { phase: "ready", connected: true, instance_id: 77 } : { phase: "provisioning", instance_id: 77 })]));
    };
    const { result } = renderHook(() => useVastEnvironments(async () => { changed++; }));
    await act(async () => {});
    assert.equal(result.current.loading, false);
    ready = true;
    await act(async () => { context.mock.timers.tick(VAST_POLL_INTERVAL); });
    assert.equal(result.current.state?.environments[0].connected, true);
    assert.equal(changed, 1);
    assert.ok(calls.length >= 2);
    assert.ok(calls.every(call => call.path === base && call.method === "GET"));
    await act(async () => { context.mock.timers.tick(VAST_POLL_INTERVAL * 3); });
    assert.equal(changed, 1);
    context.mock.timers.reset();
  });

  it("treats connected plan order as irrelevant and refreshes chat only on membership changes", async () => {
    const first = row({ plan_id: "b".repeat(32), phase: "ready", connected: true });
    const second = row({ plan_id: "a".repeat(32), phase: "ready", connected: true });
    let environments = [first, second];
    let changed = 0;
    globalThis.fetch = async () => Response.json(status(environments));
    const { result } = renderHook(() => useVastEnvironments(async () => { changed++; }));
    await waitFor(() => assert.equal(result.current.loading, false));
    assert.equal(changed, 1);
    environments = [second, first];
    await act(async () => { await result.current.refresh(); });
    assert.equal(changed, 1);
    environments = [second];
    await act(async () => { await result.current.refresh(); });
    assert.equal(changed, 2);
  });

  it("requires separate confirmation for stop and permanent release", () => {
    const actions: string[] = [];
    render(<VastEnvironmentRow row={row({ phase: "ready", instance_id: 77, connected: true, billing_possible: true })} pending={false} action={async (_id, action) => { actions.push(action); }} t={t} />);
    assert.ok(screen.getByText(/Ready for chat: choose VAST/));
    fireEvent.click(screen.getByRole("button", { name: "Stop environment" }));
    assert.equal(actions.length, 0);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    assert.equal(actions.length, 0);
    fireEvent.click(screen.getByRole("button", { name: "Release environment" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm release" }));
    fireEvent.click(screen.getByRole("button", { name: "Stop environment" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm stop" }));
    assert.deepEqual(actions, ["destroy", "stop"]);
  });

  it("does not search or rent when the profile or API is unavailable", async () => {
    const posts: string[] = [];
    globalThis.fetch = async (input, init) => { if (init?.method === "POST") posts.push(String(input)); return Response.json({ ...status(), enabled: false, configured: false, model: null }); };
    render(<VastEnvironmentsSection t={t} />);
    await waitFor(() => assert.ok(screen.getByText(/Enable the VAST API/)));
    const search = screen.getByRole("button", { name: "Find environments" }) as HTMLButtonElement;
    assert.equal(search.disabled, true);
    fireEvent.click(search);
    assert.deepEqual(posts, []);
  });

  it("surfaces a rejected order while retaining the provider result", async () => {
    globalThis.fetch = async (_input, init) => init?.method === "POST" ? Response.json({ detail: "vast.price_changed" }, { status: 409 }) : Response.json(status([row()]));
    const { result } = renderHook(() => useVastEnvironments());
    await waitFor(() => assert.equal(result.current.loading, false));
    await act(async () => { await result.current.action("a".repeat(32), "order"); });
    assert.equal(result.current.error, "vast.price_changed");
    assert.equal(result.current.state?.environments[0].phase, "planned");
    assert.equal(result.current.pending, false);
  });

  it("deduplicates simultaneous paid-order requests before rerender", async () => {
    let posts = 0; let finish: (value: Response) => void = () => {};
    globalThis.fetch = async (_input, init) => {
      if (init?.method === "POST") { posts++; return new Promise<Response>(resolve => { finish = resolve; }); }
      return Response.json(status());
    };
    const { result } = renderHook(() => useVastEnvironments());
    await waitFor(() => assert.equal(result.current.loading, false));
    let first: Promise<void>;
    act(() => { first = result.current.action("a".repeat(32), "order"); void result.current.action("a".repeat(32), "order"); });
    assert.equal(posts, 1);
    await act(async () => { finish(Response.json(row({ phase: "queued" }))); await first; });
    assert.equal(result.current.pending, false);
  });

  it("uses matching VAST translations in all supported locales", () => {
    for (const locale of [pl, de]) {
      assert.deepEqual(Object.keys(locale.models.vast).sort(), Object.keys(en.models.vast).sort());
      assert.deepEqual(Object.keys(locale.models.vast.phases).sort(), Object.keys(en.models.vast.phases).sort());
      assert.deepEqual(Object.keys(locale.models.vast.historyStates).sort(), Object.keys(en.models.vast.historyStates).sort());
    }
  });
});

it("shows old CLI attempts as read-only history without making them live environments", async () => {
  const calls: string[] = [];
  const past = row({ state: "failed", phase: "failed", instance_id: 77, error: "vast.ssh_failed" });
  globalThis.fetch = async (_input, init) => {
    calls.push(init?.method ?? "GET");
    return Response.json({ ...status(), history: [past] });
  };
  render(<VastEnvironmentsSection t={t} />);
  const history = await screen.findByRole("region", { name: "Launch attempt history" });
  await waitFor(() => assert.ok(within(history).getByText("Failed")));
  assert.ok(within(history).getByText(past.plan_id));
  assert.ok(within(history).getByText("77"));
  assert.ok(within(history).getByText("vast.ssh_failed"));
  assert.equal(within(history).queryAllByRole("button").length, 0);
  assert.ok(screen.getByText(t("models.vast.none")));
  assert.deepEqual(calls, ["GET"]);
});


it("refreshes the chat catalog when a CLI history plan connects or disconnects", async () => {
  let connected = false;
  let changed = 0;
  globalThis.fetch = async () => Response.json({
    ...status(), history: [row({ connected })],
  });
  const { result } = renderHook(() => useVastEnvironments(async () => { changed++; }));
  await waitFor(() => assert.equal(result.current.loading, false));
  assert.equal(changed, 0);
  connected = true;
  await act(async () => { await result.current.refresh(); });
  assert.equal(changed, 1);
  await act(async () => { await result.current.refresh(); });
  assert.equal(changed, 1);
  connected = false;
  await act(async () => { await result.current.refresh(); });
  assert.equal(changed, 2);
});

it("preserves CLI outcomes and shows compact billing statuses without instruction text", async () => {
  const calls: string[] = [];
  globalThis.fetch = async (_input, init) => {
    calls.push(init?.method ?? "GET");
    return Response.json({ ...status(), history: [
      row({ state: "created", connected: true, billing_possible: true }),
      row({ plan_id: "b".repeat(32), state: "outcome_unknown", billing_possible: true }),
      row({ plan_id: "c".repeat(32), state: "provider_pending", billing_possible: false }),
    ] });
  };
  render(<VastEnvironmentsSection t={t} />);
  const history = await screen.findByRole("region", { name: "Launch attempt history" });
  await waitFor(() => assert.ok(within(history).getByText("Instance created")));
  assert.ok(within(history).getByText("Order outcome unknown"));
  assert.ok(within(history).getByText("provider_pending"));
  assert.ok(within(history).getByText("Connected"));
  assert.equal(within(history).getAllByText(t("models.vast.billingStates.unverified")).length, 3);
  assert.equal(within(history).queryByText(t("models.vast.billingWarning")), null);
  assert.equal(within(history).queryByText(t("models.vast.historyBillingHint")), null);
  assert.equal(within(history).queryAllByRole("button").length, 0);
  assert.deepEqual(calls, ["GET"]);
});


it("rounds VAST quotes to four places in offers, order review and managed environments", async () => {
  const precise = { hourly_usd: "0.123456789", total_usd: "0.987654321" };
  const managed = row({ ...precise, phase: "ready", instance_id: 77 });
  const requests: string[] = [];
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    if (init?.method !== "POST") return Response.json(status([managed]));
    requests.push(path);
    return Response.json(path.endsWith("/search") ? { offers: [{ ...offer, ...precise }] } : row(precise));
  };
  render(<VastEnvironmentsSection t={t} />);
  await waitFor(() => assert.ok(screen.getByText("USD / hour: 0.1235")));
  assert.ok(screen.getByText("Estimated USD: 0.9877"));
  fireEvent.click(screen.getByRole("button", { name: "Find environments" }));
  await waitFor(() => assert.ok(screen.getByRole("button", { name: "Choose: 123" })));
  assert.ok(screen.getByRole("cell", { name: "0.1235" }));
  assert.ok(screen.getByRole("cell", { name: "0.9877" }));
  const offerRow = screen.getByRole("button", { name: "Choose: 123" }).closest("tr")!;
  const offerSummary = within(offerRow).getByText("Exact USD amounts");
  fireEvent.click(offerSummary);
  assert.equal(offerSummary.closest("details")!.open, true);
  assert.ok(within(offerRow).getByText(precise.hourly_usd));
  assert.ok(within(offerRow).getByText(precise.total_usd));
  fireEvent.click(screen.getByRole("button", { name: "Choose: 123" }));
  fireEvent.click(screen.getByRole("button", { name: "Review order" }));
  await waitFor(() => assert.ok(screen.getByText("USD / hour: 0.1235 · Estimated USD: 0.9877 · Estimated use (minutes): 30")));
  const review = screen.getByRole("button", { name: "Order and install model" }).parentElement!;
  const reviewSummary = within(review).getByText("Exact USD amounts");
  fireEvent.click(reviewSummary);
  assert.equal(reviewSummary.closest("details")!.open, true);
  assert.ok(within(review).getByText(precise.hourly_usd));
  assert.ok(within(review).getByText(precise.total_usd));
  assert.deepEqual(requests, [base + "/search", base + "/plans"]);
});

it("formats zero and missing or invalid VAST amounts distinctly", () => {
  assert.equal(formatVastUsd("0", "Unknown"), "0.0000");
  assert.equal(formatVastUsd("9.87656", "Unknown"), "9.8766");
  assert.equal(formatVastUsd("0.00001", "Unknown"), "0.0000");
  for (const amount of [null, undefined, "", " ", "NaN", "Infinity", "-1", "invalid"]) {
    assert.equal(formatVastUsd(amount, "Unknown"), "Unknown");
  }
});


it("shows recorded VAST charges including zero and uses statuses for missing billing", async () => {
  globalThis.fetch = async () => Response.json({ ...status(), history: [
    row({ billing_status: "reported", billed_usd: "0" }),
    row({ plan_id: "b".repeat(32), billing_status: "reported", billed_usd: "0.123456789" }),
    row({ plan_id: "c".repeat(32), billing_status: "unavailable", billed_usd: null }),
    row({ plan_id: "d".repeat(32), billing_status: "not_applicable", billed_usd: null }),
    row({ plan_id: "e".repeat(32), billing_status: "reported", billed_usd: "NaN" }),
  ] });
  render(<VastEnvironmentsSection t={t} />);
  const history = await screen.findByRole("region", { name: "Launch attempt history" });
  await waitFor(() => assert.ok(within(history).getByText("0.0000 USD")));
  assert.ok(within(history).getByText("0.1235 USD"));
  assert.equal(within(history).getAllByText("Reported").length, 2);
  assert.ok(within(history).getByText("Unavailable"));
  assert.ok(within(history).getByText("Not applicable"));
  assert.ok(within(history).getByText("Unverified"));
  assert.equal(within(history).queryByText(/may still incur charges/), null);
});


describe("VAST account billing", () => {
  const billing = {
    configured: true, status: "ready" as const, error: null, account_error: null,
    credit_usd: "8.9195945862", balance_usd: "0", account_observed_at: "2026-10-30T12:00:00Z",
    observed_at: "2026-10-30T12:00:00Z", from_utc: "2026-09-30", to_utc: "2026-10-30",
    total_usd: "1.080", managed_usd: "0.546", other_usd: "0.534",
    covered_days: 31, expected_days: 31, complete: true,
  };
  it("shows credit, period and provider costs with explicit reconciliation", async () => {
    const operations: boolean[] = [];
    render(<VastAccountBillingPanel billing={billing} pending={false} enabled sync={async (reconcile = false) => { operations.push(reconcile); }} t={t} />);
    assert.ok(screen.getByText("8.9196 USD"));
    assert.ok(screen.getByText("1.0800 USD"));
    assert.ok(screen.getByText(/2026-09-30/));
    fireEvent.click(screen.getByRole("button", { name: "Refresh billing" }));
    fireEvent.click(screen.getByRole("button", { name: "Reconcile history again" }));
    assert.deepEqual(operations, [false, true]);
  });
  it("retains stale values, labels partial amounts and disables external reads when off", () => {
    render(<VastAccountBillingPanel billing={{ ...billing, status: "stale", complete: false, account_error: "unavailable", covered_days: 10 }} pending={false} enabled={false} sync={async () => { throw Error("disabled"); }} t={t} />);
    assert.ok(screen.getByText("Stale data"));
    assert.ok(screen.getByText("Reported spend (incomplete)"));
    assert.ok(screen.getByText("8.9196 USD"));
    assert.ok(screen.getByText(/10 \/ 31/));
    assert.equal((screen.getByRole("button", { name: "Refresh billing" }) as HTMLButtonElement).disabled, true);
  });
  it("automatically syncs billing only and refreshes displayed history", async () => {
    const posts: string[] = [];
    globalThis.fetch = async (input, init) => {
      const path = String(input);
      if (init?.method === "POST") { posts.push(path); return Response.json(billing); }
      return Response.json({ ...status(), billing, history: [row({ instance_id: 88, billing_status: "reported", billed_usd: "0.403" })] });
    };
    render(<VastEnvironmentsSection t={t} />);
    await waitFor(() => assert.equal(posts.length, 1));
    await waitFor(() => assert.ok(screen.getByText("0.4030 USD")));
    assert.deepEqual(posts, [base + "/billing/sync"]);
    assert.ok(screen.getByText("1.0800 USD"));
  });
  it("keeps translation parity for account billing and partial amounts", () => {
    for (const locale of [pl, en, de]) {
      assert.deepEqual(Object.keys(locale.models.vast.accountBilling).sort(), Object.keys(en.models.vast.accountBilling).sort());
      assert.ok(locale.models.vast.billingStates.partial);
    }
  });
});


for (const failed of [false, true]) {
  it(`isolates billing ${failed ? "failure" : "success"} from an operator search error`, async () => {
    globalThis.fetch = async (input, init) => {
      if (init?.method !== "POST") return Response.json(status());
      if (String(input).endsWith("/billing/sync")) return failed
        ? Response.json({ detail: "vast.billing_unavailable" }, { status: 503 })
        : Response.json({ ok: true });
      return Response.json({ detail: "vast.search_failed" }, { status: 409 });
    };
    const { result } = renderHook(() => useVastEnvironments());
    await waitFor(() => assert.equal(result.current.loading, false));
    await act(async () => { await result.current.search(30); });
    assert.equal(result.current.error, "vast.search_failed");
    await act(async () => { await result.current.syncBilling(); });
    assert.equal(result.current.error, "vast.search_failed");
    assert.equal(result.current.billingError, failed ? "vast.billing_unavailable" : null);
    await act(async () => { await result.current.search(30); });
    assert.equal(result.current.billingError, failed ? "vast.billing_unavailable" : null);
  });
}
