import React from "react";
import { Search } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectMenu } from "@/components/ui/select-menu";
import {
    SectionHeader,
    EnrichedCatalogCard,
    InstalledCard,
    OperationRow
} from "./models-viewer-components";
import {
    formatDateTime
} from "@/lib/date";
import type { ModelCatalogEntry, ModelInfo, ModelOperation } from "@/lib/types";
import type { NewsItem } from "./models-helpers";
import { useModelsViewerLogic } from "./use-models-viewer-logic";
import { enrichCatalogModel } from "@/lib/model-domain-mapper";

type ModelsViewerLogic = ReturnType<typeof useModelsViewerLogic>;

function buildNewsItemKey(item: NewsItem, fallbackPrefix: string) {
    return item.url || `${fallbackPrefix}-${item.published_at || "no-date"}-${item.title || "untitled"}`;
}

interface RuntimeSectionProps {
    readonly selectedServer: ModelsViewerLogic["selectedServer"];
    readonly setSelectedServer: ModelsViewerLogic["setSelectedServer"];
    readonly serverOptions: ModelsViewerLogic["serverOptions"];
    readonly selectedModel: ModelsViewerLogic["selectedModel"];
    readonly setSelectedModel: ModelsViewerLogic["setSelectedModel"];
    readonly modelOptions: ModelsViewerLogic["modelOptions"];
    readonly activeRuntime: ModelsViewerLogic["activeRuntime"];
    readonly activeServer: ModelsViewerLogic["activeServer"];
    readonly installed: ModelsViewerLogic["installed"];
    readonly setActiveLlmServer: ModelsViewerLogic["setActiveLlmServer"];
    readonly switchModel: ModelsViewerLogic["switchModel"];
    readonly pushToast: ModelsViewerLogic["pushToast"];
    readonly t: ModelsViewerLogic["t"];
}

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
}: RuntimeSectionProps) {
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
                    <Link className="shrink-0 inline-flex items-center gap-2 text-xs underline underline-offset-2 transition hover:opacity-90 !text-[color:var(--secondary)]" href="/docs/llm-models">
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/15 text-[11px]">?</span>
                        {t("models.ui.instructions")}
                    </Link>
                </div>
            </div>
        </div>
    );
}

interface SearchSectionProps {
    readonly searchCollapsed: ModelsViewerLogic["searchCollapsed"];
    readonly setSearchCollapsed: ModelsViewerLogic["setSearchCollapsed"];
    readonly searchQuery: ModelsViewerLogic["searchQuery"];
    readonly setSearchQuery: ModelsViewerLogic["setSearchQuery"];
    readonly searchProvider: ModelsViewerLogic["searchProvider"];
    readonly setSearchProvider: ModelsViewerLogic["setSearchProvider"];
    readonly searchResults: ModelsViewerLogic["searchResults"];
    readonly handleSearch: ModelsViewerLogic["handleSearch"];
    readonly handleInstall: ModelsViewerLogic["handleInstall"];
    readonly pendingActions: ModelsViewerLogic["pendingActions"];
    readonly trainableModels: ModelsViewerLogic["trainableModels"];
    readonly t: ModelsViewerLogic["t"];
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
    trainableModels,
    t
}: SearchSectionProps) {
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
                                    onChange={(val) => setSearchProvider(val as "huggingface" | "ollama")}
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
                                {searchResults.data.map((model: ModelCatalogEntry) => {
                                    const enriched = enrichCatalogModel(model, trainableModels);
                                    return (
                                        <EnrichedCatalogCard
                                            key={`${model.provider}-${model.model_name}`}
                                            model={enriched}
                                            actionLabel={t("models.actions.install")}
                                            pending={pendingActions[`install:${model.provider}:${model.model_name}`]}
                                            onAction={() => handleInstall(model)}
                                        />
                                    );
                                })}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </section>
    );
}

