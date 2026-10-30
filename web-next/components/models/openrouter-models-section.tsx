import { useOpenRouterModels, type OpenRouterPurpose } from "./hooks/use-openrouter-models";
import { Button } from "@/components/ui/button";
import { remoteModelStyles as styles } from "./remote-model-styles";

import { OpenRouterModelTable } from "./openrouter-model-table";
import { OpenRouterBillingPanel } from "./openrouter-billing-panel";

const categories = ["programming", "roleplay", "marketing", "marketing/seo", "technology", "science", "translation", "legal", "finance", "health", "trivia", "academia"];
interface Props { t: (key: string) => string; onChanged?: () => Promise<unknown>; }
export function OpenRouterModelsSection({ t, onChanged }: Readonly<Props>) {
  const catalog = useOpenRouterModels(onChanged);
  const text = (name: string) => t("models.openrouter." + name);
  return <section className="min-w-0 space-y-6" aria-label="OpenRouter">
    <OpenRouterBillingPanel t={t} />
    <div className={styles.panel + " space-y-4"}>
      <div className="space-y-2"><h2 className={styles.heading}>OpenRouter</h2><p className={styles.hint}>{text("description")}</p></div>
      {catalog.error && <p role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-400">{text("error")}: {catalog.error}</p>}
      <h3 className="font-semibold">{text("connectedTitle")} ({catalog.connected.length})</h3>
      <p className="text-xs text-[color:var(--ui-muted)]">{text("connectedHint")}</p>
      {catalog.connectedLoading && <output className="block">{text("loading")}</output>}
      {!catalog.connectedLoading && catalog.connected.length === 0 && <p className="text-sm">{text("noneConnected")}</p>}
      {catalog.connected.length > 0 && <OpenRouterModelTable models={catalog.connected} connected={catalog.connected} pending={catalog.pending} manage={catalog.manage} caption={text("connectedTitle")} t={t} />}
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
      {catalog.results.models.length > 0 && <OpenRouterModelTable models={catalog.results.models} connected={catalog.connected} pending={catalog.pending} manage={catalog.manage} caption={text("results")} t={t} />}
      <div className="flex flex-wrap gap-3 border-t border-[color:var(--ui-border)] pt-4">
        <Button variant="secondary" disabled={catalog.loading || catalog.results.offset === 0} onClick={() => void catalog.search(Math.max(0, catalog.results!.offset - catalog.results!.limit))}>{text("previous")}</Button>
        <Button variant="secondary" disabled={catalog.loading || catalog.results.next_offset === null} onClick={() => void catalog.search(catalog.results!.next_offset ?? 0)}>{text("next")}</Button>
      </div>
    </div>}
  </section>;
}
