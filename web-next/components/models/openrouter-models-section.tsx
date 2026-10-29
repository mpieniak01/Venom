import { useOpenRouterModels, type OpenRouterModel, type OpenRouterPurpose } from "./hooks/use-openrouter-models";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const categories = ["programming", "roleplay", "marketing", "marketing/seo", "technology", "science", "translation", "legal", "finance", "health", "trivia", "academia"];
interface Props { t: (key: string) => string; onChanged?: () => Promise<unknown>; }
export function OpenRouterModelsSection({ t, onChanged }: Readonly<Props>) {
  const catalog = useOpenRouterModels(onChanged);
  const text = (name: string) => t("models.openrouter." + name);
  const connectedIds = new Set(catalog.connected.map(model => model.id));
  const card = (model: OpenRouterModel, isConnected: boolean) => <li key={model.id} className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-[color:var(--ui-border)] p-4">
    <div className="min-w-0 flex-1">
      <p className="font-medium break-words">{model.name}</p><p className="text-xs text-[color:var(--ui-muted)] break-all">{model.id}</p>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        <span>{text("context")}: {model.context_length?.toLocaleString() ?? text("unknown")}</span>
        <span>{text("input")}: {model.input_price_per_million ?? text("unknown")}</span>
        <span>{text("output")}: {model.output_price_per_million ?? text("unknown")}</span>
        {model.supports_tools && <Badge tone="neutral">{text("tools")}</Badge>}
        {isConnected && <Badge tone="success">{text("connected")}</Badge>}
        {isConnected && model.available === false && <Badge tone="warning">{text("needsRefresh")}</Badge>}
      </div>
      {model.description && <p className="mt-2 line-clamp-2 text-xs text-[color:var(--ui-muted)]">{model.description}</p>}
    </div>
    <div className="flex gap-2">{isConnected && model.available === false && <Button size="sm" variant="secondary" disabled={Boolean(catalog.pending[model.id])} aria-label={`${text("refresh")}: ${model.id}`} onClick={() => void catalog.manage(model.id, true)}>{text("refresh")}</Button>}
    <Button size="sm" variant="secondary" disabled={Boolean(catalog.pending[model.id])} aria-label={`${text(isConnected ? "disconnect" : "connect")}: ${model.id}`} onClick={() => void catalog.manage(model.id, !isConnected)}>{text(catalog.pending[model.id] ? "saving" : isConnected ? "disconnect" : "connect")}</Button></div>
  </li>;
  return <section className="space-y-6" aria-label="OpenRouter">
    <div><h2 className="text-lg font-semibold">OpenRouter</h2><p className="text-sm text-[color:var(--ui-muted)]">{text("description")}</p></div>
    {catalog.error && <p role="alert" className="text-sm text-rose-400">{text("error")}: {catalog.error}</p>}
    <div className="rounded-2xl border border-[color:var(--ui-border)] p-5 space-y-3">
      <h3 className="font-semibold">{text("connectedTitle")} ({catalog.connected.length})</h3>
      <p className="text-xs text-[color:var(--ui-muted)]">{text("connectedHint")}</p>
      {catalog.connectedLoading && <p role="status">{text("loading")}</p>}
      {!catalog.connectedLoading && catalog.connected.length === 0 && <p className="text-sm">{text("noneConnected")}</p>}
      <ul className="space-y-2">{catalog.connected.map(model => card(model, true))}</ul>
    </div>
    <form className="rounded-2xl border border-[color:var(--ui-border)] p-5 space-y-4" onSubmit={event => { event.preventDefault(); void catalog.search(); }}>
      <h3 className="font-semibold">{text("searchTitle")}</h3>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">{text("query")}<input className="rounded-lg border border-[color:var(--ui-border)] bg-transparent p-2" value={catalog.query} maxLength={120} onChange={event => catalog.setQuery(event.target.value)} /></label>
        <label className="flex flex-col gap-1 text-sm">{text("purpose")}<select className="rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-2" value={catalog.purpose} onChange={event => catalog.setPurpose(event.target.value as OpenRouterPurpose)}>{(["chat", "tasks", "programming"] as const).map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label>
        <label className="flex flex-col gap-1 text-sm">{text("category")}<select className="rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-2" value={catalog.purpose === "programming" ? "programming" : catalog.category} disabled={catalog.purpose === "programming"} onChange={event => catalog.setCategory(event.target.value)}><option value="">{text("allCategories")}</option>{categories.map(value => <option key={value} value={value}>{text("categories." + value)}</option>)}</select></label>
        <Button type="submit" disabled={catalog.loading}>{text(catalog.loading ? "loading" : "search")}</Button>
      </div>
      <p className="text-xs text-[color:var(--ui-muted)]">{text("priceHint")}</p>
    </form>
    {catalog.results && <div className="space-y-3">
      <p className="text-sm">{text("results")}: {catalog.results.total}</p>
      {catalog.results.models.length === 0 && <p>{text("noResults")}</p>}
      <ul className="space-y-2">{catalog.results.models.map(model => card(model, connectedIds.has(model.id)))}</ul>
      <div className="flex gap-3">
        <Button variant="secondary" disabled={catalog.loading || catalog.results.offset === 0} onClick={() => void catalog.search(Math.max(0, catalog.results!.offset - catalog.results!.limit))}>{text("previous")}</Button>
        <Button variant="secondary" disabled={catalog.loading || catalog.results.next_offset === null} onClick={() => void catalog.search(catalog.results!.next_offset ?? 0)}>{text("next")}</Button>
      </div>
    </div>}
  </section>;
}
