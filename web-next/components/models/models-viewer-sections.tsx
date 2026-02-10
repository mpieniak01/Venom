import React from "react";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectMenu } from "@/components/ui/select-menu";
import {
    SectionHeader,
    CatalogCard,
    InstalledCard,
    OperationRow
} from "./models-viewer-components";
import {
    formatDateTime
} from "@/lib/date";

export function RuntimeSection({
    selectedServer,
    setSelectedServer,
    serverOptions,
    selectedModel,
    setSelectedModel,
    modelOptions,
    activeRuntime,
    activeServer,
    installed,
    setActiveLlmServer,
    switchModel,
    pushToast,
    t
}: any) {
    return (
        <div className="w-full rounded-[24px] border border-white/10 bg-black/20 p-6 text-sm text-slate-200 shadow-card">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <p className="text-xs uppercase tracking-[0.35em] text-slate-400">{t("models.runtime.title")}</p>
                    <p className="mt-1 text-sm text-slate-300">{t("models.runtime.description")}</p>
                </div>
                {installed.error && <Badge tone="warning">{installed.error}</Badge>}
            </div>
            <div className="mt-4 rounded-2xl border border-white/10 bg-black/30 p-4">
                <div className="flex w-full flex-nowrap items-center gap-3 overflow-x-auto">
                    <span className="whitespace-nowrap text-[11px] uppercase tracking-[0.3em] text-slate-400">
                        {t("models.runtime.server")}
                    </span>
                    <SelectMenu
                        value={selectedServer || activeRuntime?.provider || ""}
                        options={serverOptions}
                        onChange={(val) => setSelectedServer(val || null)}
                        placeholder={t("models.runtime.select")}
                        className="w-[180px] shrink-0"
                        buttonClassName="w-full justify-between rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium normal-case tracking-normal text-slate-100 hover:border-white/30 hover:bg-white/10 overflow-hidden"
                        renderButton={(opt) => <span className="flex-1 truncate text-left text-slate-100">{opt?.label ?? t("models.runtime.select")}</span>}
                        renderOption={(opt) => <span className="w-full text-left text-sm normal-case tracking-normal text-slate-100">{opt.label}</span>}
                    />
                    <span className="whitespace-nowrap text-[11px] uppercase tracking-[0.3em] text-slate-400">
                        {t("models.runtime.model")}
                    </span>
                    <SelectMenu
                        value={selectedModel || activeRuntime?.model || ""}
                        options={modelOptions}
                        onChange={(val) => setSelectedModel(val || null)}
                        placeholder={t("models.runtime.select")}
                        className="flex-1 min-w-[200px]"
                        buttonClassName="w-full justify-between rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium normal-case tracking-normal text-slate-100 hover:border-white/30 hover:bg-white/10 overflow-hidden"
                        renderButton={(opt) => <span className="flex-1 truncate text-left">{opt?.label ?? t("models.runtime.select")}</span>}
                        renderOption={(opt) => <span className="w-full text-left text-sm normal-case tracking-normal text-slate-100">{opt.label}</span>}
                    />
                    <Button
                        size="sm"
                        className="shrink-0 rounded-full px-5"
                        variant="secondary"
                        disabled={!selectedServer || !selectedModel}
                        onClick={async () => {
                            if (!selectedServer || !selectedModel) return;
                            try {
                                const isActive = activeServer.data?.active_server === selectedServer;
                                if (!isActive) await setActiveLlmServer(selectedServer);
                                if (selectedModel !== activeRuntime?.model || !isActive) await switchModel(selectedModel);
                                pushToast(t("models.runtime.activated", { model: selectedModel, server: selectedServer }), "success");
                                await Promise.all([activeServer.refresh(), installed.refresh()]);
                            } catch {
                                pushToast("Nie udało się aktywować modelu", "error");
                            }
                        }}
                    >
                        Aktywuj
                    </Button>
                    <a className="shrink-0 inline-flex items-center gap-2 text-xs underline underline-offset-2 transition hover:opacity-90 !text-[color:var(--secondary)]" href="/docs/llm-models">
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/15 text-[11px]">?</span>
                        {t("models.ui.instructions")}
                    </a>
                </div>
            </div>
        </div>
    );
}

