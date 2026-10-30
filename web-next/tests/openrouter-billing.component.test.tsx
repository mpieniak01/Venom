import "./component-test-setup";
import React from "react";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { OpenRouterBillingPanel } from "../components/models/openrouter-billing-panel";
import { useOpenRouterBilling, OPENROUTER_BILLING_INTERVAL, type OpenRouterBillingState } from "../components/models/hooks/use-openrouter-billing";
import { en } from "../lib/i18n/locales/en";
import { pl } from "../lib/i18n/locales/pl";
import { de } from "../lib/i18n/locales/de";
const t = (key: string) => key.split(".").reduce<unknown>((value, part) => (value as Record<string, unknown>)[part], en) as string;
const initial: OpenRouterBillingState = {
  configured: true, enabled: true, available_usd: "9.542663626",
  account: { total_credits: "20", total_usage: "10.457336374" },
  key: { usage: "10.4", usage_daily: "0", usage_weekly: "0", usage_monthly: "0.0115", limit: "15", limit_remaining: "4.59303088" },
  account_observed_at: "2026-10-30T12:00:00Z", models_observed_at: "2026-10-30T12:00:00Z",
  errors: {}, stale: false, models_stale: false, source: "analytics", scope: "account",
  from_utc: "2026-10-01", to_utc: "2026-10-30", covered_days: 30, expected_days: 30,
  models: [{ model: "vendor/old-disconnected", usd: "0.5", requests: 12, share_percent: "100" }], period_usd: "0.5",
};
const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });

describe("OpenRouter aggregate billing", () => {
  it("shows account funds separately from the key limit and includes disconnected model costs", async () => {
    const calls: string[] = [];
    globalThis.fetch = async (input, init) => { calls.push(String(input)); return Response.json(init?.method === "POST" ? {ok:true} : initial); };
    render(<OpenRouterBillingPanel t={t} />);
    await waitFor(() => assert.ok(screen.getByText("9.5427 USD")));
    assert.ok(screen.getByText("4.5930 USD"));
    assert.ok(screen.getByText("vendor/old-disconnected"));
    assert.ok(screen.getByRole("columnheader", {name:"Reported cost"}));
    assert.ok(screen.getByText("12"));
    await waitFor(() => assert.equal(calls.filter(c => c.endsWith("/sync")).length,1));
    assert.ok(calls.every(c => c.startsWith("/api/v1/openrouter/billing")));
    fireEvent.change(screen.getByLabelText("Period"), {target:{value:"7d"}});
    await waitFor(() => assert.ok(calls.some(c => c.includes("period=7d"))));
    fireEvent.change(screen.getByLabelText("From (UTC)"), {target:{value:"2026-10-10"}});
    await waitFor(() => assert.ok(calls.some(c => c.includes("from_utc=2026-10-10"))));
    fireEvent.change(screen.getByLabelText("To (UTC)"), {target:{value:"2026-10-05"}});
    assert.ok(screen.getByRole("alert"));
  });
  it("keeps the available account data when model analytics needs permission", async () => {
    globalThis.fetch = async () => Response.json({...initial, errors:{models:"management_required"}, models:[], period_usd:null, covered_days:0});
    render(<OpenRouterBillingPanel t={t} />);
    await waitFor(() => assert.ok(screen.getByText("Analytics requires a management key.")));
    assert.ok(screen.getByText("9.5427 USD"));
    assert.ok(screen.getByText("No model billing data."));
    assert.equal(screen.queryByRole("table"),null);
  });
  it("does not call the provider sync endpoint when disabled and still displays cached values", async () => {
    const posts: string[] = [];
    globalThis.fetch = async (input, init) => { if(init?.method === "POST") posts.push(String(input)); return Response.json({...initial,enabled:false,stale:true}); };
    render(<OpenRouterBillingPanel t={t} />);
    await waitFor(() => assert.ok(screen.getByText("API disabled or access blocked")));
    assert.ok(screen.getByText("Stale data"));
    assert.equal((screen.getByRole("button",{name:"Refresh billing"}) as HTMLButtonElement).disabled,true);
    assert.deepEqual(posts,[]);
  });
  it("deduplicates sync requests, polls at the configured interval and retains data on failure", async context => {
    context.mock.timers.enable({apis:["setInterval"]});
    let syncs=0;
    let resolve: (r: Response) => void = () => {};
    globalThis.fetch = async (_input,init) => {
      if(init?.method === "POST") { syncs++; if(syncs===1) return Response.json({ok:true}); return new Promise<Response>(r=>{resolve=r;}); }
      return Response.json(initial);
    };
    const {result}=renderHook(()=>useOpenRouterBilling());
    await act(async()=>{});
    await act(async()=>{});
    await act(async()=>{context.mock.timers.tick(OPENROUTER_BILLING_INTERVAL);});
    assert.equal(syncs,2);
    let duplicate:Promise<void>;
    act(()=>{duplicate=result.current.sync();});
    await act(async()=>{await duplicate;resolve(Response.json({}, {status:503}));});
    assert.equal(syncs,2);
    assert.equal(result.current.state?.available_usd,initial.available_usd);
    assert.equal(result.current.error,true);
    cleanup();
  });
  it("has matching translated billing keys in all supported locales", () => {
    for(const locale of [en,pl,de]) {
      assert.deepEqual(Object.keys(locale.models.openrouter.billing).sort(),Object.keys(en.models.openrouter.billing).sort());
      assert.deepEqual(Object.keys(locale.models.openrouter.billing.errors).sort(),Object.keys(en.models.openrouter.billing.errors).sort());
    }
  });
});
