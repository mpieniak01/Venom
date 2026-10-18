"use client";

import { useCallback, useSyncExternalStore } from "react";
import { useSearchParams } from "next/navigation";

export type ConfigTab = "services" | "parameters" | "integrations" | "topology" | "audit" | "permissions";
export type ConfigNavigation = {
  tab: ConfigTab;
  integration: string | null;
  resource: string | null;
  scope: "all" | "internal" | "external";
  visibility: "environment" | "all";
  query: string;
  parameter: string | null;
  source: string;
  status: string;
  protocol: string;
  invalidTab: boolean;
};
const CHANGE_EVENT = "venom:config-navigation";
const TAB_ALIASES: Record<string, ConfigTab> = {
  topology: "topology", services: "services", parameters: "parameters", integrations: "integrations",
  apiMap: "integrations", "api-map": "integrations", audit: "audit", permissions: "permissions",
};

/** Normalize unsupported filter values to the unfiltered view. */
function allowedFilter(value: string | null, allowed: string[]) {
  return value && allowed.includes(value) ? value : "all";
}

/** Parse legacy and current configuration URLs, validating resource and parameter selectors. */
export function parseConfigNavigation(search: string): ConfigNavigation {
  const params = new URLSearchParams(search);
  const requested = params.get("tab") ?? params.get("section") ?? "services";
  const scope = params.get("scope");
  const parameter = params.get("parameter");
  const resource = params.get("resource");
  return {
    tab: Object.hasOwn(TAB_ALIASES, requested) ? TAB_ALIASES[requested] : "services",
    invalidTab: !Object.hasOwn(TAB_ALIASES, requested),
    integration: params.get("integration")?.slice(0, 200) || null,
    resource: resource && /^[a-zA-Z0-9][a-zA-Z0-9_.:/-]{0,199}$/.test(resource) ? resource : null,
    scope: scope === "internal" || scope === "external" ? scope : "all",
    visibility: params.get("visibility") === "all" ? "all" : "environment",
    source: allowedFilter(params.get("source"), ["local", "cloud", "hybrid"]),
    status: allowedFilter(params.get("status"), ["ok", "down", "degraded", "unknown"]),
    protocol: allowedFilter(params.get("protocol"), ["http", "https", "ws", "sse", "tcp"]),
    query: (params.get("q") ?? "").slice(0, 120),
    parameter: parameter && /^[A-Z][A-Z0-9_]{0,119}$/.test(parameter) ? parameter : null,
  };
}

/** Patch configuration URL state while preserving unrelated query parameters. */
export function configHref(patch: Partial<ConfigNavigation> = {}, search = "") {
  const params = new URLSearchParams(search);
  params.delete("section");
  for (const [key, value] of Object.entries(patch)) {
    const name = key === "query" ? "q" : key;
    if (key === "invalidTab") continue;
    if (value === null || value === "" || (key === "scope" && value === "all") || (key === "visibility" && value === "environment")) params.delete(name);
    else params.set(name, String(value));
  }
  const query = params.toString();
  return query ? "/config?" + query : "/config";
}

/** Subscribe to browser history and local navigation changes with symmetric cleanup. */
function subscribe(listener: () => void) {
  window.addEventListener("popstate", listener);
  window.addEventListener(CHANGE_EVENT, listener);
  return () => {
    window.removeEventListener("popstate", listener);
    window.removeEventListener(CHANGE_EVENT, listener);
  };
}
/** Read the current URL for the client navigation store. */
const browserSearch = () => window.location.search;
/** Provide an empty server snapshot until client URL state is available. */
const serverSearch = () => "";

/** Synchronize configuration selection with Next.js routing and browser history. */
export function useConfigNavigation() {
  const frameworkSearch = useSearchParams();
  const localSearch = useSyncExternalStore(subscribe, browserSearch, serverSearch);
  const search = frameworkSearch?.toString() ?? localSearch;
  const navigate = useCallback((patch: Partial<ConfigNavigation>, replace = false) => {
    const href = configHref(patch, window.location.search);
    if (href === window.location.pathname + window.location.search) return;
    // Next.js copies its own history markers; replaying them bypasses URL updates.
    if (replace) window.history.replaceState(null, "", href);
    else window.history.pushState(null, "", href);
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);
  return { ...parseConfigNavigation(search), search, navigate };
}
