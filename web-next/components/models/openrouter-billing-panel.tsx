import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/date";
import { useOpenRouterBilling, type BillingPeriod } from "./hooks/use-openrouter-billing";
import { remoteModelStyles as styles } from "./remote-model-styles";

function usd(value: string | null | undefined, unknown: string) {
  if (value == null || value.trim() === "" || !Number.isFinite(Number(value))) return unknown;
  return Number(value).toFixed(4) + " USD";
}
const knownErrors = new Set(["management_required", "missing_credentials", "provider_unavailable", "invalid_response", "analytics_truncated", "cache_invalid"]);
export function OpenRouterBillingPanel({ t }: Readonly<{ t: (key: string) => string }>) {
  const api = useOpenRouterBilling();
  const state = api.state;
  const today = new Date().toISOString().slice(0, 10);
  const text = (key: string) => t("models.openrouter.billing." + key);
  const unknown = t("models.openrouter.unknown");
  const partial = state && (state.covered_days < state.expected_days || state.errors.models || state.models_stale);
  const metrics = [
    ["available", usd(state?.available_usd, unknown)],
    ["total", usd(state?.account?.total_usage, unknown)],
    ["keyRemaining", state?.key && state.key.limit === null ? text("unlimited") : usd(state?.key?.limit_remaining, unknown)],
    ["keyMonth", usd(state?.key?.usage_monthly, unknown)],
  ] as const;
  return <section className={styles.panel + " space-y-4"} aria-label={text("title")}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className={styles.heading}>{text("title")}</h2>
      <Button size="sm" variant="secondary" disabled={api.pending || !state?.enabled || !state?.configured} onClick={() => void api.sync()}>{text(api.pending ? "working" : "refresh")}</Button>
    </div>
    {api.error && <p role="alert" className="text-xs text-amber-400">{text("requestError")}</p>}
    {state && !state.enabled && <Badge tone="warning">{text("disabled")}</Badge>}
    {state?.stale && state.account && <Badge tone="warning">{text("stale")}</Badge>}
    <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{metrics.map(([name, value]) => <div key={name} className={styles.card}>
      <dt className={styles.hint}>{text(name)}</dt><dd className="mt-2 font-mono text-base">{value}</dd>
    </div>)}</dl>
    {state?.account_observed_at && <p className={styles.hint}>{text("updated")}: {formatDateTime(state.account_observed_at)}</p>}
    {state && (["account", "key"] as const).map(section => state.errors[section] && <p key={section} className={styles.hint}>{text(section)}: {text("errors." + (knownErrors.has(state.errors[section]!) ? state.errors[section] : "provider_unavailable"))}</p>)}
    <div className="flex flex-wrap items-end gap-3 border-t border-[color:var(--ui-border)] pt-4">
      <label className={styles.label}>{text("period")}<select className={styles.input} value={api.period} onChange={e => api.choosePeriod(e.target.value as BillingPeriod)}>{(["7d", "30d", "month", "all"] as const).map(period => <option key={period} value={period}>{text("periods." + period)}</option>)}</select></label>
      <label className={styles.label}>{text("from")}<input type="date" max={today} className={styles.input} value={api.from} onChange={e => api.setFrom(e.target.value)} /></label>
      <label className={styles.label}>{text("to")}<input type="date" max={today} className={styles.input} value={api.to} min={api.from || undefined} onChange={e => api.setTo(e.target.value)} /></label>
    </div>
    {!api.validDates && <p role="alert" className="text-xs text-amber-400">{text("invalidWindow")}</p>}
    <div className="flex flex-wrap items-center gap-3"><h3 className={styles.heading}>{text("models")}</h3><Badge tone="neutral">{text("accountScope")}</Badge>{partial && <Badge tone="warning">{text("partial")}</Badge>}</div>
    {state && <p className={styles.hint}>{state.from_utc} — {state.to_utc} UTC · {text("periodTotal")}: {usd(state.period_usd, unknown)}</p>}
    {state?.errors.models && <p role="status" className={styles.hint}>{text("errors." + (knownErrors.has(state.errors.models) ? state.errors.models : "provider_unavailable"))}</p>}
    {state && state.models.length > 0 ? <div className={styles.tableWrap}><table className="w-full min-w-[480px] text-left text-sm"><caption className="sr-only">{text("models")}</caption>
      <thead><tr>{["model", "cost", "share", "requests"].map(key => <th key={key} scope="col" className={styles.tableHead}>{text(key)}</th>)}</tr></thead>
      <tbody>{state.models.map(row => <tr key={row.model} className={styles.tableRow}><td className={styles.tableCell + " break-all"}>{row.model}</td><td className={styles.tableCell}>{usd(row.usd, unknown)}</td><td className={styles.tableCell}>{Number(row.share_percent).toFixed(1)}%</td><td className={styles.tableCell}>{row.requests}</td></tr>)}</tbody>
    </table></div> : <p className="text-sm">{text(state?.covered_days && !state?.errors.models ? "noUsage" : "noData")}</p>}
    {state?.models_observed_at && <p className={styles.hint}>{text("modelsUpdated")}: {formatDateTime(state.models_observed_at)}</p>}
  </section>;
}
