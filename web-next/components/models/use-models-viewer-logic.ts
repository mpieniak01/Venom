import { useNews } from "./hooks/use-news";
import { useModelCatalog } from "./hooks/use-model-catalog";
import { useTrendingModels } from "./hooks/use-trending-models";
import { useRuntime } from "./hooks/use-runtime";
import { useTrainableModels } from "./hooks/use-trainable-models";
import { useRemoteModels } from "./hooks/use-remote-models";
import { useLanguage } from "@/lib/i18n";

export function useModelsViewerLogic() {
    const { t, language } = useLanguage();

    // Split hooks
    const news = useNews();
    const catalog = useModelCatalog();
    const trending = useTrendingModels();
    const runtime = useRuntime();
    const trainable = useTrainableModels();
    const remote = useRemoteModels();

    return {
        t, language,
        // News
        newsHf: news.newsHf, refreshNews: news.refreshNews,
        papersHf: news.papersHf, refreshPapers: news.refreshPapers,
        newsSort: news.newsSort, setNewsSort: news.setNewsSort,
        newsCollapsed: news.newsCollapsed, setNewsCollapsed: news.setNewsCollapsed,
        papersCollapsed: news.papersCollapsed, setPapersCollapsed: news.setPapersCollapsed,

        // Catalog & Search
        trendingCollapsed: trending.trendingCollapsed, setTrendingCollapsed: trending.setTrendingCollapsed,
        catalogCollapsed: catalog.catalogCollapsed, setCatalogCollapsed: catalog.setCatalogCollapsed,
        searchCollapsed: catalog.searchCollapsed, setSearchCollapsed: catalog.setSearchCollapsed,
        searchQuery: catalog.searchQuery, setSearchQuery: catalog.setSearchQuery,
        searchProvider: catalog.searchProvider, setSearchProvider: catalog.setSearchProvider,
        searchResults: catalog.searchResults, handleSearch: catalog.handleSearch,
        trendingHf: trending.trendingHf, trendingOllama: trending.trendingOllama, refreshTrending: trending.refreshTrending,
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

        // Trainable Models (v2)
        trainableModels: trainable.trainableModels,
        trainableLoading: trainable.loading,
        trainableError: trainable.error,
        refreshTrainable: trainable.refresh,

        // Remote Models
        remoteProviders: remote.providers,
        remoteProvidersLoading: remote.providersLoading,
        remoteProvidersError: remote.providersError,
        fetchRemoteProviders: remote.fetchProviders,
        remoteCatalog: remote.catalog,
        remoteCatalogProvider: remote.catalogProvider,
        remoteCatalogLoading: remote.catalogLoading,
        remoteCatalogError: remote.catalogError,
        remoteCatalogRefreshedAt: remote.catalogRefreshedAt,
        remoteCatalogSource: remote.catalogSource,
        fetchRemoteCatalog: remote.fetchCatalog,
        remoteBindings: remote.bindings,
        remoteBindingsLoading: remote.bindingsLoading,
        remoteBindingsError: remote.bindingsError,
        fetchRemoteBindings: remote.fetchBindings,

        // Unified pending actions
        pendingActions: { ...catalog.pendingActions, ...runtime.pendingActions },

        // API exports for UI
        setActiveLlmServer: runtime.setActiveLlmServer,
        switchModel: runtime.switchModel,
        pushToast: runtime.pushToast
    };
}
