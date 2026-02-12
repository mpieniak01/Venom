"use client";

import { useState, useEffect } from "react";
import { Zap, RefreshCw, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  listAdapters,
  activateAdapter,
  deactivateAdapter,
  type AdapterInfo,
} from "@/lib/academy-api";

export function AdaptersPanel() {
  const [adapters, setAdapters] = useState<AdapterInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [activating, setActivating] = useState<string | null>(null);
  const [deactivating, setDeactivating] = useState(false);

  useEffect(() => {
    loadAdapters();
  }, []);

  async function loadAdapters() {
    try {
      setLoading(true);
      const data = await listAdapters();
      setAdapters(data);
    } catch (err) {
      console.error("Failed to load adapters:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleActivate(adapter: AdapterInfo) {
    try {
      setActivating(adapter.adapter_id);
      await activateAdapter({
        adapter_id: adapter.adapter_id,
        adapter_path: adapter.adapter_path,
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
          Aktywacja...
        </>
      );
    }
    if (isActive) {
      return (
        <>
          <CheckCircle2 className="h-4 w-4" />
          Aktywny
        </>
      );
    }
    return (
      <>
        <Zap className="h-4 w-4" />
        Aktywuj
      </>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Adaptery LoRA</h2>
          <p className="text-sm text-zinc-400">
            Zarządzaj wytrenowanymi adapterami i aktywuj je hot-swap
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
              Rollback
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
            Odśwież
          </Button>
        </div>
      </div>

      {/* Lista adapterów */}
      <div className="space-y-3">
        {adapters.length === 0 ? (
          <div className="rounded-xl border border-white/10 bg-white/5 p-8 text-center">
            <Zap className="mx-auto h-12 w-12 text-zinc-600" />
            <p className="mt-4 text-sm text-zinc-400">Brak dostępnych adapterów</p>
            <p className="mt-1 text-xs text-zinc-500">
              Uruchom trening, aby utworzyć pierwszy adapter
            </p>
          </div>
        ) : (
          adapters.map((adapter) => (
            <div
              key={adapter.adapter_id}
              className={`rounded-xl border p-6 ${
                adapter.is_active
                  ? "border-emerald-500/30 bg-emerald-500/10"
                  : "border-white/10 bg-white/5"
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-semibold text-white">
                      {adapter.adapter_id}
                    </span>
                    {adapter.is_active && (
                      <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-400">
                        <CheckCircle2 className="mr-1 inline h-3 w-3" />
                        Aktywny
                      </span>
                    )}
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
                    <div>
                      <span className="text-zinc-400">Model bazowy:</span>
                      <p className="mt-0.5 font-mono text-zinc-200">{adapter.base_model}</p>
                    </div>
                    <div>
                      <span className="text-zinc-400">Utworzono:</span>
                      <p className="mt-0.5 text-zinc-200">
                        {adapter.created_at === "unknown"
                          ? "Nieznana data"
                          : new Date(adapter.created_at).toLocaleString("pl-PL")}
                      </p>
                    </div>
                  </div>

                  {Object.keys(adapter.training_params).length > 0 && (
                    <div className="mt-2">
                      <span className="text-xs text-zinc-400">Parametry:</span>
                      <div className="mt-1 flex flex-wrap gap-2">
                        {Object.entries(adapter.training_params).map(([key, value]) => (
                          <span
                            key={key}
                            className="rounded bg-white/10 px-2 py-0.5 text-xs text-zinc-300"
                          >
                            {key}: {String(value)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <p className="mt-2 text-xs font-mono text-zinc-500">{adapter.adapter_path}</p>
                </div>

                <Button
                  onClick={() => handleActivate(adapter)}
                  disabled={adapter.is_active || activating === adapter.adapter_id}
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
          ℹ Aktywacja adaptera to hot-swap - model zostanie zamieniony bez restartu backendu
        </p>
        <p className="mt-2 text-xs text-zinc-400">
          Adapter LoRA modyfikuje tylko niewielką część parametrów bazowego modelu,
          co pozwala na szybkie uczenie i niskie zużycie pamięci.
        </p>
      </div>
    </div>
  );
}