export function SearchSection({
    searchCollapsed,
    setSearchCollapsed,
    searchQuery,
    setSearchQuery,
    searchProvider,
    setSearchProvider,
    searchResults,
    handleSearch,
    handleInstall,
    pendingActions,
    t
}: any) {
    return (
        <section className="grid gap-10">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
                <SectionHeader
                    title={t("models.search.title")}
                    subtitle={t("models.search.subtitle")}
                    isCollapsed={searchCollapsed}
                    onToggle={() => setSearchCollapsed(!searchCollapsed)}
                />
                {!searchCollapsed && (
                    <div className="mt-5">
                        <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
                            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                                <div className="flex h-9 min-w-[200px] flex-1 items-center gap-3 rounded-full border border-white/10 bg-white/5 px-4 mr-4">
                                    <Search className="h-4 w-4 shrink-0 text-slate-400" />
                                    <input
                                        type="text"
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                        onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                                        placeholder={t("models.search.placeholder")}
                                        className="h-full w-full border-none !bg-transparent p-0 text-xs text-slate-100 placeholder-slate-500 !outline-none !ring-0 z-10"
                                    />
                                </div>
                                <SelectMenu
                                    value={searchProvider}
                                    options={[
                                        { value: "huggingface", label: "HuggingFace" },
                                        { value: "ollama", label: "Ollama" },
                                    ]}
                                    onChange={(val) => setSearchProvider(val as any)}
                                    className="w-full sm:w-[160px]"
                                    buttonClassName="w-full justify-between rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-100 hover:border-white/30 hover:bg-white/10"
                                    renderButton={(opt) => <span className="flex-1 truncate text-left text-slate-100 uppercase tracking-wider text-[10px]">{opt?.label ?? "Provider"}</span>}
                                />
                                <Button onClick={handleSearch} disabled={searchResults.loading || !searchQuery.trim()} className="rounded-full px-6 text-xs" size="sm" variant="secondary">
                                    {searchResults.loading ? t("models.search.searching") : t("models.search.button")}
                                </Button>
                            </div>
                        </div>
                        {searchResults.error && <p className="mt-4 text-sm text-amber-200">{searchResults.error}</p>}
                        {searchResults.performed && !searchResults.loading && searchResults.data.length === 0 && !searchResults.error && (
                            <p className="mt-4 text-sm text-slate-400">{t("models.ui.noResults", { query: searchQuery })}</p>
                        )}
                        {searchResults.data.length > 0 && (
                            <div className="mt-6 grid gap-4 lg:grid-cols-2">
                                {searchResults.data.map((model: any) => (
                                    <CatalogCard
                                        key={`${model.provider}-${model.model_name}`}
                                        model={model}
                                        actionLabel={t("models.actions.install")}
                                        pending={pendingActions[`install:${model.provider}:${model.model_name}`]}
                                        onAction={() => handleInstall(model)}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </section>
    );
}

export function NewsSection({
    newsCollapsed, setNewsCollapsed, newsHf, refreshNews, newsSort, setNewsSort, language,
    papersCollapsed, setPapersCollapsed, papersHf, refreshPapers,
    t
}: any) {
    const sortedNews = newsSort === "oldest" ? [...newsHf.items].reverse() : newsHf.items;
    const sortedPapers = newsSort === "oldest" ? [...papersHf.items].reverse() : papersHf.items;

    return (
        <section className="grid gap-10">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
                <SectionHeader
                    title={t("models.sections.news.title")}
                    subtitle={t("models.sections.news.subtitle")}
                    actionLabel={t("models.ui.refresh")}
                    actionDisabled={newsHf.loading}
                    onAction={refreshNews}
                    badge={newsHf.stale ? t("models.ui.offlineCache") : undefined}
                    isCollapsed={newsCollapsed}
                    onToggle={() => setNewsCollapsed(!newsCollapsed)}
                    extra={
                        <div className="flex items-center gap-3">
                            <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500 whitespace-nowrap">{t("models.ui.sort")}</span>
                            <select
                                className="h-7 rounded-full border border-white/10 bg-white/5 px-3 text-[10px] text-slate-200 outline-none hover:border-white/20"
                                value={newsSort}
                                onChange={(e) => setNewsSort(e.target.value as any)}
                            >
                                <option value="newest">{t("models.ui.newest")}</option>
                                <option value="oldest">{t("models.ui.oldest")}</option>
                            </select>
                        </div>
                    }
                />
                {!newsCollapsed && (
                    <div className="mt-5 rounded-2xl border border-white/10 bg-black/30 p-4">
                        {newsHf.loading ? <p className="text-xs text-slate-500">{t("models.ui.loading")}</p> :
                            newsHf.error ? <p className="text-xs text-amber-200/70">{newsHf.error}</p> :
                                newsHf.items.length === 0 ? <p className="text-xs text-slate-500">{t("models.ui.noData")}</p> : (
                                    <div className="flex flex-col">
                                        {sortedNews.slice(0, 5).map((item: any, idx: number) => (
                                            <div key={idx} className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 py-2.5 last:border-b-0 last:pb-0 first:pt-0">
                                                <p className="min-w-0 flex-1 text-sm font-medium text-slate-200 line-clamp-1">{item.title || "Nowa publikacja"}</p>
                                                <div className="flex items-center gap-4">
                                                    <span className="text-[10px] tabular-nums text-slate-500 whitespace-nowrap">{formatDateTime(item.published_at, language, "news")}</span>
                                                    {item.url && <a className="rounded-full border border-white/10 px-2.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-slate-400 hover:border-white/30 hover:text-white" href={item.url} target="_blank" rel="noreferrer">{t("models.ui.view")}</a>}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                    </div>
                )}
            </div>

            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
                <SectionHeader
                    title={t("models.sections.papers.title")}
                    subtitle={t("models.sections.papers.subtitle")}
                    actionLabel={t("models.sections.papers.refreshAction")}
                    actionDisabled={papersHf.loading}
                    onAction={refreshPapers}
                    badge={papersHf.stale ? t("models.ui.offlineCache") : undefined}
                    isCollapsed={papersCollapsed}
                    onToggle={() => setPapersCollapsed(!papersCollapsed)}
                />
                {!papersCollapsed && (
                    <div className="mt-5 grid gap-4 lg:grid-cols-3">
                        {papersHf.loading ? <p className="col-span-full text-xs text-slate-500">{t("models.ui.loading")}</p> :
                            papersHf.error ? <p className="col-span-full text-xs text-amber-200/70">{papersHf.error}</p> :
                                papersHf.items.length === 0 ? <p className="col-span-full text-xs text-slate-500">{t("models.ui.noData")}</p> :
                                    sortedPapers.slice(0, 3).map((item: any, idx: number) => (
                                        <div key={idx} className="flex h-full flex-col rounded-2xl border border-white/10 bg-black/30 p-4 text-sm">
                                            <p className="text-sm font-semibold text-slate-100 line-clamp-2">{item.title || t("models.sections.papers.defaultTitle")}</p>
                                            <p className="mt-2 text-[11px] text-slate-400 line-clamp-3 leading-relaxed">{item.summary || t("models.sections.papers.noPreview")}</p>
                                            <div className="mt-auto pt-4 flex items-center justify-between text-[10px] text-slate-500">
                                                <span>{formatDateTime(item.published_at, language, "news")}</span>
                                                {item.url && <a className="rounded-full border border-white/10 px-3 py-1 text-[9px] uppercase tracking-[0.1em] text-slate-400 hover:border-white/30 hover:text-white" href={item.url} target="_blank" rel="noreferrer">{t("models.ui.view")}</a>}
                                            </div>
                                        </div>
                                    ))
                        }
                    </div>
                )}
            </div>
        </section>
    );
}

export function RecommendedAndCatalog({
    trendingCollapsed, setTrendingCollapsed, trendingHf, trendingOllama, refreshTrending,
    catalogCollapsed, setCatalogCollapsed, catalogHf, catalogOllama, refreshCatalog,
    handleInstall, pendingActions,
    t
}: any) {
    return (
        <div className="flex flex-col gap-10">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
                <SectionHeader
                    title={t("models.sections.recommended.title")}
                    subtitle={t("models.sections.recommended.subtitle")}
                    actionLabel={t("models.ui.refresh")}
                    actionDisabled={trendingHf.loading || trendingOllama.loading}
                    onAction={refreshTrending}
                    isCollapsed={trendingCollapsed}
                    onToggle={() => setTrendingCollapsed(!trendingCollapsed)}
                />
                {!trendingCollapsed && (
                    <div className="mt-5 grid gap-6 lg:grid-cols-2">
                        {[{ label: 'Ollama', res: trendingOllama }, { label: 'HuggingFace', res: trendingHf }].map(p => (
                            <div key={p.label} className="flex flex-col gap-4">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-xs uppercase tracking-widest text-slate-400 font-semibold">{p.label}</h3>
                                    {p.res.stale && <Badge tone="warning" className="text-[9px]">{t("models.ui.offlineCache")}</Badge>}
                                </div>
                                {p.res.loading ? <p className="text-xs text-slate-500">{t("models.ui.loading")}</p> : (
                                    <div className="grid gap-4">
                                        {p.res.data.slice(0, 4).map((m: any) => (
                                            <CatalogCard key={m.model_name} model={m} actionLabel={t("models.actions.install")} pending={pendingActions[`install:${m.provider}:${m.model_name}`]} onAction={() => handleInstall(m)} />
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
                <SectionHeader
                    title={t("models.sections.catalog.title")}
                    subtitle={t("models.sections.catalog.subtitle")}
                    actionLabel={t("models.ui.refresh")}
                    actionDisabled={catalogHf.loading || catalogOllama.loading}
                    onAction={refreshCatalog}
                    isCollapsed={catalogCollapsed}
                    onToggle={() => setCatalogCollapsed(!catalogCollapsed)}
                />
                {!catalogCollapsed && (
                    <div className="mt-5 grid gap-6 lg:grid-cols-2">
                        {[{ label: 'Ollama', res: catalogOllama }, { label: 'HuggingFace', res: catalogHf }].map(p => (
                            <div key={p.label} className="flex flex-col gap-4">
                                <h3 className="text-xs uppercase tracking-widest text-slate-400 font-semibold">{p.label}</h3>
                                {p.res.loading ? <p className="text-xs text-slate-500">{t("models.ui.loading")}</p> : (
                                    <div className="grid gap-4">
                                        {p.res.data.slice(0, 6).map((m: any) => (
                                            <CatalogCard key={m.model_name} model={m} actionLabel="Zainstaluj" pending={pendingActions[`install:${m.provider}:${m.model_name}`]} onAction={() => handleInstall(m)} />
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

export function InstalledAndOperations({
    installedCollapsed, setInstalledCollapsed, installed, installedBuckets, installedModels,
    handleActivate, handleRemove, pendingActions,
    operationsCollapsed, setOperationsCollapsed, operations,
    t
}: any) {
    const allowRemoveProviders = new Set(["ollama", "huggingface"]);

    return (
        <div className="flex flex-col gap-10">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
                <SectionHeader
                    title={t("models.sections.installed.title")}
                    subtitle={t("models.sections.installed.subtitle")}
                    badge={installedModels.length ? `${installedModels.length} ${t("models.runtime.model").toLowerCase()}${installedModels.length > 1 ? "s" : ""}` : t("models.sections.installed.noModels")}
                    actionLabel={t("models.ui.refresh")}
                    actionDisabled={installed.loading}
                    onAction={installed.refresh}
                    isCollapsed={installedCollapsed}
                    onToggle={() => setInstalledCollapsed(!installedCollapsed)}
                />
                {!installedCollapsed && (
                    <div className="mt-5 space-y-6">
                        {installed.loading ? <p className="text-xs text-slate-500">{t("models.ui.loading")}</p> : (
                            <>
                                {[{ label: 'Ollama', data: installedBuckets.ollama }, { label: 'vLLM', data: installedBuckets.vllm }].map(p => (
                                    <div key={p.label} className="rounded-2xl border border-white/10 bg-black/30 p-4">
                                        <div className="flex items-center justify-between mb-3">
                                            <p className="text-[10px] uppercase tracking-widest text-slate-400 font-semibold">{p.label}</p>
                                            <Badge tone="neutral" className="text-[9px]">{p.data.length}</Badge>
                                        </div>
                                        <div className="grid gap-3">
                                            {p.data.length ? p.data.map((m: any) => (
                                                <InstalledCard
                                                    key={m.name} model={m}
                                                    pendingActivate={pendingActions[`activate:${m.name}`]}
                                                    pendingRemove={pendingActions[`remove:${m.name}`]}
                                                    onActivate={() => handleActivate(m)}
                                                    onRemove={allowRemoveProviders.has(m.provider ?? m.source ?? "") ? () => handleRemove(m) : undefined}
                                                    allowRemoveProviders={allowRemoveProviders}
                                                />
                                            )) : <p className="text-[11px] text-slate-500">{t("models.sections.installed.noModels")}</p>}
                                        </div>
                                    </div>
                                ))}
                            </>
                        )}
                    </div>
                )}
            </div>

            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
                <SectionHeader
                    title={t("models.sections.operations.title")}
                    subtitle={t("models.sections.operations.subtitle")}
                    actionLabel={t("models.ui.refresh")}
                    actionDisabled={operations.loading}
                    onAction={operations.refresh}
                    isCollapsed={operationsCollapsed}
                    onToggle={() => setOperationsCollapsed(!operationsCollapsed)}
                />
                {!operationsCollapsed && (
                    <div className="mt-5 flex flex-col gap-3">
                        {operations.loading ? <p className="text-xs text-slate-500">{t("models.ui.loading")}</p> :
                            operations.data?.operations?.length ? operations.data.operations.map((op: any) => <OperationRow key={op.operation_id} op={op} />) :
                                <p className="text-xs text-slate-500">{t("models.sections.operations.noOperations")}</p>
                        }
                    </div>
                )}
            </div>
        </div>
    );
}
