import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/date";
import { useVastEnvironments, type VastOffer } from "./hooks/use-vast-environments";
import { VastEnvironmentRow } from "./vast-environment-row";

interface Props { t: (key: string) => string; onChanged?: () => Promise<unknown>; }
const inputClass = "rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-2";
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
  return <section className="space-y-6" aria-label="VAST">
    <div><h2 className="text-lg font-semibold">{text("title")}</h2><p className="text-sm text-[color:var(--ui-muted)]">{text("description")}</p></div>
    {api.error && <p role="alert" className="text-sm text-rose-400">{text("operationError")}: <code>{api.error}</code></p>}
    {api.loading && <output className="block">{text("loading")}</output>}
    {api.state && !ready && <output className="block text-sm text-amber-300">{text(!api.state.enabled ? "disabled" : "notConfigured")}{api.state.reason && <> <code>{api.state.reason}</code></>}</output>}
    <form className="rounded-2xl border border-[color:var(--ui-border)] p-5 space-y-4" onSubmit={event => {
      event.preventDefault();
      if (!ready || api.pending || !validDuration) {
        return;
      }
      resetSelection();
      void api.search(Number(duration));
    }}>
      <p className="text-sm">{text("model")}: <strong>{api.state?.model ?? text("unknown")}</strong></p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">{text("duration")}<input type="number" min={1} max={1440} step={1} disabled={api.pending} value={duration} className={inputClass} onChange={event => { setDurationInput(event.target.value); resetSelection(); api.clearOffers(); }} /></label>
        <Button type="submit" disabled={!ready || api.pending || !validDuration}>{text(api.pending ? "working" : "search")}</Button>
      </div>
      <p className="text-xs text-[color:var(--ui-muted)]">{text("estimateHint")}</p>
    </form>
    {api.offers && <div className="rounded-2xl border border-[color:var(--ui-border)] p-5 space-y-4">
      <h3 className="font-semibold">{text("offers")}</h3>
      {api.offers.length === 0 ? <p>{text("noOffers")}</p> : <div className="max-h-96 overflow-auto"><table className="w-full text-left text-sm"><thead className="sticky top-0 z-10 bg-[color:var(--ui-surface)]"><tr>{["offer", "gpu", "country", "vram", "hourly", "estimate", "selection"].map(name => <th key={name} className="p-2">{text(name)}</th>)}</tr></thead><tbody>{api.offers.map(offer => <tr key={offer.offer_id} className="border-t border-[color:var(--ui-border)]">
        <td className="p-2">{offer.offer_id}</td><td className="p-2">{offer.gpu_name}</td><td className="p-2">{offer.country ?? text("unknown")}</td><td className="p-2">{offer.gpu_ram_mb ?? text("unknown")}</td><td className="p-2">{offer.hourly_usd ?? text("unknown")}</td><td className="p-2">{offer.total_usd ?? text("unknown")}</td>
        <td className="p-2"><Button type="button" size="sm" variant="secondary" disabled={api.pending || offer.status !== "eligible"} aria-label={`${text("choose")}: ${offer.offer_id}`} onClick={() => { api.clearDraft(); setSelected(offer); setConfirmed(false); }}>{text(offerActionLabel(offer, selected))}</Button>{offer.reasons.length > 0 && <p className="mt-1 text-xs text-[color:var(--ui-muted)]">{text("unavailableReason")}: {offer.reasons.join(", ")}</p>}</td>
      </tr>)}</tbody></table></div>}
      {selected && <div className="space-y-3 border-t border-[color:var(--ui-border)] pt-4">
        <p className="text-sm">{text("selectedOffer")}: {selected.offer_id}</p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">{text("maxHourly")}<input type="number" min="0.001" step="any" disabled={api.pending} value={hourly} className={inputClass} onChange={event => { setHourly(event.target.value); api.clearDraft(); setConfirmed(false); }} /></label>
          <label className="flex flex-col gap-1 text-sm">{text("maxTotal")}<input type="number" min="0.001" step="any" disabled={api.pending} value={total} className={inputClass} onChange={event => { setTotal(event.target.value); api.clearDraft(); setConfirmed(false); }} /></label>
          <Button disabled={api.pending || !validBudget || !validDuration || !ready} onClick={() => { setConfirmed(false); void api.prepare(selected, Number(duration), hourly, total); }}>{text("prepare")}</Button>
        </div>
      </div>}
    </div>}
    {api.draft && <div className="rounded-2xl border border-amber-500/40 p-5 space-y-3" aria-label={text("orderReview")}>
      <h3 className="font-semibold">{text("orderReview")}</h3>
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
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3"><h3 className="font-semibold">{text("environments")}</h3><Button size="sm" variant="secondary" disabled={api.pending || api.loading} onClick={() => void api.refresh()}>{text("refreshList")}</Button></div>
      {api.state?.environments.length === 0 && <p className="text-sm">{text("none")}</p>}
      <ul className="space-y-3">{api.state?.environments.map(row => <VastEnvironmentRow key={row.plan_id} row={row} pending={api.pending} action={api.action} t={t} />)}</ul>
      <p className="text-xs text-[color:var(--ui-muted)]">{text("manualZero")}</p>
      {api.state?.environments.some(row => row.connected) && <Badge tone="success">{text("chatReady")}</Badge>}
    </div>
  </section>;
}