interface NewsSectionProps {
    readonly newsCollapsed: ModelsViewerLogic["newsCollapsed"];
    readonly setNewsCollapsed: ModelsViewerLogic["setNewsCollapsed"];
    readonly newsHf: ModelsViewerLogic["newsHf"];
    readonly refreshNews: ModelsViewerLogic["refreshNews"];
    readonly newsSort: ModelsViewerLogic["newsSort"];
    readonly setNewsSort: ModelsViewerLogic["setNewsSort"];
    readonly language: ModelsViewerLogic["language"];
    readonly papersCollapsed: ModelsViewerLogic["papersCollapsed"];
    readonly setPapersCollapsed: ModelsViewerLogic["setPapersCollapsed"];
    readonly papersHf: ModelsViewerLogic["papersHf"];
    readonly refreshPapers: ModelsViewerLogic["refreshPapers"];
    readonly t: ModelsViewerLogic["t"];
}

export function NewsSection({
    newsCollapsed, setNewsCollapsed, newsHf, refreshNews, newsSort, setNewsSort, language,
    papersCollapsed, setPapersCollapsed, papersHf, refreshPapers,
    t
}: NewsSectionProps) {
    const sortedNews = newsSort === "oldest" ? [...newsHf.items].reverse() : newsHf.items;
    const sortedPapers = newsSort === "oldest" ? [...papersHf.items].reverse() : papersHf.items;

    const renderNewsBody = () => {
        if (newsHf.loading) {
            return <p className="text-xs text-slate-500">{t("models.ui.loading")}</p>;
        }
        if (newsHf.error) {
            return <p className="text-xs text-amber-200/70">{newsHf.error}</p>;
        }
        if (newsHf.items.length === 0) {
            return <p className="text-xs text-slate-500">{t("models.ui.noData")}</p>;
        }
        return (
            <div className="flex flex-col">
                {sortedNews.slice(0, 5).map((item: NewsItem) => (
                    <div key={buildNewsItemKey(item, "news")} className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 py-2.5 last:border-b-0 last:pb-0 first:pt-0">
                        <p className="min-w-0 flex-1 text-sm font-medium text-slate-200 line-clamp-1">{item.title || "Nowa publikacja"}</p>
                        <div className="flex items-center gap-4">
                            <span className="text-[10px] tabular-nums text-slate-500 whitespace-nowrap">{formatDateTime(item.published_at, language, "news")}</span>
                            {item.url && <a className="rounded-full border border-white/10 px-2.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-slate-400 hover:border-white/30 hover:text-white" href={item.url} target="_blank" rel="noreferrer">{t("models.ui.view")}</a>}
                        </div>
                    </div>
                ))}
            </div>
        );
    };

    const renderPapersBody = () => {
        if (papersHf.loading) {
            return <p className="col-span-full text-xs text-slate-500">{t("models.ui.loading")}</p>;
        }
        if (papersHf.error) {
            return <p className="col-span-full text-xs text-amber-200/70">{papersHf.error}</p>;
        }
        if (papersHf.items.length === 0) {
            return <p className="col-span-full text-xs text-slate-500">{t("models.ui.noData")}</p>;
        }
        return sortedPapers.slice(0, 3).map((item: NewsItem) => (
            <div key={buildNewsItemKey(item, "paper")} className="flex h-full flex-col rounded-2xl border border-white/10 bg-black/30 p-4 text-sm">
                <p className="text-sm font-semibold text-slate-100 line-clamp-2">{item.title || t("models.sections.papers.defaultTitle")}</p>
                <p className="mt-2 text-[11px] text-slate-400 line-clamp-3 leading-relaxed">{item.summary || t("models.sections.papers.noPreview")}</p>
                <div className="mt-auto pt-4 flex items-center justify-between text-[10px] text-slate-500">
                    <span>{formatDateTime(item.published_at, language, "news")}</span>
                    {item.url && <a className="rounded-full border border-white/10 px-3 py-1 text-[9px] uppercase tracking-[0.1em] text-slate-400 hover:border-white/30 hover:text-white" href={item.url} target="_blank" rel="noreferrer">{t("models.ui.view")}</a>}
                </div>
            </div>
        ));
    };

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
                                onChange={(e) => setNewsSort(e.target.value as "newest" | "oldest")}
                            >
                                <option value="newest">{t("models.ui.newest")}</option>
                                <option value="oldest">{t("models.ui.oldest")}</option>
                            </select>
                        </div>
                    }
                />
                {!newsCollapsed && (
                    <div className="mt-5 rounded-2xl border border-white/10 bg-black/30 p-4">
                        {renderNewsBody()}
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
                        {renderPapersBody()}
                    </div>
                )}
            </div>
        </section>
    );
}

