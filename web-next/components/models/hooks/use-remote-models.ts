import { useState, useEffect, useCallback, useRef } from "react";

export interface RemoteProviderStatus {
  provider: string;
  status: string;
  enabled?: boolean;
  configured?: boolean;
  available?: boolean | null;
  selected?: boolean;
  last_check: string | null;
  error: string | null;
  latency_ms: number | null;
}

export interface RemoteModelInfo {
  id: string;
  name: string;
  provider: string;
  capabilities: string[];
  model_alias: string | null;
}

export interface ServiceModelBinding {
  service_id: string;
  endpoint: string;
  http_method: string;
  provider: string;
  model: string;
  routing_mode: string;
  fallback_order: string[] | null;
  status: string;
}

export interface RemoteProvidersResponse {
  status: string;
  providers: RemoteProviderStatus[];
  count: number;
}

export interface RemoteCatalogResponse {
  status: string;
  provider: string;
  models: RemoteModelInfo[];
  count: number;
  refreshed_at: string;
  source: string;
  error?: string | null;
}

export interface ConnectivityResponse {
  status: string;
  bindings: ServiceModelBinding[];
  count: number;
}

export function useRemoteModels() {
  const [providers, setProviders] = useState<RemoteProviderStatus[]>([]);
  const [providersLoading, setProvidersLoading] = useState(true);
  const [providersError, setProvidersError] = useState<string | null>(null);

  const [providerActions, setProviderActions] = useState<Record<string, boolean>>({});
  const [providerActionError, setProviderActionError] = useState<string | null>(null);
  const activeActions = useRef(new Set<string>());
  const providersRequest = useRef(false);
  const mounted = useRef(true);

  const [catalog, setCatalog] = useState<RemoteModelInfo[]>([]);
  const [catalogProvider, setCatalogProvider] = useState<string | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogRefreshedAt, setCatalogRefreshedAt] = useState<string | null>(null);
  const [catalogSource, setCatalogSource] = useState<string | null>(null);

  const [bindings, setBindings] = useState<ServiceModelBinding[]>([]);
  const [bindingsLoading, setBindingsLoading] = useState(true);
  const [bindingsError, setBindingsError] = useState<string | null>(null);

  // Fetch providers
  const fetchProviders = useCallback(async () => {
    if (providersRequest.current) return;
    providersRequest.current = true;
    try {
      setProvidersError(null);
      const response = await fetch("/api/v1/models/remote/providers");
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: RemoteProvidersResponse = await response.json();
      if (mounted.current) setProviders(data.providers || []);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      if (mounted.current) { setProvidersError(message); setProviders([]); }
    } finally {
      providersRequest.current = false;
      if (mounted.current) setProvidersLoading(false);
    }
  }, []);

  // Fetch catalog for a specific provider
  const fetchCatalog = useCallback(async (provider: string) => {
    try {
      setCatalogLoading(true);
      setCatalogError(null);
      setCatalogProvider(provider);
      const response = await fetch(`/api/v1/models/remote/catalog?provider=${provider}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: RemoteCatalogResponse = await response.json();
      setCatalog(data.models || []);
      setCatalogError(data.error || null);
      setCatalogRefreshedAt(data.refreshed_at || null);
      setCatalogSource(data.source || null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setCatalogError(message);
      setCatalog([]);
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  const providerRequest = useCallback(async (provider: string, path: string, body?: object) => {
    if (activeActions.current.has(provider)) return;
    activeActions.current.add(provider);
    setProviderActions((current) => ({ ...current, [provider]: true }));
    setProviderActionError(null);
    try {
      const response = await fetch(path, {
        method: "POST",
        ...(body === undefined ? {} : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await fetchProviders();
      if (catalogProvider === provider) await fetchCatalog(provider);
    } catch (error) {
      setProviderActionError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      activeActions.current.delete(provider);
      setProviderActions((current) => ({ ...current, [provider]: false }));
    }
  }, [catalogProvider, fetchCatalog, fetchProviders]);

  const manageProvider = useCallback((provider: string, enabled?: boolean) => {
    const action = enabled === undefined ? "check" : "enable";
    return providerRequest(provider, `/api/v1/models/remote/providers/${encodeURIComponent(provider)}/${action}`, enabled === undefined ? undefined : { enabled });
  }, [providerRequest]);

  const connectVast = useCallback((planId: string | null) => {
    if (planId !== null && !/^[a-f0-9]{32}$/.test(planId)) return Promise.resolve();
    return providerRequest("vast_ollama", `/api/v1/system/vast-chat/${planId === null ? "detach" : "attach"}`, planId === null ? undefined : { plan_id: planId });
  }, [providerRequest]);

  // Fetch connectivity bindings
  const fetchBindings = useCallback(async () => {
    try {
      setBindingsLoading(true);
      setBindingsError(null);
      const response = await fetch("/api/v1/models/remote/connectivity");
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: ConnectivityResponse = await response.json();
      setBindings(data.bindings || []);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setBindingsError(message);
      setBindings([]);
    } finally {
      setBindingsLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    mounted.current = true;
    void fetchProviders();
    void fetchBindings();
    const timer = setInterval(() => { void fetchProviders(); }, 10000);
    return () => { mounted.current = false; clearInterval(timer); };
  }, [fetchProviders, fetchBindings]);

  return {
    // Providers
    providers,
    providersLoading,
    providersError,
    fetchProviders,
    providerActions,
    providerActionError,
    manageProvider,
    connectVast,

    // Catalog
    catalog,
    catalogProvider,
    catalogLoading,
    catalogError,
    catalogRefreshedAt,
    catalogSource,
    fetchCatalog,

    // Bindings
    bindings,
    bindingsLoading,
    bindingsError,
    fetchBindings,
  };
}
