"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Layers, Search, ChevronDown } from "lucide-react";
import { SectionHeading } from "@/components/ui/section-heading";
import {
  installRegistryModel,
  removeRegistryModel,
  setActiveLlmServer,
  switchModel,
  useModelOperations,
  useModels,
  useActiveLlmServer,
  useLlmServers,
} from "@/hooks/use-api";
import { apiFetch } from "@/lib/api-client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectMenu } from "@/components/ui/select-menu";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/lib/i18n";
import { formatDateTime } from "@/lib/date";
import type { ModelCatalogEntry, ModelInfo, ModelOperation, ModelCatalogResponse } from "@/lib/types";

const formatNumber = (value?: number | null) => {
  // Use en-US for consistent formatting vs pl-PL, or use language.
  // But for now keeping pl-PL or switching to en-US based on preference.
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("pl-PL");
};
const getRuntimeForProvider = (provider?: string | null) => {
  if (!provider) return "vllm";
  return provider === "ollama" ? "ollama" : "vllm";
};

const normalizeProvider = (value?: string | null) => {
  if (!value) return "";
  return value.toLowerCase();
};

const inferProviderFromName = (name?: string | null) => {
  if (!name) return null;
  return name.includes(":") ? "ollama" : "vllm";
};

const getStatusTone = (status?: string) => {
  if (!status) return "neutral";
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "in_progress") return "warning";
  return "neutral";
};

const readStorageJson = <T,>(key: string): T | null => {
  if (globalThis.window === undefined) return null;
  const raw = globalThis.window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    globalThis.window.localStorage.removeItem(key);
    return null;
  }
};

const writeStorageJson = (key: string, value: unknown) => {
  if (globalThis.window === undefined) return;
  globalThis.window.localStorage.setItem(key, JSON.stringify(value));
};

const readStorageItem = (key: string): string | null => {
  if (globalThis.window === undefined) return null;
  return globalThis.window.localStorage.getItem(key);
};

type CatalogCachePayload = {
  data: ModelCatalogEntry[];
  stale?: boolean;
  error?: string | null;
};

type NewsItem = {
  title?: string | null;
  url?: string | null;
  summary?: string | null;
  published_at?: string | null;
  authors?: string[] | null;
};

type NewsCachePayload = {
  items: NewsItem[];
  stale?: boolean;
  error?: string | null;
};

