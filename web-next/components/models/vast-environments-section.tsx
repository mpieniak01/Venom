import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/date";
import { useVastEnvironments, type VastOffer } from "./hooks/use-vast-environments";
import { VastEnvironmentRow } from "./vast-environment-row";
import { VastEnvironmentHistory } from "./vast-environment-history";
import { remoteModelStyles as styles } from "./remote-model-styles";

interface Props { t: (key: string) => string; onChanged?: () => Promise<unknown>; }
const inputClass = styles.input;
function offerActionLabel(offer: VastOffer, selected: VastOffer | null): string {
  if (selected?.offer_id === offer.offer_id) return "chosen";
  if (offer.status === "eligible") return "choose";
  return "ineligible";
}

export function VastEnvironmentsSection({ t, onChanged }: Readonly<Props>) {
  const api = useVastEnvironments(onChanged);
  const [durationInput, setDurationInput] = useState<string | null>(null);
  const [selected, setSelected] = useState<VastOffer | null>(null);
  const [hourly, setHourly] = useState("0.50");
  const [total, setTotal] = useState("1.00");
  const [confirmed, setConfirmed] = useState(false);
  const [acceptHost, setAcceptHost] = useState(false);
  const text = (name: string) => t("models.vast." + name);
  const duration = durationInput ?? String(api.state?.duration_minutes ?? 60);
  const validDuration = Number.isInteger(Number(duration)) && Number(duration) >= 1 && Number(duration) <= 1440;
  const validBudget = Number(hourly) > 0 && Number(total) > 0 && Number.isFinite(Number(hourly)) && Number.isFinite(Number(total));
  const ready = Boolean(api.state?.configured && api.state?.enabled);
  const resetSelection = () => { setSelected(null); api.clearDraft(); setConfirmed(false); };
  return <section className="min-w-0 space-y-6" aria-label="VAST">
    <form className={styles.panel + " space-y-5"} onSubmit={event => {
      event.preventDefault();
      if (!ready || api.pending || !validDuration) {
        return;
      }
      resetSelection();
      void api.search(Number(duration));
    }}>
      <div className="space-y-2"><h2 className={styles.heading}>{text("title")}</h2><p className={styles.hint}>{text("description")}</p></div>
      {api.error && <p role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-400">{text("operationError")}: <code>{api.error}</code></p>}
      {api.loading && <output className="block">{text("loading")}</output>}
      {api.state && !ready && <output className="block rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-400">{text(!api.state.enabled ? "disabled" : "notConfigured")}{api.state.reason && <> <code>{api.state.reason}</code></>}</output>}
      <p className={styles.card + " break-words text-xs leading-relaxed"}>{text("model")}: <strong>{api.state?.model ?? text("unknown")}</strong></p>
      <div className="grid items-end gap-4 sm:grid-cols-[minmax(0,20rem)_auto] sm:justify-start">
        <label className={styles.label}>{text("duration")}<input type="number" min={1} max={1440} step={1} disabled={api.pending} value={duration} className={inputClass} onChange={event => { setDurationInput(event.target.value); resetSelection(); api.clearOffers(); }} /></label>
        <Button type="submit" className="h-10 justify-center" disabled={!ready || api.pending || !validDuration}>{text(api.pending ? "working" : "search")}</Button>
      </div>
      <p className={styles.hint}>{text("estimateHint")}</p>
    </form>
    {api.offers && <div className={styles.panel + " space-y-5"}>
      <h3 className={styles.heading}>{text("offers")}</h3>
      {api.offers.length === 0 ? <p>{text("noOffers")}</p> : <div className={styles.tableWrap + " max-h-96"}><table className="w-full min-w-[680px] border-collapse text-left text-sm"><thead className="sticky top-0 z-10 bg-[color:var(--ui-surface)]"><tr>{["offer", "gpu", "country", "vram", "hourly", "estimate", "selection"].map(name => <th key={name} className={styles.tableHead}>{text(name)}</th>)}</tr></thead><tbody>{api.offers.map(offer => <tr key={offer.offer_id} className={styles.tableRow}>
        <td className={styles.tableCell}>{offer.offer_id}</td><td className={styles.tableCell}>{offer.gpu_name}</td><td className={styles.tableCell}>{offer.country ?? text("unknown")}</td><td className={styles.tableCell}>{offer.gpu_ram_mb ?? text("unknown")}</td><td className={styles.tableCell}>{offer.hourly_usd ?? text("unknown")}</td><td className={styles.tableCell}>{offer.total_usd ?? text("unknown")}</td>
        <td className={styles.tableCell}><Button type="button" size="sm" variant="secondary" disabled={api.pending || offer.status !== "eligible"} aria-label={`${text("choose")}: ${offer.offer_id}`} onClick={() => { api.clearDraft(); setSelected(offer); setConfirmed(false); }}>{text(offerActionLabel(offer, selected))}</Button>{offer.reasons.length > 0 && <p className="mt-1 text-xs text-[color:var(--ui-muted)]">{text("unavailableReason")}: {offer.reasons.join(", ")}</p>}</td>
      </tr>)}</tbody></table></div>}
      {selected && <div className="space-y-3 border-t border-[color:var(--ui-border)] pt-4">
        <p className="text-sm">{text("selectedOffer")}: {selected.offer_id}</p>
        <div className="grid items-end gap-4 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <label className={styles.label}>{text("maxHourly")}<input type="number" min="0.001" step="any" disabled={api.pending} value={hourly} className={inputClass} onChange={event => { setHourly(event.target.value); api.clearDraft(); setConfirmed(false); }} /></label>
          <label className={styles.label}>{text("maxTotal")}<input type="number" min="0.001" step="any" disabled={api.pending} value={total} className={inputClass} onChange={event => { setTotal(event.target.value); api.clearDraft(); setConfirmed(false); }} /></label>
          <Button disabled={api.pending || !validBudget || !validDuration || !ready} onClick={() => { setConfirmed(false); void api.prepare(selected, Number(duration), hourly, total); }}>{text("prepare")}</Button>
        </div>
      </div>}
    </div>}
    {api.draft && <div className="min-w-0 space-y-4 rounded-[24px] border border-amber-500/40 bg-[color:var(--ui-surface)] p-4 text-sm text-[color:var(--text-primary)] shadow-card sm:p-6" aria-label={text("orderReview")}>
      <h3 className={styles.heading}>{text("orderReview")}</h3>
      <p className="text-sm break-all">{api.draft.model}</p>
      <p className="text-sm">{text("hourly")}: {api.draft.hourly_usd} · {text("estimate")}: {api.draft.total_usd} · {text("duration")}: {api.draft.duration_minutes}</p>
      <p className="text-xs text-[color:var(--ui-muted)]">{text("expires")}: {formatDateTime(api.draft.expires_at)}</p>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={acceptHost} onChange={event => setAcceptHost(event.target.checked)} />{text("acceptHost")}</label>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />{text("acceptCost")}</label>
      <Button disabled={api.pending || !confirmed || !ready} onClick={() => {
        if (!api.draft || !confirmed) {
          return;
        }
        setConfirmed(false);
        void api.action(api.draft.plan_id, "order", acceptHost);
      }}>{text(api.pending ? "working" : "order")}</Button>
    </div>}
    <div className={styles.panel + " space-y-4"}>
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 className={styles.heading}>{text("environments")}</h3><Button size="sm" variant="secondary" disabled={api.pending || api.loading} onClick={() => void api.refresh()}>{text("refreshList")}</Button></div>
      {api.state?.environments.length === 0 && <p className="text-sm">{text("none")}</p>}
      <ul className="space-y-3">{api.state?.environments.map(row => <VastEnvironmentRow key={row.plan_id} row={row} pending={api.pending} action={api.action} t={t} />)}</ul>
      <p className={styles.hint}>{text("manualZero")}</p>
      {api.state?.environments.some(row => row.connected) && <Badge tone="success">{text("chatReady")}</Badge>}
    </div>
    <VastEnvironmentHistory rows={api.state?.history ?? []} t={t} />
  </section>;
}