interface RecommendedAndCatalogProps {
    readonly trendingCollapsed: ModelsViewerLogic["trendingCollapsed"];
    readonly setTrendingCollapsed: ModelsViewerLogic["setTrendingCollapsed"];
    readonly trendingHf: ModelsViewerLogic["trendingHf"];
    readonly trendingOllama: ModelsViewerLogic["trendingOllama"];
    readonly refreshTrending: ModelsViewerLogic["refreshTrending"];
    readonly catalogCollapsed: ModelsViewerLogic["catalogCollapsed"];
    readonly setCatalogCollapsed: ModelsViewerLogic["setCatalogCollapsed"];
    readonly catalogHf: ModelsViewerLogic["catalogHf"];
    readonly catalogOllama: ModelsViewerLogic["catalogOllama"];
    readonly refreshCatalog: ModelsViewerLogic["refreshCatalog"];
    readonly handleInstall: ModelsViewerLogic["handleInstall"];
    readonly pendingActions: ModelsViewerLogic["pendingActions"];
    readonly trainableModels: ModelsViewerLogic["trainableModels"];
    readonly t: ModelsViewerLogic["t"];
}

export function RecommendedAndCatalog({
    trendingCollapsed, setTrendingCollapsed, trendingHf, trendingOllama, refreshTrending,
    catalogCollapsed, setCatalogCollapsed, catalogHf, catalogOllama, refreshCatalog,
    handleInstall, pendingActions, trainableModels,
    t
}: RecommendedAndCatalogProps) {
    return (
        <div className="flex flex-col gap-10">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
                <SectionHeader
                    title={t("models.sections.recommended.title")}
                    subtitle={t("models.sections.recommended.subtitle")}
                    description={t("models.sections.recommended.description")}
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
                                        {p.res.data.slice(0, 4).map((m: ModelCatalogEntry) => {
                                            const enriched = enrichCatalogModel(m, trainableModels);
                                            return (
                                                <EnrichedCatalogCard
                                                    key={m.model_name}
                                                    model={enriched}
                                                    actionLabel={t("models.actions.install")}
                                                    pending={pendingActions[`install:${m.provider}:${m.model_name}`]}
                                                    onAction={() => handleInstall(m)}
                                                />
                                            );
                                        })}
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
                    description={t("models.sections.catalog.description")}
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
                                        {p.res.data.slice(0, 6).map((m: ModelCatalogEntry) => {
                                            const enriched = enrichCatalogModel(m, trainableModels);
                                            return (
                                                <EnrichedCatalogCard
                                                    key={m.model_name}
                                                    model={enriched}
                                                    actionLabel={t("models.actions.install")}
                                                    pending={pendingActions[`install:${m.provider}:${m.model_name}`]}
                                                    onAction={() => handleInstall(m)}
                                                />
                                            );
                                        })}
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

interface InstalledAndOperationsProps {
    readonly installedCollapsed: ModelsViewerLogic["installedCollapsed"];
    readonly setInstalledCollapsed: ModelsViewerLogic["setInstalledCollapsed"];
    readonly installed: ModelsViewerLogic["installed"];
    readonly installedBuckets: ModelsViewerLogic["installedBuckets"];
    readonly installedModels: ModelsViewerLogic["installedModels"];
    readonly handleActivate: ModelsViewerLogic["handleActivate"];
    readonly handleRemove: ModelsViewerLogic["handleRemove"];
    readonly pendingActions: ModelsViewerLogic["pendingActions"];
    readonly operationsCollapsed: ModelsViewerLogic["operationsCollapsed"];
    readonly setOperationsCollapsed: ModelsViewerLogic["setOperationsCollapsed"];
    readonly operations: ModelsViewerLogic["operations"];
    readonly t: ModelsViewerLogic["t"];
}

export function InstalledAndOperations({
    installedCollapsed, setInstalledCollapsed, installed, installedBuckets, installedModels,
    handleActivate, handleRemove, pendingActions,
    operationsCollapsed, setOperationsCollapsed, operations,
    t
}: InstalledAndOperationsProps) {
    const allowRemoveProviders = new Set(["ollama", "huggingface"]);
    const runtimeLabels: Record<string, string> = {
        ollama: "Ollama",
        vllm: "vLLM",
        onnx: "ONNX",
    };
    const providerSections = Object.entries(installedBuckets).map(([provider, data]) => ({
        provider,
        label: runtimeLabels[provider] ?? provider.toUpperCase(),
        data,
    }));
    let installedBadge = t("models.sections.installed.noModels");
    if (installedModels.length) {
        const suffix = installedModels.length > 1 ? "s" : "";
        installedBadge = `${installedModels.length} ${t("models.runtime.model").toLowerCase()}${suffix}`;
    }

    const renderOperationsBody = () => {
        if (operations.loading) {
            return <p className="text-xs text-slate-500">{t("models.ui.loading")}</p>;
        }
        if (operations.data?.operations?.length) {
            return operations.data.operations.map((op: ModelOperation) => (
                <OperationRow key={op.operation_id} op={op} />
            ));
        }
        return <p className="text-xs text-slate-500">{t("models.sections.operations.noOperations")}</p>;
    };

    return (
        <div className="flex flex-col gap-10">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
                <SectionHeader
                    title={t("models.sections.installed.title")}
                    subtitle={t("models.sections.installed.subtitle")}
                    badge={installedBadge}
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
                                {providerSections.length === 0 && (
                                    <p className="text-[11px] text-slate-500">{t("models.sections.installed.noModels")}</p>
                                )}
                                {providerSections.map(p => (
                                    <div key={p.label} className="rounded-2xl border border-white/10 bg-black/30 p-4">
                                        <div className="flex items-center justify-between mb-3">
                                            <p className="text-[10px] uppercase tracking-widest text-slate-400 font-semibold">{p.label}</p>
                                            <Badge tone="neutral" className="text-[9px]">{p.data.length}</Badge>
                                        </div>
                                        <div className="grid gap-3">
                                            {p.data.length ? p.data.map((m: ModelInfo) => (
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
                        {renderOperationsBody()}
                    </div>
                )}
            </div>
        </div>
    );
}

type RemoteModelsSectionProps = ModelsViewerLogic;

export function RemoteModelsSection(props: RemoteModelsSectionProps) {
    const {
        t,
        remoteProviders,
        remoteProvidersLoading,
        remoteProvidersError,
        fetchRemoteProviders,
        remoteCatalog,
        remoteCatalogLoading,
        remoteCatalogError,
        remoteCatalogRefreshedAt,
        remoteCatalogSource,
        fetchRemoteCatalog,
        remoteBindings,
        remoteBindingsLoading,
        remoteBindingsError,
        fetchRemoteBindings,
    } = props;

    const [selectedProvider, setSelectedProvider] = React.useState<string | null>(null);

    // Fetch catalog when provider is selected
    React.useEffect(() => {
        if (selectedProvider) {
            fetchRemoteCatalog(selectedProvider);
        }
    }, [selectedProvider, fetchRemoteCatalog]);

    return (
        <div className="space-y-10">
            {/* Provider Status Section */}
            <div className="w-full rounded-[24px] border border-white/10 bg-black/20 p-6 text-sm text-slate-200 shadow-card">
                <SectionHeader
                    title={t("models.sections.remote.providerStatus.title")}
                    subtitle={t("models.sections.remote.providerStatus.subtitle")}
                    actionLabel={t("models.ui.refresh")}
                    actionDisabled={remoteProvidersLoading}
                    onAction={fetchRemoteProviders}
                />
                <div className="mt-5 space-y-3">
                    {remoteProvidersLoading && (
                        <p className="text-xs text-slate-400">{t("models.ui.loading")}</p>
                    )}
                    {remoteProvidersError && (
                        <Badge tone="danger">{remoteProvidersError}</Badge>
                    )}
                    {!remoteProvidersLoading && !remoteProvidersError && remoteProviders.length === 0 && (
                        <p className="text-xs text-slate-400">{t("models.sections.remote.providerStatus.noProviders")}</p>
                    )}
                    {remoteProviders.map((provider) => (
                        <div key={provider.provider} className="flex items-center justify-between rounded-2xl border border-white/10 bg-black/30 p-4">
                            <div className="flex items-center gap-3">
                                <span className="text-sm font-medium capitalize">{provider.provider}</span>
                                <Badge tone={provider.status === "configured" ? "success" : "neutral"}>
                                    {provider.status}
                                </Badge>
                            </div>
                            <div className="flex items-center gap-4 text-xs text-slate-400">
                                {provider.latency_ms && (
                                    <span>{t("models.sections.remote.providerStatus.latency")}: {provider.latency_ms.toFixed(0)}ms</span>
                                )}
                                <span>{t("models.sections.remote.providerStatus.lastCheck")}: {formatDateTime(provider.last_check)}</span>
                                {provider.error && (
                                    <Badge tone="danger">{provider.error}</Badge>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Remote Models Catalog Section */}
            <div className="w-full rounded-[24px] border border-white/10 bg-black/20 p-6 text-sm text-slate-200 shadow-card">
                <SectionHeader
                    title={t("models.sections.remote.catalog.title")}
                    subtitle={t("models.sections.remote.catalog.subtitle")}
                />
                <div className="mt-4 flex items-center gap-3">
                    <span className="whitespace-nowrap text-[11px] uppercase tracking-[0.3em] text-slate-400">
                        {t("models.sections.remote.catalog.provider")}
                    </span>
                    <SelectMenu
                        value={selectedProvider || ""}
                        options={[
                            { value: "openai", label: "OpenAI" },
                            { value: "google", label: "Google" },
                        ]}
                        onChange={(val) => setSelectedProvider(val || null)}
                        placeholder={t("models.runtime.select")}
                        className="w-[180px]"
                        buttonClassName="w-full justify-between rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium normal-case tracking-normal text-slate-100 hover:border-white/30 hover:bg-white/10"
                        renderButton={(opt) => <span className="flex-1 truncate text-left">{opt?.label ?? t("models.runtime.select")}</span>}
                        renderOption={(opt) => <span className="w-full text-left text-sm normal-case tracking-normal text-slate-100">{opt.label}</span>}
                    />
                </div>
                <div className="mt-5 space-y-3">
                    {remoteCatalogLoading && (
                        <p className="text-xs text-slate-400">{t("models.ui.loading")}</p>
                    )}
                    {remoteCatalogError && (
                        <Badge tone="danger">{remoteCatalogError}</Badge>
                    )}
                    {!remoteCatalogLoading && !remoteCatalogError && remoteCatalog.length === 0 && selectedProvider && (
                        <p className="text-xs text-slate-400">{t("models.sections.remote.catalog.noModels")}</p>
                    )}
                    {remoteCatalog.map((model) => (
                        <div key={model.id} className="flex items-start justify-between rounded-2xl border border-white/10 bg-black/30 p-4">
                            <div className="flex-1">
                                <div className="flex items-center gap-3">
                                    <span className="text-sm font-medium">{model.name}</span>
                                    <Badge tone="neutral" className="text-[10px]">{model.provider}</Badge>
                                </div>
                                {model.model_alias && (
                                    <p className="mt-1 text-xs text-slate-400">{model.model_alias}</p>
                                )}
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                    {model.capabilities.map((cap) => (
                                        <Badge key={cap} tone="success" className="text-[10px]">
                                            {cap}
                                        </Badge>
                                    ))}
                                </div>
                            </div>
                        </div>
                    ))}
                    {remoteCatalogRefreshedAt && remoteCatalogSource && (
                        <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                            <span>{t("models.sections.remote.catalog.source")}: {remoteCatalogSource}</span>
                            <span>{t("models.sections.remote.catalog.refreshed")}: {formatDateTime(remoteCatalogRefreshedAt)}</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Connectivity Map Section */}
            <div className="w-full rounded-[24px] border border-white/10 bg-black/20 p-6 text-sm text-slate-200 shadow-card">
                <SectionHeader
                    title={t("models.sections.remote.connectivity.title")}
                    subtitle={t("models.sections.remote.connectivity.subtitle")}
                    actionLabel={t("models.ui.refresh")}
                    actionDisabled={remoteBindingsLoading}
                    onAction={fetchRemoteBindings}
                />
                <div className="mt-5">
                    {remoteBindingsLoading && (
                        <p className="text-xs text-slate-400">{t("models.ui.loading")}</p>
                    )}
                    {remoteBindingsError && (
                        <Badge tone="danger">{remoteBindingsError}</Badge>
                    )}
                    {!remoteBindingsLoading && !remoteBindingsError && remoteBindings.length === 0 && (
                        <p className="text-xs text-slate-400">{t("models.sections.remote.connectivity.noBindings")}</p>
                    )}
                    {!remoteBindingsLoading && !remoteBindingsError && remoteBindings.length > 0 && (
                        <div className="overflow-x-auto">
                            <table className="w-full border-collapse">
                                <thead>
                                    <tr className="border-b border-white/10">
                                        <th className="px-3 py-2 text-left text-xs uppercase tracking-wider text-slate-400">
                                            {t("models.sections.remote.connectivity.service")}
                                        </th>
                                        <th className="px-3 py-2 text-left text-xs uppercase tracking-wider text-slate-400">
                                            {t("models.sections.remote.connectivity.endpoint")}
                                        </th>
                                        <th className="px-3 py-2 text-left text-xs uppercase tracking-wider text-slate-400">
                                            {t("models.sections.remote.connectivity.method")}
                                        </th>
                                        <th className="px-3 py-2 text-left text-xs uppercase tracking-wider text-slate-400">
                                            {t("models.sections.remote.connectivity.provider")}
                                        </th>
                                        <th className="px-3 py-2 text-left text-xs uppercase tracking-wider text-slate-400">
                                            {t("models.sections.remote.connectivity.model")}
                                        </th>
                                        <th className="px-3 py-2 text-left text-xs uppercase tracking-wider text-slate-400">
                                            {t("models.sections.remote.connectivity.routing")}
                                        </th>
                                        <th className="px-3 py-2 text-left text-xs uppercase tracking-wider text-slate-400">
                                            {t("models.sections.remote.connectivity.status")}
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {remoteBindings.map((binding, idx) => (
                                        <tr key={idx} className="border-b border-white/5 hover:bg-white/5">
                                            <td className="px-3 py-3 text-xs">{binding.service_id}</td>
                                            <td className="px-3 py-3 text-xs font-mono">{binding.endpoint}</td>
                                            <td className="px-3 py-3 text-xs">
                                                <Badge tone="neutral" className="text-[10px]">{binding.http_method}</Badge>
                                            </td>
                                            <td className="px-3 py-3 text-xs capitalize">{binding.provider}</td>
                                            <td className="px-3 py-3 text-xs">{binding.model}</td>
                                            <td className="px-3 py-3 text-xs">
                                                <Badge tone="neutral" className="text-[10px]">{binding.routing_mode}</Badge>
                                                {binding.fallback_order && binding.fallback_order.length > 0 && (
                                                    <span className="ml-2 text-[10px] text-slate-400">
                                                        ({binding.fallback_order.join(" → ")})
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-3 py-3 text-xs">
                                                <Badge tone={binding.status === "active" ? "success" : "neutral"}>
                                                    {binding.status}
                                                </Badge>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>

            {/* Policy/Runtime Section */}
            <div className="w-full rounded-[24px] border border-white/10 bg-black/20 p-6 text-sm text-slate-200 shadow-card">
                <SectionHeader
                    title={t("models.sections.remote.policy.title")}
                    subtitle={t("models.sections.remote.policy.subtitle")}
                />
                <div className="mt-5 space-y-3">
                    <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-black/30 p-4">
                        <span className="text-sm">{t("models.sections.remote.policy.localFirst")}</span>
                        <Badge tone="success">Enabled</Badge>
                    </div>
                    <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-black/30 p-4">
                        <span className="text-sm">{t("models.sections.remote.policy.fallback")}</span>
                        <span className="text-xs text-slate-400">ollama → vllm → openai → google</span>
                    </div>
                    <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-black/30 p-4">
                        <span className="text-sm">{t("models.sections.remote.policy.rateClass")}</span>
                        <Badge tone="neutral">Standard</Badge>
                    </div>
                </div>
            </div>
        </div>
    );
}
