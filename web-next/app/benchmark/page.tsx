"use client";

import { Gauge } from "lucide-react";
import { Panel } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { BenchmarkConfigurator } from "@/components/benchmark/benchmark-configurator";
import { BenchmarkConsole } from "@/components/benchmark/benchmark-console";
import { BenchmarkResults } from "@/components/benchmark/benchmark-results";
import { useModels } from "@/hooks/use-api";
import { useBenchmark } from "@/hooks/use-benchmark";
import type { BenchmarkConfig } from "@/lib/types";

export default function BenchmarkPage() {
  const { data: modelsData, loading: modelsLoading } = useModels(15000);

  // Use the custom hook for real API interaction
  const {
    status,
    logs,
    results,
    startBenchmark,
    // error // Error is handled via logs/status display for now
  } = useBenchmark();

  const handleStart = async (config: BenchmarkConfig) => {
    await startBenchmark(config);
  };

  // Prepare available models list from API data
  const availableModels =
    modelsData?.models.map((model) => ({
      name: model.name || "unknown",
      provider: model.provider || "vllm",
    })) || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <SectionHeading
        as="h1"
        size="lg"
        eyebrow="Benchmark Control"
        title="Panel Benchmarkingu"
        description="Testuj wydajność modeli i porównaj ich parametry (czas odpowiedzi, tokens/sec, użycie VRAM)"
        rightSlot={<Gauge className="page-heading-icon" />}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Konfigurator */}
        <Panel
          eyebrow="Krok 1"
          title="Konfiguracja testu"
          description="Wybierz runtime, modele i liczbę pytań"
        >
          {modelsLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
              <span className="ml-3 text-sm text-zinc-400">
                Ładowanie modeli...
              </span>
            </div>
          ) : (
            <BenchmarkConfigurator
              availableModels={availableModels}
              onStart={handleStart}
              disabled={status === "running" || status === "pending"}
            />
          )}
        </Panel>

        {/* Console / Logi */}
        <Panel
          eyebrow="Krok 2"
          title="Postęp wykonania"
          description="Podgląd na żywo logów z testów"
        >
          <BenchmarkConsole logs={logs} isRunning={status === "running"} />
        </Panel>
      </div>

      {/* Wyniki */}
      <Panel
        eyebrow="Krok 3"
        title="Wyniki porównawcze"
        description="Tabela z metrykami wydajności dla testowanych modeli"
      >
        <BenchmarkResults currentResults={results} />
      </Panel>
    </div>
  );
}
