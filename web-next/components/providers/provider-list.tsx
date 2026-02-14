/**
 * Provider list component - displays all providers with their status and capabilities
 */

import React from "react";
import { ProviderInfo } from "@/lib/types";
import { ProviderStatusIndicator } from "./provider-status-indicator";

interface ProviderListProps {
  providers: ProviderInfo[];
  onActivate?: (providerName: string) => void;
  isActivating?: boolean;
}

const providerTypeLabels: Record<string, string> = {
  cloud_provider: "Cloud Provider",
  catalog_integrator: "Catalog Integrator",
  local_runtime: "Local Runtime",
};

export function ProviderList({ providers, onActivate, isActivating }: ProviderListProps) {
  if (!providers || providers.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 dark:text-gray-400">
        No providers available
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {providers.map((provider) => (
        <div
          key={provider.name}
          className={`border rounded-lg p-4 ${
            provider.is_active
              ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
              : "border-gray-200 dark:border-gray-700"
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {provider.display_name}
                </h3>
                {provider.is_active && (
                  <span className="px-2 py-1 text-xs bg-blue-500 text-white rounded">
                    Active
                  </span>
                )}
              </div>
              
              <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                {providerTypeLabels[provider.provider_type] || provider.provider_type}
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
                  <span className="px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 rounded">
                    Search
                  </span>
                )}
                {provider.capabilities.install && (
                  <span className="px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 rounded">
                    Install
                  </span>
                )}
                {provider.capabilities.activate && (
                  <span className="px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 rounded">
                    Activate
                  </span>
                )}
                {provider.capabilities.inference && (
                  <span className="px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 rounded">
                    Inference
                  </span>
                )}
                {provider.capabilities.trainable && (
                  <span className="px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 rounded">
                    Trainable
                  </span>
                )}
              </div>

              {provider.endpoint && (
                <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  Endpoint: {provider.endpoint}
                </div>
              )}
            </div>

            <div>
              {provider.capabilities.activate &&
                !provider.is_active &&
                provider.connection_status.status === "connected" &&
                onActivate && (
                  <button
                    onClick={() => onActivate(provider.name)}
                    disabled={isActivating}
                    className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
                  >
                    {isActivating ? "Activating..." : "Activate"}
                  </button>
                )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
