import { useCallback, useEffect, useRef, useState } from "react";

export interface OpenRouterBillingState {
  configured: boolean; enabled: boolean; available_usd: string | null;
  account: { total_credits: string; total_usage: string } | null;
  key: { usage: string; usage_daily: string | null; usage_weekly: string | null; usage_monthly: string | null; limit: string | null; limit_remaining: string | null } | null;
  account_observed_at: string | null; models_observed_at: string | null;
  errors: Partial<Record<"account" | "key" | "models", string>>;
  stale: boolean; models_stale: boolean; source: string | null; scope: "account";
  from_utc: string; to_utc: string; covered_days: number; expected_days: number;
  models: { model: string; usd: string; requests: number; share_percent: string }[];
  period_usd: string | null;
}
export type BillingPeriod = "7d" | "30d" | "month" | "all";
const base = "/api/v1/openrouter/billing";
export const OPENROUTER_BILLING_INTERVAL = 300_000;
async function jsonResponse(response: Response) {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
export function useOpenRouterBilling() {
  const [state, setState] = useState<OpenRouterBillingState | null>(null);
  const [period, setPeriod] = useState<BillingPeriod>("30d");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);
  const [syncError, setSyncError] = useState(false);
  const mounted = useRef(true);
  const busy = useRef(false);
  const sequence = useRef(0);
  const reload = useRef<() => Promise<void>>(async () => {});
  const validDates = !from || !to || from <= to;
  const refresh = useCallback(async () => {
    if (!validDates) return;
    const id = ++sequence.current;
    const query = new URLSearchParams({ period });
    if (from) query.set("from_utc", from);
    if (to) query.set("to_utc", to);
    try {
      const value = await jsonResponse(await fetch(`${base}?${query}`));
      if (mounted.current && id === sequence.current && typeof value.configured === "boolean") {
        setState(value); setError(false);
      }
    } catch {
      if (mounted.current && id === sequence.current) setError(true);
    }
  }, [period, from, to, validDates]);
  useEffect(() => { reload.current = refresh; }, [refresh]);
  const cancelRead = useCallback(() => { ++sequence.current; }, []);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => { mounted.current = false; cancelRead(); };
  }, [refresh, cancelRead]);
  const sync = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setPending(true);
    try {
      await jsonResponse(await fetch(`${base}/sync`, { method: "POST" }));
      if (mounted.current) setSyncError(false);
    } catch {
      if (mounted.current) setSyncError(true);
    } finally {
      busy.current = false;
      if (mounted.current) { setPending(false); await reload.current(); }
    }
  }, []);
  const enabled = Boolean(state?.configured && state?.enabled);
  useEffect(() => {
    if (!enabled) return;
    void sync();
    const timer = setInterval(() => { void sync(); }, OPENROUTER_BILLING_INTERVAL);
    return () => clearInterval(timer);
  }, [enabled, sync]);
  const choosePeriod = (value: BillingPeriod) => { setFrom(""); setTo(""); setPeriod(value); };
  return { state, period, choosePeriod, from, setFrom, to, setTo, validDates, pending, error: error || syncError, sync };
}
