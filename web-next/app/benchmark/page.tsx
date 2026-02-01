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
import { useTranslation } from "@/lib/i18n";

export default function BenchmarkPage() {
  const t = useTranslation();
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
        eyebrow={t("benchmark.page.eyebrow")}
        title={t("benchmark.page.title")}
        description={t("benchmark.page.description")}
        rightSlot={<Gauge className="page-heading-icon" />}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Konfigurator */}
        <Panel
          eyebrow={t("benchmark.steps.config.eyebrow")}
          title={t("benchmark.steps.config.title")}
          description={t("benchmark.steps.config.description")}
        >
          {modelsLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
              <span className="ml-3 text-sm text-zinc-400">
                {t("benchmark.loading")}
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
          eyebrow={t("benchmark.steps.console.eyebrow")}
          title={t("benchmark.steps.console.title")}
          description={t("benchmark.steps.console.description")}
        >
          <BenchmarkConsole logs={logs} isRunning={status === "running"} />
        </Panel>
      </div>

      {/* Wyniki */}
      <Panel
        eyebrow={t("benchmark.steps.results.eyebrow")}
        title={t("benchmark.steps.results.title")}
        description={t("benchmark.steps.results.description")}
      >
        <BenchmarkResults currentResults={results} />
      </Panel>
    </div>
  );
}
