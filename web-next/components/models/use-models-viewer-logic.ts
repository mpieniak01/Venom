import { useNews } from "./hooks/use-news";
import { useModelCatalog } from "./hooks/use-model-catalog";
import { useRuntime } from "./hooks/use-runtime";
import { useLanguage } from "@/lib/i18n";

export function useModelsViewerLogic() {
    const { t, language } = useLanguage();

    // Split hooks
    const news = useNews();
    const catalog = useModelCatalog();
    const runtime = useRuntime();

    return {
        t, language,
        // News
        newsHf: news.newsHf, refreshNews: news.refreshNews,
        papersHf: news.papersHf, refreshPapers: news.refreshPapers,
        newsSort: news.newsSort, setNewsSort: news.setNewsSort,
        newsCollapsed: news.newsCollapsed, setNewsCollapsed: news.setNewsCollapsed,
        papersCollapsed: news.papersCollapsed, setPapersCollapsed: news.setPapersCollapsed,

        // Catalog & Search
        trendingCollapsed: catalog.trendingCollapsed, setTrendingCollapsed: catalog.setTrendingCollapsed,
        catalogCollapsed: catalog.catalogCollapsed, setCatalogCollapsed: catalog.setCatalogCollapsed,
        searchCollapsed: catalog.searchCollapsed, setSearchCollapsed: catalog.setSearchCollapsed,
        searchQuery: catalog.searchQuery, setSearchQuery: catalog.setSearchQuery,
        searchProvider: catalog.searchProvider, setSearchProvider: catalog.setSearchProvider,
        searchResults: catalog.searchResults, handleSearch: catalog.handleSearch,
        trendingHf: catalog.trendingHf, trendingOllama: catalog.trendingOllama, refreshTrending: catalog.refreshTrending,
        catalogHf: catalog.catalogHf, catalogOllama: catalog.catalogOllama, refreshCatalog: catalog.refreshCatalog,
        handleInstall: catalog.handleInstall,

        // Runtime
        installedCollapsed: runtime.installedCollapsed, setInstalledCollapsed: runtime.setInstalledCollapsed,
        operationsCollapsed: runtime.operationsCollapsed, setOperationsCollapsed: runtime.setOperationsCollapsed,
        installed: runtime.installed, operations: runtime.operations,
        llmServers: runtime.llmServers, activeServer: runtime.activeServer,
        activeRuntime: runtime.activeRuntime,
        selectedServer: runtime.selectedServer, setSelectedServer: runtime.setSelectedServer,
        selectedModel: runtime.selectedModel, setSelectedModel: runtime.setSelectedModel,
        serverOptions: runtime.serverOptions, modelOptions: runtime.modelOptions,
        installedBuckets: runtime.installedBuckets, installedModels: runtime.installedModels,
        handleActivate: runtime.handleActivate, handleRemove: runtime.handleRemove,

        // Unified pending actions
        pendingActions: { ...catalog.pendingActions, ...runtime.pendingActions },

        // API exports for UI
        setActiveLlmServer: runtime.setActiveLlmServer,
        switchModel: runtime.switchModel,
        pushToast: runtime.pushToast
    };
}
