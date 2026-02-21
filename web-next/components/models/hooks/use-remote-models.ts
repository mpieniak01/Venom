import { useState, useEffect, useCallback } from "react";

export interface RemoteProviderStatus {
  provider: string;
  status: string;
  last_check: string;
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
    try {
      setProvidersLoading(true);
      setProvidersError(null);
      const response = await fetch("/api/v1/models/remote/providers");
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: RemoteProvidersResponse = await response.json();
      setProviders(data.providers || []);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setProvidersError(message);
      setProviders([]);
    } finally {
      setProvidersLoading(false);
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
    fetchProviders();
    fetchBindings();
  }, [fetchProviders, fetchBindings]);

  return {
    // Providers
    providers,
    providersLoading,
    providersError,
    fetchProviders,

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
