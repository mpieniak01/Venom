/**
 * Provider list component - displays all providers with their status and capabilities
 */

import React from "react";
import { ProviderInfo } from "@/lib/types";
import { ProviderStatusIndicator } from "./provider-status-indicator";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface ProviderListProps {
  providers: ProviderInfo[];
  onActivate?: (providerName: string) => void;
  isActivating?: boolean;
}

export function providerTypeToTranslationKey(providerType: string): string {
  const normalized = providerType
    .split("_")
    .map((word, i) =>
      i === 0 ? word : word.charAt(0).toUpperCase() + word.slice(1),
    )
    .join("");
  return `providers.types.${normalized}`;
}

export function canActivateProvider(provider: ProviderInfo, hasActivateHandler: boolean): boolean {
  return (
    provider.capabilities.activate &&
    !provider.is_active &&
    provider.connection_status.status === "connected" &&
    hasActivateHandler
  );
}

export function ProviderList({ providers, onActivate, isActivating }: Readonly<ProviderListProps>) {
  const t = useTranslation();

  if (!providers || providers.length === 0) {
    return (
      <div className="py-8 text-center text-theme-muted">
        {t("providers.labels.noProviders")}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {providers.map((provider) => (
        <div
          key={provider.name}
          className={cn(
            "rounded-lg border p-4",
            provider.is_active
              ? "border-[color:var(--primary)] bg-[color:var(--primary-dim)]"
              : "border-theme bg-theme-overlay",
          )}
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-semibold text-theme-heading">
                  {provider.display_name}
                </h3>
                {provider.is_active && (
                  <span className="rounded border border-theme px-2 py-1 text-xs text-theme-primary bg-theme-overlay">
                    {t("providers.labels.active")}
                  </span>
                )}
              </div>

              <div className="mt-1 text-sm text-theme-muted">
                {t(providerTypeToTranslationKey(provider.provider_type))}
              </div>

              <div className="mt-3">
                <ProviderStatusIndicator
                  status={provider.connection_status.status}
                  message={provider.connection_status.message}
                  latency_ms={provider.connection_status.latency_ms}
                />
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {provider.capabilities.search && (
                  <span className="rounded border border-theme px-2 py-1 text-xs text-theme-secondary bg-theme-overlay">
                    {t("providers.capabilities.search")}
                  </span>
                )}
                {provider.capabilities.install && (
                  <span className="rounded border border-theme px-2 py-1 text-xs text-theme-secondary bg-theme-overlay">
                    {t("providers.capabilities.install")}
                  </span>
                )}
                {provider.capabilities.activate && (
                  <span className="rounded border border-theme px-2 py-1 text-xs text-theme-secondary bg-theme-overlay">
                    {t("providers.capabilities.activate")}
                  </span>
                )}
                {provider.capabilities.inference && (
                  <span className="rounded border border-theme px-2 py-1 text-xs text-theme-secondary bg-theme-overlay">
                    {t("providers.capabilities.inference")}
                  </span>
                )}
                {provider.capabilities.trainable && (
                  <span className="rounded border border-theme px-2 py-1 text-xs text-theme-secondary bg-theme-overlay">
                    {t("providers.capabilities.trainable")}
                  </span>
                )}
              </div>

              {provider.endpoint && (
                <div className="mt-2 text-xs text-theme-muted">
                  {t("providers.labels.endpoint")} {provider.endpoint}
                </div>
              )}
            </div>

            <div>
              {provider.capabilities.activate &&
                canActivateProvider(provider, Boolean(onActivate)) && (
                  <button
                    onClick={() => onActivate?.(provider.name)}
                    disabled={isActivating}
                    className="rounded border border-[color:var(--button-secondary-border)] bg-[color:var(--button-secondary-bg)] px-4 py-2 text-[color:var(--button-secondary-text)] hover:bg-[color:var(--button-secondary-hover)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isActivating ? t("providers.labels.activating") : t("providers.labels.activate")}
                  </button>
                )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
