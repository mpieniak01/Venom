"use client";

import { useState, useEffect, useCallback } from "react";
import { Zap, RefreshCw, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";
import {
  listAdapters,
  activateAdapter,
  deactivateAdapter,
  getUnifiedModelCatalog,
  type AdapterInfo,
} from "@/lib/academy-api";
import { useLanguage, useTranslation } from "@/lib/i18n";

export function AdaptersPanel() {
  const t = useTranslation();
  const { language } = useLanguage();
  const [adapters, setAdapters] = useState<AdapterInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [activating, setActivating] = useState<string | null>(null);
  const [deactivating, setDeactivating] = useState(false);
  const [runtimeOptions, setRuntimeOptions] = useState<SelectMenuOption[]>([]);
  const [modelOptions, setModelOptions] = useState<SelectMenuOption[]>([]);
  const [selectedRuntime, setSelectedRuntime] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [adapterDeploySupported, setAdapterDeploySupported] = useState(false);

  const loadRuntimeModels = useCallback(async (runtimeOverride?: string) => {
    const catalog = await getUnifiedModelCatalog();
    const runtimes = (catalog.runtimes ?? []).filter(
      (runtime) =>
        runtime.source_type === "local-runtime" &&
        runtime.configured &&
        runtime.available,
    );
    const runtimeSelectOptions = runtimes.map((runtime) => ({
      value: runtime.runtime_id,
      label: runtime.runtime_id.toUpperCase(),
    }));
    setRuntimeOptions(runtimeSelectOptions);
    const activeRuntimeId = String(
      catalog.active?.runtime_id || catalog.active?.active_server || "",
    ).trim();
    const resolvedRuntime =
      runtimeOverride ||
      selectedRuntime ||
      activeRuntimeId ||
      runtimeSelectOptions[0]?.value ||
      "";
    if (resolvedRuntime !== selectedRuntime) {
      setSelectedRuntime(resolvedRuntime);
    }
    const selectedRuntimeMeta = runtimes.find(
      (runtime) => runtime.runtime_id === resolvedRuntime,
    );
    setAdapterDeploySupported(
      Boolean(
        selectedRuntimeMeta?.supports_adapter_runtime_apply ??
          selectedRuntimeMeta?.adapter_deploy_supported,
      ),
    );
    const models = (catalog.chat_models ?? []).filter(
      (model) => model.runtime_id === resolvedRuntime,
    );
    const modelSelectOptions = models.map((model) => ({
      value: model.name,
      label: model.name,
    }));
    setModelOptions(modelSelectOptions);
    const activeModelId = String(catalog.active?.active_model || "").trim();
    setSelectedModel((current) => {
      if (current && modelSelectOptions.some((option) => option.value === current)) {
        return current;
      }
      if (
        activeModelId &&
        modelSelectOptions.some((option) => option.value === activeModelId)
      ) {
        return activeModelId;
      }
      return modelSelectOptions[0]?.value || "";
    });
  }, [selectedRuntime]);

  const loadAdapters = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listAdapters();
      setAdapters(data);
      await loadRuntimeModels();
    } catch (err) {
      console.error("Failed to load adapters:", err);
    } finally {
      setLoading(false);
    }
  }, [loadRuntimeModels]);

  useEffect(() => {
    loadAdapters();
  }, [loadAdapters]);

  useEffect(() => {
    if (!selectedRuntime) {
      setModelOptions([]);
      setSelectedModel("");
      return;
    }
    loadRuntimeModels(selectedRuntime).catch((error) => {
      console.error("Failed to load runtime models for adapter selector:", error);
      setModelOptions([]);
      setSelectedModel("");
    });
  }, [selectedRuntime, loadRuntimeModels]);

  async function handleActivate(adapter: AdapterInfo) {
    try {
      setActivating(adapter.adapter_id);
      await activateAdapter({
        adapter_id: adapter.adapter_id,
        adapter_path: adapter.adapter_path,
        runtime_id: selectedRuntime || undefined,
        model_id: selectedModel || undefined,
        deploy_to_chat_runtime: true,
      });
      await loadAdapters();
    } catch (err) {
      console.error("Failed to activate adapter:", err);
    } finally {
      setActivating(null);
    }
  }

  async function handleDeactivate() {
    try {
      setDeactivating(true);
      await deactivateAdapter();
      await loadAdapters();
    } catch (err) {
      console.error("Failed to deactivate adapter:", err);
    } finally {
      setDeactivating(false);
    }
  }

  const hasActiveAdapter = adapters.some(a => a.is_active);

  const getButtonContent = (adapterId: string, isActive: boolean) => {
    if (activating === adapterId) {
      return (
        <>
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("academy.adapters.activating")}
        </>
      );
    }
    if (isActive) {
      return (
        <>
          <CheckCircle2 className="h-4 w-4" />
          {t("academy.adapters.active")}
        </>
      );
    }
    return (
      <>
        <Zap className="h-4 w-4" />
        {t("academy.adapters.activate")}
      </>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-theme-primary">{t("academy.adapters.title")}</h2>
          <p className="text-sm text-theme-muted">
            {t("academy.adapters.subtitle")}
          </p>
        </div>
        <div className="flex gap-2">
          {hasActiveAdapter && (
            <Button
              onClick={handleDeactivate}
              disabled={deactivating}
              variant="outline"
              size="sm"
              className="gap-2"
            >
              {deactivating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              {t("academy.adapters.rollback")}
            </Button>
          )}
          <Button
            onClick={loadAdapters}
            disabled={loading}
            variant="outline"
            size="sm"
            className="gap-2"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            {t("academy.common.refresh")}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[color:var(--text-secondary)]">
            {t("cockpit.models.server")}
          </p>
          <SelectMenu
            value={selectedRuntime}
            options={runtimeOptions}
            onChange={(value) => {
              setSelectedRuntime(value);
            }}
            placeholder={t("cockpit.models.chooseServer")}
            ariaLabel={t("cockpit.actions.selectServer")}
          />
        </div>
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[color:var(--text-secondary)]">
            {t("cockpit.models.model")}
          </p>
          <SelectMenu
            value={selectedModel}
            options={modelOptions}
            onChange={setSelectedModel}
            placeholder={t("cockpit.models.chooseModel")}
            ariaLabel={t("cockpit.actions.selectModel")}
            disabled={!selectedRuntime || modelOptions.length === 0}
          />
        </div>
      </div>
      {!adapterDeploySupported && selectedRuntime ? (
        <p className="text-xs text-amber-300">
          {t("cockpit.models.adapterRuntimeNotSupported", {
            runtime: selectedRuntime,
          })}
        </p>
      ) : null}

      {/* Lista adapterów */}
      <div className="space-y-3">
        {adapters.length === 0 ? (
          <div className="rounded-xl border border-theme bg-theme-overlay p-8 text-center">
            <Zap className="mx-auto h-12 w-12 text-theme-muted" />
            <p className="mt-4 text-sm text-theme-muted">{t("academy.adapters.emptyTitle")}</p>
            <p className="mt-1 text-xs text-theme-muted">
              {t("academy.adapters.emptyDescription")}
            </p>
          </div>
        ) : (
          adapters.map((adapter) => (
            <div
              key={adapter.adapter_id}
              className={`rounded-xl border p-6 ${
                adapter.is_active
                  ? "border-emerald-500/30 bg-emerald-500/10"
                  : "border-theme bg-theme-overlay"
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-semibold text-theme-primary">
                      {adapter.adapter_id}
                    </span>
                    {adapter.is_active && (
                      <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-400">
                        <CheckCircle2 className="mr-1 inline h-3 w-3" />
                        {t("academy.adapters.active")}
                      </span>
                    )}
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
                    <div>
                      <span className="text-theme-muted">{t("academy.adapters.baseModel")}:</span>
                      <p className="mt-0.5 font-mono text-theme-secondary">{adapter.base_model}</p>
                    </div>
                    <div>
                      <span className="text-theme-muted">{t("academy.adapters.createdAt")}:</span>
                      <p className="mt-0.5 text-theme-secondary">
                        {adapter.created_at === "unknown"
                          ? t("academy.adapters.unknownDate")
                          : new Date(adapter.created_at).toLocaleString(language)}
                      </p>
                    </div>
                  </div>

                  {Object.keys(adapter.training_params).length > 0 && (
                    <div className="mt-2">
                      <span className="text-xs text-theme-muted">{t("academy.adapters.parameters")}:</span>
                      <div className="mt-1 flex flex-wrap gap-2">
                        {Object.entries(adapter.training_params).map(([key, value]) => (
                          <span
                            key={key}
                            className="rounded bg-white/10 px-2 py-0.5 text-xs text-theme-secondary"
                          >
                            {key}: {String(value)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <p className="mt-2 text-xs font-mono text-theme-muted">{adapter.adapter_path}</p>
                </div>

                <Button
                  onClick={() => handleActivate(adapter)}
                  disabled={
                    adapter.is_active ||
                    activating === adapter.adapter_id ||
                    !selectedRuntime ||
                    !selectedModel ||
                    !adapterDeploySupported
                  }
                  variant={adapter.is_active ? "outline" : "primary"}
                  size="sm"
                  className="ml-4 gap-2"
                >
                  {getButtonContent(adapter.adapter_id, adapter.is_active)}
                </Button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Informacje */}
      <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4">
        <p className="text-sm text-blue-300">
          ℹ {t("academy.adapters.infoTitle")}
        </p>
        <p className="mt-2 text-xs text-theme-muted">
          {t("academy.adapters.infoDescription")}
        </p>
      </div>
    </div>
  );
}