const SectionHeader = ({
  title,
  subtitle,
  badge,
  actionLabel,
  onAction,
  actionDisabled,
  extra,
  isCollapsed,
  onToggle,
}: {
  title: string;
  subtitle?: string;
  badge?: string;
  actionLabel?: string;
  onAction?: () => void;
  actionDisabled?: boolean;
  extra?: React.ReactNode;
  isCollapsed?: boolean;
  onToggle?: () => void;
}) => {
  const { t } = useLanguage();
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col">
          <p className="text-[10px] uppercase tracking-[0.35em] text-slate-400">{title}</p>
          {subtitle ? <p className="mt-0.5 text-xs text-slate-300">{subtitle}</p> : null}
        </div>
        <div className="flex items-center gap-3">
          {extra ? <div className="flex items-center gap-2">{extra}</div> : null}
          {actionLabel && onAction ? (
            <Button
              size="sm"
              variant="outline"
              className="h-7 rounded-full px-3 text-[10px] uppercase tracking-wider"
              disabled={actionDisabled}
              onClick={onAction}
            >
              {actionLabel}
            </Button>
          ) : null}
          {badge ? <Badge className="text-[10px] py-0.5">{badge}</Badge> : null}
          {onToggle ? (
            <button
              type="button"
              className="inline-flex h-7 items-center rounded-full border border-white/10 px-3 text-[10px] uppercase tracking-[0.15em] text-slate-400 transition hover:border-white/20 hover:text-white"
              onClick={onToggle}
              aria-expanded={!isCollapsed}
            >
              <ChevronDown
                className={cn(
                  "mr-1.5 h-3 w-3 transition-transform",
                  isCollapsed ? "rotate-0" : "rotate-180",
                )}
              />
              {isCollapsed ? t("models.actions.expand") : t("models.actions.collapse")}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
};


const CatalogCard = ({
  model,
  actionLabel,
  onAction,
  pending,
}: {
  model: ModelCatalogEntry;
  actionLabel: string;
  onAction: () => void;
  pending?: boolean;
}) => {
  const { t } = useLanguage();
  return (
    <div className="rounded-3xl box-base p-5 text-white shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-lg font-semibold">{model.display_name}</p>
          <p className="text-xs text-slate-400">{model.model_name}</p>
        </div>
        <Badge tone="neutral">{model.runtime}</Badge>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-300">
        <span>{t("models.status.provider")}: {model.provider}</span>
        <span>
          {t("models.status.size")}: {typeof model.size_gb === "number" ? `${model.size_gb.toFixed(2)} GB` : "—"}
        </span>
        <span>👍 {formatNumber(model.likes)}</span>
        <span>⬇️ {formatNumber(model.downloads)}</span>
      </div>
      {model.tags && model.tags.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {model.tags.slice(0, 5).map((tag) => (
            <Badge key={tag} className="text-[10px]">
              {tag.length > 30 ? tag.slice(0, 30) + '...' : tag}
            </Badge>
          ))}
        </div>
      ) : null}
      <Button
        className="mt-4 rounded-full px-4"
        size="sm"
        variant="secondary"
        disabled={pending}
        onClick={onAction}
      >
        {pending ? t("models.actions.installing") : actionLabel}
      </Button>
    </div>
  );
};

const InstalledCard = ({
  model,
  onActivate,
  onRemove,
  pendingActivate,
  pendingRemove,
}: {
  model: ModelInfo;
  onActivate: () => void;
  onRemove?: () => void;
  pendingActivate?: boolean;
  pendingRemove?: boolean;
}) => {
  const { t } = useLanguage();
  const providerLabel = model.provider ?? model.source ?? "vllm";
  return (
    <div className="rounded-3xl box-base p-5 text-white shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-lg font-semibold">{model.name}</p>
          <p className="text-xs text-slate-400">
            {typeof model.size_gb === "number"
              ? `${model.size_gb.toFixed(2)} GB`
              : `${t("models.status.size")} —`}{" "}
            • {providerLabel}
          </p>
        </div>
        <Badge tone={model.active ? "success" : "neutral"}>
          {model.active ? t("models.status.active") : t("models.status.installed")}
        </Badge>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          className="rounded-full px-4"
          size="sm"
          variant={model.active ? "secondary" : "outline"}
          disabled={model.active || pendingActivate}
          onClick={onActivate}
        >
          {pendingActivate ? t("models.actions.activating") : t("models.actions.activate")}
        </Button>
        {onRemove ? (
          <Button
            className="rounded-full px-4"
            size="sm"
            variant="danger"
            disabled={pendingRemove}
            onClick={onRemove}
          >
            {pendingRemove ? t("models.actions.removing") : t("models.actions.remove")}
          </Button>
        ) : null}
      </div>
    </div>
  );
};

const OperationRow = ({ op }: { op: ModelOperation }) => (
  <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl box-base px-4 py-3 text-sm text-slate-200">
    <div>
      <p className="font-medium text-white">{op.model_name}</p>
      <p className="text-xs text-slate-400">
        {op.operation_type} • {op.message || "—"}
      </p>
    </div>
    <div className="flex items-center gap-2">
      {typeof op.progress === "number" ? (
        <span className="text-xs text-slate-400">{Math.round(op.progress)}%</span>
      ) : null}
      <Badge tone={getStatusTone(op.status)}>{op.status}</Badge>
    </div>
  </div>
);

// Update component start
export const ModelsViewer = () => {
  const { pushToast } = useToast();
  const { language, t } = useLanguage();
  const [pendingActions, setPendingActions] = useState<Record<string, boolean>>({});
  const [newsCollapsed, setNewsCollapsed] = useState(false);
  const [papersCollapsed, setPapersCollapsed] = useState(false);
  const [trendingCollapsed, setTrendingCollapsed] = useState(false);
  const [catalogCollapsed, setCatalogCollapsed] = useState(false);
  const [installedCollapsed, setInstalledCollapsed] = useState(false);
  const [operationsCollapsed, setOperationsCollapsed] = useState(false);
  const [searchCollapsed, setSearchCollapsed] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchProvider, setSearchProvider] = useState<"huggingface" | "ollama">("huggingface");
  const [searchResults, setSearchResults] = useState<{
    data: ModelCatalogEntry[];
    loading: boolean;
    error: string | null;
    performed: boolean;
  }>({ data: [], loading: false, error: null, performed: false });

  const [trendingHf, setTrendingHf] = useState<{
    data: ModelCatalogEntry[];
    stale?: boolean;
    error?: string | null;
    loading: boolean;
  }>({ data: [], loading: false });

  const [trendingOllama, setTrendingOllama] = useState<{
    data: ModelCatalogEntry[];
    stale?: boolean;
    error?: string | null;
    loading: boolean;
  }>({ data: [], loading: false });
  // ... (rest of states) ...
  const [catalogHf, setCatalogHf] = useState<{
    data: ModelCatalogEntry[];
    stale?: boolean;
    error?: string | null;
    loading: boolean;
  }>({ data: [], loading: false });
  // ... (rest of states) ...
  const [catalogOllama, setCatalogOllama] = useState<{
    data: ModelCatalogEntry[];
    stale?: boolean;
    error?: string | null;
    loading: boolean;
  }>({ data: [], loading: false });
  const [newsHf, setNewsHf] = useState<{
    items: Array<{
      title?: string | null;
      url?: string | null;
      summary?: string | null;
      published_at?: string | null;
      authors?: string[] | null;
    }>;
    stale?: boolean;
    error?: string | null;
    loading: boolean;
  }>({ items: [], loading: false });
  const [papersHf, setPapersHf] = useState<{
    items: Array<{
      title?: string | null;
      url?: string | null;
      summary?: string | null;
      published_at?: string | null;
      authors?: string[] | null;
    }>;
    stale?: boolean;
    error?: string | null;
    loading: boolean;
  }>({ items: [], loading: false });
  const [newsSort, setNewsSort] = useState<"newest" | "oldest">("newest");

  const installed = useModels(0);
  const operations = useModelOperations(10, 0);
  const llmServers = useLlmServers(0);
  const activeServer = useActiveLlmServer(0);

  const activeRuntime = installed.data?.active;
  const [selectedServer, setSelectedServer] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchResults((prev) => ({ ...prev, loading: true, error: null, performed: true }));
    try {
      const params = new URLSearchParams({
        query: searchQuery,
        provider: searchProvider,
        limit: "12",
      });
      const response = await apiFetch<ModelCatalogResponse>(
        `/api/v1/models/search?${params.toString()}`
      );
      if (response && response.success) {
        setSearchResults({
          data: response.models,
          loading: false,
          error: null,
          performed: true,
        });
      } else {
        setSearchResults({
          data: [],
          loading: false,
          error: response?.error || t("models.search.error"),
          performed: true,
        });
      }
    } catch (error) {
      let msg = "Wystąpił błąd";
      if (error instanceof Error) msg = error.message;
      setSearchResults({
        data: [],
        loading: false,
        error: msg,
        performed: true,
      });
    }
  };

  const newsBlogCacheKey = useMemo(
    () => `models-blog-hf-${language}`,
    [language],
  );
  const newsPapersCacheKey = useMemo(
    () => `models-papers-hf-${language}`,
    [language],
  );

  useEffect(() => {
    const cachedHf = readStorageJson<CatalogCachePayload>("models-trending-hf");
    const cachedOllama = readStorageJson<CatalogCachePayload>("models-trending-ollama");
    const cachedCatalogHf = readStorageJson<CatalogCachePayload>("models-catalog-hf");
    const cachedCatalogOllama = readStorageJson<CatalogCachePayload>("models-catalog-ollama");
    const cachedNewsSort = readStorageItem("models-news-sort");

    if (cachedHf) setTrendingHf((prev) => ({ ...prev, ...cachedHf, loading: false }));
    if (cachedOllama) setTrendingOllama((prev) => ({ ...prev, ...cachedOllama, loading: false }));
    if (cachedCatalogHf) setCatalogHf((prev) => ({ ...prev, ...cachedCatalogHf, loading: false }));
    if (cachedCatalogOllama) setCatalogOllama((prev) => ({ ...prev, ...cachedCatalogOllama, loading: false }));
    if (cachedNewsSort === "newest" || cachedNewsSort === "oldest") {
      setNewsSort(cachedNewsSort);
    }
  }, []);

  useEffect(() => {
    const cachedNewsHf = readStorageJson<NewsCachePayload>(newsBlogCacheKey);
    const cachedPapersHf = readStorageJson<NewsCachePayload>(newsPapersCacheKey);
    if (cachedNewsHf) {
      setNewsHf((prev) => ({ ...prev, ...cachedNewsHf, loading: false }));
    } else {
      setNewsHf((prev) => ({
        ...prev,
        items: [],
        error: null,
        stale: undefined,
        loading: false,
      }));
    }

    if (cachedPapersHf) {
      setPapersHf((prev) => ({ ...prev, ...cachedPapersHf, loading: false }));
    } else {
      setPapersHf((prev) => ({
        ...prev,
        items: [],
        error: null,
        stale: undefined,
        loading: false,
      }));
    }
  }, [language, newsBlogCacheKey, newsPapersCacheKey]);
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("models-news-sort", newsSort);
  }, [newsSort]);

  const setPending = (key: string, value: boolean) => {
    setPendingActions((prev) => ({ ...prev, [key]: value }));
  };

  const handleInstall = async (entry: ModelCatalogEntry) => {
    const key = `install:${entry.provider}:${entry.model_name}`;
    try {
      setPending(key, true);
      await installRegistryModel({
        name: entry.model_name,
        provider: entry.provider,
        runtime: entry.runtime,
      });
      pushToast(`Instalacja rozpoczęta: ${entry.model_name}`, "info");
      await Promise.all([operations.refresh(), installed.refresh()]);
    } catch {
      pushToast("Nie udało się rozpocząć instalacji.", "error");
    } finally {
      setPending(key, false);
    }
  };

  const handleActivate = async (model: ModelInfo) => {
    const key = `activate:${model.name}`;
    try {
      setPending(key, true);
      const runtime = getRuntimeForProvider(model.provider ?? model.source ?? undefined);
      if (runtime !== activeServer.data?.active_server) {
        await setActiveLlmServer(runtime);
      }
      await switchModel(model.name);
      pushToast(`Aktywowano: ${model.name}`, "success");
      await installed.refresh();
    } catch {
      pushToast("Nie udało się aktywować modelu.", "error");
    } finally {
      setPending(key, false);
    }
  };

  const handleRemove = async (model: ModelInfo) => {
    const key = `remove:${model.name}`;
    try {
      setPending(key, true);
      await removeRegistryModel(model.name);
      pushToast(`Usuwanie rozpoczęte: ${model.name}`, "warning");
      await Promise.all([installed.refresh(), operations.refresh()]);
    } catch {
      pushToast("Nie udało się usunąć modelu.", "error");
    } finally {
      setPending(key, false);
    }
  };

  const installedBuckets = useMemo(() => {
    const data = installed.data;
    if (!data) {
      return {
        vllm: [] as ModelInfo[],
        ollama: [] as ModelInfo[],
      };
    }
    const providers = data.providers ?? {};
    const vllm = providers.vllm ?? [];
    const ollama = providers.ollama ?? [];
    if (vllm.length || ollama.length) {
      return { vllm, ollama };
    }
    const fallback = Array.isArray(data.models) ? data.models : [];
    return {
      vllm: fallback.filter((model) => (model.provider ?? "").toLowerCase() === "vllm"),
      ollama: fallback.filter((model) => (model.provider ?? "").toLowerCase() === "ollama"),
    };
  }, [installed.data]);
  const installedModels = useMemo(
    () => [...installedBuckets.vllm, ...installedBuckets.ollama],
    [installedBuckets],
  );
  const availableModelsForServer = useMemo(() => {
    if (!selectedServer || !installed.data) return installedModels;
    const server = (llmServers.data ?? []).find((s) => s.name === selectedServer);
    const targetProvider = normalizeProvider(server?.provider ?? selectedServer);
    const providersMap = installed.data.providers ?? {};

    let base =
      targetProvider in providersMap
        ? providersMap[targetProvider] ?? []
        : (installed.data.models ?? []).filter(
          (model) => normalizeProvider(model.provider) === targetProvider,
        );

    // fallback do ostatnio aktywnego dla providera
    const lastModels = activeServer.data?.last_models ?? {};
    const lastForServer =
      targetProvider === "ollama"
        ? lastModels.ollama || lastModels.previous_ollama
        : targetProvider === "vllm"
          ? lastModels.vllm || lastModels.previous_vllm
          : null;
    if (!base.length && lastForServer) {
      const inferred = inferProviderFromName(lastForServer);
      if (inferred === targetProvider) {
        base = [{ name: lastForServer, provider: targetProvider, source: "cached" }];
      }
    }
    return base;
  }, [selectedServer, installed.data, installedModels, llmServers.data, activeServer.data?.last_models]);
  const serverOptions = useMemo(
    () =>
      (llmServers.data ?? []).map((server) => ({
        value: server.name,
        label: server.name,
      })),
    [llmServers.data],
  );
  const modelOptions = useMemo(
    () =>
      availableModelsForServer.map((model) => ({
        value: model.name,
        label: model.name,
      })),
    [availableModelsForServer],
  );
  const operationsList = operations.data?.operations ?? [];

  useEffect(() => {
    if (selectedServer) return;
    const active = activeServer.data?.active_server;
    if (active) setSelectedServer(active);
  }, [activeServer.data?.active_server, selectedServer]);

  useEffect(() => {
    if (selectedModel) return;
    const activeModel = activeRuntime?.model;
    if (activeModel) {
      setSelectedModel(activeModel);
      return;
    }
    if (availableModelsForServer.length) {
      setSelectedModel(availableModelsForServer[0].name);
    }
  }, [activeRuntime?.model, selectedModel, availableModelsForServer]);

  const allowRemoveProviders = useMemo(() => new Set(["ollama", "huggingface"]), []);
  const refreshTrending = async () => {
    setTrendingHf((prev) => ({ ...prev, loading: true, error: null }));
    setTrendingOllama((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const [hfResponse, ollamaResponse] = await Promise.all([
        apiFetch<{
          models: ModelCatalogEntry[];
          stale?: boolean;
          error?: string | null;
        }>("/api/v1/models/trending?provider=huggingface"),
        apiFetch<{
          models: ModelCatalogEntry[];
          stale?: boolean;
          error?: string | null;
        }>("/api/v1/models/trending?provider=ollama"),
      ]);
      const hfPayload = {
        data: hfResponse.models ?? [],
        stale: hfResponse.stale,
        error: hfResponse.error,
      };
      const ollamaPayload = {
        data: ollamaResponse.models ?? [],
        stale: ollamaResponse.stale,
        error: ollamaResponse.error,
      };
      setTrendingHf({ ...hfPayload, loading: false });
      setTrendingOllama({ ...ollamaPayload, loading: false });
      writeStorageJson("models-trending-hf", hfPayload);
      writeStorageJson("models-trending-ollama", ollamaPayload);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Nie udało się pobrać trendów.";
      setTrendingHf((prev) => ({ ...prev, loading: false, error: message }));
      setTrendingOllama((prev) => ({ ...prev, loading: false, error: message }));
    }
  };
  const refreshCatalog = async () => {
    setCatalogHf((prev) => ({ ...prev, loading: true, error: null }));
    setCatalogOllama((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const [hfResponse, ollamaResponse] = await Promise.all([
        apiFetch<{
          models: ModelCatalogEntry[];
          stale?: boolean;
          error?: string | null;
        }>("/api/v1/models/providers?provider=huggingface"),
        apiFetch<{
          models: ModelCatalogEntry[];
          stale?: boolean;
          error?: string | null;
        }>("/api/v1/models/providers?provider=ollama"),
      ]);
      const hfPayload = {
        data: hfResponse.models ?? [],
        stale: hfResponse.stale,
        error: hfResponse.error,
      };
      const ollamaPayload = {
        data: ollamaResponse.models ?? [],
        stale: ollamaResponse.stale,
        error: ollamaResponse.error,
      };
      setCatalogHf({ ...hfPayload, loading: false });
      setCatalogOllama({ ...ollamaPayload, loading: false });
      writeStorageJson("models-catalog-hf", hfPayload);
      writeStorageJson("models-catalog-ollama", ollamaPayload);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Nie udało się pobrać katalogu.";
      setCatalogHf((prev) => ({ ...prev, loading: false, error: message }));
      setCatalogOllama((prev) => ({ ...prev, loading: false, error: message }));
    }
  };
  const refreshNews = async () => {
    setNewsHf((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const params = new URLSearchParams({
        provider: "huggingface",
        lang: language,
      });
      const response = await apiFetch<{
        items: Array<{
          title?: string | null;
          url?: string | null;
          summary?: string | null;
          published_at?: string | null;
          authors?: string[] | null;
        }>;
        stale?: boolean;
        error?: string | null;
      }>(`/api/v1/models/news?${params.toString()}`);
      const payload = {
        items: response.items ?? [],
        stale: response.stale,
        error: response.error,
      };
      setNewsHf({ ...payload, loading: false });
      writeStorageJson(newsBlogCacheKey, payload);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Nie udało się pobrać newsów.";
      setNewsHf((prev) => ({ ...prev, loading: false, error: message }));
    }
  };
  const refreshPapers = async () => {
    setPapersHf((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const params = new URLSearchParams({
        provider: "huggingface",
        type: "papers",
        lang: language,
        limit: "3",
      });
      const response = await apiFetch<{
        items: Array<{
          title?: string | null;
          url?: string | null;
          summary?: string | null;
          published_at?: string | null;
          authors?: string[] | null;
        }>;
        stale?: boolean;
        error?: string | null;
      }>(
        `/api/v1/models/news?${params.toString()}`,
      );
      const payload = {
        items: response.items ?? [],
        stale: response.stale,
        error: response.error,
      };
      setPapersHf({ ...payload, loading: false });
      writeStorageJson(newsPapersCacheKey, payload);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("models.sections.papers.fetchError");
      setPapersHf((prev) => ({ ...prev, loading: false, error: message }));
    }
  };
  const newsItemsSorted = useMemo(() => {
    const items = [...newsHf.items];
    if (newsSort === "oldest") {
      return items.reverse();
    }
    return items;
  }, [newsHf.items, newsSort]);
  const papersItemsSorted = useMemo(() => {
    const items = [...papersHf.items];
    if (newsSort === "oldest") {
      return items.reverse();
    }
    return items;
  }, [papersHf.items, newsSort]);

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow={t("models.page.eyebrow")}
        title={t("models.page.title")}
        description={t("models.page.description")}
        as="h1"
        size="lg"
        rightSlot={<Layers className="page-heading-icon" />}
      />

      <div className="grid gap-10 items-start" style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
        <div className="w-full rounded-[24px] border border-white/10 bg-black/20 p-6 text-sm text-slate-200 shadow-card">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-slate-400">{t("models.runtime.title")}</p>
              <p className="mt-1 text-sm text-slate-300">
                {t("models.runtime.description")}
              </p>
            </div>
            {installed.error ? (
              <Badge tone="warning">{installed.error}</Badge>
            ) : null}
          </div>
          <div className="mt-4 rounded-2xl border border-white/10 bg-black/30 p-4">
            <div className="flex w-full flex-nowrap items-center gap-3 overflow-x-auto">
              <span className="whitespace-nowrap text-[11px] uppercase tracking-[0.3em] text-slate-400">
                {t("models.runtime.server")}
              </span>
              <SelectMenu
                value={selectedServer || activeRuntime?.provider || ""}
                options={serverOptions}
                onChange={(value) => setSelectedServer(value || null)}
                placeholder={t("models.runtime.select")}
                className="w-[180px] shrink-0"
                buttonClassName="w-full justify-between rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium normal-case tracking-normal text-slate-100 hover:border-white/30 hover:bg-white/10 overflow-hidden"
                menuClassName="min-w-[220px]"
                optionClassName="text-sm whitespace-nowrap"
                renderButton={(option) => (
                  <span className="flex-1 truncate text-left text-slate-100">
                    {option?.label ?? t("models.runtime.select")}
                  </span>
                )}
                renderOption={(option) => (
                  <span className="w-full text-left text-sm normal-case tracking-normal text-slate-100">
                    {option.label}
                  </span>
                )}
              />
              <span className="whitespace-nowrap text-[11px] uppercase tracking-[0.3em] text-slate-400">
                {t("models.runtime.model")}
              </span>
              <SelectMenu
                value={selectedModel || activeRuntime?.model || ""}
                options={modelOptions}
                onChange={(value) => setSelectedModel(value || null)}
                placeholder={t("models.runtime.select")}
                className="flex-1 min-w-[200px] max-w-full"
                buttonClassName="w-full justify-between rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium normal-case tracking-normal text-slate-100 hover:border-white/30 hover:bg-white/10 overflow-hidden"
                menuClassName="min-w-[300px] max-w-[80vw]"
                menuWidth="trigger"
                optionClassName="text-sm whitespace-nowrap"
                renderButton={(option) => (
                  <span className="flex-1 truncate text-left">
                    {option?.label ?? t("models.runtime.select")}
                  </span>
                )}
                renderOption={(option) => (
                  <span className="w-full text-left text-sm normal-case tracking-normal text-slate-100">
                    {option.label}
                  </span>
                )}
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
                    if (!isActive) {
                      await setActiveLlmServer(selectedServer);
                    }
                    if (selectedModel !== activeRuntime?.model || !isActive) {
                      await switchModel(selectedModel);
                    }
                    pushToast(t("models.runtime.activated", { model: selectedModel, server: selectedServer }), "success");
                    await Promise.all([activeServer.refresh(), installed.refresh()]);
                  } catch (error) {
                    pushToast("Nie udało się aktywować modelu", "error");
                    console.error(error);
                  }
                }}
              >
                Aktywuj
              </Button>
              <a
                className="shrink-0 inline-flex items-center gap-2 text-xs underline underline-offset-2 transition hover:opacity-90 !text-[color:var(--secondary)]"
                href="/docs/llm-models"
              >
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/15 text-[11px]">
                  ?
                </span>
                {t("models.ui.instructions")}
              </a>
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-10">
        <section className="grid gap-10">
          <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
            <SectionHeader
              title={t("models.search.title")}
              subtitle={t("models.search.subtitle")}
              isCollapsed={searchCollapsed}
              onToggle={() => setSearchCollapsed((prev) => !prev)}
            />
            {!searchCollapsed ? (
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
                      onChange={(val) =>
                        setSearchProvider(val as "huggingface" | "ollama")
                      }
                      className="w-full sm:w-[160px]"
                      buttonClassName="w-full justify-between rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-100 hover:border-white/30 hover:bg-white/10"
                      renderButton={(option) => (
                        <span className="flex-1 truncate text-left text-slate-100 uppercase tracking-wider text-[10px]">
                          {option?.label ?? "Provider"}
                        </span>
                      )}
                    />
                    <Button
                      onClick={handleSearch}
                      disabled={searchResults.loading || !searchQuery.trim()}
                      className="rounded-full px-6 text-xs"
                      size="sm"
                      variant="secondary"
                    >
                      {searchResults.loading ? t("models.search.searching") : t("models.search.button")}
                    </Button>
                  </div>
                </div>

                {searchResults.error ? (
                  <p className="mt-4 text-sm text-amber-200">{searchResults.error}</p>
                ) : null}

                {searchResults.performed &&
                  !searchResults.loading &&
                  searchResults.data.length === 0 &&
                  !searchResults.error ? (
                  <p className="mt-4 text-sm text-slate-400">
                    {t("models.ui.noResults", { query: searchQuery })}
                  </p>
                ) : null}

                {searchResults.data.length > 0 ? (
                  <div className="mt-6 grid gap-4 lg:grid-cols-2">
                    {searchResults.data.map((model) => (
                      <CatalogCard
                        key={`${model.provider}-${model.model_name}`}
                        model={model}
                        actionLabel={t("models.actions.install")}
                        pending={
                          pendingActions[`install:${model.provider}:${model.model_name}`]
                        }
                        onAction={() => handleInstall(model)}
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </section>

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
              onToggle={() => setNewsCollapsed((prev) => !prev)}
              extra={
                <div className="flex items-center gap-3">
                  <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500 whitespace-nowrap">
                    {t("models.ui.sort")}
                  </span>
                  <select
                    className="h-7 rounded-full border border-white/10 bg-white/5 px-3 text-[10px] text-slate-200 outline-none transition hover:border-white/20"
                    value={newsSort}
                    onChange={(event) =>
                      setNewsSort(event.target.value as "newest" | "oldest")
                    }
                  >
                    <option value="newest">{t("models.ui.newest")}</option>
                    <option value="oldest">{t("models.ui.oldest")}</option>
                  </select>
                </div>
              }
            />
            {!newsCollapsed ? (
              <div className="mt-5 rounded-2xl border border-white/10 bg-black/30 p-4">
                {newsHf.loading ? (
                  <p className="text-xs text-slate-500">{t("models.ui.loading")}</p>
                ) : newsHf.error ? (
                  <p className="text-xs text-amber-200/70">{newsHf.error}</p>
                ) : newsHf.items.length === 0 ? (
                  <p className="text-xs text-slate-500">
                    {t("models.ui.noData")}
                  </p>
                ) : (
                  <div className="flex flex-col">
                    {newsItemsSorted.slice(0, 5).map((item, index) => (
                      <div
                        key={`${item.title ?? "news"}-${index}`}
                        className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 py-2.5 last:border-b-0 last:pb-0 first:pt-0"
                      >
                        <p className="min-w-0 flex-1 text-sm font-medium text-slate-200 line-clamp-1">
                          {item.title || "Nowa publikacja"}
                        </p>
                        <div className="flex items-center gap-4">
                          <span className="text-[10px] tabular-nums text-slate-500 whitespace-nowrap">
                            {formatDateTime(item.published_at, language, "news")}
                          </span>
                          {item.url ? (
                            <a
                              className="rounded-full border border-white/10 px-2.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-slate-400 transition hover:border-white/30 hover:text-white"
                              href={item.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {t("models.ui.view")}
                            </a>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : null}
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
              onToggle={() => setPapersCollapsed((prev) => !prev)}
            />
            {!papersCollapsed ? (
              <div className="mt-5 grid gap-4 lg:grid-cols-3">
                {papersHf.loading ? (
                  <p className="col-span-full text-xs text-slate-500">{t("models.ui.loading")}</p>
                ) : papersHf.error ? (
                  <p className="col-span-full text-xs text-amber-200/70">{papersHf.error}</p>
                ) : papersHf.items.length === 0 ? (
                  <p className="col-span-full text-xs text-slate-500">
                    {t("models.ui.noData")}
                  </p>
                ) : (
                  papersItemsSorted.slice(0, 3).map((item, index) => (
                    <div
                      key={`${item.title ?? "paper"}-${index}`}
                      className="flex h-full flex-col rounded-2xl border border-white/10 bg-black/30 p-4 text-sm"
                    >
                      <div className="flex flex-1 flex-col">
                        <p className="text-sm font-semibold text-slate-100 line-clamp-2">
                          {item.title || t("models.sections.papers.defaultTitle")}
                        </p>
                        <div className="mt-2 text-[11px] text-slate-400 line-clamp-3 leading-relaxed">
                          {item.summary ? item.summary : t("models.sections.papers.noPreview")}
                        </div>
                        <div className="mt-auto pt-4 space-y-1.5">
                          <div className="flex items-center justify-between text-[10px] text-slate-500">
                            <span>{formatDateTime(item.published_at, language, "news")}</span>
                            <span className="truncate max-w-[100px] text-right">
                              {item.authors && item.authors.length ? item.authors[0] : "—"}
                            </span>
                          </div>
                          <div className="flex justify-end">
                            {item.url ? (
                              <a
                                className="rounded-full border border-white/10 px-3 py-1 text-[9px] uppercase tracking-[0.1em] text-slate-400 transition hover:border-white/30 hover:text-white"
                                href={item.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {t("models.ui.view")}
                              </a>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            ) : null}
          </div>
        </section>

        <section className="grid gap-10 lg:grid-cols-[2.2fr_1fr]">
          <div className="flex flex-col gap-10">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
              <SectionHeader
                title={t("models.sections.recommended.title")}
                subtitle={t("models.sections.recommended.subtitle")}
                actionLabel={t("models.ui.refresh")}
                actionDisabled={trendingHf.loading || trendingOllama.loading}
                onAction={refreshTrending}
                isCollapsed={trendingCollapsed}
                onToggle={() => setTrendingCollapsed((prev) => !prev)}
              />
              {!trendingCollapsed ? (
                <div className="mt-5 grid gap-6 lg:grid-cols-2">
                  <div className="flex flex-col gap-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs uppercase tracking-widest text-slate-400 font-semibold">Ollama</h3>
                      {trendingOllama.stale ? (
                        <Badge tone="warning" className="text-[9px]">{t("models.ui.offlineCache")}</Badge>
                      ) : null}
                    </div>
                    {trendingOllama.loading ? (
                      <p className="text-xs text-slate-500">{t("models.ui.loading")}</p>
                    ) : (
                      <div className="grid gap-4">
                        {(trendingOllama.data ?? []).slice(0, 4).map((model) => (
                          <CatalogCard
                            key={model.model_name}
                            model={model}
                            actionLabel={t("models.actions.install")}
                            pending={pendingActions[`install:${model.provider}:${model.model_name}`]}
                            onAction={() => handleInstall(model)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs uppercase tracking-widest text-slate-400 font-semibold">HuggingFace</h3>
                      {trendingHf.stale ? (
                        <Badge tone="warning" className="text-[9px]">{t("models.ui.offlineCache")}</Badge>
                      ) : null}
                    </div>
                    {trendingHf.loading ? (
                      <p className="text-xs text-slate-500">{t("models.ui.loading")}</p>
                    ) : (
                      <div className="grid gap-4">
                        {(trendingHf.data ?? []).slice(0, 4).map((model) => (
                          <CatalogCard
                            key={model.model_name}
                            model={model}
                            actionLabel={t("models.actions.install")}
                            pending={pendingActions[`install:${model.provider}:${model.model_name}`]}
                            onAction={() => handleInstall(model)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
              <SectionHeader
                title={t("models.sections.catalog.title")}
                subtitle={t("models.sections.catalog.subtitle")}
                actionLabel={t("models.ui.refresh")}
                actionDisabled={catalogHf.loading || catalogOllama.loading}
                onAction={refreshCatalog}
                isCollapsed={catalogCollapsed}
                onToggle={() => setCatalogCollapsed((prev) => !prev)}
              />
              {!catalogCollapsed ? (
                <div className="mt-5 grid gap-6 lg:grid-cols-2">
                  <div className="flex flex-col gap-4">
                    <h3 className="text-xs uppercase tracking-widest text-slate-400 font-semibold">Ollama</h3>
                    {catalogOllama.loading ? (
                      <p className="text-xs text-slate-500">{t("models.ui.loading")}</p>
                    ) : (
                      <div className="grid gap-4">
                        {(catalogOllama.data ?? []).slice(0, 6).map((model) => (
                          <CatalogCard
                            key={model.model_name}
                            model={model}
                            actionLabel="Zainstaluj"
                            pending={pendingActions[`install:${model.provider}:${model.model_name}`]}
                            onAction={() => handleInstall(model)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-4">
                    <h3 className="text-xs uppercase tracking-widest text-slate-400 font-semibold">HuggingFace</h3>
                    {catalogHf.loading ? (
                      <p className="text-xs text-slate-500">{t("models.ui.loading")}</p>
                    ) : (
                      <div className="grid gap-4">
                        {(catalogHf.data ?? []).slice(0, 6).map((model) => (
                          <CatalogCard
                            key={model.model_name}
                            model={model}
                            actionLabel="Zainstaluj"
                            pending={pendingActions[`install:${model.provider}:${model.model_name}`]}
                            onAction={() => handleInstall(model)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <div className="flex flex-col gap-10">
            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
              <SectionHeader
                title={t("models.sections.installed.title")}
                subtitle={t("models.sections.installed.subtitle")}
                badge={
                  installedModels.length ? `${installedModels.length} ` + t("models.runtime.model").toLowerCase() + (installedModels.length > 1 ? "s" : "") : t("models.sections.installed.noModels")
                }
                actionLabel={t("models.ui.refresh")}
                actionDisabled={installed.loading}
                onAction={installed.refresh}
                isCollapsed={installedCollapsed}
                onToggle={() => setInstalledCollapsed((prev) => !prev)}
              />
              {!installedCollapsed ? (
                <div className="mt-5 space-y-6">
                  {installed.loading ? (
                    <p className="text-xs text-slate-500">{t("models.ui.loading")}</p>
                  ) : (
                    <>
                      <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
                        <div className="flex items-center justify-between mb-3">
                          <p className="text-[10px] uppercase tracking-widest text-slate-400 font-semibold">Ollama</p>
                          <Badge tone="neutral" className="text-[9px]">
                            {installedBuckets.ollama.length || 0}
                          </Badge>
                        </div>
                        <div className="grid gap-3">
                          {installedBuckets.ollama.length ? (
                            installedBuckets.ollama.map((model) => (
                              <InstalledCard
                                key={model.name}
                                model={model}
                                pendingActivate={pendingActions[`activate:${model.name}`]}
                                pendingRemove={pendingActions[`remove:${model.name}`]}
                                onActivate={() => handleActivate(model)}
                                onRemove={
                                  allowRemoveProviders.has(model.provider ?? model.source ?? "")
                                    ? () => handleRemove(model)
                                    : undefined
                                }
                              />
                            ))
                          ) : (
                            <p className="text-[11px] text-slate-500">{t("models.sections.installed.noModels")}</p>
                          )}
                        </div>
                      </div>
                      <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
                        <div className="flex items-center justify-between mb-3">
                          <p className="text-[10px] uppercase tracking-widest text-slate-400 font-semibold">vLLM</p>
                          <Badge tone="neutral" className="text-[9px]">
                            {installedBuckets.vllm.length || 0}
                          </Badge>
                        </div>
                        <div className="grid gap-3">
                          {installedBuckets.vllm.length ? (
                            installedBuckets.vllm.map((model) => (
                              <InstalledCard
                                key={model.name}
                                model={model}
                                pendingActivate={pendingActions[`activate:${model.name}`]}
                                pendingRemove={pendingActions[`remove:${model.name}`]}
                                onActivate={() => handleActivate(model)}
                                onRemove={
                                  allowRemoveProviders.has(model.provider ?? model.source ?? "")
                                    ? () => handleRemove(model)
                                    : undefined
                                }
                              />
                            ))
                          ) : (
                            <p className="text-[11px] text-slate-500">{t("models.sections.installed.noModels")}</p>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              ) : null}
            </div>

            <div className="rounded-[24px] border border-white/10 bg-white/5 p-6 shadow-card">
              <SectionHeader
                title={t("models.sections.operations.title")}
                subtitle={t("models.sections.operations.subtitle")}
                actionLabel={t("models.ui.refresh")}
                actionDisabled={operations.loading}
                onAction={operations.refresh}
                isCollapsed={operationsCollapsed}
                onToggle={() => setOperationsCollapsed((prev) => !prev)}
              />
              {!operationsCollapsed ? (
                <div className="mt-5 flex flex-col gap-3">
                  {operations.loading ? (
                    <p className="text-xs text-slate-500">{t("models.ui.loading")}</p>
                  ) : operationsList.length ? (
                    operationsList.map((op) => (
                      <OperationRow key={op.operation_id} op={op} />
                    ))
                  ) : (
                    <p className="text-xs text-slate-500">{t("models.sections.operations.noOperations")}</p>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </section>

      </div>
    </div>
  );
};
