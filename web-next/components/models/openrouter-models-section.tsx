import { useOpenRouterModels, type OpenRouterModel, type OpenRouterPurpose } from "./hooks/use-openrouter-models";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { remoteModelStyles as styles } from "./remote-model-styles";

import { OpenRouterBillingPanel } from "./openrouter-billing-panel";

const categories = ["programming", "roleplay", "marketing", "marketing/seo", "technology", "science", "translation", "legal", "finance", "health", "trivia", "academia"];
interface Props { t: (key: string) => string; onChanged?: () => Promise<unknown>; }
export function OpenRouterModelsSection({ t, onChanged }: Readonly<Props>) {
  const catalog = useOpenRouterModels(onChanged);
  const text = (name: string) => t("models.openrouter." + name);
  const connectedIds = new Set(catalog.connected.map(model => model.id));
  const actionLabel = (id: string, isConnected: boolean) => {
    if (catalog.pending[id]) return "saving";
    return isConnected ? "disconnect" : "connect";
  };
  const card = (model: OpenRouterModel, isConnected: boolean) => <li key={model.id} className={styles.card + " flex flex-wrap items-start justify-between gap-4"}>
    <div className="min-w-0 flex-1">
      <p className="break-words text-sm font-semibold text-[color:var(--text-primary)]">{model.name}</p><p className="text-xs text-[color:var(--ui-muted)] break-all">{model.id}</p>
      <div className="mt-3 grid justify-items-start gap-x-5 gap-y-2 text-xs sm:grid-cols-2 xl:grid-cols-3">
        <span>{text("context")}: {model.context_length?.toLocaleString() ?? text("unknown")}</span>
        <span>{text("input")}: {model.input_price_per_million ?? text("unknown")}</span>
        <span>{text("output")}: {model.output_price_per_million ?? text("unknown")}</span>
        {isConnected && model.max_output_tokens !== undefined && <span>{text("outputLimit")}: {model.max_output_tokens}</span>}
        {model.supports_tools && <Badge tone="neutral">{text("tools")}</Badge>}
        {isConnected && <Badge tone="success">{text("connected")}</Badge>}
        {isConnected && model.available === false && <Badge tone="warning">{text("needsRefresh")}</Badge>}
      </div>
      {model.description && <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-[color:var(--ui-muted)]">{model.description}</p>}
    </div>
    <div className="flex w-full flex-wrap gap-2 sm:w-auto">{isConnected && model.available === false && <Button size="sm" variant="secondary" disabled={Boolean(catalog.pending[model.id])} aria-label={`${text("refresh")}: ${model.id}`} onClick={() => void catalog.manage(model.id, true)}>{text("refresh")}</Button>}
    <Button size="sm" variant="secondary" disabled={Boolean(catalog.pending[model.id])} aria-label={`${text(isConnected ? "disconnect" : "connect")}: ${model.id}`} onClick={() => void catalog.manage(model.id, !isConnected)}>{text(actionLabel(model.id, isConnected))}</Button></div>
  </li>;
  return <section className="min-w-0 space-y-6" aria-label="OpenRouter">
    <OpenRouterBillingPanel t={t} />
    <div className={styles.panel + " space-y-4"}>
      <div className="space-y-2"><h2 className={styles.heading}>OpenRouter</h2><p className={styles.hint}>{text("description")}</p></div>
      {catalog.error && <p role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-400">{text("error")}: {catalog.error}</p>}
      <h3 className="font-semibold">{text("connectedTitle")} ({catalog.connected.length})</h3>
      <p className="text-xs text-[color:var(--ui-muted)]">{text("connectedHint")}</p>
      {catalog.connectedLoading && <output className="block">{text("loading")}</output>}
      {!catalog.connectedLoading && catalog.connected.length === 0 && <p className="text-sm">{text("noneConnected")}</p>}
      <ul className="space-y-2">{catalog.connected.map(model => card(model, true))}</ul>
    </div>
    <form className={styles.panel + " space-y-5"} onSubmit={event => { event.preventDefault(); void catalog.search(); }}>
      <h3 className={styles.heading}>{text("searchTitle")}</h3>
      <div className="grid items-end gap-4 sm:grid-cols-2 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
        <label className={styles.label}>{text("query")}<input className={styles.input} value={catalog.query} maxLength={120} onChange={event => catalog.setQuery(event.target.value)} /></label>
        <label className={styles.label}>{text("purpose")}<select className={styles.input} value={catalog.purpose} onChange={event => catalog.setPurpose(event.target.value as OpenRouterPurpose)}>{(["chat", "tasks", "programming"] as const).map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label>
        <label className={styles.label}>{text("category")}<select className={styles.input} value={catalog.purpose === "programming" ? "programming" : catalog.category} disabled={catalog.purpose === "programming"} onChange={event => catalog.setCategory(event.target.value)}><option value="">{text("allCategories")}</option>{categories.map(value => <option key={value} value={value}>{text("categories." + value)}</option>)}</select></label>
        <Button type="submit" className="h-10 justify-center" disabled={catalog.loading}>{text(catalog.loading ? "loading" : "search")}</Button>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm text-[color:var(--text-primary)]">
        <input type="checkbox" className="h-4 w-4 accent-emerald-400" checked={catalog.freeOnly} onChange={event => catalog.setFreeOnly(event.target.checked)} />
        {text("freeOnly")}
      </label>
      <p className={styles.hint}>{text("priceHint")}</p>
    </form>
    {catalog.results && <div className={styles.panel + " space-y-4"}>
      <p className="text-sm">{text("results")}: {catalog.results.total}</p>
      {catalog.results.models.length === 0 && <p>{text("noResults")}</p>}
      <ul className="space-y-2">{catalog.results.models.map(model => card(model, connectedIds.has(model.id)))}</ul>
      <div className="flex flex-wrap gap-3 border-t border-[color:var(--ui-border)] pt-4">
        <Button variant="secondary" disabled={catalog.loading || catalog.results.offset === 0} onClick={() => void catalog.search(Math.max(0, catalog.results!.offset - catalog.results!.limit))}>{text("previous")}</Button>
        <Button variant="secondary" disabled={catalog.loading || catalog.results.next_offset === null} onClick={() => void catalog.search(catalog.results!.next_offset ?? 0)}>{text("next")}</Button>
      </div>
    </div>}
  </section>;
}
