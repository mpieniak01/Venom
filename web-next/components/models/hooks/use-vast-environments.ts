import { useCallback, useEffect, useRef, useState } from "react";

export interface VastEnvironment {
  plan_id: string; model: string; state: string; phase: string;
  instance_id: number | null; hourly_usd: string | null; total_usd: string | null;
  duration_minutes: number; expires_at: string | null; connected: boolean;
  error: string | null; billing_possible: boolean;
  billing_status?: "reported" | "partial" | "unavailable" | "unverified" | "not_applicable";
  billed_usd?: string | null;
  billing_observed_at?: string | null;
}
export interface VastOffer {
  offer_id: number; gpu_name: string; country: string | null; gpu_ram_mb: number | null;
  hourly_usd: string; total_usd: string; status: "eligible" | "ineligible" | "unknown";
  reasons: string[];
}
export interface VastAccountBilling {
  configured: boolean;
  status: "empty" | "ready" | "partial" | "stale" | "unavailable";
  error: string | null; account_error: string | null;
  credit_usd: string | null; balance_usd: string | null;
  account_observed_at: string | null; observed_at: string | null;
  from_utc: string; to_utc: string;
  total_usd: string | null; managed_usd: string | null; other_usd: string | null;
  covered_days: number; expected_days: number; complete: boolean;
}
export interface VastEnvironmentsState {
  configured: boolean; enabled: boolean; model: string | null;
  duration_minutes: number; reason: string | null; environments: VastEnvironment[];
  history?: VastEnvironment[];
  billing?: VastAccountBilling;
}
const base = "/api/v1/vast/environments";
const activePhases = new Set(["queued", "creating", "waiting", "provisioning", "connecting", "stop_requested", "destroy_requested"]);
export const VAST_POLL_INTERVAL = 5000;

async function jsonResponse(response: Response) {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(typeof payload?.detail === "string" ? payload.detail : `HTTP ${response.status}`);
  }
  return response.json();
}

function actionBody(operation: "order" | "refresh" | "stop" | "destroy", acceptNewHostKey: boolean): object {
  if (operation === "order") return { confirmed: true, accept_new_host_key: acceptNewHostKey };
  if (operation === "refresh") return {};
  return { confirmed: true };
}

export function useVastEnvironments(onChanged?: () => Promise<unknown>) {
  const [state, setState] = useState<VastEnvironmentsState | null>(null);
  const [offers, setOffers] = useState<VastOffer[] | null>(null);
  const [draft, setDraft] = useState<VastEnvironment | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [billingPending, setBillingPending] = useState(false);
  const billingBusy = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  const busy = useRef(false);
  const reading = useRef(false);
  const readSequence = useRef(0);
  const refreshQueued = useRef(false);
  const callback = useRef(onChanged); callback.current = onChanged;
  const connectionSignature = useRef("");

  const refresh = useCallback(async (): Promise<void> => {
    if (reading.current || busy.current) { refreshQueued.current = true; return; }
    reading.current = true;
    const sequence = ++readSequence.current;
    try {
      const value: VastEnvironmentsState = await jsonResponse(await fetch(base));
      if (!mounted.current || sequence !== readSequence.current) return;
      setState(value);
      const connected = [...value.environments, ...(value.history ?? [])].filter(row => row.connected).map(row => row.plan_id);
      const signature = [...new Set(connected)].sort((left, right) => left.localeCompare(right)).join(",");
      if (signature !== connectionSignature.current) {
        connectionSignature.current = signature;
        await callback.current?.();
      }
    } catch (e) {
      if (mounted.current && sequence === readSequence.current) setError(e instanceof Error ? e.message : "vast.request_failed");
    } finally {
      reading.current = false;
      if (mounted.current) {
        setLoading(false);
        if (refreshQueued.current) { refreshQueued.current = false; void refresh(); }
      }
    }
  }, []);

  const syncBilling = useCallback(async (reconcile = false) => {
    if (billingBusy.current) return;
    billingBusy.current = true;
    setBillingPending(true);
    try {
      await jsonResponse(await fetch(base + "/billing/sync", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reconcile }),
      }));
      if (mounted.current) setError(null);
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : "vast.request_failed");
    } finally {
      billingBusy.current = false;
      if (mounted.current) { setBillingPending(false); await refresh(); }
    }
  }, [refresh]);
  const billingEnabled = Boolean(state?.enabled && state?.billing?.configured);
  useEffect(() => {
    if (!billingEnabled) return;
    void syncBilling();
    const timer = setInterval(() => { void syncBilling(); }, 300_000);
    return () => clearInterval(timer);
  }, [billingEnabled, syncBilling]);

  const cancelRead = useCallback(() => { ++readSequence.current; }, []);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => { mounted.current = false; cancelRead(); };
  }, [refresh, cancelRead]);

  const hasActiveOrder = state?.environments.some(row => activePhases.has(row.phase)) ?? false;
  useEffect(() => {
    if (!hasActiveOrder) return;
    const timer = setInterval(() => { void refresh(); }, VAST_POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [hasActiveOrder, refresh]);

  const post = async (path: string, body: object, accept: (data: unknown) => void) => {
    if (busy.current) return;
    busy.current = true;
    ++readSequence.current;
    setPending(true); setError(null);
    try {
      const result = await jsonResponse(await fetch(base + path, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      }));
      if (mounted.current) accept(result);
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : "vast.request_failed");
    } finally {
      busy.current = false;
      if (mounted.current) { setPending(false); await refresh(); }
    }
  };
  const search = (duration: number) => {
    setDraft(null); setOffers(null);
    return post("/search", { duration_minutes: duration }, data => setOffers((data as { offers: VastOffer[] }).offers));
  };
  const prepare = (offer: VastOffer, duration: number, hourly: string, total: string) => {
    setDraft(null);
    return post("/plans", {
      offer_id: offer.offer_id, duration_minutes: duration, max_hourly_usd: hourly, max_total_usd: total,
    }, data => setDraft(data as VastEnvironment));
  };
  const action = (planId: string, operation: "order" | "refresh" | "stop" | "destroy", acceptNewHostKey = false) => post(
    `/${encodeURIComponent(planId)}/${operation}`,
    actionBody(operation, acceptNewHostKey),
    () => { if (operation === "order") setDraft(null); },
  );
  const clearDraft = () => setDraft(null);
  const clearOffers = () => setOffers(null);
  return { state, offers, draft, loading, pending, billingPending, syncBilling, error, search, prepare, action, refresh, clearDraft, clearOffers };
}
