"use client";

import { useCallback, useSyncExternalStore } from "react";
import { useSearchParams } from "next/navigation";

export type ConfigTab = "services" | "parameters" | "integrations" | "audit" | "permissions";
export type ConfigNavigation = {
  tab: ConfigTab;
  integration: string | null;
  scope: "all" | "internal" | "external";
  visibility: "environment" | "all";
  query: string;
  parameter: string | null;
  invalidTab: boolean;
};
const CHANGE_EVENT = "venom:config-navigation";
const TAB_ALIASES: Record<string, ConfigTab> = {
  services: "services", parameters: "parameters", integrations: "integrations",
  apiMap: "integrations", "api-map": "integrations", audit: "audit", permissions: "permissions",
};

export function parseConfigNavigation(search: string): ConfigNavigation {
  const params = new URLSearchParams(search);
  const requested = params.get("tab") ?? params.get("section") ?? "services";
  const scope = params.get("scope");
  const parameter = params.get("parameter");
  return {
    tab: Object.hasOwn(TAB_ALIASES, requested) ? TAB_ALIASES[requested] : "services",
    invalidTab: !Object.hasOwn(TAB_ALIASES, requested),
    integration: params.get("integration")?.slice(0, 200) || null,
    scope: scope === "internal" || scope === "external" ? scope : "all",
    visibility: params.get("visibility") === "all" ? "all" : "environment",
    query: (params.get("q") ?? "").slice(0, 120),
    parameter: parameter && /^[A-Z][A-Z0-9_]{0,119}$/.test(parameter) ? parameter : null,
  };
}

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
  return `/config${query ? `?${query}` : ""}`;
}

function subscribe(listener: () => void) {
  window.addEventListener("popstate", listener);
  window.addEventListener(CHANGE_EVENT, listener);
  return () => {
    window.removeEventListener("popstate", listener);
    window.removeEventListener(CHANGE_EVENT, listener);
  };
}
const browserSearch = () => window.location.search;
const serverSearch = () => "";

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
